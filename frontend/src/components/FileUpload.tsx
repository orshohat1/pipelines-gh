import { useCallback, useRef, useState } from "react";
import { Upload, X, Type, FileCode, ArrowRight, Loader2 } from "lucide-react";

type Mode = "file" | "text";

interface Props {
  onUpload: (files: File[]) => void;
  onSubmitText: (content: string, filename: string) => void;
  disabled?: boolean;
}

export default function FileUpload({ onUpload, onSubmitText, disabled }: Props) {
  const [mode, setMode] = useState<Mode>("file");
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("pipeline.yml");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return;
      const arr = Array.from(fileList);
      setSelectedFiles((prev) => [...prev, ...arr]);
    },
    [],
  );

  const removeFile = (index: number) =>
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));

  const submitFiles = () => {
    if (selectedFiles.length === 0) return;
    onUpload(selectedFiles);
  };

  const submitText = () => {
    if (!text.trim()) return;
    onSubmitText(text, filename);
  };

  const lineCount = text.split("\n").length;

  return (
    <div className="rounded-2xl border border-gray-800/50 bg-gray-900/50 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-200">Pipeline Source</h2>
        {/* Mode toggle */}
        <div className="flex rounded-lg bg-gray-800/50 p-0.5 text-xs">
          <button
            type="button"
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              mode === "file"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
            onClick={() => setMode("file")}
          >
            <Upload size={12} /> Upload
          </button>
          <button
            type="button"
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              mode === "text"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
            onClick={() => setMode("text")}
          >
            <Type size={12} /> Paste
          </button>
        </div>
      </div>

      {mode === "file" && (
        <div className="space-y-3">
          {/* Drop zone */}
          <div
            className={`group relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-all cursor-pointer ${
              dragOver
                ? "border-indigo-500 bg-indigo-500/10 scale-[1.01]"
                : "border-gray-700/50 hover:border-gray-600 hover:bg-gray-800/30"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              handleFiles(e.dataTransfer.files);
            }}
          >
            <div className={`mb-3 flex h-12 w-12 items-center justify-center rounded-xl transition ${
              dragOver ? "bg-indigo-500/20" : "bg-gray-800 group-hover:bg-gray-700"
            }`}>
              <Upload className={`transition ${dragOver ? "text-indigo-400" : "text-gray-500 group-hover:text-gray-400"}`} size={22} />
            </div>
            <p className="text-sm text-gray-300">
              Drop pipeline files here, or{" "}
              <span className="text-indigo-400 font-medium">browse</span>
            </p>
            <p className="mt-1.5 text-xs text-gray-600">
              .yml &middot; .yaml &middot; Jenkinsfile &middot; .groovy
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              accept=".yml,.yaml,.groovy,Jenkinsfile"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>

          {/* File list */}
          {selectedFiles.length > 0 && (
            <ul className="space-y-1.5">
              {selectedFiles.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="group/file flex items-center gap-3 rounded-lg border border-gray-800/50 bg-gray-800/30 px-3.5 py-2.5 text-sm"
                >
                  <FileCode size={16} className="shrink-0 text-indigo-400/70" />
                  <span className="flex-1 truncate text-gray-300">{f.name}</span>
                  <span className="text-xs text-gray-600">{(f.size / 1024).toFixed(1)}KB</span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                    className="opacity-0 group-hover/file:opacity-100 text-gray-500 hover:text-red-400 transition"
                  >
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Submit files */}
          <button
            type="button"
            onClick={submitFiles}
            disabled={disabled || selectedFiles.length === 0}
            className="group flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {disabled ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <>
                Migrate {selectedFiles.length > 0 ? `${selectedFiles.length} file${selectedFiles.length > 1 ? "s" : ""}` : ""}
                <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
              </>
            )}
          </button>
        </div>
      )}

      {mode === "text" && (
        <div className="space-y-3">
          {/* Filename input */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <FileCode size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                className="w-full rounded-lg border border-gray-700/50 bg-gray-800/50 pl-9 pr-3 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none transition"
                placeholder="Filename (e.g. azure-pipelines.yml)"
                value={filename}
                disabled={disabled}
                onChange={(e) => setFilename(e.target.value)}
              />
            </div>
          </div>

          {/* Text area with line numbers feel */}
          <div className="relative">
            <textarea
              className="w-full rounded-xl border border-gray-700/50 bg-gray-800/30 px-4 py-3.5 text-sm text-gray-100 font-mono leading-relaxed placeholder-gray-600 focus:border-indigo-500 focus:outline-none resize-none yaml-code transition"
              rows={14}
              placeholder={"Paste your pipeline content here..."}
              value={text}
              disabled={disabled}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
            />
            {text && (
              <span className="absolute bottom-3 right-3 text-[10px] text-gray-600">
                {lineCount} lines
              </span>
            )}
          </div>

          {/* Submit text */}
          <button
            type="button"
            onClick={submitText}
            disabled={disabled || !text.trim()}
            className="group flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {disabled ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <>
                Migrate Pipeline
                <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
