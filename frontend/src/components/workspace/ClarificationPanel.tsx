"use client";

import { useState } from "react";
import { ClarificationQuestion, ClarificationAnswers } from "@/types/clinical";

interface Props {
  questions: ClarificationQuestion[];
  onSubmit:  (answers: ClarificationAnswers) => void;
  onSkip:    () => void;
  className?: string;
}

const PRIORITY_CONFIG = {
  critical:  { badge: "bg-red-900/40 border-red-700/40 text-red-300",    dot: "bg-red-400" },
  important: { badge: "bg-amber-900/40 border-amber-700/40 text-amber-300", dot: "bg-amber-400" },
  optional:  { badge: "bg-slate-800 border-slate-700 text-slate-400",     dot: "bg-slate-500" },
};

const CATEGORY_ICONS: Record<string, string> = {
  demographics:    "👤",
  vitals:          "❤️",
  chief_complaint: "🩺",
  symptoms:        "📋",
  history:         "📁",
  medications:     "💊",
  allergies:       "⚠️",
  labs:            "🧪",
  imaging:         "🩻",
  timeline:        "⏱",
};

export default function ClarificationPanel({ questions, onSubmit, onSkip, className = "" }: Props) {
  const [answers, setAnswers] = useState<ClarificationAnswers>({});
  const [submitted, setSubmitted] = useState(false);

  const criticalQuestions  = questions.filter(q => q.priority === "critical");
  const importantQuestions = questions.filter(q => q.priority === "important");
  const optionalQuestions  = questions.filter(q => q.priority === "optional");

  const criticalAnswered = criticalQuestions.every(q => answers[q.question_id]?.trim());
  const canSubmit = criticalAnswered;

  const handleSubmit = () => {
    if (!canSubmit) return;
    setSubmitted(true);
    onSubmit(answers);
  };

  const renderQuestion = (q: ClarificationQuestion) => {
    const config = PRIORITY_CONFIG[q.priority as keyof typeof PRIORITY_CONFIG] ?? PRIORITY_CONFIG.optional;
    const icon   = CATEGORY_ICONS[q.category] ?? "📌";
    const answer = answers[q.question_id] ?? "";

    return (
      <div key={q.question_id} className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 space-y-2">
        {/* Question header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-base">{icon}</span>
            <p className="text-[11px] font-medium text-slate-200 leading-snug">{q.question_text}</p>
          </div>
          <span className={`shrink-0 text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${config.badge}`}>
            {q.priority}
          </span>
        </div>

        {/* Hint */}
        {q.hint && (
          <p className="text-[10px] text-slate-600 italic">{q.hint}</p>
        )}

        {/* Input */}
        {q.expected_format === "choice" && q.choices.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {q.choices.map(choice => (
              <button
                key={choice}
                onClick={() => setAnswers(a => ({ ...a, [q.question_id]: choice }))}
                className={`text-[11px] px-3 py-1.5 rounded-lg border transition-all ${
                  answer === choice
                    ? "border-blue-500 bg-blue-600/20 text-blue-200"
                    : "border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-500 hover:text-slate-300"
                }`}
              >
                {choice}
              </button>
            ))}
          </div>
        ) : (
          <input
            type="text"
            value={answer}
            onChange={e => setAnswers(a => ({ ...a, [q.question_id]: e.target.value }))}
            placeholder={q.default_if_skipped ? `Default: ${q.default_if_skipped}` : "Enter your answer..."}
            className="w-full bg-slate-900/60 border border-slate-700/60 rounded-lg px-3 py-2 text-[11px] text-white placeholder-slate-600 focus:outline-none focus:border-blue-500/50 transition-colors"
          />
        )}
      </div>
    );
  };

  return (
    <div className={`rounded-xl border border-amber-700/30 bg-amber-950/10 ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-amber-800/30">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-xl bg-amber-900/40 border border-amber-700/40 flex items-center justify-center text-base">
            🤔
          </div>
          <div>
            <h3 className="text-sm font-bold text-amber-200">Clarification Needed</h3>
            <p className="text-[10px] text-amber-500/80">
              {criticalQuestions.length} critical · {importantQuestions.length} important · {optionalQuestions.length} optional
            </p>
          </div>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
          The system detected missing clinical information that could affect accuracy. 
          Please provide details below, or click &quot;Proceed Anyway&quot; to continue with available data.
        </p>
      </div>

      {/* Questions */}
      <div className="p-5 space-y-3 max-h-[60vh] overflow-y-auto custom-scrollbar">
        {criticalQuestions.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-red-400 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
              Critical — Required for safe analysis
            </p>
            {criticalQuestions.map(renderQuestion)}
          </div>
        )}

        {importantQuestions.length > 0 && (
          <div className="space-y-2 mt-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-400 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              Important — Strongly recommended
            </p>
            {importantQuestions.map(renderQuestion)}
          </div>
        )}

        {optionalQuestions.length > 0 && (
          <div className="space-y-2 mt-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
              Optional — Helpful but not required
            </p>
            {optionalQuestions.map(renderQuestion)}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-amber-800/30 flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || submitted}
          className={`flex-1 py-3 rounded-xl font-bold text-[12px] tracking-wide transition-all duration-200 ${
            canSubmit && !submitted
              ? "bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white shadow-lg shadow-amber-900/30"
              : "bg-slate-700/50 text-slate-500 cursor-not-allowed"
          }`}
        >
          {submitted ? (
            <span className="flex items-center justify-center gap-2">
              <span className="h-3.5 w-3.5 border-2 border-slate-500 border-t-slate-300 rounded-full animate-spin" />
              Analyzing...
            </span>
          ) : (
            <span>Submit Answers & Analyze →</span>
          )}
        </button>
        <button
          onClick={onSkip}
          className="text-[11px] text-slate-500 hover:text-slate-300 border border-slate-700 hover:border-slate-500 rounded-xl px-4 py-3 transition-colors"
        >
          Proceed Anyway
        </button>
      </div>

      {!criticalAnswered && !submitted && (
        <p className="text-[10px] text-red-400/70 text-center pb-3">
          Answer all critical questions to submit
        </p>
      )}
    </div>
  );
}
