import type { PipelineFile, Stage } from "../types";
import {
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ShieldCheck,
  FileCode,
  Code2,
  Eye,
  Search,
  ClipboardList,
  ExternalLink,
} from "lucide-react";

/** Visible pipeline stages shown in the stepper (collapsed from internal stages). */
const VISIBLE_STAGES = [
  { key: "validate", label: "Validate", covers: ["queued", "validating", "validated", "requesting_templates"] as Stage[] },
  { key: "plan", label: "Plan", covers: ["planning", "plan_ready"] as Stage[] },
  { key: "approve", label: "Approve", covers: ["awaiting_approval"] as Stage[] },
  { key: "generate", label: "Generate", covers: ["coding"] as Stage[] },
  { key: "evaluate", label: "Evaluate", covers: ["evaluating"] as Stage[] },
  { key: "done", label: "Done", covers: ["completed"] as Stage[] },
];

function getVisibleIndex(stage: Stage): number {
  for (let i = 0; i < VISIBLE_STAGES.length; i++) {
    if (VISIBLE_STAGES[i]!.covers.includes(stage)) return i;
  }
  return -1;
}

function stageIcon(stage: Stage, size = 16) {
  switch (stage) {
    case "completed":
      return <CheckCircle2 size={size} className="text-emerald-400" />;
    case "error":
      return <AlertTriangle size={size} className="text-red-400" />;
    case "awaiting_approval":
      return <ShieldCheck size={size} className="text-amber-400 animate-pulse" />;
    case "validating":
    case "validated":
      return <Search size={size} className="text-indigo-400 animate-spin" />;
    case "requesting_templates":
      return <FileCode size={size} className="text-amber-400 animate-pulse" />;
    case "planning":
    case "plan_ready":
      return <ClipboardList size={size} className="text-indigo-400 animate-spin" />;
    case "coding":
      return <Code2 size={size} className="text-indigo-400 animate-spin" />;
    case "evaluating":
      return <Eye size={size} className="text-indigo-400 animate-spin" />;
    default:
      return <Loader2 size={size} className="text-gray-500 animate-spin" />;
  }
}

function stageLabel(stage: Stage): string {
  const labels: Record<Stage, string> = {
    queued: "Queued",
    validating: "Analyzing pipeline...",
    validated: "Pipeline identified",
    requesting_templates: "Waiting for template files...",
    planning: "Creating migration plan...",
    plan_ready: "Plan ready",
    awaiting_approval: "Awaiting your approval",
    coding: "Generating workflow...",
    evaluating: "Evaluating quality...",
    completed: "Migration complete",
    error: "Error",
  };
  return labels[stage];
}

interface Props {
  file: PipelineFile;
  onViewYaml?: () => void;
}

function ValidationBadge({ data }: { data?: Record<string, unknown> | null }) {
  if (!data || !data.pipeline_type) return null;
  const pType = String(data.pipeline_type).replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const confidence = typeof data.confidence === "number" ? data.confidence : null;
  const details = typeof data.details === "string" ? data.details : "";
  return (
    <div className="flex items-center gap-3 rounded-lg border border-indigo-500/15 bg-indigo-500/5 px-3.5 py-2.5">
      <div className="flex items-center gap-2 text-xs">
        <Search size={12} className="text-indigo-400 shrink-0" />
        <span className="text-gray-400">Detected</span>
        <span className="font-medium text-indigo-400">{pType}</span>
        {confidence !== null && (
          <span className="text-gray-500">({Math.round(confidence * 100)}% confidence)</span>
        )}
      </div>
      {details && (
        <span className="text-[11px] text-gray-500 ml-auto truncate max-w-[50%]" title={details}>{details}</span>
      )}
    </div>
  );
}

export default function PipelineStatus({ file, onViewYaml }: Props) {
  const currentVisibleIdx = getVisibleIndex(file.stage);
  const isError = file.stage === "error";
  const isComplete = file.stage === "completed";

  return (
    <div
      className={`rounded-2xl border p-5 space-y-4 transition-all animate-fade-in-up ${
        isComplete
          ? "border-emerald-500/20 bg-emerald-500/5 glow-green"
          : isError
            ? "border-red-500/20 bg-red-500/5"
            : "border-gray-800/50 bg-gray-900/50"
      }`}
    >
      {/* Header row */}
      <div className="flex items-center gap-3">
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${
          isComplete ? "bg-emerald-500/10" : isError ? "bg-red-500/10" : "bg-gray-800"
        }`}>
          {isComplete ? (
            <CheckCircle2 size={18} className="text-emerald-400" />
          ) : isError ? (
            <AlertTriangle size={18} className="text-red-400" />
          ) : (
            <FileCode size={18} className="text-indigo-400" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-gray-100 truncate">{file.filename}</h3>
          <p className={`text-xs ${isError ? "text-red-400" : isComplete ? "text-emerald-400" : "text-gray-500"}`}>
            {stageLabel(file.stage)}
          </p>
        </div>
        {!isError && !isComplete && stageIcon(file.stage, 18)}
      </div>

      {/* Stage stepper */}
      <div className="flex items-center gap-1">
        {VISIBLE_STAGES.map((vs, idx) => {
          const isDone = currentVisibleIdx > idx || isComplete;
          const isCurrent = currentVisibleIdx === idx && !isComplete && !isError;
          const isErrorStage = isError && currentVisibleIdx === idx;

          return (
            <div key={vs.key} className="flex-1 flex flex-col items-center gap-1.5">
              {/* Segment bar */}
              <div className="w-full h-1.5 rounded-full overflow-hidden bg-gray-800/50">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    isDone
                      ? "bg-emerald-500 w-full"
                      : isCurrent
                        ? "bg-indigo-500 w-full animate-pulse"
                        : isErrorStage
                          ? "bg-red-500 w-full"
                          : "w-0"
                  }`}
                  style={{ width: isDone || isCurrent || isErrorStage ? "100%" : "0%" }}
                />
              </div>
              {/* Label */}
              <span
                className={`text-[10px] leading-none transition ${
                  isDone
                    ? "text-emerald-400/70"
                    : isCurrent
                      ? "text-indigo-400 font-medium"
                      : isErrorStage
                        ? "text-red-400"
                        : "text-gray-600"
                }`}
              >
                {vs.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Validation result */}
      {file.stage !== "error" && <ValidationBadge data={file.validationData} />}

      {/* Message */}
      {file.message && (
        <p className={`text-xs leading-relaxed ${isError ? "text-red-400/80" : "text-gray-400"}`}>
          {file.message}
        </p>
      )}

      {/* Warnings */}
      {file.warnings && file.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/10 bg-amber-500/5 px-3 py-2 space-y-1">
          {file.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-400 flex items-start gap-1.5">
              <AlertTriangle size={11} className="mt-0.5 shrink-0" />
              {w}
            </p>
          ))}
        </div>
      )}

      {/* View YAML button */}
      {isComplete && file.yaml && (
        <button
          type="button"
          className="group flex items-center gap-1.5 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition"
          onClick={onViewYaml}
        >
          View generated workflow
          <ExternalLink size={12} className="transition group-hover:translate-x-0.5" />
        </button>
      )}
    </div>
  );
}
