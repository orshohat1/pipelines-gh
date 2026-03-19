import type { PipelineFile, Stage } from "../types";
import {
  CheckCircle2,
  Circle,
  AlertTriangle,
  Loader2,
  Clock,
  ShieldQuestion,
} from "lucide-react";

const STAGE_ORDER: Stage[] = [
  "queued",
  "validating",
  "validated",
  "planning",
  "plan_ready",
  "awaiting_approval",
  "coding",
  "evaluating",
  "completed",
];

function stageIcon(stage: Stage) {
  switch (stage) {
    case "completed":
      return <CheckCircle2 size={16} className="text-green-400" />;
    case "error":
      return <AlertTriangle size={16} className="text-red-400" />;
    case "awaiting_approval":
      return <ShieldQuestion size={16} className="text-amber-400 animate-pulse" />;
    case "queued":
      return <Clock size={16} className="text-gray-500" />;
    default:
      return <Loader2 size={16} className="text-indigo-400 animate-spin" />;
  }
}

function stageLabel(stage: Stage): string {
  const labels: Record<Stage, string> = {
    queued: "Queued",
    validating: "Validating",
    validated: "Validated",
    planning: "Planning",
    plan_ready: "Plan Ready",
    awaiting_approval: "Awaiting Approval",
    coding: "Generating YAML",
    evaluating: "Evaluating",
    completed: "Completed",
    error: "Error",
  };
  return labels[stage];
}

function stageIndex(stage: Stage): number {
  const idx = STAGE_ORDER.indexOf(stage);
  return idx === -1 ? STAGE_ORDER.length : idx;
}

interface Props {
  file: PipelineFile;
  onViewYaml?: () => void;
}

export default function PipelineStatus({ file, onViewYaml }: Props) {
  const current = stageIndex(file.stage);
  const total = STAGE_ORDER.length;
  const progress = file.stage === "error" ? current : Math.min(((current + 1) / total) * 100, 100);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        {stageIcon(file.stage)}
        <h3 className="text-sm font-medium text-gray-100 truncate flex-1">
          {file.filename}
        </h3>
        <span className="rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
          {stageLabel(file.stage)}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            file.stage === "error" ? "bg-red-500" : file.stage === "completed" ? "bg-green-500" : "bg-indigo-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Message */}
      {file.message && (
        <p className="text-xs text-gray-400 leading-relaxed">{file.message}</p>
      )}

      {/* Warnings */}
      {file.warnings && file.warnings.length > 0 && (
        <div className="space-y-1">
          {file.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-400 flex items-start gap-1">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {w}
            </p>
          ))}
        </div>
      )}

      {/* View YAML button */}
      {file.stage === "completed" && file.yaml && (
        <button
          type="button"
          className="text-xs text-indigo-400 hover:text-indigo-300 transition"
          onClick={onViewYaml}
        >
          View generated YAML &rarr;
        </button>
      )}
    </div>
  );
}
