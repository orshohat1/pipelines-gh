"""Planner agent — designs a migration plan from source pipeline to GitHub Actions.

Uses platform-specific system prompts so each planner only carries knowledge
relevant to the detected source CI/CD system, reducing prompt size and latency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from typing import Any, Callable, Coroutine

from copilot import CopilotClient, PermissionHandler

from backend.config import BYOKProviderConfig
from backend.models import MigrationPlan, PipelineType

logger = logging.getLogger(__name__)

# ── Docs context (set by orchestrator at runtime) ────────────────────────────

_docs_context: str = ""


def set_docs_context(ctx: str) -> None:
    """Set the GitHub Actions best-practices reference for the planner."""
    global _docs_context
    _docs_context = ctx


# ── Shared preamble & JSON schema ────────────────────────────────────────────

_SECURITY_RULES = """\
Security rules (apply to every workflow):
- Default `permissions: contents: read` at workflow level
- Pin actions to major version tags (e.g. `@v4`), never `@main`/`@latest`
- Sensitive credentials via `${{ secrets.NAME }}`; non-sensitive config (app names, resource groups, regions, URLs) via `${{ vars.NAME }}`
- Prefer OIDC over long-lived creds
- Include `concurrency` groups for deployment workflows
- Use built-in caching and set `retention-days` on artifacts

Job separation rules:
- NEVER combine build and deploy in the same job. Build and deploy are separate concerns with separate failure modes.
- Each logical stage (build, test, deploy, promote, tag) should be its own job connected via `needs:`.
- If the source pipeline has build+deploy in one job, SPLIT them — this is a migration improvement, not a 1:1 copy.
- Template references (Azure DevOps `template:`, Jenkins shared libs, GitLab `include:`) MUST each become a separate reusable workflow file."""

_JSON_SCHEMA = """\
Always respond in English.
Return ONLY a valid JSON object (no markdown, no fences, no extra text).
Do NOT use escaped quotes (\\" ) as string delimiters — use plain double quotes (").

{
  "workflow_name": "string",
  "workflow_type": "standalone|reusable|composite",
  "description": "2-3 sentence plain-English summary for a human reviewer.",
  "triggers": ["push", ...],
  "jobs": [{
    "name": "job-id", "display_name": "Human Name", "runs_on": "ubuntu-latest",
    "needs": [], "steps": [{"name":"...","uses":"...","run":"..."}],
    "environment": null, "permissions": {}
  }],
  "output_files": [{"filename": "deploy.yml", "file_type": "workflow|reusable|composite", "description": "...", "job_names": ["job-id-1"]}],
  "prerequisites": [{"what": "...", "why": "...", "how": "CLI command or portal step"}],
  "enhancements": [{"title": "short title", "description": "what + why"}],
  "warnings": [{"severity":"warning|critical","message":"..."}]
}

Rules:
- "output_files": one entry per workflow file. Templates/includes → separate reusable workflow each. Main calls them via `uses: ./.github/workflows/filename.yml`.
- "enhancements": propose 2-5 best-practice upgrades (job splitting, CodeQL, dependency-review, environment protection, matrix, artifact signing).
- Use `secrets.*` ONLY for credentials; use `vars.*` for app names, regions, resource groups. Prefer environment-level over repo-level for env-specific values."""

# ── Platform-specific planner prompts ────────────────────────────────────────

AZURE_DEVOPS_PROMPT = f"""\
You are an Azure DevOps → GitHub Actions migration specialist.

Key mappings:
- `trigger:` / `pr:` → `on: push:` / `on: pull_request:`
- `trigger: none` → `on: workflow_dispatch`
- `pool: vmImage` → `runs-on:`
- `task: UseDotNet@2` → `actions/setup-dotnet@v4`
- `task: NodeTool@0` → `actions/setup-node@v4`
- `task: Docker@2` → `docker/build-push-action@v6`
- `$(Build.SourceBranch)` → `${{{{ github.ref }}}}`
- `$(System.AccessToken)` → `${{{{ secrets.GITHUB_TOKEN }}}}`
- Service connections → OIDC via `azure/login@v2`
- Variable groups → GitHub environment secrets/variables:
  * Sensitive values (client IDs, secrets, passwords, tokens, connection strings) → `${{ secrets.NAME }}`
  * Non-sensitive config (app names, resource groups, regions, slot names, URLs) → `${{ vars.NAME }}`
  * Prefer environment-scoped over repository-level for environment-specific values
- Template refs → reusable workflows (EVERY template file becomes a reusable workflow, including deployment templates)
- `dependsOn:` → `needs:`
- Environments + approvals → environments + protection rules
- Multi-step jobs (build+deploy in one job) → split into separate jobs (build job + deploy job)

{_SECURITY_RULES}

{_JSON_SCHEMA}"""

JENKINS_PROMPT = f"""\
You are a Jenkins → GitHub Actions migration specialist.

Key mappings:
- `pipeline {{ agent any }}` → `runs-on: ubuntu-latest`
- `agent {{ docker {{ image '...' }} }}` → `container: image: '...'`
- `stage('Name') {{ steps {{ ... }} }}` → named job with steps
- `sh '...'` → `run:` step
- `when {{ branch 'main' }}` → `if: github.ref == 'refs/heads/main'`
- `credentials('...')` / `withCredentials` → `${{{{ secrets.* }}}}`
- `post {{ always {{ ... }} }}` → `if: always()` step
- `post {{ failure {{ ... }} }}` → `if: failure()` step
- `parallel {{ ... }}` → multiple jobs without `needs:`
- Shared libraries → reusable workflows / composite actions
- `archiveArtifacts` → `actions/upload-artifact@v4`
- `input {{ message '...' }}` → environment with required reviewers
- Jenkinsfile parameters → `workflow_dispatch` inputs

{_SECURITY_RULES}

{_JSON_SCHEMA}"""

GITLAB_CI_PROMPT = f"""\
You are a GitLab CI → GitHub Actions migration specialist.

Key mappings:
- `stages:` → job ordering via `needs:`
- `image:` → `container:` or `runs-on:` with setup action
- `script:` → `run:` steps
- `before_script:` / `after_script:` → additional run steps
- `variables:` → `env:` at workflow/job level
- `$CI_COMMIT_REF_NAME` → `${{{{ github.ref_name }}}}`
- `$CI_COMMIT_SHA` → `${{{{ github.sha }}}}`
- `$CI_JOB_TOKEN` → `${{{{ secrets.GITHUB_TOKEN }}}}`
- `only:` / `except:` / `rules:` → `on:` triggers + `if:` conditions
- `artifacts:` → `actions/upload-artifact@v4`
- `cache:` → `actions/cache@v4`
- `services:` → `services:` in job config
- `include:` → reusable workflows
- `extends:` → YAML anchors or composite actions
- `allow_failure: true` → `continue-on-error: true`

{_SECURITY_RULES}

{_JSON_SCHEMA}"""

GENERIC_PROMPT = f"""\
You are a CI/CD migration architect. Convert the given pipeline to GitHub Actions.

{_SECURITY_RULES}

{_JSON_SCHEMA}"""

_PROMPTS: dict[PipelineType, str] = {
    PipelineType.AZURE_DEVOPS: AZURE_DEVOPS_PROMPT,
    PipelineType.JENKINS: JENKINS_PROMPT,
    PipelineType.GITLAB_CI: GITLAB_CI_PROMPT,
    PipelineType.UNKNOWN: GENERIC_PROMPT,
}


# ── Streaming helper ────────────────────────────────────────────────────────


async def _send_with_streaming(
    session: Any,
    options: dict,
    timeout: float = 300,
) -> Any:
    """Send a message using streaming events instead of send_and_wait.

    Uses session.send() + on() to receive assistant.message_delta events.
    The session stays alive as long as tokens are flowing — no idle-timeout
    risk.  Falls back to send_and_wait if event subscription fails.
    """
    done: asyncio.Event = asyncio.Event()
    collected_content: list[str] = []
    final_event: list[Any] = []  # mutable container for the last event

    def handler(event: Any) -> None:
        etype = event.type.value if hasattr(event.type, "value") else str(event.type)

        if etype == "assistant.message_delta":
            delta = getattr(event.data, "content", "")
            if delta:
                collected_content.append(delta)

        elif etype == "assistant.message":
            # Full final message — prefer this over deltas if present
            content = getattr(event.data, "content", "")
            if content:
                collected_content.clear()
                collected_content.append(content)
            final_event.append(event)

        elif etype in ("session.idle", "assistant.turn_end"):
            done.set()

        elif etype == "session.error":
            msg = getattr(event.data, "message", str(event.data))
            logger.error("Planner session error: %s", msg)
            done.set()

    unsubscribe = session.on(handler)
    try:
        await session.send(options)
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Planner streaming timed out after %ds", timeout)
        raise
    finally:
        unsubscribe()

    # Return a result object compatible with send_and_wait's return value
    if final_event:
        return final_event[0]

    # Build a synthetic event from collected deltas
    class _SyntheticData:
        content = "".join(collected_content)

    class _SyntheticEvent:
        data = _SyntheticData()

    return _SyntheticEvent()


async def plan_migration(
    client: CopilotClient,
    filename: str,
    content: str,
    pipeline_type: PipelineType,
    byok: BYOKProviderConfig | None = None,
    on_user_question: Callable[..., Coroutine] | None = None,
    revision_feedback: str | None = None,
    previous_plan: dict | None = None,
    template_contents: list[dict[str, str]] | None = None,
    use_advanced_model: bool = False,
) -> MigrationPlan:
    """Generate a migration plan from a source pipeline to GitHub Actions.

    Args:
        client: Shared CopilotClient instance.
        filename: Original filename.
        content: Original pipeline file content.
        pipeline_type: Detected pipeline type from validator.
        byok: Optional BYOK provider config.
        on_user_question: Async callback for human-in-the-loop questions.
        revision_feedback: User feedback for revising a previous plan.
        previous_plan: The previous plan JSON to revise.
        template_contents: Template file contents referenced by the pipeline.
        use_advanced_model: Use claude-sonnet-4.6 for complex pipelines.
    """
    if byok:
        model = byok.model_name
    elif use_advanced_model:
        model = "claude-sonnet-4.6"
    else:
        model = "openai/gpt-5.4-mini"
    system_prompt = _PROMPTS.get(pipeline_type, GENERIC_PROMPT)
    if _docs_context:
        system_prompt = f"{system_prompt}\n\n{_docs_context}"
    logger.info("Planner system prompt: %d chars (model=%s)", len(system_prompt), model)
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": system_prompt},
        "on_permission_request": PermissionHandler.approve_all,
    }
    provider = byok.to_sdk_provider() if byok else None
    if provider:
        session_opts["provider"] = provider

    # Wire up human-in-the-loop if callback provided
    if on_user_question:

        async def handle_user_input(request: Any, invocation: Any) -> dict:
            question = request.get("question", "") if isinstance(request, dict) else getattr(request, "question", "")
            choices = request.get("choices") if isinstance(request, dict) else getattr(request, "choices", None)
            answer = await on_user_question(question, choices)
            return {"answer": answer, "wasFreeform": True}

        session_opts["on_user_input_request"] = handle_user_input

    session = await client.create_session(session_opts)
    try:
        # Build template context if template files were provided
        template_context = ""
        if template_contents:
            parts = [
                f"### Template: {tc['path']}\n```\n{tc['content']}\n```"
                for tc in template_contents
            ]
            template_context = (
                "\n\n## Referenced Template Files\n"
                "The user provided these template files referenced by the main pipeline. "
                "Create a comprehensive plan that maps each template to a reusable GitHub Actions workflow.\n\n"
                + "\n\n".join(parts)
            )

        if revision_feedback and previous_plan:
            prompt = (
                f"Revise this migration plan based on user feedback. "
                f"Return ONLY the updated JSON matching the schema in your instructions.\n\n"
                f"User feedback: {revision_feedback}\n\n"
                f"Previous plan:\n{json.dumps(previous_plan, indent=2)}\n\n"
                f"Original pipeline:\n{content}"
                f"{template_context}"
            )
        else:
            prompt = (
                f"Migrate this {pipeline_type.value} pipeline to GitHub Actions. "
                f"Return ONLY valid JSON matching the schema in your instructions.\n\n"
                f"Filename: {filename}\n\n{content}"
                f"{template_context}"
            )
        response = await _send_with_streaming(session, {"prompt": prompt}, timeout=300)
        raw = response.data.content if response else ""

        # Extract JSON from response — handle markdown fences and surrounding text
        text = raw.strip()

        # Strip markdown fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        else:
            # No fences — try to find the outermost JSON object
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                text = text[brace_start : brace_end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # LLMs sometimes use \" as string delimiters instead of " — repair and retry
            repaired = text.replace('\\"', '"')
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                logger.warning("Planner returned non-JSON: %s", raw[:300])
                return MigrationPlan(raw_plan=raw)

        return MigrationPlan(
            workflow_name=data.get("workflow_name", ""),
            workflow_type=data.get("workflow_type", "standalone"),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            jobs=data.get("jobs", []),
            output_files=[
                {"filename": f.get("filename", ""), "file_type": f.get("file_type", "workflow"),
                 "description": f.get("description", ""), "job_names": f.get("job_names", [])}
                for f in data.get("output_files", [])
            ],
            prerequisites=[
                {"what": p.get("what", ""), "why": p.get("why", ""), "how": p.get("how", "")}
                for p in data.get("prerequisites", [])
            ],
            enhancements=[
                {"title": e.get("title", ""), "description": e.get("description", "")}
                for e in data.get("enhancements", [])
            ],
            warnings=[
                {"severity": w.get("severity", "warning"), "message": w.get("message", "")}
                for w in data.get("warnings", [])
            ],
            raw_plan=raw,
        )
    finally:
        sid = session.session_id
        await session.disconnect()
        try:
            await client.delete_session(sid)
        except Exception:
            pass
