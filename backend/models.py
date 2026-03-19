"""Pydantic models for API requests/responses and internal data flow."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineType(str, Enum):
    AZURE_DEVOPS = "azure-devops"
    JENKINS = "jenkins"
    GITLAB_CI = "gitlab-ci"
    UNKNOWN = "unknown"


class Stage(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    CODING = "coding"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    ERROR = "error"


# ---------- Validator output ----------


class ValidationResult(BaseModel):
    pipeline_type: PipelineType
    confidence: float = Field(ge=0, le=1)
    details: str = ""


# ---------- Planner output ----------


class SecretDependency(BaseModel):
    name: str
    description: str
    source: str = ""  # where it was referenced in the original pipeline


class PlanWarning(BaseModel):
    severity: str = "info"  # info | warning | critical
    message: str


class MigrationPlan(BaseModel):
    workflow_name: str = ""
    workflow_type: str = ""  # standalone | reusable | composite
    triggers: list[str] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    secrets_required: list[SecretDependency] = Field(default_factory=list)
    environment_variables: list[dict[str, str]] = Field(default_factory=list)
    recommended_actions: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[PlanWarning] = Field(default_factory=list)
    notes: str = ""
    raw_plan: str = ""  # full text plan from the agent


# ---------- Coder / eval output ----------


class EvalDimension(BaseModel):
    name: str
    score: float = Field(ge=0, le=1)
    status: str = "PASS"  # PASS | FAIL
    feedback: str = ""


class EvalResult(BaseModel):
    overall_score: float = Field(ge=0, le=1)
    dimensions: list[EvalDimension] = Field(default_factory=list)
    iteration: int = 0
    actionlint_passed: bool | None = None
    actionlint_output: str = ""


# ---------- Stage updates (WebSocket messages) ----------


class StageUpdate(BaseModel):
    file_id: str
    filename: str
    stage: Stage
    message: str = ""
    data: dict[str, Any] | None = None


class HumanQuestion(BaseModel):
    """Question sent from planner agent to user via WebSocket."""

    file_id: str
    question_id: str
    question: str
    choices: list[str] | None = None
    allow_freeform: bool = True


class HumanAnswer(BaseModel):
    """Answer from user back to the planner agent."""

    question_id: str
    answer: str


class PlanApproval(BaseModel):
    """User approval/rejection of a migration plan."""

    file_id: str
    approved: bool
    feedback: str = ""


# ---------- Final result ----------


class MigrationResult(BaseModel):
    file_id: str
    filename: str
    source_type: PipelineType
    plan: MigrationPlan | None = None
    generated_yaml: str = ""
    eval_results: list[EvalResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


# ---------- API request/response ----------


class BYOKConfigRequest(BaseModel):
    provider_type: str = "openai"
    base_url: str | None = None
    api_key: str | None = None
    model_name: str = "claude-sonnet-4.6"
    wire_api: str = "completions"


class MigrateResponse(BaseModel):
    job_id: str
    file_count: int
