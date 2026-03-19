import { useState, useRef } from "react";
import { Upload, FileCode, X, ArrowRight } from "lucide-react";
import type { TemplateRequestMsg } from "../types";

interface Props {
  request: TemplateRequestMsg;
  onSubmit: (fileId: string, templates: { path: string; content: string }[]) => void;
  onSkip: (fileId: string) => void;
}

export default function TemplateRequestModal({ request, onSubmit, onSkip }: Props) {
  const [contents, setContents] = useState<Record<string, string>>({});
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const updateContent = (path: string, content: string) => {
    setContents((prev) => ({ ...prev, [path]: content }));
  };

  const handleFileUpload = (path: string, file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      updateContent(path, text);
    };
    reader.readAsText(file);
  };

  const providedCount = Object.values(contents).filter((v) => v?.trim()).length;

  const handleSubmit = () => {
    const result = request.templates
      .filter((t) => contents[t.path]?.trim())
      .map((t) => ({ path: t.path, content: contents[t.path]! }));
    onSubmit(request.file_id, result);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border border-gray-800 bg-gray-950 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/10">
              <FileCode size={18} className="text-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">Template Files Required</h2>
              <p className="text-xs text-gray-500">
                {request.templates.length} template{request.templates.length !== 1 ? "s" : ""} referenced
              </p>
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="px-6 pt-4">
          <p className="text-sm text-gray-400 leading-relaxed">
            This pipeline references template files. Provide their contents for a complete migration,
            or skip to proceed with best-effort migration.
          </p>
        </div>

        {/* Template list */}
        <div className="flex-1 overflow-auto px-6 py-4 space-y-4">
          {request.templates.map((t) => (
            <div key={t.path} className="rounded-lg border border-gray-800/50 bg-gray-900/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileCode size={14} className="text-indigo-400" />
                  <code className="text-sm text-gray-300 font-mono">{t.path}</code>
                </div>
                {contents[t.path]?.trim() ? (
                  <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                    Provided
                  </span>
                ) : t.required ? (
                  <span className="text-[10px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
                    Required
                  </span>
                ) : (
                  <span className="text-[10px] text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">
                    Optional
                  </span>
                )}
              </div>
              <textarea
                value={contents[t.path] || ""}
                onChange={(e) => updateContent(t.path, e.target.value)}
                placeholder="Paste template file content here..."
                className="w-full rounded-lg border border-gray-700/50 bg-gray-900/50 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 font-mono focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 resize-none"
                rows={4}
              />
              <div className="flex items-center gap-2">
                <input
                  type="file"
                  accept=".yml,.yaml,.groovy,*"
                  className="hidden"
                  ref={(el) => { fileInputRefs.current[t.path] = el; }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(t.path, file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRefs.current[t.path]?.click()}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 hover:text-white transition ring-1 ring-gray-700/50"
                >
                  <Upload size={12} />
                  Upload file
                </button>
                {contents[t.path]?.trim() && (
                  <button
                    type="button"
                    onClick={() => updateContent(t.path, "")}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-400 transition"
                  >
                    <X size={12} />
                    Clear
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-800/50 px-6 py-4">
          <button
            type="button"
            onClick={() => onSkip(request.file_id)}
            className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-gray-300 transition"
          >
            Skip — migrate without templates
          </button>
          <button
            type="button"
            disabled={providedCount === 0}
            onClick={handleSubmit}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Continue with {providedCount} template{providedCount !== 1 ? "s" : ""}
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
