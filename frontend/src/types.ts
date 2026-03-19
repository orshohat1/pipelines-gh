/* Shared TypeScript types mirroring backend Pydantic models. */

export type PipelineType = "azure-devops" | "jenkins" | "gitlab-ci" | "unknown";

export type Stage =
  | "queued"
  | "validating"
  | "validated"
  | "planning"
  | "plan_ready"
  | "awaiting_approval"
  | "coding"
  | "evaluating"
  | "completed"
  | "error";

export interface StageUpdate {
  file_id: string;
  filename: string;
  stage: Stage;
  message: string;
  data?: Record<string, unknown> | null;
}

export interface HumanQuestion {
  file_id: string;
  question_id: string;
  question: string;
  choices?: string[] | null;
  allow_freeform: boolean;
}

export interface PlanApprovalRequest {
  file_id: string;
  plan: Record<string, unknown>;
}

export interface EvalDimension {
  name: string;
  score: number;
  status: string;
  feedback: string;
}

export interface EvalResult {
  overall_score: number;
  dimensions: EvalDimension[];
  iteration: number;
  actionlint_passed: boolean | null;
  actionlint_output: string;
}

export interface MigrationResult {
  file_id: string;
  filename: string;
  source_type: PipelineType;
  plan?: Record<string, unknown> | null;
  generated_yaml: string;
  eval_results: EvalResult[];
  warnings: string[];
  error?: string | null;
}

/** Per-file state tracked in the UI. */
export interface PipelineFile {
  file_id: string;
  filename: string;
  stage: Stage;
  message: string;
  data?: Record<string, unknown> | null;
  yaml?: string;
  warnings?: string[];
}

export interface BYOKConfig {
  provider_type: string;
  base_url: string;
  api_key: string;
  model_name: string;
  wire_api: string;
}

/** WebSocket message received from server (discriminated by "type"). */
export type ServerMessage =
  | ({ type: "stage_update" } & StageUpdate)
  | ({ type: "question" } & HumanQuestion)
  | ({ type: "plan_approval_request" } & PlanApprovalRequest);
