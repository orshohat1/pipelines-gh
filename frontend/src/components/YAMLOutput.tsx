import { Copy, Download, X } from "lucide-react";

interface Props {
  yaml: string;
  filename: string;
  onClose: () => void;
}

export default function YAMLOutput({ yaml, filename, onClose }: Props) {
  const copyToClipboard = () => navigator.clipboard.writeText(yaml);

  const download = () => {
    const blob = new Blob([yaml], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename.replace(/\.[^.]+$/, "") + ".github-actions.yml";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800 px-5 py-3">
          <h2 className="text-sm font-semibold text-gray-100">{filename} — Generated YAML</h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={copyToClipboard}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-white transition"
              title="Copy"
            >
              <Copy size={16} />
            </button>
            <button
              type="button"
              onClick={download}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-white transition"
              title="Download"
            >
              <Download size={16} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-white transition"
              title="Close"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* YAML content */}
        <pre className="flex-1 overflow-auto p-5 text-sm leading-relaxed text-green-300 font-mono whitespace-pre">
          {yaml}
        </pre>
      </div>
    </div>
  );
}
