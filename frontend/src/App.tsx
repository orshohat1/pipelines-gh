import { useState } from "react";
import BYOKConfigPanel from "./components/BYOKConfig";
import FileUpload from "./components/FileUpload";
import PipelineStatus from "./components/PipelineStatus";
import QuestionModal from "./components/QuestionModal";
import PlanApprovalModal from "./components/PlanApprovalModal";
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

  const { files, pendingQuestion, pendingApproval, connected, answerQuestion, approvePlan } =
    useWebSocket(jobId);

  const handleUpload = async (selectedFiles: File[]) => {
    setUploading(true);
    try {
      const formData = new FormData();
      for (const f of selectedFiles) {
        formData.append("files", f);
      }
      // Only send BYOK if user provided an API key
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

  const fileList = Array.from(files.values());

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-4 py-8">
      {/* Header */}
      <header className="text-center space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Pipeline Migration
        </h1>
        <p className="text-sm text-gray-400">
          Convert Azure DevOps, Jenkins &amp; GitLab CI pipelines to GitHub Actions
        </p>
      </header>

      {/* Config + Upload (only before job starts) */}
      {!jobId && (
        <section className="space-y-4">
          <BYOKConfigPanel config={byok} onChange={setBYOK} disabled={uploading} />
          <FileUpload onUpload={handleUpload} disabled={uploading} />
        </section>
      )}

      {/* Job status */}
      {jobId && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-300">
              Migration Progress
            </h2>
            {connected && (
              <span className="flex items-center gap-1 text-xs text-green-400">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-400" />
                Live
              </span>
            )}
          </div>

          {fileList.length === 0 && (
            <p className="text-sm text-gray-500 animate-pulse">Waiting for updates...</p>
          )}

          {fileList.map((f) => (
            <PipelineStatus
              key={f.file_id}
              file={f}
              onViewYaml={() => setViewingYaml(f)}
            />
          ))}

          {/* New migration button (when all done) */}
          {fileList.length > 0 &&
            fileList.every((f) => f.stage === "completed" || f.stage === "error") && (
              <button
                type="button"
                className="w-full rounded-lg border border-gray-700 py-2 text-sm text-gray-400 hover:border-gray-600 hover:text-gray-200 transition"
                onClick={() => {
                  setJobId(null);
                  setViewingYaml(null);
                }}
              >
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

      {viewingYaml?.yaml && (
        <YAMLOutput
          yaml={viewingYaml.yaml}
          filename={viewingYaml.filename}
          onClose={() => setViewingYaml(null)}
        />
      )}
    </div>
  );
}
