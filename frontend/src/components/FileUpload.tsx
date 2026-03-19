import { useCallback, useRef, useState } from "react";
import { Upload, X } from "lucide-react";

interface Props {
  onUpload: (files: File[]) => void;
  disabled?: boolean;
}

export default function FileUpload({ onUpload, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
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

  const submit = () => {
    if (selectedFiles.length === 0) return;
    onUpload(selectedFiles);
  };

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 transition cursor-pointer ${
          dragOver
            ? "border-indigo-500 bg-indigo-500/10"
            : "border-gray-700 bg-gray-900 hover:border-gray-600"
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
        <Upload className="mb-2 text-gray-500" size={32} />
        <p className="text-sm text-gray-400">
          Drag &amp; drop pipeline files here, or{" "}
          <span className="text-indigo-400 underline">browse</span>
        </p>
        <p className="mt-1 text-xs text-gray-600">
          Supports Azure DevOps YAML, Jenkinsfile, GitLab CI YAML
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
        <ul className="space-y-1">
          {selectedFiles.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between rounded-lg bg-gray-900 px-3 py-2 text-sm text-gray-300"
            >
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="ml-2 text-gray-500 hover:text-red-400 transition"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Submit */}
      <button
        type="button"
        onClick={submit}
        disabled={disabled || selectedFiles.length === 0}
        className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Migrate {selectedFiles.length > 0 ? `${selectedFiles.length} file${selectedFiles.length > 1 ? "s" : ""}` : ""}
      </button>
    </div>
  );
}
