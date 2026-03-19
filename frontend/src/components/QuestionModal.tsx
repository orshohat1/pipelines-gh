import { useState } from "react";
import { MessageCircleQuestion, Send } from "lucide-react";
import type { HumanQuestion } from "../types";

interface Props {
  question: HumanQuestion;
  onAnswer: (questionId: string, answer: string) => void;
}

export default function QuestionModal({ question, onAnswer }: Props) {
  const [answer, setAnswer] = useState("");
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);

  const submit = () => {
    const val = selectedChoice ?? answer;
    if (!val.trim()) return;
    onAnswer(question.question_id, val);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-lg rounded-2xl border border-gray-800 bg-gray-950 shadow-2xl animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-gray-800/50 px-6 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10">
            <MessageCircleQuestion size={18} className="text-indigo-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-100">Input Required</h2>
            <p className="text-xs text-gray-500">The migration agent needs your input</p>
          </div>
        </div>

        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-gray-300 leading-relaxed">{question.question}</p>

          {/* Choice buttons */}
          {question.choices && question.choices.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {question.choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setSelectedChoice(choice)}
                  className={`rounded-lg border px-3.5 py-2 text-sm transition ${
                    selectedChoice === choice
                      ? "border-indigo-500 bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/20"
                      : "border-gray-700/50 text-gray-400 hover:border-gray-600 hover:text-gray-300"
                  }`}
                >
                  {choice}
                </button>
              ))}
            </div>
          )}

          {/* Free-form input */}
          {question.allow_freeform && (
            <textarea
              className="w-full rounded-xl border border-gray-700/50 bg-gray-800/30 px-4 py-3 text-sm text-gray-100 placeholder-gray-600 focus:border-indigo-500 focus:outline-none resize-none transition"
              rows={3}
              placeholder="Type your answer..."
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
                setSelectedChoice(null);
              }}
            />
          )}
        </div>

        <div className="flex justify-end border-t border-gray-800/50 px-6 py-4">
          <button
            type="button"
            onClick={submit}
            disabled={!answer.trim() && !selectedChoice}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={14} />
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
