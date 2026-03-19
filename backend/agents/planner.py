"""Planner agent — designs a migration plan from source pipeline to GitHub Actions."""

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

# ── Compact system prompt — mapping knowledge lives in the agent.md file ─────

SYSTEM_MESSAGE = """You are a CI/CD migration architect. Convert pipelines from Azure DevOps,
Jenkins, or GitLab CI to GitHub Actions.

Security rules for every plan:
- Default `permissions: contents: read` at workflow level
- Pin actions to major version tags (`@v4`), never `@main`/`@latest`
- Secrets via `${{ secrets.NAME }}` only; prefer OIDC over long‑lived creds
- Include `concurrency` groups for deployment workflows
- Use built‑in caching and set `retention-days` on artifacts

Return ONLY a valid JSON object (no markdown fences) with this schema:
{
  "workflow_name": "string",
  "workflow_type": "standalone|reusable|composite",
  "triggers": ["push", ...],
  "jobs": [{
    "name": "job-id", "display_name": "...", "runs_on": "ubuntu-latest",
    "needs": [], "steps": [{"name":"...","uses":"...","run":"...","with":{},"env":{},"if":"..."}],
    "services": {}, "container": null, "environment": null, "permissions": {}
  }],
  "secrets_required": [{"name":"...","description":"...","source":"..."}],
  "environment_variables": [{"name":"...","value":"..."}],
  "recommended_actions": [{"name":"...","version":"v4","purpose":"..."}],
  "warnings": [{"severity":"info|warning|critical","message":"..."}],
  "notes": "..."
}
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
        "system_message": {"mode": "replace", "content": SYSTEM_MESSAGE},
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
        sid = session.session_id
        await session.disconnect()
        try:
            await client.delete_session(sid)
        except Exception:
            pass
