import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentActivity,
  GeneratedFile,
  HumanQuestion,
  PipelineFile,
  PlanApprovalRequest,
  ServerMessage,
  TemplateRequestMsg,
} from "../types";

interface UseWebSocketReturn {
  /** Per-file status map (file_id → PipelineFile). */
  files: Map<string, PipelineFile>;
  /** Currently pending HITL question, if any. */
  pendingQuestion: HumanQuestion | null;
  /** Currently pending plan approval request, if any. */
  pendingApproval: PlanApprovalRequest | null;
  /** Currently pending template request, if any. */
  pendingTemplateRequest: TemplateRequestMsg | null;
  /** Active agent activity map (agent_id → AgentActivity). */
  activeAgents: Map<string, AgentActivity>;
  /** Send an answer to a HITL question. */
  answerQuestion: (questionId: string, answer: string) => void;
  /** Send a plan approval response. */
  approvePlan: (fileId: string, approved: boolean, feedback?: string, revise?: boolean) => void;
  /** Submit template file contents. */
  submitTemplates: (fileId: string, templates: { path: string; content: string }[]) => void;
  /** Whether the WebSocket is connected. */
  connected: boolean;
}

export function useWebSocket(jobId: string | null): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [files, setFiles] = useState<Map<string, PipelineFile>>(new Map());
  const [pendingQuestion, setPendingQuestion] = useState<HumanQuestion | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PlanApprovalRequest | null>(null);
  const [pendingTemplateRequest, setPendingTemplateRequest] = useState<TemplateRequestMsg | null>(null);
  const [activeAgents, setActiveAgents] = useState<Map<string, AgentActivity>>(new Map());
  const agentTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const agentStartTimesRef = useRef<Map<string, number>>(new Map());
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${jobId}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data) as ServerMessage;
      } catch {
        return;
      }

      switch (msg.type) {
        case "stage_update":
          setFiles((prev) => {
            const next = new Map(prev);
            const existing = next.get(msg.file_id);
            const generatedFiles = msg.stage === "completed"
              ? (msg.data?.generated_files as GeneratedFile[] | undefined) ?? existing?.generatedFiles
              : existing?.generatedFiles;
            const updated: PipelineFile = {
              file_id: msg.file_id,
              filename: msg.filename,
              stage: msg.stage,
              message: msg.message,
              data: msg.data,
              validationData: msg.stage === "validated" ? msg.data : existing?.validationData,
              yaml: msg.stage === "completed" ? (msg.data?.yaml as string | undefined) ?? existing?.yaml : existing?.yaml,
              generatedFiles,
              warnings: msg.stage === "completed" ? (msg.data?.warnings as string[] | undefined) ?? existing?.warnings : existing?.warnings,
            };
            next.set(msg.file_id, updated);
            return next;
          });
          break;

        case "question":
          setPendingQuestion({
            file_id: msg.file_id,
            question_id: msg.question_id,
            question: msg.question,
            choices: msg.choices,
            allow_freeform: msg.allow_freeform,
          });
          break;

        case "plan_approval_request":
          setPendingApproval({
            file_id: msg.file_id,
            plan: msg.plan,
          });
          break;

        case "template_request":
          setPendingTemplateRequest({
            file_id: msg.file_id,
            templates: msg.templates,
          });
          break;

        case "agent_activity": {
          const activity: AgentActivity = {
            agent_id: msg.agent_id,
            agent_type: msg.agent_type,
            status: msg.status,
            file_id: msg.file_id,
            filename: msg.filename,
            detail: msg.detail,
            target_file: msg.target_file,
            timestamp: msg.timestamp || 0,
          };

          // Track start times for duration calculation
          if (activity.status === "running") {
            agentStartTimesRef.current.set(activity.agent_id, activity.timestamp || Date.now() / 1000);
            const existing = agentTimersRef.current.get(activity.agent_id);
            if (existing) {
              clearTimeout(existing);
              agentTimersRef.current.delete(activity.agent_id);
            }
          }

          // For completed/error, keep the original start timestamp so the card shows total duration
          if (activity.status !== "running") {
            const startTs = agentStartTimesRef.current.get(activity.agent_id);
            if (startTs) {
              activity.timestamp = startTs;
            }
          }

          setActiveAgents((prev) => {
            const next = new Map(prev);
            next.set(activity.agent_id, activity);
            return next;
          });

          // Auto-remove completed/error agents after a short delay
          if (activity.status === "completed" || activity.status === "error") {
            const existing = agentTimersRef.current.get(activity.agent_id);
            if (existing) clearTimeout(existing);
            const timer = setTimeout(() => {
              setActiveAgents((prev) => {
                const next = new Map(prev);
                next.delete(activity.agent_id);
                return next;
              });
              agentTimersRef.current.delete(activity.agent_id);
              agentStartTimesRef.current.delete(activity.agent_id);
            }, activity.status === "completed" ? 2000 : 3000);
            agentTimersRef.current.set(activity.agent_id, timer);
          }
          break;
        }
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setConnected(false);
      setActiveAgents(new Map());
      for (const timer of agentTimersRef.current.values()) {
        clearTimeout(timer);
      }
      agentTimersRef.current.clear();
      agentStartTimesRef.current.clear();
    };
  }, [jobId]);

  const answerQuestion = useCallback(
    (questionId: string, answer: string) => {
      wsRef.current?.send(
        JSON.stringify({ type: "answer", question_id: questionId, answer }),
      );
      setPendingQuestion(null);
    },
    [],
  );

  const approvePlan = useCallback(
    (fileId: string, approved: boolean, feedback = "", revise = false) => {
      wsRef.current?.send(
        JSON.stringify({ type: "plan_approval", file_id: fileId, approved, feedback, revise }),
      );
      setPendingApproval(null);
    },
    [],
  );

  const submitTemplates = useCallback(
    (fileId: string, templates: { path: string; content: string }[]) => {
      wsRef.current?.send(
        JSON.stringify({ type: "template_response", file_id: fileId, templates }),
      );
      setPendingTemplateRequest(null);
    },
    [],
  );

  return {
    files, pendingQuestion, pendingApproval, pendingTemplateRequest,
    activeAgents, connected, answerQuestion, approvePlan, submitTemplates,
  };
}
