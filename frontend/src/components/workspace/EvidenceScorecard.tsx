"use client";

import { useMemo } from "react";
import { EvidenceQualitySummary } from "@/types/clinical";

interface Props {
  summary?: EvidenceQualitySummary | null;
  className?: string;
}

const TIER_COLORS = {
  strong:       { bar: "bg-emerald-500", text: "text-emerald-300", badge: "bg-emerald-900/40 border-emerald-700/40" },
  adequate:     { bar: "bg-blue-500",    text: "text-blue-300",    badge: "bg-blue-900/40 border-blue-700/40"    },
  weak:         { bar: "bg-amber-500",   text: "text-amber-300",   badge: "bg-amber-900/40 border-amber-700/40"  },
  insufficient: { bar: "bg-red-500",     text: "text-red-300",     badge: "bg-red-900/40 border-red-700/40"     },
  unknown:      { bar: "bg-slate-500",   text: "text-slate-400",   badge: "bg-slate-800 border-slate-700"        },
};

function ScoreBar({ value, color }: { value: number; color: string }) {
  const clampedValue = Math.max(0, Math.min(1, value));
  const pct = Math.round(clampedValue * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-slate-500 w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}

function SourcePill({ type, active }: { type: string; active: boolean }) {
  const icons: Record<string, string> = {
    "Authoritative": "🏛",
    "Systematic Review": "📊",
    "Semantic": "🔍",
    "Graph": "🕸",
    "Research": "📚",
    "Multimodal": "🩻",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] border transition-all ${
      active
        ? "border-blue-600/50 bg-blue-900/30 text-blue-300"
        : "border-slate-700/50 bg-slate-800/50 text-slate-600"
    }`}>
      {icons[type] ?? "📄"} {type}
    </span>
  );
}

export default function EvidenceScorecard({ summary, className = "" }: Props) {
  const tier = (summary?.overall_sufficiency ?? "unknown") as keyof typeof TIER_COLORS;
  const colors = TIER_COLORS[tier] ?? TIER_COLORS.unknown;

  const tierLabel = useMemo(() => {
    const labels: Record<string, string> = {
      strong:       "Strong Evidence Base",
      adequate:     "Adequate Evidence",
      weak:         "Weak Evidence — Use with caution",
      insufficient: "Insufficient Evidence — Review required",
      unknown:      "Evidence quality unknown",
    };
    return labels[tier] ?? "Unknown";
  }, [tier]);

  if (!summary) {
    return (
      <div className={`rounded-xl border border-slate-800/60 bg-slate-900/30 p-4 ${className}`}>
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600 flex items-center gap-2 mb-3">
          <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
          Evidence Quality
        </p>
        <div className="text-[11px] text-slate-600 text-center py-4">
          Evidence evaluation pending...
        </div>
      </div>
    );
  }

  return (
    <div className={`rounded-xl border ${colors.badge.includes("emerald") ? "border-emerald-800/40" : colors.badge.includes("blue") ? "border-blue-800/40" : colors.badge.includes("amber") ? "border-amber-800/40" : colors.badge.includes("red") ? "border-red-800/40" : "border-slate-800/60"} bg-slate-900/40 p-4 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
          Evidence Quality
        </p>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${colors.badge} ${colors.text}`}>
          {tier.toUpperCase()}
        </span>
      </div>

      {/* Overall tier label */}
      <p className={`text-[11px] font-medium ${colors.text} mb-3`}>{tierLabel}</p>

      {/* Score bars */}
      <div className="space-y-2 mb-3">
        <div>
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-slate-500">Trust</span>
          </div>
          <ScoreBar value={summary.avg_trust} color={colors.bar} />
        </div>
        <div>
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-slate-500">Relevance</span>
          </div>
          <ScoreBar value={summary.avg_relevance} color={colors.bar} />
        </div>
        <div>
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-slate-500">Freshness</span>
          </div>
          <ScoreBar value={summary.avg_freshness} color={colors.bar} />
        </div>
      </div>

      {/* Source counts */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center">
          <p className="text-sm font-bold text-emerald-400">{summary.high_quality_count}</p>
          <p className="text-[9px] text-slate-600">High Quality</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-bold text-amber-400">{summary.medium_quality_count}</p>
          <p className="text-[9px] text-slate-600">Medium</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-bold text-red-400">{summary.low_quality_count + summary.filtered_count}</p>
          <p className="text-[9px] text-slate-600">Low/Filtered</p>
        </div>
      </div>

      {/* Authority badges */}
      <div className="flex flex-wrap gap-1.5">
        <SourcePill type="Authoritative" active={summary.has_authoritative} />
        <SourcePill type="Systematic Review" active={summary.has_systematic_review} />
        <SourcePill type="Semantic" active={summary.total_sources > 0} />
      </div>

      {summary.filtered_count > 0 && (
        <p className="text-[10px] text-amber-500/80 mt-2">
          ⚠ {summary.filtered_count} low-quality source{summary.filtered_count !== 1 ? "s" : ""} filtered from reasoning
        </p>
      )}
    </div>
  );
}
