import { useState } from "react";
import { Copy, Download, X, Check, FileCode } from "lucide-react";

interface Props {
  yaml: string;
  filename: string;
  onClose: () => void;
}

export default function YAMLOutput({ yaml, filename, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(yaml);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const download = () => {
    const blob = new Blob([yaml], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename.replace(/\.[^.]+$/, "") + ".github-actions.yml";
    a.click();
    URL.revokeObjectURL(url);
  };

  const lineCount = yaml.split("\n").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-gray-800 bg-gray-950 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
              <FileCode size={16} className="text-emerald-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">Generated Workflow</h2>
              <p className="text-xs text-gray-500">
                {filename} &middot; {lineCount} lines
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={copyToClipboard}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition ${
                copied
                  ? "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              onClick={download}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 hover:text-white transition"
            >
              <Download size={14} />
              Download
            </button>
            <div className="ml-1 h-4 w-px bg-gray-800" />
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* YAML content with line numbers */}
        <div className="flex-1 overflow-auto">
          <div className="flex min-h-full">
            {/* Line numbers */}
            <div className="sticky left-0 flex flex-col items-end border-r border-gray-800/50 bg-gray-950 px-3 py-5 text-xs leading-relaxed text-gray-700 font-mono select-none">
              {yaml.split("\n").map((_, i) => (
                <span key={i}>{i + 1}</span>
              ))}
            </div>
            {/* Code */}
            <pre className="flex-1 p-5 text-sm leading-relaxed text-emerald-300/90 font-mono whitespace-pre yaml-code">
              {yaml}
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-800/50 px-6 py-2.5 flex items-center justify-between">
          <p className="text-[10px] text-gray-600">
            Save to .github/workflows/ in your repository
          </p>
          <button
            type="button"
            onClick={download}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition active:scale-[0.98]"
          >
            Download .yml
          </button>
        </div>
      </div>
    </div>
  );
}
