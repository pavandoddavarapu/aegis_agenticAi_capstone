"use client";

import { ContradictionSummary } from "@/types/clinical";

interface Props {
  summary?: ContradictionSummary | null;
  className?: string;
}

const SEVERITY_CONFIG = {
  none:     null,   // don't render
  minor:    { bg: "bg-amber-950/30", border: "border-amber-700/40", text: "text-amber-300",   icon: "⚠️", label: "Minor Contradictions" },
  moderate: { bg: "bg-orange-950/40", border: "border-orange-700/40", text: "text-orange-300", icon: "⚠️", label: "Moderate Contradictions" },
  critical: { bg: "bg-red-950/50", border: "border-red-700/50",   text: "text-red-300",    icon: "🚨", label: "CRITICAL Contradictions" },
};

export default function ContradictionAlert({ summary, className = "" }: Props) {
  if (!summary || !summary.has_contradictions) return null;

  const severity = summary.overall_severity as keyof typeof SEVERITY_CONFIG;
  const config = SEVERITY_CONFIG[severity];
  if (!config) return null;

  return (
    <div className={`rounded-xl border ${config.border} ${config.bg} p-4 ${className}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-base">{config.icon}</span>
          <div>
            <p className={`text-[11px] font-bold ${config.text}`}>{config.label}</p>
            <p className="text-[10px] text-slate-500">{summary.contradiction_count} conflict{summary.contradiction_count !== 1 ? "s" : ""} detected</p>
          </div>
        </div>
        {summary.total_penalty > 0 && (
          <span className={`text-[10px] font-mono ${config.text} bg-black/20 rounded-lg px-2 py-1 border ${config.border}`}>
            −{Math.round(summary.total_penalty * 100)}% confidence
          </span>
        )}
      </div>

      {/* Summary */}
      <p className="text-[11px] text-slate-400 leading-relaxed mb-3">{summary.summary}</p>

      {/* Conflict pairs */}
      {summary.pairs && summary.pairs.length > 0 && (
        <div className="space-y-1.5">
          {summary.pairs.map((pair, i) => (
            <div key={i} className="rounded-lg bg-black/20 border border-slate-800/60 px-3 py-2">
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[9px] font-bold uppercase tracking-wider ${
                  pair.severity === "critical" ? "text-red-400" : pair.severity === "moderate" ? "text-orange-400" : "text-amber-400"
                }`}>{pair.conflict_type.replace(/_/g, " ")}</span>
                <span className="text-[9px] text-slate-600">{pair.severity}</span>
              </div>
              <p className="text-[10px] text-slate-400">{pair.description}</p>
              <p className="text-[9px] text-slate-600 mt-1">
                Resolve: {pair.resolution.replace(/_/g, " ")}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Escalation notice */}
      {summary.escalation_required && (
        <div className="mt-3 flex items-center gap-2 bg-red-900/30 rounded-lg px-3 py-2 border border-red-800/50">
          <span className="text-red-400 text-sm">🔴</span>
          <p className="text-[10px] text-red-300 font-medium">
            Critical contradiction requires human clinical review before acting on this analysis.
          </p>
        </div>
      )}
    </div>
  );
}
