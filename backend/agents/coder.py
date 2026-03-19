"""Coder agent — generates GitHub Actions YAML with evaluator-optimizer loop and actionlint."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from copilot import CopilotClient, PermissionHandler

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])

from backend.config import BYOKProviderConfig, settings
from backend.models import EvalDimension, EvalResult, MigrationPlan, PipelineType

logger = logging.getLogger(__name__)

# ── System messages ──────────────────────────────────────────────────────────

GENERATOR_SYSTEM = """You are an expert GitHub Actions workflow author. Generate a complete,
production-ready GitHub Actions YAML workflow file.

STRICT RULES — every workflow you generate MUST:
1. Start with `name:` and include descriptive workflow name
2. Use `permissions:` at workflow level defaulting to `contents: read`
3. Pin all actions to specific major version tags (e.g. `actions/checkout@v4`), NEVER `@main`
4. Use `${{ secrets.NAME }}` for all secrets — never hardcode credentials
5. Include `concurrency:` configuration for deployment workflows
6. Use caching where appropriate (setup-node cache, setup-python cache, actions/cache)
7. Set artifact retention with `retention-days` where applicable
8. Use `env:` blocks for shared environment variables
9. Use `needs:` to express job dependencies
10. Include appropriate `if:` conditions for conditional execution
11. Use `runs-on: ubuntu-latest` unless the plan specifies otherwise

Output ONLY the raw YAML content. No markdown fences, no explanation. Just valid YAML starting
with `name:`.
"""

EVALUATOR_SYSTEM = """You are a GitHub Actions workflow quality evaluator. Given a generated
GitHub Actions YAML workflow, evaluate it against this rubric.

Score each dimension 0.0-1.0 and mark PASS (>= 0.7) or FAIL (< 0.7):

1. **yaml_syntax**: Is the YAML syntactically valid? Proper indentation, no missing colons,
   correct list formatting. This is the most critical dimension.
2. **action_pinning**: Are ALL actions pinned to specific versions (@v4 etc.)? Are any using
   @main, @latest, or missing version tags? Deduct heavily for unpinned actions.
3. **permissions**: Is `permissions:` configured? Does it default to `contents: read`?
   Are job-level permissions overriding only when needed?
4. **secrets_handling**: Are secrets accessed via `${{ secrets.* }}`? No hardcoded credentials?
   Environment variables used appropriately?
5. **trigger_config**: Do the triggers match the migration plan? Are branch filters correct?
6. **completeness**: Are all jobs/steps from the migration plan present? Any missing stages?
7. **best_practices**: Concurrency control? Caching? Artifact retention? Job dependencies
   with `needs:`? Conditional execution with `if:`?

Return ONLY valid JSON:
{
  "overall_score": 0.0-1.0,
  "dimensions": [
    {"name": "yaml_syntax", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "action_pinning", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "permissions", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "secrets_handling", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "trigger_config", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "completeness", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."},
    {"name": "best_practices", "score": 0.0-1.0, "status": "PASS|FAIL", "feedback": "..."}
  ]
}
"""

REFINER_SYSTEM = """You are a GitHub Actions workflow fixer. You will receive a workflow YAML
that failed evaluation, along with the evaluation feedback. Fix ALL issues identified in the
feedback while preserving the workflow's functionality.

Output ONLY the corrected raw YAML content. No markdown fences, no explanation.
Start directly with `name:`.
"""


# ── actionlint integration ──────────────────────────────────────────────────


def _actionlint_available() -> bool:
    """Check if actionlint binary is available on the system."""
    return shutil.which(settings.actionlint_path) is not None


def run_actionlint(yaml_content: str) -> tuple[bool, str]:
    """Run actionlint on a YAML string.

    Returns (passed: bool, output: str).
    """
    if not _actionlint_available():
        return True, "(actionlint not installed — skipped)"

    with tempfile.TemporaryDirectory() as tmpdir:
        # actionlint requires the file to be under .github/workflows/
        workflows_dir = Path(tmpdir) / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow_file = workflows_dir / "check.yml"
        workflow_file.write_text(yaml_content, encoding="utf-8")

        try:
            result = subprocess.run(
                [settings.actionlint_path, "-format", "{{range $err := .Errors}}{{$err.Filepath}}:{{$err.Line}}:{{$err.Column}}: {{$err.Message}}\n{{end}}", str(workflow_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir,
            )
            output = (result.stdout + result.stderr).strip()
            passed = result.returncode == 0
            return passed, output if output else "(no issues found)"
        except subprocess.TimeoutExpired:
            return False, "actionlint timed out after 30s"
        except FileNotFoundError:
            return True, "(actionlint not found — skipped)"


# ── Agent functions ──────────────────────────────────────────────────────────


async def _generate_yaml(
    client: CopilotClient,
    plan: MigrationPlan,
    source_content: str,
    pipeline_type: PipelineType,
    byok: BYOKProviderConfig | None,
) -> str:
    """Generate initial GitHub Actions YAML from a migration plan."""
    model = byok.model_name if byok else "claude-sonnet-4.6"
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": GENERATOR_SYSTEM},
        "on_permission_request": PermissionHandler.approve_all,
        "config_dir": PROJECT_ROOT,
    }
    provider = byok.to_sdk_provider() if byok else None
    if provider:
        session_opts["provider"] = provider

    session = await client.create_session(session_opts)
    try:
        prompt = (
            f"Generate a complete GitHub Actions workflow YAML based on this migration plan "
            f"and the original {pipeline_type.value} pipeline.\n\n"
            f"## Migration Plan\n```json\n{plan.model_dump_json(indent=2)}\n```\n\n"
            f"## Original Pipeline\n```\n{source_content}\n```"
        )
        response = await session.send_and_wait({"prompt": prompt}, timeout=180)
        raw = response.data.content if response else ""

        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else 3
            text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text
    finally:
        await session.disconnect()


async def _evaluate_yaml(
    client: CopilotClient,
    yaml_content: str,
    plan: MigrationPlan,
    iteration: int,
    byok: BYOKProviderConfig | None,
) -> EvalResult:
    """Evaluate generated YAML against the quality rubric + actionlint."""
    model = byok.model_name if byok else "claude-sonnet-4.6"
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": EVALUATOR_SYSTEM},
        "on_permission_request": PermissionHandler.approve_all,
        "config_dir": PROJECT_ROOT,
    }
    provider = byok.to_sdk_provider() if byok else None
    if provider:
        session_opts["provider"] = provider

    # Run actionlint concurrently with LLM evaluation
    lint_task = asyncio.get_event_loop().run_in_executor(None, run_actionlint, yaml_content)

    session = await client.create_session(session_opts)
    try:
        prompt = (
            f"Evaluate this GitHub Actions workflow YAML.\n\n"
            f"## Generated Workflow\n```yaml\n{yaml_content}\n```\n\n"
            f"## Migration Plan (for completeness check)\n```json\n{plan.model_dump_json(indent=2)}\n```"
        )
        response = await session.send_and_wait({"prompt": prompt}, timeout=180)
        raw = response.data.content if response else ""
    finally:
        await session.disconnect()

    # Parse LLM evaluation
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Evaluator returned non-JSON: %s", raw[:200])
        data = {"overall_score": 0.5, "dimensions": []}

    # Get actionlint results
    lint_passed, lint_output = await lint_task

    dimensions = [
        EvalDimension(
            name=d.get("name", ""),
            score=float(d.get("score", 0.5)),
            status=d.get("status", "PASS"),
            feedback=d.get("feedback", ""),
        )
        for d in data.get("dimensions", [])
    ]

    # Add actionlint as a dimension
    dimensions.append(
        EvalDimension(
            name="actionlint",
            score=1.0 if lint_passed else 0.0,
            status="PASS" if lint_passed else "FAIL",
            feedback=lint_output,
        )
    )

    # Recalculate overall score including actionlint
    if dimensions:
        overall = sum(d.score for d in dimensions) / len(dimensions)
    else:
        overall = float(data.get("overall_score", 0.5))

    return EvalResult(
        overall_score=overall,
        dimensions=dimensions,
        iteration=iteration,
        actionlint_passed=lint_passed,
        actionlint_output=lint_output,
    )


async def _refine_yaml(
    client: CopilotClient,
    yaml_content: str,
    eval_result: EvalResult,
    byok: BYOKProviderConfig | None,
) -> str:
    """Refine YAML based on evaluation feedback."""
    model = byok.model_name if byok else "claude-sonnet-4.6"
    session_opts: dict = {
        "model": model,
        "system_message": {"mode": "replace", "content": REFINER_SYSTEM},
        "on_permission_request": PermissionHandler.approve_all,
        "config_dir": PROJECT_ROOT,
    }
    provider = byok.to_sdk_provider() if byok else None
    if provider:
        session_opts["provider"] = provider

    session = await client.create_session(session_opts)
    try:
        failed = [d for d in eval_result.dimensions if d.status == "FAIL"]
        feedback_text = "\n".join(
            f"- **{d.name}** (score {d.score:.1f}): {d.feedback}" for d in failed
        )

        prompt = (
            f"Fix the following issues in this GitHub Actions workflow YAML.\n\n"
            f"## Issues to Fix\n{feedback_text}\n\n"
            f"## Current YAML\n```yaml\n{yaml_content}\n```"
        )
        response = await session.send_and_wait({"prompt": prompt}, timeout=180)
        raw = response.data.content if response else ""

        text = raw.strip()
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else 3
            text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text
    finally:
        await session.disconnect()


# ── Public API ───────────────────────────────────────────────────────────────

SCORE_THRESHOLD = 0.8
MAX_ITERATIONS = 3


async def generate_workflow(
    client: CopilotClient,
    plan: MigrationPlan,
    source_content: str,
    pipeline_type: PipelineType,
    byok: BYOKProviderConfig | None = None,
    on_eval_update: callable | None = None,
) -> tuple[str, list[EvalResult]]:
    """Generate GitHub Actions YAML with evaluator-optimizer loop.

    Implements the Evaluator-Optimizer pattern from the agentic-eval skill:
    Generate → Evaluate (LLM rubric + actionlint) → Refine → repeat until threshold met.

    Args:
        client: Shared CopilotClient.
        plan: Migration plan from the planner agent.
        source_content: Original pipeline file content.
        pipeline_type: Source pipeline type.
        byok: Optional BYOK config.
        on_eval_update: Optional callback(eval_result) for progress reporting.

    Returns:
        (final_yaml, list_of_eval_results)
    """
    yaml_content = await _generate_yaml(client, plan, source_content, pipeline_type, byok)
    eval_results: list[EvalResult] = []

    for iteration in range(MAX_ITERATIONS):
        eval_result = await _evaluate_yaml(client, yaml_content, plan, iteration, byok)
        eval_results.append(eval_result)

        if on_eval_update:
            await on_eval_update(eval_result)

        # Check if quality threshold met AND actionlint passes
        all_pass = all(d.status == "PASS" for d in eval_result.dimensions)
        if eval_result.overall_score >= SCORE_THRESHOLD and all_pass:
            logger.info("YAML passed evaluation on iteration %d (score: %.2f)", iteration, eval_result.overall_score)
            break

        if iteration < MAX_ITERATIONS - 1:
            logger.info(
                "YAML failed evaluation on iteration %d (score: %.2f), refining...",
                iteration,
                eval_result.overall_score,
            )
            yaml_content = await _refine_yaml(client, yaml_content, eval_result, byok)

    return yaml_content, eval_results
