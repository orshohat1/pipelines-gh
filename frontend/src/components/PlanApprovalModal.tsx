import type { PlanApprovalRequest } from "../types";

interface Props {
  approval: PlanApprovalRequest;
  onApprove: (fileId: string, approved: boolean, feedback?: string) => void;
}

export default function PlanApprovalModal({ approval, onApprove }: Props) {
  const plan = approval.plan;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl border border-amber-800/50 bg-gray-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-gray-800 px-5 py-3">
          <span className="text-amber-400 text-lg">⚠</span>
          <h2 className="text-sm font-semibold text-gray-100">
            Approve Migration Plan
          </h2>
        </div>

        {/* Plan details */}
        <div className="flex-1 overflow-auto px-5 py-4 space-y-3 text-sm">
          {plan.workflow_name && (
            <div>
              <span className="text-gray-400">Workflow: </span>
              <span className="text-gray-100">{plan.workflow_name as string}</span>
            </div>
          )}

          {plan.workflow_type && (
            <div>
              <span className="text-gray-400">Type: </span>
              <span className="text-gray-100 capitalize">{plan.workflow_type as string}</span>
            </div>
          )}

          {Array.isArray(plan.triggers) && plan.triggers.length > 0 && (
            <div>
              <span className="text-gray-400">Triggers: </span>
              <span className="text-gray-100">{(plan.triggers as string[]).join(", ")}</span>
            </div>
          )}

          {Array.isArray(plan.jobs) && plan.jobs.length > 0 && (
            <div>
              <p className="text-gray-400 mb-1">Jobs:</p>
              <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                {(plan.jobs as Record<string, unknown>[]).map((job, i) => (
                  <li key={i}>{(job.name as string) || (job.id as string) || `Job ${i + 1}`}</li>
                ))}
              </ul>
            </div>
          )}

          {Array.isArray(plan.secrets_required) && plan.secrets_required.length > 0 && (
            <div>
              <p className="text-gray-400 mb-1">Secrets Required:</p>
              <ul className="list-disc list-inside text-amber-300 space-y-0.5">
                {(plan.secrets_required as { name: string; description: string }[]).map((s, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs">{s.name}</span> — {s.description}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Array.isArray(plan.warnings) && plan.warnings.length > 0 && (
            <div>
              <p className="text-gray-400 mb-1">Warnings:</p>
              {(plan.warnings as { severity: string; message: string }[]).map((w, i) => (
                <p key={i} className="text-amber-400 text-xs">
                  [{w.severity}] {w.message}
                </p>
              ))}
            </div>
          )}

          {plan.notes && (
            <div>
              <p className="text-gray-400 mb-1">Notes:</p>
              <p className="text-gray-300 text-xs whitespace-pre-wrap">{plan.notes as string}</p>
            </div>
          )}

          {plan.raw_plan && (
            <details className="cursor-pointer">
              <summary className="text-xs text-gray-500 hover:text-gray-400">
                Full plan text
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-gray-800 p-3 text-xs text-gray-400 whitespace-pre-wrap">
                {plan.raw_plan as string}
              </pre>
            </details>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-800 px-5 py-3">
          <button
            type="button"
            onClick={() => onApprove(approval.file_id, false, "Plan rejected by user")}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:border-red-500 hover:text-red-400 transition"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onApprove(approval.file_id, true)}
            className="rounded-lg bg-green-600 px-5 py-2 text-sm font-semibold text-white hover:bg-green-500 transition"
          >
            Approve &amp; Generate
          </button>
        </div>
      </div>
    </div>
  );
}
