"use client";
// components/workspace/GovernancePanel.tsx — Right panel: confidence & governance

import { useState } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { AnalysisResult, RecentCase, Severity } from "@/types/clinical";

// ── Confidence Gauge ───────────────────────────────────────────────────────

function ConfidenceGauge({ score, label }: { score: number; label: string }) {
  const clampedScore = Math.max(0, Math.min(1, score));
  const pct = Math.round(clampedScore * 100);
  const color =
    pct >= 80 ? "#34d399" : pct >= 60 ? "#fbbf24" : "#f87171";
  const strokeDash = `${(pct / 100) * 220} 220`;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-24 w-24">
        <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
          <circle cx="40" cy="40" r="35" fill="none" stroke="#1e293b" strokeWidth="8" />
          <circle
            cx="40" cy="40" r="35" fill="none"
            stroke={color} strokeWidth="8"
            strokeDasharray={strokeDash}
            strokeLinecap="round"
            className="transition-all duration-1000"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-white">{pct}%</span>
          <span className="text-[9px] text-slate-500">confidence</span>
        </div>
      </div>
      <span
        className={`text-xs font-bold px-2 py-0.5 rounded-full ${
          label === "HIGH" ? "bg-emerald-900/60 text-emerald-300" :
          label === "MEDIUM" ? "bg-amber-900/60 text-amber-300" :
          "bg-red-900/60 text-red-300"
        }`}
      >{label} CONFIDENCE</span>
    </div>
  );
}

// ── Metric Row ─────────────────────────────────────────────────────────────

function MetricRow({ label, value, color = "text-slate-300" }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-700/30 last:border-0">
      <span className="text-[10px] text-slate-500">{label}</span>
      <span className={`text-[10px] font-semibold ${color}`}>{value}</span>
    </div>
  );
}

// ── Escalation Banner ──────────────────────────────────────────────────────

function EscalationBanner({ result }: { result: AnalysisResult }) {
  const { setResult } = useWorkspaceStore();
  const [approving, setApproving] = useState(false);

  if (!result.review_required && !result.escalation_required) return null;

  const handleQuickApprove = async () => {
    if (!result.review_id) return;
    setApproving(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/governance/reviews/${result.review_id}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "approve", reviewed_by: "Admin", notes: "Quick approved via Workspace" })
      });
      if (res.ok) {
        const data = await res.json();
        setResult({
          ...result,
          review_status: "approved",
          review_required: false,
          escalation_required: false,
          final_response: data.final_output || result.final_response,
          status: "success"
        });
      }
    } catch (e) {
      console.error(e);
    }
    setApproving(false);
  };

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
        <span className="text-amber-300 text-xs font-bold">⏳ Pending Clinical Review</span>
      </div>
      <p className="text-[10px] text-amber-200/70 leading-relaxed mb-3">
        This analysis contains findings that require mandatory review before finalization. The
        AI output has been held and a review ticket has been generated.
      </p>
      {result.review_id && (
        <div className="rounded-lg bg-amber-900/20 border border-amber-700/30 px-2.5 py-1.5">
          <span className="text-[9px] text-amber-500 font-mono">Review ID: {result.review_id.slice(0, 16)}...</span>
        </div>
      )}
      <div className="mt-3 flex flex-col gap-2">
        <button
          onClick={handleQuickApprove}
          disabled={approving}
          className="w-full text-center rounded-lg border border-emerald-500/40 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-[11px] font-semibold py-2 transition-colors disabled:opacity-50"
        >
          {approving ? "Approving..." : "Quick Approve (Admin) ✓"}
        </button>
        <a
          href="/governance"
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full text-center rounded-lg border border-amber-500/40 bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 text-[11px] font-semibold py-2 transition-colors"
        >
          Open Governance Dashboard →
        </a>
      </div>
    </div>
  );
}

// ── Recent Cases ───────────────────────────────────────────────────────────

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-red-500",
  high: "bg-orange-400",
  medium: "bg-amber-400",
  low: "bg-blue-400",
  none: "bg-slate-500",
};

function RecentCaseRow({ c }: { c: RecentCase }) {
  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-slate-700/30 last:border-0">
      <span className={`mt-1 h-1.5 w-1.5 rounded-full shrink-0 ${SEVERITY_DOT[c.severity]}`} />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-slate-300 font-medium truncate">{c.patientLabel}</p>
        <p className="text-[10px] text-slate-500 mt-0.5 line-clamp-1">{c.summary}</p>
        <p className="text-[9px] text-slate-600 mt-0.5">{c.timestamp}</p>
      </div>
      {c.reviewRequired && (
        <span className="text-[9px] text-amber-400 border border-amber-700/40 rounded px-1 py-0.5 shrink-0">Review</span>
      )}
    </div>
  );
}

// ── Main Governance Panel ──────────────────────────────────────────────────

export default function GovernancePanel() {
  const { status, result, recentCases } = useWorkspaceStore();

  return (
    <div className="h-full flex flex-col gap-4 overflow-y-auto pr-1 custom-scrollbar">
      {/* Confidence */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-4">AI Confidence</p>
        {result ? (
          <>
            <div className="flex justify-center mb-4">
              <ConfidenceGauge score={result.confidence_score} label={result.confidence_label} />
            </div>
            <div>
              <MetricRow
                label="Grounding Quality"
                value={result.confidence_label}
                color={result.confidence_label === "HIGH" ? "text-emerald-400" : result.confidence_label === "MEDIUM" ? "text-amber-400" : "text-red-400"}
              />
              <MetricRow
                label="Evidence Documents"
                value={`${result.evidence_count} retrieved`}
                color="text-blue-300"
              />
              <MetricRow
                label="Reflection Loops"
                value={result.retry_count === 0 ? "None required" : `${result.retry_count} iteration(s)`}
                color={result.retry_count > 0 ? "text-amber-300" : "text-emerald-300"}
              />
              <MetricRow
                label="Hallucination Risk"
                value={result.confidence_score >= 0.8 ? "Low" : result.confidence_score >= 0.6 ? "Moderate" : "Elevated"}
                color={result.confidence_score >= 0.8 ? "text-emerald-300" : result.confidence_score >= 0.6 ? "text-amber-300" : "text-red-300"}
              />
              <MetricRow
                label="Query Classification"
                value={result.query_type}
                color="text-slate-300"
              />
              <MetricRow
                label="Processing Time"
                value={`${result.processing_ms}ms`}
              />
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-2 py-6">
            <div className="h-16 w-16 rounded-full border-2 border-dashed border-slate-700 flex items-center justify-center text-2xl">
              —
            </div>
            <p className="text-[10px] text-slate-600">No analysis yet</p>
          </div>
        )}
      </div>

      {/* Governance / Escalation */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-3">Governance Status</p>
        {result ? (
          <>
            <EscalationBanner result={result} />
            {!result.review_required && !result.escalation_required && (
              <div className="flex items-center gap-2.5 rounded-lg bg-emerald-900/20 border border-emerald-700/30 px-3 py-2.5">
                <span className="text-emerald-400 text-base">✅</span>
                <div>
                  <p className="text-[11px] text-emerald-300 font-medium">Auto-cleared</p>
                  <p className="text-[10px] text-emerald-700">No mandatory review required</p>
                </div>
              </div>
            )}
            <div className="mt-3">
              <MetricRow
                label="Review Status"
                value={result.review_status?.replace("_", " ").toUpperCase() ?? "N/A"}
                color={result.review_required ? "text-amber-300" : "text-emerald-300"}
              />
              <MetricRow
                label="Escalation"
                value={result.escalation_required ? "Yes — Flagged" : "Not required"}
                color={result.escalation_required ? "text-red-300" : "text-slate-400"}
              />
              <MetricRow
                label="Response Status"
                value={result.status?.toUpperCase() ?? "—"}
                color={result.status === "success" ? "text-emerald-300" : result.status === "partial" ? "text-amber-300" : "text-red-300"}
              />
            </div>
          </>
        ) : (
          <p className="text-[10px] text-slate-600 text-center py-4">Run analysis to see governance status</p>
        )}
      </div>

      {/* Evidence Strategy */}
      {result && result.query_plan?.length > 0 && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-3">Retrieval Strategy</p>
          <div className="space-y-1.5">
            {result.query_plan.map((plan, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] text-slate-400">
                <span className="h-1 w-1 rounded-full bg-blue-500" />
                {plan}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Cases */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">Recent Analyses</p>
          {recentCases.length > 0 && (
            <span className="text-[9px] text-slate-600">{recentCases.length} cases</span>
          )}
        </div>
        {recentCases.length === 0 ? (
          <p className="text-[10px] text-slate-600 text-center py-4">No prior analyses this session</p>
        ) : (
          recentCases.map((c) => <RecentCaseRow key={c.id} c={c} />)
        )}
      </div>

      {/* Governance link */}
      <a
        href="/governance"
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4 flex items-center gap-3 hover:border-slate-600 hover:bg-slate-800/80 transition-all group"
      >
        <span className="text-2xl">🏛</span>
        <div>
          <p className="text-xs font-semibold text-slate-300 group-hover:text-white transition-colors">Governance Dashboard</p>
          <p className="text-[10px] text-slate-500">Review flagged outputs · Audit trail</p>
        </div>
        <span className="ml-auto text-slate-600 group-hover:text-slate-400 transition-colors">→</span>
      </a>
    </div>
  );
}
