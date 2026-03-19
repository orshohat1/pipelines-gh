/* Shared TypeScript types mirroring backend Pydantic models. */

export type PipelineType = "azure-devops" | "jenkins" | "gitlab-ci" | "unknown";

export type Stage =
  | "queued"
  | "validating"
  | "validated"
  | "requesting_templates"
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

export interface TemplateRef {
  path: string;
  required: boolean;
}

export interface TemplateRequestMsg {
  file_id: string;
  templates: TemplateRef[];
}

export interface GeneratedFile {
  filename: string;
  content: string;
  file_type: string;
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
  /** Preserved validation data (pipeline_type, confidence, details). */
  validationData?: Record<string, unknown> | null;
  yaml?: string;
  generatedFiles?: GeneratedFile[];
  warnings?: string[];
}

export interface BYOKConfig {
  provider_type: string;
  base_url: string;
  api_key: string;
  model_name: string;
  wire_api: string;
}

export interface AgentActivity {
  agent_id: string;
  agent_type: string;
  status: string;
  file_id: string;
  filename: string;
  detail: string;
  target_file: string;
  timestamp: number;
}

/** WebSocket message received from server (discriminated by "type"). */
export type ServerMessage =
  | ({ type: "stage_update" } & StageUpdate)
  | ({ type: "question" } & HumanQuestion)
  | ({ type: "plan_approval_request" } & PlanApprovalRequest)
  | ({ type: "template_request" } & TemplateRequestMsg)
  | ({ type: "agent_activity" } & AgentActivity);
