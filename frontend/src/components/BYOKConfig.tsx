import { useState } from "react";
import type { BYOKConfig } from "../types";
import { ChevronDown, ChevronUp, Settings2 } from "lucide-react";

interface Props {
  config: BYOKConfig;
  onChange: (config: BYOKConfig) => void;
  disabled?: boolean;
}

export default function BYOKConfigPanel({ config, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);

  const update = (patch: Partial<BYOKConfig>) =>
    onChange({ ...config, ...patch });

  const inputClass =
    "mt-1 block w-full rounded-lg border border-gray-700/50 bg-gray-800/50 px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:border-indigo-500 focus:outline-none transition";

  return (
    <div className="rounded-2xl border border-gray-800/50 bg-gray-900/50">
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3.5 text-sm text-gray-400 hover:text-gray-200 transition"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex items-center gap-2.5">
          <Settings2 size={15} className="text-gray-500" />
          <span className="font-medium">Model Configuration</span>
          {config.api_key.trim() && (
            <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] text-indigo-400 ring-1 ring-indigo-500/20">
              BYOK
            </span>
          )}
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="border-t border-gray-800/30 px-5 pb-5 pt-3">
          <p className="mb-3 text-xs text-gray-600">
            Optional. Leave empty to use the default Copilot model.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">Provider</span>
              <select className={inputClass} value={config.provider_type} disabled={disabled} onChange={(e) => update({ provider_type: e.target.value })}>
                <option value="openai">OpenAI-compatible</option>
                <option value="azure">Azure OpenAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </label>

            <label className="block">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">Model</span>
              <input
                className={inputClass}
                value={config.model_name}
                disabled={disabled}
                placeholder="claude-sonnet-4.6"
                onChange={(e) => update({ model_name: e.target.value })}
              />
            </label>

            <label className="block sm:col-span-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">Base URL</span>
              <input
                className={inputClass}
                value={config.base_url}
                disabled={disabled}
                placeholder="https://api.openai.com/v1"
                onChange={(e) => update({ base_url: e.target.value })}
              />
            </label>

            <label className="block sm:col-span-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">API Key</span>
              <input
                type="password"
                className={inputClass}
                value={config.api_key}
                disabled={disabled}
                placeholder="sk-..."
                onChange={(e) => update({ api_key: e.target.value })}
              />
            </label>

            <label className="block">
              <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">Wire API</span>
              <select className={inputClass} value={config.wire_api} disabled={disabled} onChange={(e) => update({ wire_api: e.target.value })}>
                <option value="completions">completions</option>
                <option value="responses">responses</option>
              </select>
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
