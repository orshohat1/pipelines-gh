"""Planner agent — designs a migration plan from source pipeline to GitHub Actions.

Uses platform-specific system prompts so each planner only carries knowledge
relevant to the detected source CI/CD system, reducing prompt size and latency.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Coroutine

from copilot import CopilotClient, PermissionHandler

from backend.config import BYOKProviderConfig
from backend.models import MigrationPlan, PipelineType

logger = logging.getLogger(__name__)

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])

# ── Shared preamble & JSON schema ────────────────────────────────────────────

_SECURITY_RULES = """\
Security rules (apply to every workflow):
- Default `permissions: contents: read` at workflow level
- Pin actions to major version tags (e.g. `@v4`), never `@main`/`@latest`
- Secrets via `${{ secrets.NAME }}` only; prefer OIDC over long-lived creds
- Include `concurrency` groups for deployment workflows
- Use built-in caching and set `retention-days` on artifacts"""

_JSON_SCHEMA = """\
Return ONLY a valid JSON object (no markdown, no fences, no extra text).

{
  "workflow_name": "string",
  "workflow_type": "standalone|reusable|composite",
  "description": "2-3 sentences in plain English explaining what this workflow does, what it builds, and where it deploys. Written for a human reviewer, not a machine.",
  "triggers": ["push", ...],
  "jobs": [{
    "name": "job-id", "display_name": "Human Name", "runs_on": "ubuntu-latest",
    "needs": [], "steps": [{"name":"...","uses":"...","run":"..."}],
    "environment": null, "permissions": {}
  }],
  "prerequisites": [
    {"what": "thing to create", "why": "reason it's needed", "how": "CLI command or portal step"}
  ],
  "enhancements": [
    {"title": "short title", "description": "what this adds and why it matters"}
  ],
  "warnings": [{"severity":"warning|critical","message":"..."}]
}

IMPORTANT:
- "prerequisites" lists things the user MUST create before the workflow can run (OIDC credentials, secrets, environments, etc.)
- "enhancements" proposes best-practice upgrades beyond a 1:1 migration: splitting into multiple jobs, adding security scanning (CodeQL, dependency-review), artifact signing, environment protection rules, matrix builds, or anything that would make this a world-class GitHub Actions workflow. Be ambitious — propose 2-5 improvements.
- When migrating variable groups, prefer GitHub ENVIRONMENT variables/secrets over repository-level variables for any value that is environment-specific (app names, resource groups, connection strings, etc.). Repository variables should only be used for values shared across ALL environments."""

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
- Variable groups → GitHub environment secrets/variables (prefer environment-scoped vars over repository-level vars for environment-specific values like app names, resource groups, etc.)
- Template refs → reusable workflows or composite actions
- `dependsOn:` → `needs:`
- Environments + approvals → environments + protection rules

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


async def plan_migration(
    client: CopilotClient,
    filename: str,
    content: str,
    pipeline_type: PipelineType,
    byok: BYOKProviderConfig | None = None,
    on_user_question: Callable[..., Coroutine] | None = None,
    revision_feedback: str | None = None,
    previous_plan: dict | None = None,
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
    """
    model = byok.model_name if byok else "gpt-4o-mini"
    system_prompt = _PROMPTS.get(pipeline_type, GENERIC_PROMPT)
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": system_prompt},
        "on_permission_request": PermissionHandler.approve_all,
        "config_dir": PROJECT_ROOT,
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
        if revision_feedback and previous_plan:
            prompt = (
                f"Revise this migration plan based on user feedback. "
                f"Return ONLY the updated JSON matching the schema in your instructions.\n\n"
                f"User feedback: {revision_feedback}\n\n"
                f"Previous plan:\n{json.dumps(previous_plan, indent=2)}\n\n"
                f"Original pipeline:\n{content}"
            )
        else:
            prompt = (
                f"Migrate this {pipeline_type.value} pipeline to GitHub Actions. "
                f"Return ONLY valid JSON matching the schema in your instructions.\n\n"
                f"Filename: {filename}\n\n{content}"
            )
        response = await session.send_and_wait({"prompt": prompt}, timeout=180)
        raw = response.data.content if response else ""

        # Parse JSON
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Planner returned non-JSON, using raw text as plan.")
            return MigrationPlan(raw_plan=raw)

        return MigrationPlan(
            workflow_name=data.get("workflow_name", ""),
            workflow_type=data.get("workflow_type", "standalone"),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            jobs=data.get("jobs", []),
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
