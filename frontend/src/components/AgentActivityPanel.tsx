import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Clock,
  Code2,
  Combine,
  Eye,
  GitMerge,
  Layers,
  ClipboardList,
  Loader2,
  Search,
  ShieldCheck,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { AgentActivity } from "../types";

const AGENT_CONFIG: Record<
  string,
  { icon: LucideIcon; label: string; color: string; bg: string; border: string; dot: string }
> = {
  validator: {
    icon: Search,
    label: "Validator",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/25",
    dot: "bg-blue-400",
  },
  planner: {
    icon: ClipboardList,
    label: "Planner",
    color: "text-purple-400",
    bg: "bg-purple-500/10",
    border: "border-purple-500/25",
    dot: "bg-purple-400",
  },
  generator: {
    icon: Code2,
    label: "Generator",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/25",
    dot: "bg-emerald-400",
  },
  "job-gen": {
    icon: Combine,
    label: "Job Agent",
    color: "text-teal-400",
    bg: "bg-teal-500/10",
    border: "border-teal-500/25",
    dot: "bg-teal-400",
  },
  assembler: {
    icon: Layers,
    label: "Assembler",
    color: "text-violet-400",
    bg: "bg-violet-500/10",
    border: "border-violet-500/25",
    dot: "bg-violet-400",
  },
  evaluator: {
    icon: Eye,
    label: "Evaluator",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/25",
    dot: "bg-amber-400",
  },
  actionlint: {
    icon: ShieldCheck,
    label: "Actionlint",
    color: "text-orange-400",
    bg: "bg-orange-500/10",
    border: "border-orange-500/25",
    dot: "bg-orange-400",
  },
  refiner: {
    icon: Wrench,
    label: "Refiner",
    color: "text-cyan-400",
    bg: "bg-cyan-500/10",
    border: "border-cyan-500/25",
    dot: "bg-cyan-400",
  },
  merge: {
    icon: GitMerge,
    label: "Merge",
    color: "text-pink-400",
    bg: "bg-pink-500/10",
    border: "border-pink-500/25",
    dot: "bg-pink-400",
  },
};

const DEFAULT_CONFIG = AGENT_CONFIG.validator!;

function getConfig(agentType: string) {
  return AGENT_CONFIG[agentType] ?? DEFAULT_CONFIG;
}

function formatElapsed(seconds: number): string {
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m${secs.toString().padStart(2, "0")}s`;
}

function AgentCard({ agent, index }: { agent: AgentActivity; index: number }) {
  const config = getConfig(agent.agent_type);
  const Icon = config.icon;
  const isRunning = agent.status === "running";
  const isCompleted = agent.status === "completed";
  const isError = agent.status === "error";

  // Live elapsed-time counter for running agents
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isRunning && agent.timestamp > 0) {
      const tick = () => setElapsed((Date.now() / 1000) - agent.timestamp);
      tick();
      timerRef.current = setInterval(tick, 250);
      return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }
    // For completed/error, show final snapshot
    if (!isRunning && agent.timestamp > 0) {
      setElapsed((Date.now() / 1000) - agent.timestamp);
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    }
  }, [isRunning, agent.timestamp]);

  return (
    <div
      className={`
        flex items-center gap-2.5 rounded-lg border px-3 py-2 transition-all duration-300
        ${isRunning ? `${config.bg} ${config.border}` : ""}
        ${isCompleted ? "border-emerald-500/20 bg-emerald-500/5 opacity-60" : ""}
        ${isError ? "border-red-500/20 bg-red-500/5" : ""}
        agent-card-enter
      `}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Icon with status indicator */}
      <div className="relative flex-shrink-0">
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
            isRunning ? config.bg : isCompleted ? "bg-emerald-500/10" : "bg-red-500/10"
          }`}
        >
          {isCompleted ? (
            <CheckCircle2 size={14} className="text-emerald-400" />
          ) : (
            <Icon
              size={14}
              className={`${isRunning ? config.color : "text-red-400"} ${isRunning ? "animate-pulse" : ""}`}
            />
          )}
        </div>
        {isRunning && (
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
            <span
              className={`absolute inline-flex h-full w-full animate-ping rounded-full ${config.dot} opacity-75`}
            />
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${config.dot}`} />
          </span>
        )}
      </div>

      {/* Text content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span
            className={`text-xs font-medium ${
              isRunning ? config.color : isCompleted ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {config.label}
          </span>
          {agent.target_file && (
            <span className="truncate text-[10px] text-gray-500">· {agent.target_file}</span>
          )}
        </div>
        {agent.detail && (
          <p className="mt-0.5 truncate text-[10px] leading-tight text-gray-500">{agent.detail}</p>
        )}
      </div>

      {/* Elapsed time + spinning indicator */}
      <div className="flex flex-shrink-0 items-center gap-1.5">
        {agent.timestamp > 0 && (
          <span className={`flex items-center gap-0.5 text-[10px] font-mono tabular-nums ${
            isRunning ? "text-gray-400" : "text-gray-600"
          }`}>
            <Clock size={9} className="opacity-50" />
            {formatElapsed(elapsed)}
          </span>
        )}
        {isRunning && (
          <Loader2 size={12} className={`animate-spin ${config.color} opacity-50`} />
        )}
      </div>
    </div>
  );
}

interface Props {
  agents: Map<string, AgentActivity>;
}

export default function AgentActivityPanel({ agents }: Props) {
  const agentList = Array.from(agents.values());
  const activeCount = agentList.filter((a) => a.status === "running").length;
  const [peakConcurrent, setPeakConcurrent] = useState(0);

  useEffect(() => {
    if (activeCount > peakConcurrent) {
      setPeakConcurrent(activeCount);
    }
  }, [activeCount, peakConcurrent]);

  if (agentList.length === 0) return null;

  return (
    <div className="animate-fade-in-up overflow-hidden rounded-xl border border-gray-800/50 bg-gray-900/50 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500/15">
            <Zap size={12} className="text-indigo-400" />
          </div>
          <span className="text-xs font-medium text-gray-300">Live Agents</span>
          {activeCount > 0 && (
            <span className="flex items-center gap-1.5 rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-mono text-indigo-400 ring-1 ring-indigo-500/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-indigo-400" />
              </span>
              {activeCount} active
            </span>
          )}
        </div>
        {peakConcurrent > 1 && (
          <span className="text-[10px] text-gray-600">
            Peak: {peakConcurrent} parallel
          </span>
        )}
      </div>

      {/* Agent cards grid */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {agentList.map((agent, idx) => (
          <AgentCard key={agent.agent_id} agent={agent} index={idx} />
        ))}
      </div>
    </div>
  );
}
