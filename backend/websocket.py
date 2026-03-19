"""WebSocket connection manager for real-time pipeline migration updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from backend.models import HumanAnswer, PlanApproval, StageUpdate

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per job and handles bidirectional messaging."""

    def __init__(self) -> None:
        # job_id -> list of connected WebSockets
        self._connections: dict[str, list[WebSocket]] = {}
        # Pending human-in-the-loop questions: question_id -> asyncio.Future
        self._pending_questions: dict[str, asyncio.Future[str]] = {}
        # Pending plan approvals: file_id -> asyncio.Future
        self._pending_approvals: dict[str, asyncio.Future[PlanApproval]] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(job_id, []).append(websocket)
        logger.info("WebSocket connected for job %s", job_id)

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        if job_id in self._connections:
            self._connections[job_id] = [
                ws for ws in self._connections[job_id] if ws is not websocket
            ]
            if not self._connections[job_id]:
                del self._connections[job_id]
        logger.info("WebSocket disconnected for job %s", job_id)

    async def broadcast(self, job_id: str, update: StageUpdate) -> None:
        """Send a stage update to all connected clients for a job."""
        if job_id not in self._connections:
            return
        message = json.dumps({"type": "stage_update", **update.model_dump()})
        dead: list[WebSocket] = []
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(job_id, ws)

    async def send_question(
        self,
        job_id: str,
        file_id: str,
        question_id: str,
        question: str,
        choices: list[str] | None = None,
    ) -> str:
        """Send a human-in-the-loop question and wait for the answer.

        Returns the user's answer string.
        """
        message = json.dumps({
            "type": "question",
            "file_id": file_id,
            "question_id": question_id,
            "question": question,
            "choices": choices,
            "allow_freeform": True,
        })
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                pass

        # Create a future to wait for the answer
        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_questions[question_id] = future

        try:
            answer = await asyncio.wait_for(future, timeout=300)  # 5 min timeout
            return answer
        except asyncio.TimeoutError:
            logger.warning("Question %s timed out", question_id)
            return "(no response — timed out)"
        finally:
            self._pending_questions.pop(question_id, None)

    async def request_plan_approval(
        self,
        job_id: str,
        file_id: str,
        plan_data: dict[str, Any],
    ) -> PlanApproval:
        """Send the migration plan to the user and wait for approval before coding.

        Returns PlanApproval with approved=True/False and optional feedback.
        """
        message = json.dumps({
            "type": "plan_approval_request",
            "file_id": file_id,
            "plan": plan_data,
        })
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        future: asyncio.Future[PlanApproval] = loop.create_future()
        self._pending_approvals[file_id] = future

        try:
            approval = await asyncio.wait_for(future, timeout=600)  # 10 min timeout
            return approval
        except asyncio.TimeoutError:
            logger.warning("Plan approval for %s timed out", file_id)
            return PlanApproval(file_id=file_id, approved=False, feedback="Approval timed out")
        finally:
            self._pending_approvals.pop(file_id, None)

    def resolve_question(self, answer: HumanAnswer) -> None:
        """Resolve a pending human-in-the-loop question with the user's answer."""
        future = self._pending_questions.get(answer.question_id)
        if future and not future.done():
            future.set_result(answer.answer)

    def resolve_approval(self, approval: PlanApproval) -> None:
        """Resolve a pending plan approval."""
        future = self._pending_approvals.get(approval.file_id)
        if future and not future.done():
            future.set_result(approval)

    async def handle_client_message(self, job_id: str, raw: str) -> None:
        """Process an incoming message from a WebSocket client."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from client: %s", raw[:100])
            return

        msg_type = data.get("type")

        if msg_type == "answer":
            self.resolve_question(
                HumanAnswer(
                    question_id=data.get("question_id", ""),
                    answer=data.get("answer", ""),
                )
            )
        elif msg_type == "plan_approval":
            self.resolve_approval(
                PlanApproval(
                    file_id=data.get("file_id", ""),
                    approved=data.get("approved", False),
                    feedback=data.get("feedback", ""),
                    revise=data.get("revise", False),
                )
            )
        else:
            logger.warning("Unknown message type from client: %s", msg_type)


manager = ConnectionManager()
