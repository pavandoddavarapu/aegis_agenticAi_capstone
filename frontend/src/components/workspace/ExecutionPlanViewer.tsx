"use client";

import { ExecutionPlanSummary, EvidenceStrategyFlags } from "@/types/clinical";

interface Props {
  plan?: ExecutionPlanSummary | null;
  intent?: string;
  className?: string;
}

const INTENT_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  emergency_triage:     { icon: "🚨", label: "Emergency Triage",       color: "text-red-300" },
  diagnostic_workup:    { icon: "🔬", label: "Diagnostic Workup",      color: "text-blue-300" },
  treatment_planning:   { icon: "💊", label: "Treatment Planning",      color: "text-violet-300" },
  medication_review:    { icon: "💉", label: "Medication Review",       color: "text-amber-300" },
  research_lookup:      { icon: "📚", label: "Evidence Lookup",         color: "text-cyan-300" },
  literature_synthesis: { icon: "📊", label: "Literature Synthesis",    color: "text-indigo-300" },
  similar_case_search:  { icon: "🔍", label: "Similar Case Search",     color: "text-emerald-300" },
  risk_stratification:  { icon: "⚖️", label: "Risk Stratification",     color: "text-orange-300" },
  monitoring_follow_up: { icon: "📈", label: "Monitoring / Follow-up",  color: "text-teal-300" },
  unknown:              { icon: "🤖", label: "General Clinical Analysis", color: "text-slate-400" },
};

const CAPABILITY_ICONS: Record<string, string> = {
  query_understanding:  "🧠",
  semantic_retrieval:   "🔍",
  graph_retrieval:      "🕸",
  research_retrieval:   "📚",
  similar_case_lookup:  "🗂",
  multimodal_analysis:  "🩻",
  clinical_reasoning:   "💡",
  evidence_evaluation:  "⚖️",
  contradiction_check:  "🔀",
  validation:           "✅",
  reflection:           "🔄",
  governance:           "🏛",
};

const DEPTH_COLORS: Record<string, string> = {
  shallow:  "text-emerald-400",
  standard: "text-blue-400",
  deep:     "text-violet-400",
};

const RISK_COLORS: Record<string, { text: string; bg: string }> = {
  low:      { text: "text-emerald-400", bg: "bg-emerald-900/30" },
  medium:   { text: "text-amber-400",   bg: "bg-amber-900/30" },
  high:     { text: "text-orange-400",  bg: "bg-orange-900/30" },
  critical: { text: "text-red-400",     bg: "bg-red-900/30" },
};

export default function ExecutionPlanViewer({ plan, intent, className = "" }: Props) {
  const intentKey = (intent ?? plan?.clinical_intent ?? "unknown").toLowerCase();
  const intentConfig = INTENT_CONFIG[intentKey] ?? INTENT_CONFIG.unknown;
  const riskKey = (plan?.risk_level ?? "low").toLowerCase();
  const riskColors = RISK_COLORS[riskKey] ?? RISK_COLORS.low;

  if (!plan && !intent) return null;

  return (
    <div className={`rounded-xl border border-slate-800/60 bg-slate-900/30 p-4 ${className}`}>
      {/* Header */}
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 flex items-center gap-2 mb-3">
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
        Execution Plan
      </p>

      {/* Intent badge */}
      <div className="flex items-center gap-3 mb-4">
        <div className="h-9 w-9 rounded-xl bg-slate-800 border border-slate-700/50 flex items-center justify-center text-lg shrink-0">
          {intentConfig.icon}
        </div>
        <div>
          <p className={`text-[12px] font-bold ${intentConfig.color}`}>{intentConfig.label}</p>
          {plan?.goal && (
            <p className="text-[10px] text-slate-600">{plan.goal.replace(/_/g, " ")}</p>
          )}
        </div>
        {plan?.risk_level && (
          <span className={`ml-auto text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg ${riskColors.bg} ${riskColors.text}`}>
            {plan.risk_level} risk
          </span>
        )}
      </div>

      {/* Capabilities */}
      {plan?.required_capabilities && plan.required_capabilities.length > 0 && (
        <div className="mb-3">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-600 mb-1.5">Active Capabilities</p>
          <div className="flex flex-wrap gap-1.5">
            {plan.required_capabilities.map(cap => (
              <span
                key={cap}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800/60 border border-slate-700/50 text-[10px] text-slate-300"
              >
                {CAPABILITY_ICONS[cap] ?? "⚙"} {cap.replace(/_/g, " ")}
              </span>
            ))}
            {plan.optional_capabilities?.map(cap => (
              <span
                key={cap}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800/30 border border-slate-700/30 text-[10px] text-slate-500"
              >
                {CAPABILITY_ICONS[cap] ?? "⚙"} {cap.replace(/_/g, " ")}
                <span className="text-[8px] text-slate-600">(opt)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Evidence strategy */}
      {plan?.evidence_strategy && (
        <div className="mb-3">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-600 mb-1.5">Evidence Strategy</p>
          <div className="grid grid-cols-2 gap-1.5">
            {[
              { key: "use_graph"        as keyof EvidenceStrategyFlags, label: "Graph",    icon: "🕸" },
              { key: "use_research"     as keyof EvidenceStrategyFlags, label: "Research", icon: "📚" },
              { key: "use_similar_cases" as keyof EvidenceStrategyFlags, label: "Cases",  icon: "🗂" },
              { key: "use_multimodal"   as keyof EvidenceStrategyFlags, label: "Visual",   icon: "🩻" },
            ].map(({ key, label, icon }) => {
              const active = Boolean(plan.evidence_strategy[key]);
              return (
                <div
                  key={key}
                  className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg border text-[10px] ${
                    active
                      ? "border-blue-700/40 bg-blue-900/20 text-blue-300"
                      : "border-slate-700/30 bg-slate-800/20 text-slate-600"
                  }`}
                >
                  <span>{icon}</span>
                  <span>{label}</span>
                  {active && <span className="ml-auto text-emerald-400">✓</span>}
                </div>
              );
            })}
          </div>
          <p className={`text-[10px] mt-1.5 ${DEPTH_COLORS[plan.evidence_strategy.retrieval_depth] ?? "text-slate-400"}`}>
            Retrieval depth: {plan.evidence_strategy.retrieval_depth}
          </p>
        </div>
      )}

      {/* Emergency badge */}
      {plan?.emergency_override && (
        <div className="flex items-center gap-2 bg-red-900/20 rounded-lg px-3 py-2 border border-red-800/40">
          <span>🚨</span>
          <p className="text-[10px] text-red-300 font-medium">Emergency bypass active — all safeguards engaged</p>
        </div>
      )}
    </div>
  );
}
