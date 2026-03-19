"""Orchestrator — coordinates validator → planner → (HITL approval) → coder pipeline."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import uuid
from typing import Any, Callable, Coroutine

from copilot import CopilotClient

from backend.agents.coder import generate_workflow, generate_workflows_parallel
from backend.agents.planner import plan_migration
from backend.agents.validator import validate_pipeline
from backend.config import BYOKProviderConfig, settings
from backend.models import (
    EvalResult,
    GeneratedFile,
    MigrationResult,
    PipelineType,
    PlanApproval,
    Stage,
    StageUpdate,
)
from backend.websocket import ConnectionManager

logger = logging.getLogger(__name__)


# ── Template detection ───────────────────────────────────────────────────────


def detect_template_refs(content: str, pipeline_type: PipelineType) -> list[dict[str, Any]]:
    """Detect template/include references in pipeline content."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()

    if pipeline_type == PipelineType.AZURE_DEVOPS:
        for match in re.finditer(r'template:\s*([^\s#]+\.ya?ml)', content):
            path = match.group(1).strip()
            if path not in seen:
                seen.add(path)
                refs.append({"path": path, "required": True})
    elif pipeline_type == PipelineType.GITLAB_CI:
        for match in re.finditer(r"(?:local|file):\s*['\"]?([^'\"\s]+\.ya?ml)['\"]?", content):
            path = match.group(1).strip()
            if path not in seen:
                seen.add(path)
                refs.append({"path": path, "required": True})
    elif pipeline_type == PipelineType.JENKINS:
        for match in re.finditer(r"@Library\(['\"]([^'\"]+)['\"]\)", content):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                refs.append({"path": name, "required": False})

    return refs


async def _process_single_file(
    client: CopilotClient,
    job_id: str,
    file_id: str,
    filename: str,
    content: str,
    byok: BYOKProviderConfig | None,
    ws_manager: ConnectionManager,
) -> MigrationResult:
    """Process a single pipeline file through all three agent stages.

    Flow: Validate → Plan → HITL Approval Gate → Code (with eval loop)
    """

    async def emit(stage: Stage, message: str = "", data: dict | None = None) -> None:
        update = StageUpdate(file_id=file_id, filename=filename, stage=stage, message=message, data=data)
        await ws_manager.broadcast(job_id, update)

    async def emit_agent(agent_type: str, status: str, detail: str = "", target_file: str = "") -> None:
        agent_id = f"{agent_type}-{file_id[:8]}"
        if target_file:
            agent_id = f"{agent_type}-{target_file.replace('.', '-').replace('/', '-')}-{file_id[:8]}"
        await ws_manager.broadcast_agent_activity(job_id, {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "file_id": file_id,
            "filename": filename,
            "detail": detail,
            "target_file": target_file,
        })

    # ── Stage 1: Validation ──────────────────────────────────────────────
    await emit(Stage.VALIDATING, "Detecting pipeline type...")
    await emit_agent("validator", "running", "Detecting pipeline type...")

    try:
        validation = await validate_pipeline(client, filename, content, byok)
    except Exception as e:
        logger.exception("Validation failed for %s", filename)
        await emit_agent("validator", "error", str(e))
        await emit(Stage.ERROR, f"Validation failed: {e}")
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=PipelineType.UNKNOWN,
            error=f"Validation failed: {e}",
        )

    await emit_agent("validator", "completed", f"Detected {validation.pipeline_type.value}")

    if validation.pipeline_type == PipelineType.UNKNOWN:
        await emit(
            Stage.ERROR,
            f"Could not identify pipeline type (confidence: {validation.confidence:.0%}). {validation.details}",
        )
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=PipelineType.UNKNOWN,
            error=f"Unrecognized pipeline format: {validation.details}",
        )

    await emit(
        Stage.VALIDATED,
        f"Detected {validation.pipeline_type.value} pipeline (confidence: {validation.confidence:.0%})",
        data=validation.model_dump(),
    )

    # ── Template detection ───────────────────────────────────────────────
    template_refs = detect_template_refs(content, validation.pipeline_type)
    template_contents: list[dict[str, str]] = []

    if template_refs:
        await emit(
            Stage.REQUESTING_TEMPLATES,
            f"Found {len(template_refs)} template reference(s). Please provide the template files.",
            data={"templates": template_refs},
        )
        template_contents = await ws_manager.request_templates(job_id, file_id, template_refs)
        if template_contents:
            await emit(Stage.PLANNING, f"Received {len(template_contents)} template(s). Planning full migration...")
        else:
            await emit(Stage.PLANNING, "No templates provided. Proceeding with best-effort plan...")
    else:
        await emit(Stage.PLANNING, "Generating migration plan...")

    # ── Stage 2: Planning ────────────────────────────────────────────────

    async def on_user_question(question: str, choices: list[str] | None) -> str:
        question_id = str(uuid.uuid4())
        return await ws_manager.send_question(job_id, file_id, question_id, question, choices)

    await emit_agent("planner", "running", "Generating migration plan...")
    try:
        plan = await plan_migration(
            client,
            filename,
            content,
            validation.pipeline_type,
            byok,
            on_user_question=on_user_question,
            template_contents=template_contents or None,
        )
    except Exception as e:
        logger.exception("Planning failed for %s", filename)
        await emit_agent("planner", "error", str(e))
        await emit(Stage.ERROR, f"Planning failed: {e}")
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=validation.pipeline_type,
            error=f"Planning failed: {e}",
        )

    await emit_agent("planner", "completed", "Migration plan ready")
    plan_data = plan.model_dump()
    await emit(Stage.PLAN_READY, "Migration plan ready — awaiting approval", data=plan_data)

    # ── HITL Approval Gate (with revision loop) ──────────────────────────
    max_revisions = 5
    for _revision_round in range(max_revisions):
        await emit(Stage.AWAITING_APPROVAL, "Waiting for user to approve the migration plan...")

        approval: PlanApproval = await ws_manager.request_plan_approval(job_id, file_id, plan_data)

        if approval.revise and approval.feedback:
            # User wants to revise — re-plan with feedback
            await emit(Stage.PLANNING, f"Revising plan: {approval.feedback}")
            await emit_agent("planner", "running", f"Revising plan: {approval.feedback}")
            try:
                plan = await plan_migration(
                    client,
                    filename,
                    content,
                    validation.pipeline_type,
                    byok,
                    on_user_question=on_user_question,
                    revision_feedback=approval.feedback,
                    previous_plan=plan_data,
                    template_contents=template_contents or None,
                )
            except Exception as e:
                logger.exception("Plan revision failed for %s", filename)
                await emit_agent("planner", "error", str(e))
                await emit(Stage.ERROR, f"Plan revision failed: {e}")
                return MigrationResult(
                    file_id=file_id,
                    filename=filename,
                    source_type=validation.pipeline_type,
                    error=f"Plan revision failed: {e}",
                )
            await emit_agent("planner", "completed", "Revised plan ready")
            plan_data = plan.model_dump()
            await emit(Stage.PLAN_READY, "Revised plan ready — awaiting approval", data=plan_data)
            continue

        if not approval.approved:
            msg = f"Plan rejected by user. Feedback: {approval.feedback}" if approval.feedback else "Plan rejected by user."
            await emit(Stage.ERROR, msg)
            return MigrationResult(
                file_id=file_id,
                filename=filename,
                source_type=validation.pipeline_type,
                plan=plan,
                error=msg,
            )

        # Approved — proceed to coding
        break

    # ── Stage 3: Code Generation (with eval loop) ────────────────────────
    use_parallel = bool(plan.output_files and len(plan.output_files) > 1)

    if use_parallel:
        await emit(Stage.CODING, f"Generating {len(plan.output_files)} workflow files in parallel...")
    else:
        await emit(Stage.CODING, "Generating GitHub Actions workflow YAML...")

    async def on_eval_update(eval_result: EvalResult) -> None:
        await emit(
            Stage.EVALUATING,
            f"Eval iteration {eval_result.iteration + 1}: score {eval_result.overall_score:.0%}"
            + (f" | actionlint: {'PASS' if eval_result.actionlint_passed else 'FAIL'}" if eval_result.actionlint_passed is not None else ""),
            data=eval_result.model_dump(),
        )

    async def agent_activity_cb(agent_type: str, status: str, detail: str = "", target_file: str = "") -> None:
        await emit_agent(agent_type, status, detail, target_file)

    try:
        if use_parallel:
            # Build full source context including templates
            full_source = content
            if template_contents:
                for tc in template_contents:
                    full_source += f"\n\n# Template: {tc['path']}\n{tc['content']}"

            generated_files, eval_results = await generate_workflows_parallel(
                client,
                plan,
                full_source,
                validation.pipeline_type,
                byok=byok,
                on_progress=lambda msg: emit(Stage.CODING, msg),
                on_agent_activity=agent_activity_cb,
            )
            yaml_content = generated_files[0].content if generated_files else ""
        else:
            source_for_gen = content
            if template_contents:
                for tc in template_contents:
                    source_for_gen += f"\n\n# Template: {tc['path']}\n{tc['content']}"

            yaml_content, eval_results = await generate_workflow(
                client,
                plan,
                source_for_gen,
                validation.pipeline_type,
                byok,
                on_eval_update=on_eval_update,
                on_agent_activity=agent_activity_cb,
            )
            generated_files = [GeneratedFile(
                filename=f"{plan.workflow_name or 'workflow'}.yml",
                content=yaml_content,
                file_type="workflow",
            )]
    except Exception as e:
        logger.exception("Code generation failed for %s", filename)
        await emit(Stage.ERROR, f"Code generation failed: {e}")
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=validation.pipeline_type,
            plan=plan,
            error=f"Code generation failed: {e}",
        )

    # ── Done ─────────────────────────────────────────────────────────────
    warnings = []
    if eval_results and eval_results[-1].overall_score < 0.8:
        warnings.append(f"Final eval score {eval_results[-1].overall_score:.0%} below threshold")
    if eval_results and eval_results[-1].actionlint_passed is False:
        warnings.append(f"actionlint issues: {eval_results[-1].actionlint_output}")

    result = MigrationResult(
        file_id=file_id,
        filename=filename,
        source_type=validation.pipeline_type,
        plan=plan,
        generated_yaml=yaml_content,
        generated_files=generated_files,
        eval_results=eval_results,
        warnings=warnings,
    )

    file_count = len(generated_files)
    score_msg = f" — final score: {eval_results[-1].overall_score:.0%}" if eval_results else ""
    files_msg = f" ({file_count} files)" if file_count > 1 else ""

    await emit(
        Stage.COMPLETED,
        f"Migration complete{files_msg}{score_msg}",
        data={
            "yaml": yaml_content,
            "generated_files": [f.model_dump() for f in generated_files],
            "warnings": warnings,
        },
    )

    return result


async def run_migration(
    job_id: str,
    files: list[dict[str, str]],
    byok: BYOKProviderConfig | None,
    ws_manager: ConnectionManager,
) -> list[MigrationResult]:
    """Run the full migration pipeline for multiple files in parallel.

    Args:
        job_id: Unique job identifier.
        files: List of {"file_id": ..., "filename": ..., "content": ...} dicts.
        byok: Optional BYOK configuration.
        ws_manager: WebSocket connection manager for real-time updates.

    Returns:
        List of MigrationResult for each file.
    """
    client = CopilotClient({"cwd": tempfile.mkdtemp(prefix="copilot-")})
    await client.start()

    semaphore = asyncio.Semaphore(settings.max_concurrent_pipelines)

    async def process_with_semaphore(file_info: dict) -> MigrationResult:
        async with semaphore:
            return await _process_single_file(
                client=client,
                job_id=job_id,
                file_id=file_info["file_id"],
                filename=file_info["filename"],
                content=file_info["content"],
                byok=byok,
                ws_manager=ws_manager,
            )

    try:
        results = await asyncio.gather(
            *(process_with_semaphore(f) for f in files),
            return_exceptions=False,
        )
        return list(results)
    except Exception:
        logger.exception("Migration job %s failed", job_id)
        raise
    finally:
        await client.stop()
