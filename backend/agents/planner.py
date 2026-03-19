"""Planner agent — designs a migration plan from source pipeline to GitHub Actions."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

from copilot import CopilotClient, PermissionHandler

from backend.config import BYOKProviderConfig
from backend.models import MigrationPlan, PipelineType

logger = logging.getLogger(__name__)

SYSTEM_MESSAGE = """You are a senior CI/CD migration architect specializing in converting
pipelines from Azure DevOps, Jenkins, and GitLab CI to GitHub Actions.

You are also a GitHub Actions security expert. Every workflow you plan MUST follow these
principles:
- Default permissions: `contents: read` at workflow level
- Pin actions to specific major version tags (e.g. `@v4`), never `@main` or `@latest`
- Secrets accessed only via `${{ secrets.NAME }}` environment variables
- Prefer OIDC (id-token: write) over long-lived credentials for cloud access
- Implement concurrency control with `concurrency` groups
- Use built-in caching (setup-node, setup-python) and `actions/cache`
- Set appropriate artifact retention
- Include dependency review, CodeQL, and container scanning where appropriate

## Your task

Given a source pipeline file and its detected type, create a detailed migration plan.
The plan must include:

1. **Workflow structure**: standalone workflow, reusable workflow, or composite action
2. **Triggers**: map source triggers to GitHub Actions on: events
3. **Jobs and steps**: map each stage/job/step from the source to GitHub Actions equivalents
4. **Secrets and variables**: identify ALL secrets, tokens, service connections, and variables
   that need to be configured in GitHub. Flag each one clearly.
5. **Actions to use**: recommend specific GitHub Actions marketplace actions with version pins
6. **Warnings**: note any constructs that cannot be directly migrated or need manual attention
7. **Environment setup**: runners, services, containers needed

## Platform-specific mapping knowledge

### Azure DevOps → GitHub Actions
- `trigger:` → `on: push:`
- `pr:` → `on: pull_request:`
- `pool: vmImage: 'ubuntu-latest'` → `runs-on: ubuntu-latest`
- `task: DotNetCoreCLI@2` → appropriate `dotnet` commands or actions
- `task: Docker@2` → `docker/build-push-action@v6`
- `$(Build.SourceBranch)` → `${{ github.ref }}`
- `$(Build.BuildId)` → `${{ github.run_id }}`
- `$(System.AccessToken)` → `${{ secrets.GITHUB_TOKEN }}`
- Variable groups → GitHub environment variables or secrets
- Templates → reusable workflows or composite actions
- Environments → GitHub environments with protection rules
- Service connections → OIDC or secrets-based auth

### Jenkins → GitHub Actions
- `agent any` / `agent { docker { image '...' } }` → `runs-on:` / `container:`
- `stage('Name') { steps { ... } }` → job with steps
- `sh '...'` → `run: |` step
- `post { always { ... } }` → `if: always()` step or separate job
- `post { failure { ... } }` → `if: failure()` step
- `when { branch 'main' }` → job-level `if:` condition
- `withCredentials([...])` → `${{ secrets.* }}`
- `Jenkinsfile` parameters → `workflow_dispatch` inputs
- `parallel { ... }` → matrix strategy or parallel jobs with `needs`
- `stash/unstash` → `actions/upload-artifact` / `actions/download-artifact`

### GitLab CI → GitHub Actions
- `stages:` → job dependency graph via `needs:`
- `image:` → `container:` or `runs-on:` with setup action
- `services:` → `services:` in job config
- `before_script:` → early `run:` steps
- `script:` → `run:` steps
- `artifacts:` → `actions/upload-artifact@v4`
- `cache:` → `actions/cache@v4`
- `rules:` / `only:` / `except:` → `if:` conditions on jobs/steps
- `variables:` → `env:` at workflow or job level
- `$CI_COMMIT_SHA` → `${{ github.sha }}`
- `$CI_COMMIT_REF_NAME` → `${{ github.ref_name }}`
- `extends:` → reusable workflows or YAML anchors
- `needs:` → `needs:` (same concept)
- `environment:` → GitHub environments

## Response format

Return ONLY a valid JSON object with this structure:
{
  "workflow_name": "string — descriptive name for the workflow",
  "workflow_type": "standalone" | "reusable" | "composite",
  "triggers": ["push", "pull_request", ...],
  "jobs": [
    {
      "name": "job-id",
      "display_name": "Human readable name",
      "runs_on": "ubuntu-latest",
      "needs": [],
      "steps": [
        {
          "name": "Step name",
          "uses": "actions/checkout@v4" or null,
          "run": "command" or null,
          "with": {} or null,
          "env": {} or null,
          "if": "condition" or null
        }
      ],
      "services": {},
      "container": null,
      "environment": null,
      "permissions": {}
    }
  ],
  "secrets_required": [
    {"name": "SECRET_NAME", "description": "What this secret is for", "source": "Where it was referenced"}
  ],
  "environment_variables": [
    {"name": "VAR_NAME", "value": "suggested value or description"}
  ],
  "recommended_actions": [
    {"name": "actions/checkout", "version": "v4", "purpose": "Check out repository code"}
  ],
  "warnings": [
    {"severity": "info|warning|critical", "message": "Description of issue or limitation"}
  ],
  "notes": "Any additional migration notes"
}

IMPORTANT:
- If you identify secrets, tokens, or service connections that need to be set up in GitHub,
  list ALL of them in secrets_required. This is critical for the user to set up before the
  workflow can run.
- If there are constructs that cannot be directly migrated, add them as warnings.
- Respond with ONLY valid JSON. No markdown fences, no extra text.
"""


async def plan_migration(
    client: CopilotClient,
    filename: str,
    content: str,
    pipeline_type: PipelineType,
    byok: BYOKProviderConfig | None = None,
    on_user_question: Callable[..., Coroutine] | None = None,
) -> MigrationPlan:
    """Generate a migration plan from a source pipeline to GitHub Actions.

    Args:
        client: Shared CopilotClient instance.
        filename: Original filename.
        content: Original pipeline file content.
        pipeline_type: Detected pipeline type from validator.
        byok: Optional BYOK provider config.
        on_user_question: Async callback for human-in-the-loop questions.
            Signature: async (question: str, choices: list|None) -> str
    """
    model = byok.model_name if byok else "claude-sonnet-4.6"
    session_opts: dict = {
        "model": model,
        "system_message": {"content": SYSTEM_MESSAGE},
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
        prompt = (
            f"Create a GitHub Actions migration plan for this {pipeline_type.value} pipeline.\n"
            f"Filename: {filename}\n\n"
            f"```\n{content}\n```"
        )
        response = await session.send_and_wait(prompt)
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
            triggers=data.get("triggers", []),
            jobs=data.get("jobs", []),
            secrets_required=[
                {"name": s["name"], "description": s.get("description", ""), "source": s.get("source", "")}
                for s in data.get("secrets_required", [])
            ],
            environment_variables=data.get("environment_variables", []),
            recommended_actions=data.get("recommended_actions", []),
            warnings=[
                {"severity": w.get("severity", "info"), "message": w.get("message", "")}
                for w in data.get("warnings", [])
            ],
            notes=data.get("notes", ""),
            raw_plan=raw,
        )
    finally:
        await session.disconnect()
