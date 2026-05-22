"use client";
// components/workspace/AnalysisPanel.tsx — Phase 12 evolved: EvidenceScorecard + Phase 12 metadata

import { useState } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { AnalysisResult, ClinicalSection, Severity } from "@/types/clinical";
import EvidenceScorecard from "./EvidenceScorecard";
import ContradictionAlert from "./ContradictionAlert";

// ── Severity config ────────────────────────────────────────────────────────

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "border-l-red-500 bg-red-950/20",
  high:     "border-l-orange-500 bg-orange-950/20",
  medium:   "border-l-amber-500 bg-amber-950/10",
  low:      "border-l-blue-500 bg-blue-950/10",
  none:     "border-l-slate-600 bg-slate-800/30",
};

const SEVERITY_BADGE: Record<Severity, string> = {
  critical: "bg-red-600 text-white",
  high:     "bg-orange-500 text-white",
  medium:   "bg-amber-600 text-white",
  low:      "bg-blue-600 text-white",
  none:     "bg-slate-600 text-slate-300",
};

// ── Processing State ───────────────────────────────────────────────────────

function ProcessingState() {
  const stages = [
    { icon: "🗂", label: "Planning execution strategy" },
    { icon: "🔍", label: "Retrieving evidence from all sources" },
    { icon: "⚖️", label: "Evaluating evidence quality" },
    { icon: "🔀", label: "Checking for contradictions" },
    { icon: "💡", label: "Synthesising clinical reasoning" },
    { icon: "🏛", label: "Validating with governance layer" },
  ];

  const [activeIdx] = useState(0);

  return (
    <div className="flex flex-col items-center justify-center h-full gap-8">
      <div className="relative">
        <div className="h-20 w-20 rounded-full border-2 border-blue-500/30 flex items-center justify-center">
          <div className="h-14 w-14 rounded-full border-2 border-blue-400/50 flex items-center justify-center animate-pulse">
            <span className="text-3xl">⚕️</span>
          </div>
        </div>
        <div className="absolute inset-0 rounded-full border-t-2 border-blue-400 animate-spin" />
        <div className="absolute inset-2 rounded-full border-t border-indigo-500/60 animate-spin" style={{ animationDirection: "reverse", animationDuration: "1.5s" }} />
      </div>

      <div className="text-center">
        <p className="text-white font-semibold text-sm mb-1">Aegis is analyzing this patient</p>
        <p className="text-slate-400 text-xs">Phase 12 adaptive orchestration running...</p>
      </div>

      <div className="space-y-2 w-full max-w-xs">
        {stages.map((s, i) => (
          <div key={i} className={`flex items-center gap-2.5 rounded-lg px-3 py-2 transition-all ${
            i === activeIdx ? "bg-blue-600/20 border border-blue-500/30" : "opacity-40"
          }`}>
            <span className="text-base">{s.icon}</span>
            <span className="text-xs text-slate-300">{s.label}</span>
            {i < activeIdx && <span className="ml-auto text-emerald-400 text-xs">✓</span>}
            {i === activeIdx && (
              <span className="ml-auto flex gap-0.5">
                {[0,1,2].map(d => (
                  <span key={d} className="h-1 w-1 rounded-full bg-blue-400 animate-bounce"
                    style={{ animationDelay: `${d * 0.15}s` }} />
                ))}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Empty State ────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
      <div className="h-24 w-24 rounded-2xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center">
        <span className="text-4xl">🏥</span>
      </div>
      <div>
        <h2 className="text-white font-semibold text-base mb-2">Patient Analysis Workspace</h2>
        <p className="text-slate-400 text-xs leading-relaxed max-w-[280px]">
          Complete the patient intake on the left, upload clinical documents,
          then click <strong className="text-blue-400">Analyze Patient</strong> to generate
          a structured clinical intelligence report.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
        {[
          { icon: "🗂", label: "Adaptive execution planning" },
          { icon: "⚖️", label: "Evidence quality scoring" },
          { icon: "🔀", label: "Contradiction detection" },
          { icon: "📚", label: "Live PubMed research" },
          { icon: "🧬", label: "Similar case intelligence" },
          { icon: "🏛", label: "HITL governance" },
        ].map(f => (
          <div key={f.label} className="rounded-lg bg-slate-800/40 border border-slate-700/40 px-3 py-2 flex items-center gap-2">
            <span className="text-base">{f.icon}</span>
            <span className="text-[10px] text-slate-400">{f.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Clinical Section Card ──────────────────────────────────────────────────

function SectionCard({ section }: { section: ClinicalSection }) {
  const [expanded, setExpanded] = useState(true);
  const severityStyle = SEVERITY_STYLE[section.severity ?? "none"];
  const severityBadge = SEVERITY_BADGE[section.severity ?? "none"];

  return (
    <div className={`rounded-xl border-l-4 border border-slate-700/40 p-4 ${severityStyle}`}>
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => section.expandable && setExpanded(e => !e)}
      >
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white">{section.title}</h3>
          {section.severity && section.severity !== "none" && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full uppercase ${severityBadge}`}>
              {section.severity}
            </span>
          )}
        </div>
        {section.expandable && (
          <span className="text-slate-500 text-xs">{expanded ? "▼" : "▶"}</span>
        )}
      </div>
      {expanded && (
        <div className="mt-2 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
          {section.content}
        </div>
      )}
    </div>
  );
}

// ── Phase 12: Evidence Quality Inline Bar ─────────────────────────────────

function EvidenceQualityBar({ result }: { result: AnalysisResult }) {
  const eq = result.evidence_quality_summary;
  if (!eq) return null;

  const score = eq.sufficiency_score ?? 0;
  const color =
    eq.overall_sufficiency === "strong"    ? "bg-emerald-500" :
    eq.overall_sufficiency === "adequate"  ? "bg-blue-500"    :
    eq.overall_sufficiency === "weak"      ? "bg-amber-500"   :
    "bg-red-500";

  const textColor =
    eq.overall_sufficiency === "strong"    ? "text-emerald-400" :
    eq.overall_sufficiency === "adequate"  ? "text-blue-400"    :
    eq.overall_sufficiency === "weak"      ? "text-amber-400"   :
    "text-red-400";

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-slate-900/40 border-b border-slate-800/40">
      <span className="text-[10px] text-slate-500 shrink-0">Evidence quality</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <span className={`text-[10px] font-bold shrink-0 ${textColor}`}>
        {eq.overall_sufficiency.toUpperCase()}
      </span>
      <span className="text-[10px] text-slate-600 shrink-0">
        {eq.high_quality_count} high · {eq.filtered_count} filtered
      </span>
    </div>
  );
}

// ── Evidence Panel ─────────────────────────────────────────────────────────

function EvidencePanel({ result }: { result: AnalysisResult }) {
  const [showScorecard, setShowScorecard] = useState(false);
  const topEvidence = result.evidence?.slice(0, 5) ?? [];
  if (!topEvidence.length) return null;

  return (
    <div className="rounded-xl border border-slate-700/40 bg-slate-800/30 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-slate-300 flex items-center gap-2">
          <span className="text-base">📄</span> Retrieved Evidence
          <span className="ml-1 bg-slate-700 text-slate-300 text-[10px] px-2 py-0.5 rounded-full">
            {result.evidence_count} documents
          </span>
        </h3>
        {result.evidence_quality_summary && (
          <button
            onClick={() => setShowScorecard(s => !s)}
            className="text-[10px] text-blue-400 hover:text-blue-300 border border-blue-700/30 hover:border-blue-600/40 rounded-lg px-2 py-1 transition-colors"
          >
            {showScorecard ? "Hide" : "⚖️ Quality Scorecard"}
          </button>
        )}
      </div>

      {/* Phase 12: Inline EvidenceScorecard (toggleable) */}
      {showScorecard && result.evidence_quality_summary && (
        <div className="mb-3">
          <EvidenceScorecard summary={result.evidence_quality_summary} />
        </div>
      )}

      <div className="space-y-2">
        {topEvidence.map((ev, i) => (
          <div key={i} className="rounded-lg bg-slate-900/60 border border-slate-700/30 p-3">
            <div className="flex items-start justify-between gap-2 mb-1">
              <span className="text-[10px] text-slate-500 font-mono">{ev.source} · p.{ev.page}</span>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${
                ev.confidence === "HIGH"   ? "bg-emerald-900 text-emerald-300" :
                ev.confidence === "MEDIUM" ? "bg-amber-900 text-amber-300"   :
                "bg-slate-700 text-slate-400"
              }`}>{ev.confidence}</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed line-clamp-3">{ev.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Phase 12: Metadata Strip ───────────────────────────────────────────────

function Phase12MetaStrip({ result }: { result: AnalysisResult }) {
  const chips = [
    result.clinical_intent && {
      label: result.clinical_intent.replace(/_/g, " "),
      color: "bg-indigo-900/30 border-indigo-700/40 text-indigo-300",
    },
    result.replan_count && result.replan_count > 0 && {
      label: `${result.replan_count} re-plan${result.replan_count !== 1 ? "s" : ""}`,
      color: "bg-violet-900/30 border-violet-700/40 text-violet-300",
    },
    result.escalation_required && {
      label: "⚠️ Escalation required",
      color: "bg-red-900/30 border-red-700/40 text-red-300",
    },
    result.review_required && {
      label: "⏳ Pending review",
      color: "bg-amber-900/30 border-amber-700/40 text-amber-300",
    },
  ].filter(Boolean) as Array<{ label: string; color: string }>;

  if (!chips.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5 px-4 py-2 bg-slate-900/30 border-b border-slate-800/40">
      {chips.map(chip => (
        <span key={chip.label} className={`text-[10px] font-medium px-2 py-0.5 rounded-full border capitalize ${chip.color}`}>
          {chip.label}
        </span>
      ))}
    </div>
  );
}

// ── Workflow Trace ─────────────────────────────────────────────────────────

function WorkflowTrace({ result }: { result: AnalysisResult }) {
  const { showWorkflowTrace, toggleWorkflowTrace } = useWorkspaceStore();

  return (
    <div className="rounded-xl border border-slate-700/40 bg-slate-800/20">
      <button
        onClick={toggleWorkflowTrace}
        className="w-full flex items-center justify-between px-4 py-3 text-xs text-slate-400 hover:text-slate-300 transition-colors"
      >
        <span className="flex items-center gap-2">
          <span>🔭</span> AI Workflow Trace
          <span className="text-[10px] text-slate-600">
            {result.retry_count > 0 ? `${result.retry_count} reflection loops` : "Single pass"}
            {" · "}{result.processing_ms}ms
            {result.replan_count ? ` · ${result.replan_count} re-plans` : ""}
          </span>
        </span>
        <span>{showWorkflowTrace ? "▼" : "▶"}</span>
      </button>
      {showWorkflowTrace && (
        <div className="px-4 pb-4 space-y-1.5">
          {result.workflow_trace.map((step, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <span className="h-4 w-4 rounded-full bg-blue-600/30 border border-blue-500/40 flex items-center justify-center text-[9px] text-blue-400 shrink-0">{i + 1}</span>
              <span className="text-slate-400 font-mono">{step}</span>
            </div>
          ))}
          {result.reflection_notes && (
            <div className="mt-2 rounded-lg bg-slate-900/60 border border-slate-700/30 p-2">
              <p className="text-[10px] text-slate-500 font-medium mb-1">Reflection Notes</p>
              <p className="text-[10px] text-slate-400">{result.reflection_notes}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Analysis Panel ────────────────────────────────────────────────────

export default function AnalysisPanel() {
  const { status, result } = useWorkspaceStore();

  if (status === "analyzing") return (
    <div className="h-full rounded-2xl border border-slate-700/50 bg-slate-900/80 p-6">
      <ProcessingState />
    </div>
  );

  if (status === "idle" || !result) return (
    <div className="h-full rounded-2xl border border-slate-700/50 bg-slate-900/80 p-6">
      <EmptyState />
    </div>
  );

  if (status === "error") return (
    <div className="h-full rounded-2xl border border-red-700/40 bg-red-950/20 p-6 flex flex-col items-center justify-center gap-4">
      <span className="text-4xl">⚠️</span>
      <div className="text-center">
        <p className="text-red-400 font-semibold text-sm">Analysis Failed</p>
        <p className="text-slate-400 text-xs mt-1">{result?.error ?? "An unexpected error occurred. Please try again."}</p>
      </div>
    </div>
  );

  // ── Render full report ──────────────────────────────────────────────────
  return (
    <div className="h-full rounded-2xl border border-slate-700/50 bg-slate-900/80 flex flex-col overflow-hidden">

      {/* Report header */}
      <div className="border-b border-slate-700/50 px-5 py-3 flex items-center justify-between bg-slate-900/60 shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm font-semibold text-white">Clinical Intelligence Report</span>
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
            result.confidence_label === "HIGH"   ? "bg-emerald-900 text-emerald-300" :
            result.confidence_label === "MEDIUM" ? "bg-amber-900 text-amber-300"    :
            "bg-red-900 text-red-300"
          }`}>{result.confidence_label} CONFIDENCE</span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-500">
          <span>⚡ {result.processing_ms}ms</span>
          <span>📄 {result.evidence_count} docs</span>
          {result.review_required && (
            <span className="bg-amber-600/20 border border-amber-500/40 text-amber-300 px-2 py-0.5 rounded-full">
              ⏳ Pending Review
            </span>
          )}
        </div>
      </div>

      {/* Phase 12 meta strip */}
      <Phase12MetaStrip result={result} />

      {/* Phase 12: Contradiction alert (inline) */}
      {result.contradiction_summary?.has_contradictions && (
        <div className="px-4 pt-3 shrink-0">
          <ContradictionAlert summary={result.contradiction_summary} />
        </div>
      )}

      {/* Phase 12: Evidence quality bar */}
      <EvidenceQualityBar result={result} />

      {/* Scrollable report */}
      <div className="flex-1 overflow-y-auto p-5 space-y-3 custom-scrollbar">
        {/* Sections */}
        {result.sections?.map((s, i) => (
          <SectionCard key={i} section={s} />
        ))}

        {/* Evidence with integrated scorecard */}
        <EvidencePanel result={result} />

        {/* Workflow trace (collapsible) */}
        <WorkflowTrace result={result} />
      </div>
    </div>
  );
}
