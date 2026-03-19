import { useState } from "react";
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg rounded-2xl border border-gray-800 bg-gray-900 p-6 space-y-4 shadow-2xl">
        <h2 className="text-base font-semibold text-gray-100">Question Required</h2>
        <p className="text-sm text-gray-300 leading-relaxed">{question.question}</p>

        {/* Choice buttons */}
        {question.choices && question.choices.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {question.choices.map((choice) => (
              <button
                key={choice}
                type="button"
                onClick={() => setSelectedChoice(choice)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                  selectedChoice === choice
                    ? "border-indigo-500 bg-indigo-500/20 text-indigo-300"
                    : "border-gray-700 text-gray-400 hover:border-gray-600"
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
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none resize-none"
            rows={3}
            placeholder="Type your answer..."
            value={answer}
            onChange={(e) => {
              setAnswer(e.target.value);
              setSelectedChoice(null);
            }}
          />
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={submit}
            disabled={!answer.trim() && !selectedChoice}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-500 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
