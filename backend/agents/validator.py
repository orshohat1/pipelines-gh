"""Validator agent — classifies pipeline files by CI/CD platform type."""

from __future__ import annotations

import json
import logging
import re

from copilot import CopilotClient, PermissionHandler

from backend.config import BYOKProviderConfig
from backend.models import PipelineType, ValidationResult

logger = logging.getLogger(__name__)

SYSTEM_MESSAGE = """You are a CI/CD pipeline file classifier. Your ONLY job is to determine
which CI/CD platform a given pipeline file belongs to, and assess its complexity.

Analyze the file content and return a JSON object with exactly these fields:
{
  "pipeline_type": "azure-devops" | "jenkins" | "gitlab-ci" | "unknown",
  "confidence": 0.0 to 1.0,
  "complexity": "simple" | "complex",
  "details": "Brief explanation of why you classified it this way"
}

Classification rules:
- **Azure DevOps**: Look for `trigger:`, `pool:`, `steps:`, `task:`, `stages:` (with `- stage:`),
  `variables:`, `resources:`, `extends:`, `template:`, `parameters:`, `pr:` trigger,
  `azure-pipelines.yml` patterns. Uses `$(variable)` syntax for variables.
- **Jenkins**: Look for `pipeline {`, `agent`, `stages {`, `stage('...')`, `steps {`,
  `post {`, `when {`, `environment {`, `Jenkinsfile` patterns. Uses Groovy DSL syntax.
  Also handles scripted pipelines with `node {`, `checkout scm`.
- **GitLab CI**: Look for `stages:`, `image:`, `script:`, `before_script:`, `after_script:`,
  `artifacts:`, `cache:`, `services:`, `rules:`, `only:`, `except:`, `variables:` (with `$CI_`
  prefixed variables), `.gitlab-ci.yml` patterns, `extends:` for template inheritance.
- **unknown**: If the file doesn't clearly match any of the above platforms.

Complexity rules:
- **complex**: Multiple stages/environments, template references, deployment steps, multi-stage
  builds with deploy, matrix builds, conditional logic, extensive variable groups, service
  connections/integrations, or more than 3 jobs/stages. Also complex if the pipeline has
  infrastructure provisioning, approval gates, or artifact publishing across environments.
- **simple**: Single stage or basic build-test, no deployments, no templates, 1-3 straightforward
  jobs, no conditional branching, basic CI only.

IMPORTANT:
- Respond with ONLY valid JSON. No markdown, no explanation outside the JSON.
- confidence should be >= 0.9 for clear matches, 0.5-0.8 for ambiguous files.
- If a file has characteristics of multiple platforms, pick the most likely one and note it in details.
"""


async def validate_pipeline(
    client: CopilotClient,
    filename: str,
    content: str,
    byok: BYOKProviderConfig | None = None,
) -> ValidationResult:
    """Classify a pipeline file using a Copilot SDK session.

    Returns a ValidationResult with the detected pipeline type.
    """
    model = byok.model_name if byok else "openai/gpt-5.4-mini"
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": SYSTEM_MESSAGE},
        "on_permission_request": PermissionHandler.approve_all,
    }
    provider = byok.to_sdk_provider() if byok else None
    if provider:
        session_opts["provider"] = provider

    session = await client.create_session(session_opts)
    try:
        prompt = (
            f"Classify this CI/CD pipeline file.\n"
            f"Filename: {filename}\n\n"
            f"```\n{content}\n```"
        )
        response = await session.send_and_wait({"prompt": prompt}, timeout=120)
        raw = response.data.content if response else ""

        # Parse JSON from the response — handle markdown fences and surrounding text
        text = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        else:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                text = text[brace_start : brace_end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Validator returned non-JSON: %s", raw[:200])
            return ValidationResult(
                pipeline_type=PipelineType.UNKNOWN,
                confidence=0.0,
                details=f"Failed to parse validator response: {raw[:200]}",
                complexity="simple",
            )

        return ValidationResult(
            pipeline_type=PipelineType(data.get("pipeline_type", "unknown")),
            confidence=float(data.get("confidence", 0.0)),
            details=data.get("details", ""),
            complexity=data.get("complexity", "simple"),
        )
    finally:
        sid = session.session_id
        await session.disconnect()
        try:
            await client.delete_session(sid)
        except Exception:
            pass
