import { ShieldCheck, X, AlertTriangle, Key, Briefcase, GitBranch, Code2 } from "lucide-react";
import type { PlanApprovalRequest } from "../types";

interface Props {
  approval: PlanApprovalRequest;
  onApprove: (fileId: string, approved: boolean, feedback?: string) => void;
}

function SectionLabel({ children, icon: Icon }: { children: React.ReactNode; icon: React.ComponentType<{ size: number; className?: string }> }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <Icon size={14} className="text-gray-500" />
      <span className="text-xs font-medium uppercase tracking-wider text-gray-500">{children}</span>
    </div>
  );
}

export default function PlanApprovalModal({ approval, onApprove }: Props) {
  const raw = approval.plan;

  // Extract typed values for safe JSX rendering
  const workflowName = typeof raw.workflow_name === "string" ? raw.workflow_name : "";
  const workflowType = typeof raw.workflow_type === "string" ? raw.workflow_type : "";
  const triggers = Array.isArray(raw.triggers) ? (raw.triggers as string[]) : [];
  const jobs = Array.isArray(raw.jobs) ? (raw.jobs as Record<string, unknown>[]) : [];
  const secrets = Array.isArray(raw.secrets_required) ? (raw.secrets_required as { name: string; description: string }[]) : [];
  const warnings = Array.isArray(raw.warnings) ? (raw.warnings as { severity: string; message: string }[]) : [];
  const notes = typeof raw.notes === "string" ? raw.notes : "";
  const rawPlan = typeof raw.raw_plan === "string" ? raw.raw_plan : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border border-gray-800 bg-gray-950 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/10">
              <ShieldCheck size={18} className="text-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">Approve Migration Plan</h2>
              <p className="text-xs text-gray-500">Review the plan before generating the workflow</p>
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

        {/* Plan details */}
        <div className="flex-1 overflow-auto px-6 py-5 space-y-5 text-sm">
          {/* Top info row */}
          {(workflowName || workflowType) && (
            <div className="grid grid-cols-2 gap-3">
              {workflowName && (
                <div className="rounded-lg border border-gray-800/50 bg-gray-900/50 px-3.5 py-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">Workflow</p>
                  <p className="text-sm text-gray-200 font-medium">{workflowName}</p>
                </div>
              )}
              {workflowType && (
                <div className="rounded-lg border border-gray-800/50 bg-gray-900/50 px-3.5 py-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">Type</p>
                  <p className="text-sm text-gray-200 capitalize">{workflowType}</p>
                </div>
              )}
            </div>
          )}

          {/* Triggers */}
          {triggers.length > 0 && (
            <div>
              <SectionLabel icon={GitBranch}>Triggers</SectionLabel>
              <div className="flex flex-wrap gap-1.5">
                {triggers.map((t) => (
                  <span key={t} className="rounded-md bg-indigo-500/10 px-2.5 py-1 text-xs font-mono text-indigo-400 ring-1 ring-indigo-500/20">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Jobs */}
          {jobs.length > 0 && (
            <div>
              <SectionLabel icon={Briefcase}>Jobs ({jobs.length})</SectionLabel>
              <div className="space-y-1.5">
                {jobs.map((job, i) => (
                  <div key={i} className="flex items-center gap-2.5 rounded-lg border border-gray-800/50 bg-gray-900/30 px-3 py-2">
                    <Code2 size={14} className="shrink-0 text-indigo-400/70" />
                    <span className="text-sm text-gray-300">
                      {String(job.display_name || job.name || job.id || `Job ${i + 1}`)}
                    </span>
                    {job.runs_on ? (
                      <span className="ml-auto text-[10px] text-gray-600 font-mono">{String(job.runs_on)}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Secrets */}
          {secrets.length > 0 && (
            <div>
              <SectionLabel icon={Key}>Secrets Required</SectionLabel>
              <div className="rounded-lg border border-amber-500/10 bg-amber-500/5 px-3.5 py-2.5 space-y-1.5">
                {secrets.map((s, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="font-mono text-amber-400 shrink-0">{s.name}</span>
                    <span className="text-gray-400">{s.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warnings */}
          {warnings.length > 0 && (
            <div>
              <SectionLabel icon={AlertTriangle}>Warnings</SectionLabel>
              <div className="space-y-1.5">
                {warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 rounded-lg border border-amber-500/10 bg-amber-500/5 px-3 py-2 text-xs text-amber-400">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    <span>{w.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          {notes && (
            <div className="rounded-lg border border-gray-800/50 bg-gray-900/30 px-3.5 py-2.5">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Notes</p>
              <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">{notes}</p>
            </div>
          )}

          {/* Raw plan expandable */}
          {rawPlan && (
            <details className="group cursor-pointer">
              <summary className="text-xs text-gray-600 hover:text-gray-400 transition">
                Show raw plan output
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-gray-800/50 bg-gray-900/50 p-3 text-xs text-gray-500 whitespace-pre-wrap font-mono">
                {rawPlan}
              </pre>
            </details>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-gray-800/50 px-6 py-4">
          <p className="text-xs text-gray-600">This action will generate the workflow YAML</p>
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
