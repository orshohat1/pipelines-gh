"""FastAPI application — REST + WebSocket entry point for pipeline migration."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.orchestrator import run_migration
from backend.config import BYOKProviderConfig, settings
from backend.models import BYOKConfigRequest, MigrateResponse, MigrationResult
from backend.websocket import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Pipeline Migration Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (job_id → list[MigrationResult])
_job_results: dict[str, list[MigrationResult] | None] = {}


# ── REST endpoints ───────────────────────────────────────────────────────


@app.post("/api/migrate", response_model=MigrateResponse)
async def start_migration(
    files: list[UploadFile] = File(...),
    byok_json: str | None = Form(default=None),
) -> MigrateResponse:
    """Accept pipeline files and optional BYOK config, start migration job."""

    # Parse optional BYOK payload
    byok: BYOKProviderConfig | None = None
    if byok_json:
        req = BYOKConfigRequest.model_validate_json(byok_json)
        byok = BYOKProviderConfig(
            provider_type=req.provider_type,
            base_url=req.base_url,
            api_key=req.api_key,
            model_name=req.model_name,
            wire_api=req.wire_api,
        )

    # Read uploaded files
    file_list: list[dict[str, str]] = []
    for upload in files:
        content = (await upload.read()).decode("utf-8")
        file_list.append(
            {
                "file_id": str(uuid.uuid4()),
                "filename": upload.filename or "unknown",
                "content": content,
            }
        )

    job_id = str(uuid.uuid4())
    _job_results[job_id] = None  # mark as in-progress

    # Fire-and-forget in the background
    asyncio.create_task(_run_job(job_id, file_list, byok))

    return MigrateResponse(job_id=job_id, file_count=len(file_list))


async def _run_job(
    job_id: str,
    file_list: list[dict[str, str]],
    byok: BYOKProviderConfig | None,
) -> None:
    """Background task that runs the orchestrator and stores results."""
    try:
        results = await run_migration(job_id, file_list, byok, manager)
        _job_results[job_id] = results
    except Exception:
        logger.exception("Job %s failed", job_id)
        _job_results[job_id] = []


@app.get("/api/jobs/{job_id}/results")
async def get_job_results(job_id: str) -> dict:
    """Poll for completed job results."""
    if job_id not in _job_results:
        return {"status": "not_found"}
    results = _job_results[job_id]
    if results is None:
        return {"status": "in_progress"}
    return {
        "status": "completed",
        "results": [r.model_dump() for r in results],
    }


# ── WebSocket ────────────────────────────────────────────────────────────


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """WebSocket for real-time updates, HITL questions, and plan approvals."""
    await manager.connect(job_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            await manager.handle_client_message(job_id, raw)
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)
