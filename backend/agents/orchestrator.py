"""Orchestrator — coordinates validator → planner → (HITL approval) → coder pipeline."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine

from copilot import CopilotClient

from backend.agents.coder import generate_workflow
from backend.agents.planner import plan_migration
from backend.agents.validator import validate_pipeline
from backend.config import BYOKProviderConfig, settings
from backend.models import (
    EvalResult,
    MigrationResult,
    PipelineType,
    PlanApproval,
    Stage,
    StageUpdate,
)
from backend.websocket import ConnectionManager

logger = logging.getLogger(__name__)


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

    # ── Stage 1: Validation ──────────────────────────────────────────────
    await emit(Stage.VALIDATING, "Detecting pipeline type...")

    try:
        validation = await validate_pipeline(client, filename, content, byok)
    except Exception as e:
        logger.exception("Validation failed for %s", filename)
        await emit(Stage.ERROR, f"Validation failed: {e}")
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=PipelineType.UNKNOWN,
            error=f"Validation failed: {e}",
        )

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

    # ── Stage 2: Planning ────────────────────────────────────────────────
    await emit(Stage.PLANNING, "Generating migration plan...")

    async def on_user_question(question: str, choices: list[str] | None) -> str:
        question_id = str(uuid.uuid4())
        return await ws_manager.send_question(job_id, file_id, question_id, question, choices)

    try:
        plan = await plan_migration(
            client,
            filename,
            content,
            validation.pipeline_type,
            byok,
            on_user_question=on_user_question,
        )
    except Exception as e:
        logger.exception("Planning failed for %s", filename)
        await emit(Stage.ERROR, f"Planning failed: {e}")
        return MigrationResult(
            file_id=file_id,
            filename=filename,
            source_type=validation.pipeline_type,
            error=f"Planning failed: {e}",
        )

    plan_data = plan.model_dump()
    await emit(Stage.PLAN_READY, "Migration plan ready — awaiting approval", data=plan_data)

    # ── HITL Approval Gate ───────────────────────────────────────────────
    await emit(Stage.AWAITING_APPROVAL, "Waiting for user to approve the migration plan...")

    approval: PlanApproval = await ws_manager.request_plan_approval(job_id, file_id, plan_data)

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

    # ── Stage 3: Code Generation (with eval loop) ────────────────────────
    await emit(Stage.CODING, "Generating GitHub Actions workflow YAML...")

    async def on_eval_update(eval_result: EvalResult) -> None:
        await emit(
            Stage.EVALUATING,
            f"Eval iteration {eval_result.iteration + 1}: score {eval_result.overall_score:.0%}"
            + (f" | actionlint: {'PASS' if eval_result.actionlint_passed else 'FAIL'}" if eval_result.actionlint_passed is not None else ""),
            data=eval_result.model_dump(),
        )

    try:
        yaml_content, eval_results = await generate_workflow(
            client,
            plan,
            content,
            validation.pipeline_type,
            byok,
            on_eval_update=on_eval_update,
        )
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
        eval_results=eval_results,
        warnings=warnings,
    )

    await emit(
        Stage.COMPLETED,
        f"Migration complete — final score: {eval_results[-1].overall_score:.0%}" if eval_results else "Migration complete",
        data={"yaml": yaml_content, "warnings": warnings},
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
    client = CopilotClient()
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
