import { useCallback, useEffect, useRef, useState } from "react";
import type {
  HumanQuestion,
  PipelineFile,
  PlanApprovalRequest,
  ServerMessage,
} from "../types";

interface UseWebSocketReturn {
  /** Per-file status map (file_id → PipelineFile). */
  files: Map<string, PipelineFile>;
  /** Currently pending HITL question, if any. */
  pendingQuestion: HumanQuestion | null;
  /** Currently pending plan approval request, if any. */
  pendingApproval: PlanApprovalRequest | null;
  /** Send an answer to a HITL question. */
  answerQuestion: (questionId: string, answer: string) => void;
  /** Send a plan approval response. */
  approvePlan: (fileId: string, approved: boolean, feedback?: string) => void;
  /** Whether the WebSocket is connected. */
  connected: boolean;
}

export function useWebSocket(jobId: string | null): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [files, setFiles] = useState<Map<string, PipelineFile>>(new Map());
  const [pendingQuestion, setPendingQuestion] = useState<HumanQuestion | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PlanApprovalRequest | null>(null);
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
            const updated: PipelineFile = {
              file_id: msg.file_id,
              filename: msg.filename,
              stage: msg.stage,
              message: msg.message,
              data: msg.data,
              yaml: msg.stage === "completed" ? (msg.data?.yaml as string | undefined) ?? existing?.yaml : existing?.yaml,
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
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setConnected(false);
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
    (fileId: string, approved: boolean, feedback = "") => {
      wsRef.current?.send(
        JSON.stringify({ type: "plan_approval", file_id: fileId, approved, feedback }),
      );
      setPendingApproval(null);
    },
    [],
  );

  return { files, pendingQuestion, pendingApproval, connected, answerQuestion, approvePlan };
}
