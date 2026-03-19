import { useState } from "react";
import { ArrowRight, GitBranch, RefreshCw, Zap } from "lucide-react";
import BYOKConfigPanel from "./components/BYOKConfig";
import FileUpload from "./components/FileUpload";
import AgentActivityPanel from "./components/AgentActivityPanel";
import PipelineStatus from "./components/PipelineStatus";
import QuestionModal from "./components/QuestionModal";
import PlanApprovalModal from "./components/PlanApprovalModal";
import TemplateRequestModal from "./components/TemplateRequestModal";
import YAMLOutput from "./components/YAMLOutput";
import { useWebSocket } from "./hooks/useWebSocket";
import type { BYOKConfig, PipelineFile } from "./types";

const DEFAULT_BYOK: BYOKConfig = {
  provider_type: "openai",
  base_url: "",
  api_key: "",
  model_name: "claude-sonnet-4.6",
  wire_api: "completions",
};

export default function App() {
  const [byok, setBYOK] = useState<BYOKConfig>(DEFAULT_BYOK);
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [viewingYaml, setViewingYaml] = useState<PipelineFile | null>(null);

  const { files, pendingQuestion, pendingApproval, pendingTemplateRequest, activeAgents, connected, answerQuestion, approvePlan, submitTemplates } =
    useWebSocket(jobId);

  const handleUpload = async (selectedFiles: File[]) => {
    setUploading(true);
    try {
      const formData = new FormData();
      for (const f of selectedFiles) {
        formData.append("files", f);
      }
      if (byok.api_key.trim()) {
        formData.append("byok_json", JSON.stringify(byok));
      }

      const res = await fetch("/api/migrate", { method: "POST", body: formData });
      if (!res.ok) {
        throw new Error(`Upload failed: ${res.status}`);
      }
      const data = (await res.json()) as { job_id: string; file_count: number };
      setJobId(data.job_id);
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleTextSubmit = async (content: string, filename: string) => {
    setUploading(true);
    try {
      const body: Record<string, unknown> = { content, filename };
      if (byok.api_key.trim()) {
        body.byok = byok;
      }
      const res = await fetch("/api/migrate-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`Submit failed: ${res.status}`);
      }
      const data = (await res.json()) as { job_id: string; file_count: number };
      setJobId(data.job_id);
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setUploading(false);
    }
  };

  const fileList = Array.from(files.values());
  const allDone = fileList.length > 0 && fileList.every((f) => f.stage === "completed" || f.stage === "error");
  const completedCount = fileList.filter((f) => f.stage === "completed").length;
  const errorCount = fileList.filter((f) => f.stage === "error").length;

  return (
    <div className="min-h-screen bg-gray-950 relative">
      {/* Background gradient decoration */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-indigo-600/10 blur-[100px]" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-violet-600/10 blur-[100px]" />
      </div>

      <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        {/* Header */}
        <header className="mb-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/20 ring-1 ring-indigo-500/30">
                <GitBranch size={20} className="text-indigo-400" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-white">
                  Pipeline Migrator
                </h1>
                <p className="text-xs text-gray-500">
                  Powered by GitHub Copilot SDK
                </p>
              </div>
            </div>

            {jobId && (
              <div className="flex items-center gap-3">
                {connected ? (
                  <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400 ring-1 ring-emerald-500/20">
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                    </span>
                    Connected
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-500 ring-1 ring-gray-700">
                    <span className="h-2 w-2 rounded-full bg-gray-600" />
                    Disconnected
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Platform badges */}
          {!jobId && (
            <div className="mt-6 flex flex-wrap items-center gap-2">
              <span className="text-xs text-gray-500">Supports:</span>
              {["Azure DevOps", "Jenkins", "GitLab CI"].map((p) => (
                <span
                  key={p}
                  className="rounded-full bg-gray-900 px-3 py-1 text-xs text-gray-400 ring-1 ring-gray-800"
                >
                  {p}
                </span>
              ))}
              <ArrowRight size={14} className="text-gray-600" />
              <span className="rounded-full bg-indigo-600/10 px-3 py-1 text-xs font-medium text-indigo-400 ring-1 ring-indigo-500/20">
                GitHub Actions
              </span>
            </div>
          )}
        </header>

        {/* Features bar (before job) */}
        {!jobId && (
          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              { icon: Zap, label: "AI-Powered", desc: "Multi-agent pipeline analysis" },
              { icon: GitBranch, label: "Security-First", desc: "OIDC, pinned actions, least privilege" },
              { icon: RefreshCw, label: "Eval Loop", desc: "Iterative quality improvement" },
            ].map(({ icon: Icon, label, desc }) => (
              <div
                key={label}
                className="flex items-start gap-3 rounded-xl border border-gray-800/50 bg-gray-900/50 p-4"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800">
                  <Icon size={16} className="text-indigo-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-200">{label}</p>
                  <p className="text-xs text-gray-500">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Config + Upload (only before job starts) */}
        {!jobId && (
          <section className="space-y-4 animate-fade-in-up">
            <BYOKConfigPanel config={byok} onChange={setBYOK} disabled={uploading} />
            <FileUpload onUpload={handleUpload} onSubmitText={handleTextSubmit} disabled={uploading} />
          </section>
        )}

        {/* Job status */}
        {jobId && (
          <section className="space-y-4 animate-fade-in-up">
            {/* Summary bar */}
            {fileList.length > 0 && (
              <div className="flex items-center justify-between rounded-xl border border-gray-800/50 bg-gray-900/50 px-5 py-3">
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-gray-500">
                    {fileList.length} file{fileList.length !== 1 ? "s" : ""}
                  </span>
                  {completedCount > 0 && (
                    <span className="text-emerald-400">{completedCount} completed</span>
                  )}
                  {errorCount > 0 && (
                    <span className="text-red-400">{errorCount} failed</span>
                  )}
                  {!allDone && fileList.length > 0 && (
                    <span className="text-indigo-400 animate-pulse">Processing...</span>
                  )}
                </div>
              </div>
            )}

            {fileList.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 space-y-3">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-indigo-500" />
                <p className="text-sm text-gray-500">Initializing migration...</p>
              </div>
            )}

            {/* Agent activity visualization */}
            <AgentActivityPanel agents={activeAgents} />

            <div className="space-y-3">
              {fileList.map((f) => (
                <PipelineStatus
                  key={f.file_id}
                  file={f}
                  onViewYaml={() => setViewingYaml(f)}
                />
              ))}
            </div>

            {/* New migration button (when all done) */}
            {allDone && (
              <button
                type="button"
                className="group flex w-full items-center justify-center gap-2 rounded-xl border border-gray-700/50 bg-gray-900/50 py-3 text-sm text-gray-400 transition hover:border-indigo-500/30 hover:text-indigo-400"
                onClick={() => {
                  setJobId(null);
                  setViewingYaml(null);
                }}
              >
                <RefreshCw size={14} className="transition group-hover:rotate-180 duration-500" />
                Start new migration
              </button>
            )}
          </section>
        )}

        {/* Modals */}
        {pendingQuestion && (
          <QuestionModal question={pendingQuestion} onAnswer={answerQuestion} />
        )}

        {pendingApproval && (
          <PlanApprovalModal approval={pendingApproval} onApprove={approvePlan} />
        )}

        {pendingTemplateRequest && (
          <TemplateRequestModal
            request={pendingTemplateRequest}
            onSubmit={submitTemplates}
            onSkip={(fileId) => submitTemplates(fileId, [])}
          />
        )}

        {viewingYaml?.yaml && (
          <YAMLOutput
            yaml={viewingYaml.yaml}
            filename={viewingYaml.filename}
            onClose={() => setViewingYaml(null)}
            files={viewingYaml.generatedFiles}
          />
        )}

        {/* Footer */}
        <footer className="mt-auto pt-8 pb-4 text-center">
          <p className="text-xs text-gray-700">
            Built with GitHub Copilot SDK &middot; Security-first migration
          </p>
        </footer>
      </div>
    </div>
  );
}
