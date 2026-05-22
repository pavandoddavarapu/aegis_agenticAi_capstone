"use client";
// components/workspace/OrchestraCopilot.tsx — Phase 13: Session-aware copilot using real backend
// Phase 13 fix: Now calls POST /analyze/copilot/ via askCopilot() service (was causing 404)
// Phase 13 new: session_id integration for persistent context enrichment

import { useState, useRef, useCallback, useEffect } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { AnalysisResult } from "@/types/clinical";
import { askCopilot } from "@/services/analysisService";

interface Message {
  role: "user" | "assistant";
  content: string;
  ts: string;
  confidence?: string;
}

// Pre-canned context-aware prompts based on what we know
const SMART_PROMPTS = [
  { icon: "🔍", label: "What's the differential?" },
  { icon: "⚠️", label: "Any contraindications?" },
  { icon: "📊", label: "Explain the evidence quality" },
  { icon: "🩺", label: "What workup is next?" },
  { icon: "💊", label: "Drug interaction risks?" },
  { icon: "📈", label: "Risk stratification?" },
];

function TypingIndicator() {
  return (
    <div className="flex items-end gap-1 px-3 py-2.5 bg-slate-800/60 rounded-xl rounded-bl-sm w-fit">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.9s" }}
        />
      ))}
    </div>
  );
}

function ConfidenceDot({ confidence }: { confidence?: string }) {
  if (!confidence) return null;
  const color =
    confidence === "high"   ? "bg-emerald-400" :
    confidence === "medium" ? "bg-amber-400"   :
    "bg-slate-500";
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ml-1.5 ${color} shrink-0`} />;
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} gap-2`}>
      {!isUser && (
        <div className="h-6 w-6 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center text-[10px] font-black shrink-0 mt-0.5">
          Æ
        </div>
      )}
      <div
        className={`max-w-[85%] px-3 py-2 rounded-xl text-[11px] leading-relaxed ${
          isUser
            ? "bg-blue-600/30 border border-blue-500/40 text-blue-100 rounded-br-sm"
            : "bg-slate-800/60 border border-slate-700/40 text-slate-300 rounded-bl-sm"
        }`}
      >
        <div className="whitespace-pre-wrap">{msg.content}</div>
        <div className={`flex items-center gap-1.5 mt-1 ${isUser ? "justify-end" : "justify-start"}`}>
          <span className="text-[9px] text-slate-600">{msg.ts}</span>
          {!isUser && <ConfidenceDot confidence={msg.confidence} />}
        </div>
      </div>
    </div>
  );
}

export default function OrchestraCopilot() {
  const { result, intake, sessionId } = useWorkspaceStore();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: result
        ? `I've reviewed the clinical analysis for this case. I can help you explore the evidence, clarify reasoning, identify gaps, or discuss the differential. What would you like to know?`
        : `Hello. I'm Aegis Copilot. Once you run a patient analysis, I can answer questions about the evidence, reasoning, contradictions, and clinical decisions. What would you like to discuss?`,
      ts: new Date().toLocaleTimeString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Update greeting when result first arrives
  useEffect(() => {
    if (result && messages.length === 1 && messages[0].role === "assistant") {
      const timer = setTimeout(() => {
        setMessages([{
          role: "assistant",
          content: `I've analyzed this case (${result.clinical_intent?.replace(/_/g, " ") ?? "clinical workup"}, confidence: ${result.confidence_label}). I can help you explore the evidence quality, understand the reasoning, check for contradictions, or discuss the differential. What would you like to know?`,
          ts: new Date().toLocaleTimeString(),
        }]);
      }, 0);
      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.confidence_label]);

  const buildContext = useCallback(() => {
    const parts: string[] = [];
    if (result) {
      parts.push(`Clinical intent: ${result.clinical_intent ?? "unknown"}`);
      const confidencePct = Math.max(0, Math.min(100, Math.round((result.confidence_score ?? 0) * 100)));
      parts.push(`Confidence: ${result.confidence_label} (${confidencePct}%)`);
      if (result.final_response) parts.push(`Summary: ${result.final_response.slice(0, 300)}`);
      if (result.evidence_quality_summary) {
        const eq = result.evidence_quality_summary;
        const avgTrustClamped = Math.max(0, Math.min(1, eq.avg_trust));
        parts.push(`Evidence quality: ${eq.overall_sufficiency} (avg trust ${(avgTrustClamped * 100).toFixed(0)}%)`);
        parts.push(`Sources: ${eq.total_sources} total, ${eq.high_quality_count} high-quality, ${eq.filtered_count} filtered`);
      }
      if (result.contradiction_summary?.has_contradictions) {
        parts.push(`Contradictions: ${result.contradiction_summary.summary}`);
        parts.push(`Contradiction severity: ${result.contradiction_summary.overall_severity}`);
      }
      if (result.missing_information?.length) {
        parts.push(`Missing information: ${result.missing_information.join(", ")}`);
      }
      if (result.escalation_required) {
        parts.push("Escalation: required");
      }
      if (result.execution_plan_summary) {
        const ep = result.execution_plan_summary;
        parts.push(`Risk level: ${ep.risk_level}`);
        if (ep.required_capabilities?.length) {
          parts.push(`Capabilities used: ${ep.required_capabilities.join(", ")}`);
        }
      }
    }
    if (intake.vitals.age) parts.push(`Patient age: ${intake.vitals.age}, gender: ${intake.vitals.gender}`);
    if (intake.history.medications) parts.push(`Medications: ${intake.history.medications}`);
    if (intake.history.allergies) parts.push(`Allergies: ${intake.history.allergies}`);
    return parts.join("\n");
  }, [result, intake]);

  const getHistory = useCallback(() => {
    return messages.slice(-6).map(m => ({ role: m.role, content: m.content }));
  }, [messages]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text, ts: new Date().toLocaleTimeString() };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Scroll to bottom
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);

    try {
      const context = buildContext();
      const history = getHistory();

      // Phase 13: Use askCopilot() service — now calls real /analyze/copilot/ endpoint
      const copilotResponse = await askCopilot(text, context, history, sessionId ?? undefined);

      const botMsg: Message = {
        role: "assistant",
        content: copilotResponse.answer,
        ts: new Date().toLocaleTimeString(),
        confidence: copilotResponse.confidence,
      };
      setMessages(prev => [...prev, botMsg]);
    } catch {
      // Graceful degradation
      const fallback = buildFallbackAnswer(text, result, buildContext());
      setMessages(prev => [...prev, {
        role: "assistant",
        content: fallback,
        ts: new Date().toLocaleTimeString(),
        confidence: "low",
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }, [loading, buildContext, getHistory, result, sessionId]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  const hasResult = Boolean(result);

  return (
    <div className="flex flex-col h-full rounded-xl border border-slate-800/60 bg-slate-900/30 overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-slate-800/50 shrink-0">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center text-[10px] font-black">Æ</div>
          <div>
            <p className="text-[11px] font-bold text-white">Aegis Copilot</p>
            <p className="text-[9px] text-slate-500">
              Context-aware clinical assistant
              {sessionId && <span className="ml-1 text-indigo-400">• Session active</span>}
            </p>
          </div>
          <div className={`ml-auto h-1.5 w-1.5 rounded-full ${hasResult ? "bg-emerald-400" : "bg-slate-600"}`} />
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 custom-scrollbar">
        {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Smart prompt chips */}
      <div className="px-3 py-2 border-t border-slate-800/40 flex gap-1.5 overflow-x-auto shrink-0 custom-scrollbar">
        {SMART_PROMPTS.map(p => (
          <button
            key={p.label}
            onClick={() => send(p.label)}
            disabled={loading}
            className="flex items-center gap-1 px-2 py-1 rounded-full bg-slate-800/60 border border-slate-700/40 text-[9px] text-slate-400 hover:text-white hover:border-slate-500 whitespace-nowrap transition-all disabled:opacity-40 shrink-0"
          >
            <span>{p.icon}</span>
            <span>{p.label}</span>
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-3 pb-3 pt-1 shrink-0">
        <div className="flex items-center gap-2 bg-slate-800/50 border border-slate-700/50 rounded-xl px-3 py-2 focus-within:border-blue-500/40 transition-colors">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about this case..."
            disabled={loading}
            className="flex-1 bg-transparent text-[11px] text-white placeholder-slate-600 focus:outline-none"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            className="h-6 w-6 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M1 9L9 5L1 1V4.5L6.5 5L1 5.5V9Z" fill="white"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Graceful degradation: context-aware offline answers ────────────────────

function buildFallbackAnswer(
  question: string,
  result: AnalysisResult | null,
  context: string,
): string {
  const q = question.toLowerCase();

  if (!result) {
    return "Please run a patient analysis first, then I can answer questions about the specific case.";
  }

  if (q.includes("differential")) {
    return `Based on the analysis (${result.clinical_intent?.replace(/_/g, " ") ?? "clinical workup"}), the reasoning section of the report contains the differential. Confidence is ${result.confidence_label}. Check the Clinical Intelligence Report above for the detailed breakdown.`;
  }
  if (q.includes("evidence")) {
    const eq = result.evidence_quality_summary;
    return eq
      ? `Evidence quality is ${eq.overall_sufficiency.toUpperCase()} — ${eq.high_quality_count} high-quality sources, avg trust ${(eq.avg_trust * 100).toFixed(0)}%. ${eq.filtered_count} low-quality sources were filtered out.`
      : `${result.evidence_count} documents were retrieved. See the Evidence tab on the right panel for quality scores.`;
  }
  if (q.includes("contraindication") || q.includes("drug")) {
    return result.contradiction_summary?.has_contradictions
      ? `⚠️ Contradictions detected (${result.contradiction_summary.overall_severity} severity): ${result.contradiction_summary.summary}`
      : "No contraindications or drug conflicts were flagged in this analysis. Always verify against the patient's current medication list.";
  }
  if (q.includes("risk")) {
    const confidencePct = (Math.max(0, Math.min(1, result.confidence_score)) * 100).toFixed(0);
    return `The execution plan assessed risk as: ${result.execution_plan_summary?.risk_level ?? "unknown"}. Escalation required: ${result.escalation_required ? "Yes ⚠️" : "No ✓"}. Confidence score: ${confidencePct}%.`;
  }
  if (q.includes("missing") || q.includes("gap")) {
    const missing = result.missing_information ?? [];
    return missing.length
      ? `Information gaps detected: ${missing.map(m => m.replace(/_/g, " ")).join(", ")}. Providing this would improve analysis confidence.`
      : "No critical information gaps were detected for this case.";
  }

  return `Based on the analysis: ${context.split("\n")[1] ?? "see the Clinical Intelligence Report for details."}`;
}
