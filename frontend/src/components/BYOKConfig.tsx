import { useState } from "react";
import type { BYOKConfig } from "../types";
import { ChevronDown, ChevronUp, Key } from "lucide-react";

interface Props {
  config: BYOKConfig;
  onChange: (config: BYOKConfig) => void;
  disabled?: boolean;
}

export default function BYOKConfigPanel({ config, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);

  const update = (patch: Partial<BYOKConfig>) =>
    onChange({ ...config, ...patch });

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-300 hover:text-white transition"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex items-center gap-2">
          <Key size={16} />
          BYOK Model Configuration
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {open && (
        <div className="grid grid-cols-1 gap-3 px-4 pb-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-xs text-gray-400">Provider type</span>
            <select
              className="mt-1 block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none"
              value={config.provider_type}
              disabled={disabled}
              onChange={(e) => update({ provider_type: e.target.value })}
            >
              <option value="openai">OpenAI-compatible</option>
              <option value="azure">Azure OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Model name</span>
            <input
              className="mt-1 block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              value={config.model_name}
              disabled={disabled}
              placeholder="claude-sonnet-4.6"
              onChange={(e) => update({ model_name: e.target.value })}
            />
          </label>

          <label className="block sm:col-span-2">
            <span className="text-xs text-gray-400">Base URL</span>
            <input
              className="mt-1 block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              value={config.base_url}
              disabled={disabled}
              placeholder="https://api.openai.com/v1"
              onChange={(e) => update({ base_url: e.target.value })}
            />
          </label>

          <label className="block sm:col-span-2">
            <span className="text-xs text-gray-400">API key</span>
            <input
              type="password"
              className="mt-1 block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              value={config.api_key}
              disabled={disabled}
              placeholder="sk-..."
              onChange={(e) => update({ api_key: e.target.value })}
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Wire API</span>
            <select
              className="mt-1 block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none"
              value={config.wire_api}
              disabled={disabled}
              onChange={(e) => update({ wire_api: e.target.value })}
            >
              <option value="completions">completions</option>
              <option value="responses">responses</option>
            </select>
          </label>
        </div>
      )}
    </div>
  );
}
