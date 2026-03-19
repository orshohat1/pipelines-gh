import { useState } from "react";
import {
  ShieldCheck,
  X,
  AlertTriangle,
  ArrowRight,
  Zap,
  GitBranch,
  ChevronDown,
  Lightbulb,
  ClipboardList,
  MessageSquare,
  Send,
  FileCode,
} from "lucide-react";
import type { PlanApprovalRequest } from "../types";

interface Props {
  approval: PlanApprovalRequest;
  onApprove: (fileId: string, approved: boolean, feedback?: string, revise?: boolean) => void;
}

/** Build a plain-language summary of the migration plan. */
function buildSummary(raw: Record<string, unknown>) {
  // If structured fields are empty but raw_plan has data, try parsing it
  let plan = raw;
  if (
    !raw.workflow_name &&
    (!Array.isArray(raw.jobs) || raw.jobs.length === 0) &&
    typeof raw.raw_plan === "string" &&
    raw.raw_plan.trim().startsWith("{")
  ) {
    try {
      const parsed = JSON.parse(raw.raw_plan as string) as Record<string, unknown>;
      if (parsed.workflow_name || (Array.isArray(parsed.jobs) && parsed.jobs.length > 0)) {
        plan = parsed;
      }
    } catch {
      // keep using original raw
    }
  }

  const workflowName = typeof plan.workflow_name === "string" ? plan.workflow_name : "GitHub Actions workflow";
  const description = typeof plan.description === "string" ? plan.description : "";
  const triggers = Array.isArray(plan.triggers) ? (plan.triggers as string[]) : [];
  const jobs = Array.isArray(plan.jobs) ? (plan.jobs as Record<string, unknown>[]) : [];
  const warnings = Array.isArray(plan.warnings) ? (plan.warnings as { severity: string; message: string }[]) : [];
  const prerequisites = Array.isArray(plan.prerequisites) ? (plan.prerequisites as { what: string; why: string; how: string }[]) : [];
  const enhancements = Array.isArray(plan.enhancements) ? (plan.enhancements as { title: string; description: string }[]) : [];
  const outputFiles = Array.isArray(plan.output_files) ? (plan.output_files as { filename: string; file_type: string; description: string }[]) : [];

  const sentences: string[] = [];

  // Trigger sentence
  if (triggers.length > 0) {
    const triggerNames = triggers.map(t => {
      if (t === "workflow_dispatch") return "manual trigger";
      if (t === "push") return "pushes";
      if (t === "pull_request") return "pull requests";
      if (t === "schedule") return "scheduled runs";
      return t;
    });
    sentences.push(`Runs on ${triggerNames.join(", ")}.`);
  }

  // Jobs sentence
  if (jobs.length === 1) {
    const j = jobs[0]!;
    const name = String(j.display_name || j.name || "a single job");
    const steps = Array.isArray(j.steps) ? j.steps.length : 0;
    sentences.push(`One job "${name}" with ${steps} steps on ${String(j.runs_on || "ubuntu-latest")}.`);
  } else if (jobs.length > 1) {
    const names = jobs.map(j => String(j.display_name || j.name || "unnamed"));
    sentences.push(`${jobs.length} jobs: ${names.join(" → ")}.`);
  }

  // OIDC detection
  const hasOIDC = jobs.some(j => {
    const perms = j.permissions as Record<string, unknown> | undefined;
    return perms && perms["id-token"] === "write";
  });
  if (hasOIDC) {
    sentences.push("Uses OIDC for keyless Azure/cloud login.");
  }

  // Caching detection
  const allSteps = jobs.flatMap(j => (Array.isArray(j.steps) ? j.steps : []) as Record<string, unknown>[]);
  const hasCache = allSteps.some(s => {
    const w = s.with as Record<string, unknown> | undefined;
    return (typeof s.uses === "string" && s.uses.includes("cache")) || (w && "cache" in w);
  });
  if (hasCache) {
    sentences.push("Dependency caching enabled.");
  }

  // Job flow for visual
  const jobFlow = jobs.map(j => String(j.display_name || j.name || "Job"));

  // Only critical/warning-level warnings
  const criticalWarnings = warnings
    .filter(w => w.severity === "critical" || w.severity === "warning")
    .map(w => w.message);

  return { title: workflowName, description, sentences, jobFlow, criticalWarnings, prerequisites, enhancements, outputFiles };
}

export default function PlanApprovalModal({ approval, onApprove }: Props) {
  const raw = approval.plan;
  const { title, description, sentences, jobFlow, criticalWarnings, prerequisites, enhancements, outputFiles } = buildSummary(raw);
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  const handleRevise = () => {
    if (!feedback.trim()) return;
    onApprove(approval.file_id, false, feedback.trim(), true);
    setFeedback("");
    setShowFeedback(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border border-gray-800 bg-gray-950 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10">
              <ShieldCheck size={18} className="text-emerald-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">Migration Plan</h2>
              <p className="text-xs text-gray-500">Review, revise, or approve</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onApprove(approval.file_id, false, "Dismissed")}
            className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-5 space-y-5">
          {/* Title + Description */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Zap size={14} className="text-indigo-400" />
              <span className="text-[10px] uppercase tracking-wider text-gray-500">Workflow</span>
            </div>
            <h3 className="text-base font-semibold text-gray-100">{title}</h3>
            {description && (
              <p className="mt-2 text-sm text-gray-400 leading-relaxed">{description}</p>
            )}
          </div>

          {/* Quick facts */}
          {sentences.length > 0 && (
            <div className="space-y-1">
              {sentences.map((s, i) => (
                <p key={i} className="text-sm text-gray-500 leading-relaxed">• {s}</p>
              ))}
            </div>
          )}

          {/* Job flow visualization */}
          {jobFlow.length > 1 && (
            <div className="flex items-center gap-2 flex-wrap py-1">
              {jobFlow.map((name, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="rounded-lg bg-indigo-500/10 px-3 py-1.5 text-xs font-medium text-indigo-400 ring-1 ring-indigo-500/20">
                    {name}
                  </span>
                  {i < jobFlow.length - 1 && (
                    <ArrowRight size={14} className="text-gray-600" />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Output files (multi-file generation) */}
          {outputFiles.length > 1 && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <FileCode size={14} className="text-indigo-400" />
                <span className="text-xs font-medium text-indigo-400">
                  {outputFiles.length} workflow files will be generated
                </span>
              </div>
              <div className="space-y-1.5">
                {outputFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-indigo-500/15 bg-indigo-500/5 px-3.5 py-2">
                    <code className="text-xs font-mono text-gray-300">{f.filename}</code>
                    <span className="text-[10px] text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">{f.file_type}</span>
                    {f.description && <span className="text-xs text-gray-500 ml-auto truncate max-w-[40%]">{f.description}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Prerequisites */}
          {prerequisites.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <ClipboardList size={14} className="text-amber-400" />
                <span className="text-xs font-medium text-amber-400">Before you run this workflow</span>
              </div>
              <div className="space-y-2">
                {prerequisites.map((p, i) => (
                  <div key={i} className="rounded-lg border border-amber-500/15 bg-amber-500/5 px-3.5 py-2.5">
                    <p className="text-sm font-medium text-gray-200">{p.what}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{p.why}</p>
                    {p.how && (
                      <code className="mt-1.5 block text-[11px] text-amber-300/70 bg-gray-900/50 rounded px-2 py-1 font-mono break-all">
                        {p.how}
                      </code>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Enhancement proposals */}
          {enhancements.length > 0 && (
            <details className="group">
              <summary className="flex items-center gap-2 cursor-pointer text-xs font-medium text-violet-400 hover:text-violet-300 transition">
                <Lightbulb size={14} />
                <span>{enhancements.length} best-practice enhancement{enhancements.length > 1 ? "s" : ""} proposed</span>
                <ChevronDown size={12} className="ml-auto transition-transform group-open:rotate-180 text-gray-600" />
              </summary>
              <div className="mt-2.5 space-y-2">
                {enhancements.map((e, i) => (
                  <div key={i} className="rounded-lg border border-violet-500/15 bg-violet-500/5 px-3.5 py-2.5">
                    <p className="text-sm font-medium text-gray-200">{e.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{e.description}</p>
                  </div>
                ))}
                <p className="text-[11px] text-gray-600 italic">
                  Want these? Click "Revise Plan" and ask for them.
                </p>
              </div>
            </details>
          )}

          {/* Warnings */}
          {criticalWarnings.length > 0 && (
            <div className="space-y-2">
              {criticalWarnings.map((msg, i) => (
                <div key={i} className="flex items-start gap-2.5 rounded-lg border border-amber-500/15 bg-amber-500/5 px-3.5 py-2.5">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-400" />
                  <p className="text-xs text-amber-300/90 leading-relaxed">{msg}</p>
                </div>
              ))}
            </div>
          )}

          {/* Raw plan expandable */}
          <details className="group">
            <summary className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-600 hover:text-gray-400 transition">
              <ChevronDown size={12} className="transition-transform group-open:rotate-180" />
              View full plan JSON
            </summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-gray-800/50 bg-gray-900/50 p-3 text-xs text-gray-500 whitespace-pre-wrap font-mono">
              {JSON.stringify(raw, null, 2)}
            </pre>
          </details>

          {/* Revision feedback area */}
          {showFeedback && (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs font-medium text-gray-300">
                <MessageSquare size={14} className="text-indigo-400" />
                What would you like to change?
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="e.g. Split into separate build and deploy jobs, add CodeQL scanning, use matrix strategy for node 18 and 20..."
                className="w-full rounded-lg border border-gray-700/50 bg-gray-900/50 px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 resize-none"
                rows={3}
                autoFocus
              />
              <button
                type="button"
                disabled={!feedback.trim()}
                onClick={handleRevise}
                className="flex items-center gap-2 rounded-lg bg-indigo-600/20 px-4 py-2 text-sm font-medium text-indigo-400 ring-1 ring-indigo-500/30 hover:bg-indigo-600/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Send size={14} />
                Send & Revise Plan
              </button>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-gray-800/50 px-6 py-4">
          <div className="flex items-center gap-1.5">
            <GitBranch size={12} className="text-gray-600" />
            <p className="text-xs text-gray-600">
              {outputFiles.length > 1
                ? `${outputFiles.length} YAML workflow files will be generated`
                : "A YAML workflow file will be generated"}
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => onApprove(approval.file_id, false, "Plan rejected by user")}
              className="rounded-lg border border-gray-700/50 px-4 py-2 text-sm text-gray-400 hover:border-red-500/50 hover:text-red-400 transition"
            >
              Reject
            </button>
            <button
              type="button"
              onClick={() => setShowFeedback(!showFeedback)}
              className="rounded-lg border border-indigo-500/30 bg-indigo-600/10 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-600/20 transition"
            >
              Revise Plan
            </button>
            <button
              type="button"
              onClick={() => onApprove(approval.file_id, true)}
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-500 transition active:scale-[0.98]"
            >
              Approve &amp; Generate
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
