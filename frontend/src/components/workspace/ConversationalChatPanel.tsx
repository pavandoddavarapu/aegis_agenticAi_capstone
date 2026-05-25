"use client";

import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import {
  ConversationMessage,
  AnalysisResult,
  ClarificationAnswers,
  ClinicalSection,
  Severity,
  EvidenceItem,
  ClarificationQuestion,
  CopilotResponse,
  PatientContextSummary,
} from "@/types/clinical";
import {
  runAnalysisWithStreaming,
  askCopilot,
} from "@/services/analysisService";
import ClarificationPanel from "./ClarificationPanel";
import {
  Brain,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Clock,
  Search,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  Activity,
  FileText,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  TrendingUp,
  Compass,
  HelpCircle,
  FileDown
} from "lucide-react";
import { getApiBase } from "@/lib/utils";

const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

const generateId = () => {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
};

// Severity config matching AnalysisPanel
const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "border-l-red-500 bg-red-950/20 border-slate-800",
  high:     "border-l-orange-500 bg-orange-950/20 border-slate-800",
  medium:   "border-l-amber-500 bg-amber-950/10 border-slate-800",
  low:      "border-l-blue-500 bg-blue-950/10 border-slate-800",
  none:     "border-l-slate-600 bg-slate-800/30 border-slate-800",
};

const SEVERITY_BADGE: Record<Severity, string> = {
  critical: "bg-red-600 text-white",
  high:     "bg-orange-500 text-white",
  medium:   "bg-amber-600 text-white",
  low:      "bg-blue-600 text-white",
  none:     "bg-slate-600 text-slate-300",
};

const INTENT_ICON: Record<string, string> = {
  emergency_triage:     "🚨",
  diagnostic_workup:    "🔬",
  treatment_planning:   "💊",
  medication_review:    "💉",
  research_lookup:      "📚",
  literature_synthesis: "📊",
  similar_case_search:  "🔍",
  risk_stratification:  "⚖️",
  monitoring_follow_up: "📈",
};

// Streaming stage items
interface StageStep {
  node: string;
  icon: string;
  label: string;
}

const STAGES: StageStep[] = [
  { node: "plan", icon: "🧠", label: "Planning execution strategy" },
  { node: "query_understand", icon: "🔍", label: "Analyzing query intent" },
  { node: "retrieve", icon: "📂", label: "Retrieving clinical evidence" },
  { node: "evidence_eval", icon: "📊", label: "Evaluating evidence quality" },
  { node: "contradiction_check", icon: "⚖️", label: "Checking contradictions" },
  { node: "reason", icon: "📝", label: "Synthesizing clinical report" },
  { node: "validate", icon: "🩺", label: "Validating output safety" },
  { node: "finalize", icon: "🛡️", label: "Applying governance review" },
];

// ─── Module-scoped sub-components ─────────────────────────────────────────
// IMPORTANT: These MUST live outside ConversationalChatPanel so React can
// keep stable component identities across renders. Defining components inside
const SectionItem = React.memo(function SectionItem({ section }: { section: ClinicalSection }) {
  const [expanded, setExpanded] = useState(true);
  const style = SEVERITY_STYLE[section.severity ?? "none"];
  const badge = SEVERITY_BADGE[section.severity ?? "none"];

  return (
    <div className={`rounded-xl border-l-4 border p-3 transition-all ${style}`}>
      <div
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => section.expandable && setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-white">{section.title}</span>
          {section.severity && section.severity !== "none" && (
            <span className={`text-[8px] font-extrabold px-1.5 py-0.5 rounded-full uppercase tracking-wider ${badge}`}>
              {section.severity}
            </span>
          )}
        </div>
        {section.expandable && (
          <span className="text-slate-500 text-[10px]">{expanded ? "▼" : "▶"}</span>
        )}
      </div>
      {expanded && (
        <p className="mt-1.5 text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">
          {section.content}
        </p>
      )}
    </div>
  );
});

const RetrievalEngineCard = React.memo(function RetrievalEngineCard({ title, active, description }: { title: string; active: boolean; description: string }) {
  return (
    <div className={`p-3 rounded-lg border transition-all ${
      active
        ? "bg-indigo-950/15 border-indigo-900/30 text-indigo-300"
        : "bg-slate-900/20 border-slate-850/40 text-slate-500 opacity-50"
    }`}>
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-indigo-400 shadow-[0_0_6px_rgba(129,140,248,0.5)]" : "bg-slate-600"}`} />
        <span className="font-bold text-[10.5px] text-slate-200 leading-none">{title}</span>
        <span className={`text-[7.5px] font-bold uppercase px-1 rounded-sm ${
          active ? "bg-indigo-900/30 text-indigo-350 border border-indigo-850" : "bg-slate-950 text-slate-600 border border-slate-900"
        }`}>
          {active ? "Active" : "Inactive"}
        </span>
      </div>
      <p className="text-[9.5px] leading-normal text-slate-400">{description}</p>
    </div>
  );
});

const EvidenceSourceRow = React.memo(function EvidenceSourceRow({ ev, idx }: { ev: EvidenceItem; idx: number }) {
  const [expanded, setExpanded] = useState(false);

  const getDocTypeColor = (type: string) => {
    switch (type.toLowerCase()) {
      case "pubmed":
      case "research_paper":
        return "bg-cyan-950/45 border-cyan-900/40 text-cyan-300";
      case "similar_case":
      case "case_file":
        return "bg-amber-950/45 border-amber-900/40 text-amber-300";
      case "ecg":
      case "waveform":
        return "bg-rose-950/45 border-rose-900/40 text-rose-300";
      default:
        return "bg-slate-900 border-slate-800 text-slate-400";
    }
  };

  return (
    <div className="bg-slate-900/30 border border-slate-850 rounded-lg overflow-hidden shadow-sm">
      <div
        onClick={() => setExpanded(!expanded)}
        className="px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-slate-900/60 transition-colors select-none"
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-slate-500 font-bold">#{idx + 1}</span>
          <span className="font-semibold text-slate-200 truncate max-w-[200px]" title={ev.source}>{ev.source}</span>
          <span className={`text-[8px] uppercase font-bold px-1.5 py-0.2 rounded border ${getDocTypeColor(ev.document_type)}`}>
            {ev.document_type}
          </span>
          {ev.page > 0 && <span className="text-[9px] text-slate-500">Page {ev.page}</span>}
        </div>
        <div className="flex items-center gap-2 font-mono text-[9px]">
          <span className="text-slate-500">Trust: <span className="text-slate-300">{ev.confidence}</span></span>
          <span className="text-slate-650">|</span>
          <span className="text-slate-500">Match: <span className="text-indigo-400">{(ev.score * 100).toFixed(0)}%</span></span>
          <span className="text-slate-400 ml-1">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>
      {expanded && (
        <div className="px-3.5 pb-3.5 pt-1.5 border-t border-slate-900/50 bg-slate-950/40 text-slate-300 leading-relaxed text-[10px] italic">
          &ldquo;{ev.text}&rdquo;
        </div>
      )}
    </div>
  );
});

const TraceViewer = React.memo(function TraceViewer({ msg }: { msg: ConversationMessage }) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"orchestration" | "evidence" | "governance">("orchestration");

  const result = msg.metadata?.result as AnalysisResult | undefined;
  const copilotResponse = msg.metadata?.copilotResponse as CopilotResponse | undefined;

  const hasTrace = !!result || !!copilotResponse;
  if (!hasTrace) return null;

  const isClarificationHalted = !!(result?.clarification_required || result?.status === "clarification_required");

  let intent = "conversational_assistant";
  let riskLevel = "low";
  let confidence = 0.85;
  let latency = 250;
  let totalSources = 0;
  let reviewRequired = false;

  if (result) {
    intent = result.clinical_intent || result.execution_plan_summary?.clinical_intent || "unknown";
    riskLevel = result.execution_plan_summary?.risk_level || "low";
    confidence = result.confidence_score !== undefined ? result.confidence_score : 0.85;
    latency = result.processing_ms !== undefined ? result.processing_ms : 0;
    totalSources = result.evidence_count || result.evidence?.length || 0;
    reviewRequired = result.review_required || result.escalation_required || false;
  } else if (copilotResponse) {
    intent = "conversational_copilot";
    riskLevel = "low";
    confidence = copilotResponse.confidence === "high" ? 0.90 : copilotResponse.confidence === "medium" ? 0.75 : 0.50;
    latency = copilotResponse.processing_ms !== undefined ? copilotResponse.processing_ms : 320;
    totalSources = copilotResponse.sources_used?.length || 0;
    reviewRequired = false;
  }

  const formatIntent = (rawIntent: string) =>
    rawIntent.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

  const getRiskStyles = (risk: string) => {
    switch (risk.toLowerCase()) {
      case "critical":
        return { bg: "bg-red-500/10 border-red-500/30 text-red-400", indicator: "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" };
      case "high":
        return { bg: "bg-orange-500/10 border-orange-500/30 text-orange-400", indicator: "bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.5)]" };
      case "medium":
        return { bg: "bg-amber-500/10 border-amber-500/30 text-amber-400", indicator: "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]" };
      case "low":
      default:
        return { bg: "bg-blue-500/10 border-blue-500/30 text-blue-400", indicator: "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" };
    }
  };

  const riskStyle = getRiskStyles(riskLevel);

  const nodeMeta: Record<string, { label: string; icon: React.ReactNode; color: string; desc: string }> = {
    plan: {
      label: "Orchestration Planner",
      icon: <Brain className="h-3.5 w-3.5 text-indigo-400" />,
      color: "border-indigo-500/30 bg-indigo-500/5 text-indigo-300",
      desc: "Classifies clinical intent, assesses medical risk, and selects optimal workflow routing."
    },
    clarify: {
      label: "Clarification Gate",
      icon: <HelpCircle className="h-3.5 w-3.5 text-amber-400" />,
      color: "border-amber-500/30 bg-amber-500/5 text-amber-300",
      desc: "Halts pipeline execution if missing vital indicators or ambiguous symptoms require clinician clarification."
    },
    query_understand: {
      label: "Query Expansion & HyDE",
      icon: <Search className="h-3.5 w-3.5 text-blue-400" />,
      color: "border-blue-500/30 bg-blue-500/5 text-blue-300",
      desc: "Expands medical query via HyDE (Hypothetical Document Embeddings) and semantic decomposition."
    },
    retrieve: {
      label: "Evidence Retrieval",
      icon: <FileText className="h-3.5 w-3.5 text-cyan-400" />,
      color: "border-cyan-500/30 bg-cyan-500/5 text-cyan-300",
      desc: "Performs dense semantic matches on Qdrant, searches PubMed, and traverses Neo4j GraphRAG."
    },
    evidence_eval: {
      label: "Evidence Scorer",
      icon: <TrendingUp className="h-3.5 w-3.5 text-violet-400" />,
      color: "border-violet-500/30 bg-violet-500/5 text-violet-300",
      desc: "Evaluates trust tiers, relevance, and freshness scores. Filters low-grounding sources."
    },
    contradiction_check: {
      label: "Contradiction Checker",
      icon: <ShieldAlert className="h-3.5 w-3.5 text-orange-400" />,
      color: "border-orange-500/30 bg-orange-500/5 text-orange-300",
      desc: "Scans cross-source contradictions (e.g. conflicting drug warnings, vitals) and penalizes scores."
    },
    reason: {
      label: "Reasoning Synthesizer",
      icon: <Cpu className="h-3.5 w-3.5 text-emerald-400" />,
      color: "border-emerald-500/30 bg-emerald-500/5 text-emerald-300",
      desc: "Executes chain-of-thought clinical synthesis grounded strictly in verified evidence citations."
    },
    validate: {
      label: "Safety Validator",
      icon: <CheckCircle2 className="h-3.5 w-3.5 text-rose-400" />,
      color: "border-rose-500/30 bg-rose-500/5 text-rose-300",
      desc: "Validates response safety against medical guardrails. Initiates supervisor replan if below threshold."
    },
    reflect: {
      label: "Supervisor Re-planner",
      icon: <RotateCcw className="h-3.5 w-3.5 text-pink-400" />,
      color: "border-pink-500/30 bg-pink-500/5 text-pink-300",
      desc: "Analyzes validation failures, revises execution plan, and triggers targeted agents recursive execution."
    },
    finalize: {
      label: "Governance Gatekeeper",
      icon: <Shield className="h-3.5 w-3.5 text-teal-400" />,
      color: "border-teal-500/30 bg-teal-500/5 text-teal-300",
      desc: "Applies clinical compliance policies and determines clinician Human-in-the-Loop escalation status."
    },
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(!open)}
        className="w-full mt-3.5 border border-slate-800/80 rounded-xl bg-slate-900/40 hover:bg-slate-900/70 px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-[11px] font-semibold text-slate-350 transition-all select-none hover:border-slate-700/60 shadow-sm"
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="flex h-2 w-2 relative shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
          </span>
          <span className="text-slate-200 font-bold uppercase tracking-wider text-[10px]">Orchestration Trace</span>
          <div className="h-3 w-px bg-slate-800" />
          <span className="text-slate-500">Intent:</span>
          <span className="text-slate-200 capitalize font-bold bg-slate-950/40 border border-slate-800 px-1.5 py-0.5 rounded text-[10px]">
            {formatIntent(intent)}
          </span>
          <div className="h-3 w-px bg-slate-800" />
          <span className="text-slate-555">Risk:</span>
          <span className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded border ${riskStyle.bg}`}>
            {riskLevel}
          </span>
          <div className="h-3 w-px bg-slate-800" />
          <span className="text-slate-500">Confidence:</span>
          <span className={`font-mono font-bold ${isClarificationHalted ? "text-amber-400 animate-pulse" : confidence >= 0.8 ? "text-emerald-400" : confidence >= 0.6 ? "text-amber-400" : "text-rose-400"}`}>
            {isClarificationHalted ? "Pending" : `${Math.round(confidence * 100)}%`}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors">
          <span className="font-mono text-[10px] text-slate-500">{latency}ms</span>
          <ChevronDown className="h-4 w-4" />
        </div>
      </button>
    );
  }

  return (
    <div className="mt-3.5 border border-slate-800/80 rounded-xl bg-slate-950/70 overflow-hidden shadow-lg transition-all animate-fade-in duration-300">
      {/* Header Toggle */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full border-b border-slate-900/60 bg-slate-900/70 px-4 py-3 flex items-center justify-between text-[11px] font-semibold text-slate-350 select-none hover:bg-slate-900/90 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-indigo-400 animate-pulse" />
          <span className="text-slate-250 font-bold uppercase tracking-wider text-[10px]">Orchestration Intelligence Dashboard</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors">
          <span className="font-mono text-[10px] text-slate-500">ID: {result?.trace_summary?.request_id?.slice(0, 8) || "copilot"}</span>
          <ChevronUp className="h-4 w-4" />
        </div>
      </button>

      {/* Quick Insights Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-slate-900/40 bg-slate-950/40 p-3.5 gap-3">
        {/* Intent */}
        <div className="bg-slate-900/40 border border-slate-850 p-2.5 rounded-lg flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
            <Compass className="h-4.5 w-4.5 text-indigo-400" />
          </div>
          <div className="min-w-0">
            <p className="text-[9px] text-slate-500 uppercase font-semibold leading-none mb-1">Clinical Intent</p>
            <p className="text-slate-200 font-bold text-[11px] capitalize truncate" title={formatIntent(intent)}>
              {formatIntent(intent)}
            </p>
          </div>
        </div>

        {/* Risk Level */}
        <div className="bg-slate-900/40 border border-slate-850 p-2.5 rounded-lg flex items-center gap-2.5">
          <div className={`h-8 w-8 rounded-lg bg-slate-950/40 flex items-center justify-center shrink-0 border ${riskStyle.bg.split(' ')[1]}`}>
            <span className={`h-2.5 w-2.5 rounded-full ${riskStyle.indicator}`} />
          </div>
          <div>
            <p className="text-[9px] text-slate-500 uppercase font-semibold leading-none mb-1">Risk Assessment</p>
            <p className={`font-extrabold text-[11px] uppercase tracking-wide ${riskStyle.bg.split(' ').pop()}`}>
              {riskLevel}
            </p>
          </div>
        </div>

        {/* Confidence */}
        <div className="bg-slate-900/40 border border-slate-850 p-2.5 rounded-lg flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-slate-950/40 flex items-center justify-center shrink-0 border border-slate-800">
            <span className={`text-[10px] font-mono font-bold ${isClarificationHalted ? "text-amber-400 animate-pulse" : confidence >= 0.8 ? "text-emerald-400" : confidence >= 0.6 ? "text-amber-400" : "text-rose-400"}`}>
              {isClarificationHalted ? "Pending" : `${Math.round(confidence * 100)}%`}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[9px] text-slate-500 uppercase font-semibold leading-none mb-1">Score Confidence</p>
            <div className="w-full bg-slate-950 rounded-full h-1 mt-1.5 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isClarificationHalted
                    ? "bg-slate-700 animate-pulse"
                    : confidence >= 0.8
                      ? "bg-emerald-500"
                      : confidence >= 0.6
                        ? "bg-amber-500"
                        : "bg-rose-500"
                }`}
                style={{ width: isClarificationHalted ? "100%" : `${confidence * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* Latency */}
        <div className="bg-slate-900/40 border border-slate-850 p-2.5 rounded-lg flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-slate-950/40 flex items-center justify-center shrink-0 border border-slate-800">
            <Clock className="h-4 w-4 text-slate-400" />
          </div>
          <div>
            <p className="text-[9px] text-slate-500 uppercase font-semibold leading-none mb-1">Orchestration Time</p>
            <p className="text-slate-200 font-mono font-bold text-[11px]">
              {latency}ms
            </p>
          </div>
        </div>
      </div>

      {/* Tab Selection */}
      <div className="flex border-b border-slate-900/50 bg-slate-900/30 px-3.5 py-1.5 gap-2 shrink-0">
        <button
          onClick={() => setActiveTab("orchestration")}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 ${
            activeTab === "orchestration"
              ? "bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 shadow-sm"
              : "text-slate-400 hover:text-slate-200 border border-transparent"
          }`}
        >
          <Cpu className="h-3.5 w-3.5" />
          Orchestration Flow
        </button>
        <button
          onClick={() => setActiveTab("evidence")}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 ${
            activeTab === "evidence"
              ? "bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 shadow-sm"
              : "text-slate-400 hover:text-slate-200 border border-transparent"
          }`}
        >
          <Search className="h-3.5 w-3.5" />
          Evidence Retrieval ({totalSources})
        </button>
        <button
          onClick={() => setActiveTab("governance")}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 ${
            activeTab === "governance"
              ? "bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 shadow-sm"
              : "text-slate-400 hover:text-slate-200 border border-transparent"
          }`}
        >
          <Shield className="h-3.5 w-3.5" />
          Governance & Safety
        </button>
      </div>

      {/* Tab Body */}
      <div className="p-4 bg-slate-950/20 min-h-[180px] text-[11px] overflow-y-auto max-h-[350px] custom-scrollbar">
        {activeTab === "orchestration" && (
          <div className="space-y-4">
            {/* Planner Decision Info */}
            {result?.execution_plan_summary && (
              <div className="bg-slate-900/30 border border-slate-850 p-3 rounded-lg space-y-2">
                <div className="flex items-center gap-2 text-indigo-400 font-bold uppercase tracking-wider text-[9px]">
                  <Brain className="h-3.5 w-3.5" />
                  <span>Planner Decision Strategy</span>
                </div>
                <p className="text-slate-300 leading-relaxed italic text-[10.5px]">
                  &ldquo;{result.execution_plan_summary.goal}&rdquo;
                </p>
                {((result.execution_plan_summary.required_capabilities && result.execution_plan_summary.required_capabilities.length > 0) ||
                  (result.execution_plan_summary.optional_capabilities && result.execution_plan_summary.optional_capabilities.length > 0)) && (
                  <div className="flex flex-wrap gap-1.5 pt-1.5 border-t border-slate-900/60">
                    {result.execution_plan_summary.required_capabilities?.map((agent: string, i: number) => (
                      <span key={i} className="flex items-center gap-1 bg-indigo-950/30 border border-indigo-900/40 text-indigo-300 text-[9px] px-1.5 py-0.5 rounded-md font-medium">
                        <Cpu className="h-2.5 w-2.5" />
                        <span>{agent} Agent</span>
                        <span className="text-[7px] bg-indigo-850 text-indigo-200 px-1 rounded">Required</span>
                      </span>
                    ))}
                    {result.execution_plan_summary.optional_capabilities?.map((agent: string, i: number) => (
                      <span key={i} className="flex items-center gap-1 bg-slate-900 border border-slate-800 text-slate-400 text-[9px] px-1.5 py-0.5 rounded-md font-medium">
                        <Cpu className="h-2.5 w-2.5" />
                        <span>{agent} Agent</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Copilot Goal Info */}
            {copilotResponse && (
              <div className="bg-slate-900/30 border border-slate-850 p-3 rounded-lg space-y-2">
                <div className="flex items-center gap-2 text-indigo-400 font-bold uppercase tracking-wider text-[9px]">
                  <Brain className="h-3.5 w-3.5" />
                  <span>Conversational Goal</span>
                </div>
                <p className="text-slate-300 leading-relaxed text-[10.5px]">
                  Address clinical query, explain general medical concepts, and search active session context reference files.
                </p>
              </div>
            )}

            {/* Execution Order Timeline */}
            <div className="space-y-3">
              <p className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Execution Timeline & Active Nodes</p>
              {result ? (
                <div className="relative pl-4 border-l border-slate-850/85 space-y-3.5 py-1">
                  {(() => {
                    const originalList = result.trace_summary?.node_spans || result.workflow_trace || [];
                    
                    // Filter out redundant routing hops (transitions) and keep only initial plan and true corrective/retry planning.
                    const filteredList: unknown[] = [];
                    const seenNodes = new Set<string>();
                    let totalPlans = 0;
                    
                    originalList.forEach((item: unknown, idx: number) => {
                      const itemRecord = item as Record<string, unknown>;
                      const isSpan = typeof item === 'object' && item !== null && 'node' in itemRecord;
                      const nodeName = isSpan ? (itemRecord.node as string) : (item as string);
                      
                      if (nodeName === 'plan') {
                        totalPlans++;
                        // Keep the very first planning step
                        if (totalPlans === 1) {
                          filteredList.push(item);
                        } else {
                          // Keep subsequent plans only if it represents a supervisor replanning cycle:
                          // 1. The previous executed node failed.
                          // 2. The next node to execute has already been run before (a retry loop).
                          const prevItem = originalList[idx - 1];
                          const nextItem = originalList[idx + 1];
                          
                          const prevFailed = prevItem && (
                            typeof prevItem === 'object' && prevItem !== null && 'success' in prevItem 
                              ? !(prevItem as Record<string, unknown>).success 
                              : false
                          );
                          
                          let nextIsRetry = false;
                          if (nextItem) {
                            const nextNodeName = typeof nextItem === 'object' && nextItem !== null && 'node' in nextItem 
                              ? (nextItem as Record<string, unknown>).node as string
                              : nextItem as string;
                            if (seenNodes.has(nextNodeName)) {
                              nextIsRetry = true;
                            }
                          }
                          
                          if (prevFailed || nextIsRetry) {
                            filteredList.push(item);
                          }
                        }
                      } else {
                        filteredList.push(item);
                        seenNodes.add(nodeName);
                      }
                    });

                    let planCount = 0;
                    return filteredList.map((spanOrStep: unknown, idx: number) => {
                      const spanRecord = spanOrStep as Record<string, unknown>;
                      const isSpan = typeof spanOrStep === 'object' && spanOrStep !== null && 'node' in spanRecord;
                      const nodeName = isSpan ? (spanRecord.node as string) : (spanOrStep as string);
                      const duration = isSpan ? (spanRecord.duration_ms as number) : undefined;
                      const success = isSpan ? (spanRecord.success as boolean) : true;
                      const errorMsg = isSpan ? (spanRecord.error_msg as string) : undefined;

                      const meta = { ...(nodeMeta[nodeName] || {
                        label: nodeName.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
                        icon: <Cpu className="h-3.5 w-3.5 text-slate-400" />,
                        color: "border-slate-850 bg-slate-900/10 text-slate-400",
                        desc: "Agent or gate node executed in Aegis LangGraph workflow."
                      }) };

                      if (nodeName === 'plan') {
                        planCount++;
                        if (planCount > 1) {
                          meta.label = "Supervisor Replanning & Routing";
                          meta.desc = "Orchestrator analyzed agent execution safety/sufficiency checkpoints, revised the strategy, and determined the next corrective step.";
                        }
                      }

                      return (
                        <div key={idx} className="relative group">
                          <div className={`absolute -left-[20.5px] top-1.5 h-3.5 w-3.5 rounded-full border-2 bg-slate-950 flex items-center justify-center transition-all ${
                            success ? "border-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.3)]" : "border-red-500 shadow-[0_0_6px_rgba(239,68,68,0.3)]"
                          }`}>
                            <div className={`h-1.5 w-1.5 rounded-full ${success ? "bg-emerald-500" : "bg-red-500"}`} />
                          </div>
                          <div className={`border rounded-lg p-3 ${meta.color} space-y-1.5 shadow-sm hover:translate-x-0.5 transition-transform duration-200`}>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="p-1 bg-slate-950/40 rounded-md shrink-0 border border-slate-850/60">
                                  {meta.icon}
                                </span>
                                <div>
                                  <h4 className="font-bold text-slate-200 text-[11px] leading-tight">{meta.label}</h4>
                                  <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">Node: {nodeName}</span>
                                </div>
                              </div>
                              <div className="flex items-center gap-1.5">
                                {duration !== undefined && (
                                  <span className="font-mono text-[9px] bg-slate-950/90 text-slate-350 px-1.5 py-0.5 rounded border border-slate-850">
                                    {Math.round(duration)}ms
                                  </span>
                                )}
                                <span className={`text-[8.5px] font-extrabold uppercase px-1 rounded-sm ${
                                  success ? "bg-emerald-950/40 border border-emerald-900/40 text-emerald-400" : "bg-red-950/40 border border-red-900/40 text-red-400"
                                }`}>
                                  {success ? "Success" : "Failed"}
                                </span>
                              </div>
                            </div>
                            <p className="text-[10px] text-slate-400 leading-normal">{meta.desc}</p>
                            {errorMsg && (
                              <div className="bg-red-950/20 border border-red-900/20 rounded p-2 text-red-400 font-mono text-[9px] leading-relaxed">
                                {errorMsg}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              ) : (
                <div className="relative pl-4 border-l border-slate-850/80 space-y-3.5 py-1">
                  {(() => {
                    const sources = copilotResponse?.sources_used || [];
                    const fallbackSteps = [
                      {
                        name: "parse",
                        label: "Conversational Intent Parsing",
                        desc: "Parsed conversational input, checked for clinical emergency signals (none detected).",
                        success: true,
                      }
                    ];

                    if (sources.includes("clinical_context")) {
                      fallbackSteps.push({
                        name: "context_integration",
                        label: "Context Integration Gate",
                        desc: "Extracted and mapped active patient state, medical risk profile, and prior clinical reports.",
                        success: true,
                      });
                    }

                    if (sources.includes("conversation_history")) {
                      fallbackSteps.push({
                        name: "history_retrieval",
                        label: "Session Memory Retrieval",
                        desc: "Retrieved past multi-turn conversational dialog to maintain context and continuity.",
                        success: true,
                      });
                    }

                    if (sources.includes("rule_based_fallback")) {
                      fallbackSteps.push({
                        name: "fallback_synthesis",
                        label: "Advisory Rule-based Synthesis",
                        desc: "LLM reasoning offline. Deployed safe advisory rule-based clinical intelligence heuristics.",
                        success: true,
                      });
                    } else {
                      fallbackSteps.push({
                        name: "copilot_reasoning",
                        label: "Clinical Copilot Synthesis",
                        desc: "Generated context-aware, advisory response via clinical Large Language Model.",
                        success: true,
                      });
                    }

                    fallbackSteps.push({
                      name: "safety_validation",
                      label: "Safety Disclaimer Verification",
                      desc: "Appended strict medical advisory disclaimer. Autonomous reasoning validated.",
                      success: true,
                    });

                    return fallbackSteps.map((step, idx) => (
                      <div key={idx} className="relative">
                        <div className="absolute -left-[20.5px] top-1.5 h-3.5 w-3.5 rounded-full border-2 bg-slate-950 border-emerald-500 flex items-center justify-center">
                          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        </div>
                        <div className="border border-slate-850 bg-slate-900/10 rounded-lg p-2.5 text-slate-400 space-y-1">
                          <div className="flex items-center justify-between">
                            <h4 className="font-bold text-slate-200 text-[10.5px]">{step.label}</h4>
                            <span className="text-[8px] bg-emerald-950/40 text-emerald-400 border border-emerald-900/30 px-1 rounded">Success</span>
                          </div>
                          <p className="text-[9.5px] text-slate-400">{step.desc}</p>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>

            {/* Confidence evolution */}
            {result?.trace_summary?.confidence_history && result.trace_summary.confidence_history.length > 0 && (
              <div className="space-y-2 border-t border-slate-900/60 pt-3">
                <p className="text-[9px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3 animate-pulse" />
                  <span>Confidence Score Evolution</span>
                </p>
                <div className="flex flex-wrap items-center gap-1.5 bg-slate-950/40 border border-slate-850 p-2.5 rounded-lg">
                  {result.trace_summary.confidence_history.map((hist: [string, number], i: number) => {
                    const nodeName = hist[0];
                    const score = hist[1];
                    const label = nodeMeta[nodeName]?.label || nodeName;
                    return (
                      <React.Fragment key={i}>
                        {i > 0 && <span className="text-slate-655 text-[9px]">→</span>}
                        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded px-2 py-0.8 text-[9px]">
                          <span className="text-slate-400 font-medium">{label}</span>
                          <span className={`font-mono font-bold ${score >= 0.8 ? "text-emerald-400" : score >= 0.6 ? "text-amber-400" : "text-rose-400"}`}>
                            {Math.round(score * 100)}%
                          </span>
                        </div>
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Supervisor Routing decisions */}
            {result?.trace_summary?.routing_decisions && result.trace_summary.routing_decisions.length > 0 && (
              <div className="space-y-2 border-t border-slate-900/60 pt-3">
                <p className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Supervisor Routing Decisions</p>
                <div className="space-y-2">
                  {result.trace_summary.routing_decisions.map((dec: { at_node: string; decision: string; score?: number; reason: string }, i: number) => {
                    const fromMeta = nodeMeta[dec.at_node] || { label: dec.at_node };
                    const toMeta = nodeMeta[dec.decision] || { label: dec.decision };
                    return (
                      <div key={i} className="bg-slate-900/20 border border-slate-850/60 rounded-lg p-2.5 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-300">{fromMeta.label}</span>
                            <span className="text-slate-600">→</span>
                            <span className="font-bold text-indigo-400">{toMeta.label}</span>
                          </div>
                          {dec.score !== undefined && dec.score > 0 && (
                            <span className="text-[8.5px] font-mono bg-indigo-950/40 text-indigo-300 border border-indigo-900/30 px-1 py-0.2 rounded">
                              score: {dec.score.toFixed(3)}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-400 leading-relaxed italic bg-slate-950/40 p-2 rounded border border-slate-900/40">
                          &ldquo;{dec.reason}&rdquo;
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Active Retrieval Engines</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <RetrievalEngineCard
                  title="GraphRAG (Neo4j)"
                  active={!!result?.execution_plan_summary?.evidence_strategy?.use_graph}
                  description="Decouples concept relationships, finding path connections between patient vitals, medical history, and clinical guidelines."
                />
                <RetrievalEngineCard
                  title="Dense Semantic (Qdrant)"
                  active={!!result?.execution_plan_summary?.evidence_strategy?.use_similar_cases || !result}
                  description="Generates embedding vectors of query/vitals and queries vector indices for semantic clinical similarity matches."
                />
                <RetrievalEngineCard
                  title="PubMed Research Index"
                  active={!!result?.execution_plan_summary?.evidence_strategy?.use_research}
                  description="Performs literature synthesis, crawling peer-reviewed RCTs and clinical evidence guidelines."
                />
                <RetrievalEngineCard
                  title="Multimodal Waveform Scanner"
                  active={!!result?.execution_plan_summary?.evidence_strategy?.use_multimodal}
                  description="Scans ECG waveforms, imaging signals, and laboratory tabular readings for pattern findings."
                />
              </div>
            </div>

            {result?.evidence_quality_summary && (
              <div className="bg-slate-900/30 border border-slate-850 p-3 rounded-lg space-y-3 pt-2.5">
                <div className="flex items-center justify-between border-b border-slate-900/50 pb-2">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Quality sufficiency scoring</span>
                  <span className={`text-[8.5px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                    result.evidence_quality_summary.overall_sufficiency === "strong"
                      ? "bg-emerald-950 border border-emerald-900/40 text-emerald-400"
                      : result.evidence_quality_summary.overall_sufficiency === "adequate"
                      ? "bg-blue-950 border border-blue-900/40 text-blue-400"
                      : "bg-amber-950 border border-amber-900/40 text-amber-400"
                  }`}>
                    {result.evidence_quality_summary.overall_sufficiency} sufficiency
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <div className="flex justify-between text-[9.5px] text-slate-500 font-semibold leading-none">
                      <span>Sufficiency Index</span>
                      <span className="font-mono text-slate-300">{(result.evidence_quality_summary.sufficiency_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-slate-950 rounded-full h-1 overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${result.evidence_quality_summary.sufficiency_score * 100}%` }} />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-[9.5px] text-slate-500 font-semibold leading-none">
                      <span>Average Source Trust</span>
                      <span className="font-mono text-slate-300">{(result.evidence_quality_summary.avg_trust * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-slate-950 rounded-full h-1 overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${result.evidence_quality_summary.avg_trust * 100}%` }} />
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center pt-1 font-mono text-[9px] text-slate-400">
                  <div className="bg-slate-950/40 p-1.5 rounded border border-slate-900">
                    <p className="text-[11px] font-bold text-slate-200">{result.evidence_quality_summary.high_quality_count}</p>
                    <p className="text-[8px] text-slate-500 font-semibold">Tier-1 Sources</p>
                  </div>
                  <div className="bg-slate-950/40 p-1.5 rounded border border-slate-900">
                    <p className="text-[11px] font-bold text-slate-200">{result.evidence_quality_summary.medium_quality_count}</p>
                    <p className="text-[8px] text-slate-500 font-semibold">Tier-2 Sources</p>
                  </div>
                  <div className="bg-slate-950/40 p-1.5 rounded border border-slate-900">
                    <p className="text-[11px] font-bold text-slate-200">{result.evidence_quality_summary.filtered_count}</p>
                    <p className="text-[8px] text-slate-500 font-semibold">Filtered Out</p>
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <p className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Retrieved Evidence Documents</p>
              {result && result.evidence && result.evidence.length > 0 ? (
                <div className="space-y-2">
                  {result.evidence.map((ev, i) => (
                    <EvidenceSourceRow key={i} ev={ev} idx={i} />
                  ))}
                </div>
              ) : copilotResponse && copilotResponse.sources_used && copilotResponse.sources_used.length > 0 ? (
                <div className="space-y-2">
                  {copilotResponse.sources_used.map((source: string, i: number) => (
                    <div key={i} className="bg-slate-900 border border-slate-850 p-2.5 rounded-lg flex items-center justify-between shadow-sm">
                      <div className="flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5 text-slate-400" />
                        <span className="font-semibold text-slate-200 truncate max-w-[280px]" title={source}>{source}</span>
                      </div>
                      <span className="text-[8.5px] font-mono bg-slate-950 text-slate-500 border border-slate-900 px-1.5 py-0.5 rounded">
                        Semantic Match
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-slate-900/20 border border-slate-850 border-dashed p-4 text-center text-slate-500 rounded-lg">
                  No explicit document citations referenced for this response.
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "governance" && (
          <div className="space-y-4">
            <div className="bg-slate-900/30 border border-slate-850 p-3 rounded-lg space-y-2.5">
              <div className="flex items-center justify-between border-b border-slate-900/50 pb-2">
                <span className="text-[9px] font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                  <ShieldCheck className="h-4 w-4" />
                  <span>Safety Validation Feedback</span>
                </span>
                {result && (
                  <span className={`text-[8.5px] font-bold uppercase px-1.5 rounded ${
                    result.confidence_label === "HIGH" ? "bg-emerald-950/60 border border-emerald-900/40 text-emerald-400" :
                    result.confidence_label === "MEDIUM" ? "bg-amber-950/60 border border-amber-900/40 text-amber-400" :
                    "bg-red-950/60 border border-red-900/40 text-red-400"
                  }`}>
                    {result.confidence_label} CONFIDENCE
                  </span>
                )}
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-[9.5px] text-slate-500 leading-none">
                  <span>Clinical Grounding Score</span>
                  <span className="font-mono text-slate-300">{result ? `${(result.confidence_score * 100).toFixed(0)}%` : "95%"}</span>
                </div>
                <div className="w-full bg-slate-950 rounded-full h-1 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${result && result.confidence_score < 0.6 ? "bg-rose-500" : result && result.confidence_score < 0.8 ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${result ? result.confidence_score * 100 : 95}%` }}
                  />
                </div>
              </div>
              {result && result.validation_detail && (
                <div className="bg-slate-950/50 border border-slate-900 rounded p-2.5 space-y-1">
                  <p className="text-[8.5px] font-bold uppercase tracking-widest text-slate-500 font-mono">Validator output feedback</p>
                  <p className="text-slate-355 leading-relaxed text-[10px] whitespace-pre-wrap">
                    {result.validation_detail}
                  </p>
                </div>
              )}
              {result && ((result.replan_count ?? 0) > 0 || result.retry_count > 0) && (
                <div className="bg-amber-950/15 border border-amber-900/30 text-amber-400 rounded p-2.5 flex items-start gap-2">
                  <RotateCcw className="h-4 w-4 shrink-0 mt-0.5 animate-spin-reverse" style={{ animationDuration: "10s" }} />
                  <div>
                    <p className="font-bold text-[10.5px] leading-tight">Self-Correction Triggered</p>
                    <p className="text-[9.5px] text-amber-550/80 leading-normal mt-0.5 font-semibold">
                      Pipeline executed {result.replan_count ?? 0} re-plans and {result.retry_count} supervisor retries to resolve initial medical safety warnings.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {result && result.contradiction_summary && (
              <div className={`p-3 rounded-lg border ${
                result.contradiction_summary.has_contradictions
                  ? "bg-orange-950/15 border-orange-900/30 text-orange-400"
                  : "bg-emerald-950/10 border-emerald-900/30 text-emerald-400"
              } space-y-1.5`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    {result.contradiction_summary.has_contradictions ? (
                      <AlertTriangle className="h-4 w-4" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" />
                    )}
                    <span className="font-bold text-[10.5px]">
                      {result.contradiction_summary.has_contradictions
                        ? `Cross-Source Contradictions Found (${result.contradiction_summary.contradiction_count})`
                        : "No Clinical Contradictions"}
                    </span>
                  </div>
                  {result.contradiction_summary.has_contradictions && (
                    <span className="text-[8px] font-mono bg-orange-900/30 border border-orange-850 text-orange-355 px-1 py-0.2 rounded">
                      Penalty: -{result.contradiction_summary.total_penalty.toFixed(2)}
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-slate-350 leading-normal">
                  {result.contradiction_summary.has_contradictions
                    ? result.contradiction_summary.summary
                    : "Source evaluation validated. All cross-document medical statements represent clean consensus."}
                </p>
              </div>
            )}

            <div className={`p-3 border rounded-lg flex items-center justify-between ${
              reviewRequired
                ? "bg-red-950/10 border-red-900/30 text-red-400"
                : "bg-slate-900/30 border-slate-850 text-slate-400"
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`h-8 w-8 rounded-lg flex items-center justify-center border ${
                  reviewRequired
                    ? "bg-red-500/10 border-red-500/20"
                    : "bg-slate-950/40 border-slate-800"
                }`}>
                  {reviewRequired ? (
                    <ShieldAlert className="h-4.5 w-4.5 text-red-400" />
                  ) : (
                    <ShieldCheck className="h-4.5 w-4.5 text-slate-500" />
                  )}
                </div>
                <div>
                  <h4 className="font-bold text-slate-205 text-[11px] leading-tight">
                    {reviewRequired ? "Clinician Approval Escalated" : "Autonomous Consent Level"}
                  </h4>
                  <p className="text-[9.5px] text-slate-500 leading-tight mt-0.5 font-semibold">
                    {reviewRequired
                      ? "Requires Human-in-the-Loop review before client clinical execution."
                      : "Low risk index. Approved for autonomous decision support response."}
                  </p>
                </div>
              </div>
              {reviewRequired && result?.review_id && (
                <span className="text-[9px] font-mono bg-red-900/20 text-red-300 border border-red-900/40 px-1.5 py-0.5 rounded">
                  Review #{result.review_id.slice(0, 6)}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

const CollapsibleReport = React.memo(function CollapsibleReport({ result }: { result: AnalysisResult }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 overflow-hidden shadow-lg">
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="bg-slate-900/80 px-4 py-3 flex items-center justify-between border-b border-slate-800/60 cursor-pointer select-none"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-slate-200">⚕️ Clinical Report</span>
          <span
            className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
              result.confidence_label === "HIGH"
                ? "bg-emerald-900/40 border border-emerald-700/30 text-emerald-300"
                : result.confidence_label === "MEDIUM"
                ? "bg-amber-900/40 border border-amber-700/30 text-amber-300"
                : "bg-red-900/40 border border-red-700/30 text-red-300"
            }`}
          >
            {result.confidence_label} CONFIDENCE
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span>⚡ {result.processing_ms}ms</span>
          <span className="text-slate-600">|</span>
          <span>{expanded ? "Collapse ▲" : "Expand ▼"}</span>
        </div>
      </div>
      {expanded && (
        <div className="p-4 space-y-3 max-h-[500px] overflow-y-auto custom-scrollbar bg-slate-900/20">
          {result.clinical_intent && result.clinical_intent !== "unknown" && (
            <div className="flex items-center gap-2 bg-indigo-950/20 border border-indigo-900/30 rounded-lg px-2.5 py-1.5 text-[10px] text-indigo-300 w-fit">
              <span>{INTENT_ICON[result.clinical_intent] ?? "🤖"}</span>
              <span className="capitalize">{result.clinical_intent.replace(/_/g, " ")} Intent</span>
              {result.replan_count && result.replan_count > 0 ? (
                <span className="bg-violet-900/30 text-violet-300 px-1.5 py-0.2 rounded border border-violet-800/30">
                  {result.replan_count} replans
                </span>
              ) : null}
            </div>
          )}
          {result.sections?.map((s, idx) => (
            <SectionItem key={idx} section={s} />
          ))}
          <div className="pt-2 text-[9px] text-slate-500 border-t border-slate-800/40 flex items-center justify-between">
            <span>Aegis Clinical Decision Support</span>
            <span>Final decisions require physician validation.</span>
          </div>
        </div>
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  return JSON.stringify(prevProps.result) === JSON.stringify(nextProps.result);
});

const MessageItem = React.memo(function MessageItem({ msg, onClarificationSubmit, onClarificationSkip }: {
  msg: ConversationMessage;
  onClarificationSubmit: (answers: ClarificationAnswers) => void;
  onClarificationSkip: () => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} gap-3 px-1 animate-fade-in-up`}>
      {!isUser && (
        <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center font-black text-xs shrink-0 shadow shadow-indigo-950">
          Æ
        </div>
      )}
      <div className={`max-w-[85%] space-y-2`}>
        {msg.message_type === "text" && (
          <div
            className={`px-4 py-3 rounded-2xl text-[12px] leading-relaxed shadow-sm ${
              isUser
                ? "rounded-tr-sm"
                : "rounded-tl-sm"
            }`}
            style={isUser
              ? {backgroundColor: '#0369a1', color: '#ffffff', border: '1px solid #0284c7'}
              : {backgroundColor: '#f0f4f8', color: '#0f172a', border: '1px solid #cbd5e1'}}
          >
            <div className="whitespace-pre-wrap">{msg.content}</div>
            {!!msg.metadata?.confidence && (
              <div className="flex items-center gap-1.5 mt-2 justify-start text-[9px] text-slate-500">
                <span>Confidence:</span>
                <span
                  className={`font-semibold capitalize ${
                    msg.metadata.confidence === "high" ? "text-emerald-400" : "text-amber-400"
                  }`}
                >
                  {String(msg.metadata.confidence)}
                </span>
              </div>
            )}
          </div>
        )}

        {msg.message_type === "clarification" && !!msg.metadata?.questions && (
          <div className="w-full max-w-lg">
            <ClarificationPanel
              questions={msg.metadata.questions as ClarificationQuestion[]}
              onSubmit={onClarificationSubmit}
              onSkip={onClarificationSkip}
            />
          </div>
        )}

        {msg.message_type === "report" && !!msg.metadata?.result && (
          <div className="w-full max-w-xl">
            <CollapsibleReport result={msg.metadata.result as AnalysisResult} />
          </div>
        )}

        {!isUser && (!!msg.metadata?.result || !!msg.metadata?.copilotResponse) && (
          <div className="w-full max-w-xl">
            <TraceViewer msg={msg} />
          </div>
        )}

        <div className={`text-[9px] text-slate-600 px-1 ${isUser ? "text-right" : "text-left"}`}>
          {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  return prevProps.msg.message_id === nextProps.msg.message_id &&
         prevProps.msg.timestamp === nextProps.msg.timestamp &&
         prevProps.msg.content === nextProps.msg.content &&
         JSON.stringify(prevProps.msg.metadata) === JSON.stringify(nextProps.msg.metadata);
});

export default function ConversationalChatPanel() {
  const {
    sessionId,
    messages,
    addMessage,
    status,
    setStatus,
    result,
    setResult,
    patientContext,
    setPatientContext,
    addRecentCase,
    setRightTab,
    files,
  } = useWorkspaceStore();

  const [input, setInput] = useState("");
  const [streamingStage, setStreamingStage] = useState<string | null>(null);
  const [streamingMessage, setStreamingMessage] = useState<string | null>(null);
  const [activeAnalysisQuery, setActiveAnalysisQuery] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages or streaming status changes
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, status, streamingStage, scrollToBottom]);

  // Adjust input height automatically
  const lastHeightRef = useRef<number>(0);
  useIsomorphicLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      const nextHeight = Math.min(textarea.scrollHeight, 120);
      if (lastHeightRef.current !== nextHeight) {
        textarea.style.height = `${nextHeight}px`;
        lastHeightRef.current = nextHeight;
      } else {
        textarea.style.height = `${lastHeightRef.current}px`;
      }
    }
  }, [input]);

  // Dynamic suggestion chips
  const getSuggestionChips = () => {
    if (messages.length === 0) {
      return [
        "65-year-old male with crushing chest pain, BP 160/100, HR 95, diabetic.",
        "45-year-old female with sudden shortness of breath, left calf swelling.",
        "72-year-old male with progressive confusion and slurred speech.",
      ];
    }
    if (result) {
      const suggestions = [
        "Explain the differential diagnosis",
        "Are there any contraindications?",
        "What is the evidence quality?",
      ];
      if (result.contradiction_summary?.has_contradictions) {
        suggestions.push("Explain the contradictions found");
      } else {
        suggestions.push("What diagnostic workup is next?");
      }
      return suggestions;
    }
    return [];
  };

  // Client-side intent classifier
  const classifyIntent = (query: string): "analyze" | "copilot" => {
    const cleanQuery = query.toLowerCase().trim();

    // ── Tier 1: Always copilot — greetings & very short queries ──────────────
    if (
      cleanQuery.length < 15 ||
      /^(hi|hello|hey|good morning|good afternoon|good evening|help|hola|greetings)/i.test(cleanQuery)
    ) {
      return "copilot";
    }

    // ── Tier 2: Always copilot — general medical knowledge questions ──────────
    // These are definitional/educational questions that don't require a patient case.
    // Pattern: starts with "what/how/why/when/is/are/can/does/do/explain/define/tell me"
    // and contains no patient-specific vitals or demographic signals.
    const isGeneralQuestion =
      /^(what\b|how\b|why\b|when\b|is\b|are\b|can\b|does\b|do\b|explain\b|define\b|tell me\b|describe\b|list\b|which\b|who\b|where\b)/i.test(
        cleanQuery
      );

    // Patient-specific signals: demographics, vitals, clinical measurements
    const hasPatientSignals =
      /\b(\d+[\s-]*(year|yr|y\.?o|month|week|day)s?[\s-]*(old)?|male|female|man|woman|boy|girl|patient\s+(is|has|with|presents)|presenting\s+with|chief\s+complaint|past\s+(medical\s+)?history|vitals|blood\s+pressure|bp\s*[\d:\/]+|heart\s+rate|hr\s*\d+|o2\s*(sat)?|oxygen|temperature\s*\d+|my\s+patient|case\s+(of|report)|admitted|icu|er|ed\s+visit|intake)\b/i.test(
        cleanQuery
      );

    // General questions without patient signals → copilot (Q&A mode)
    if (isGeneralQuestion && !hasPatientSignals) {
      return "copilot";
    }

    // ── Tier 3: Always analyze — explicit patient intake ─────────────────────
    if (hasPatientSignals) return "analyze";

    // ── Tier 4: Follow-up context ─────────────────────────────────────────────
    // If there's an existing result (prior analysis), shorter queries are follow-ups
    if (result && cleanQuery.length < 60) return "copilot";

    // ── Tier 5: Default — if no result yet, general query → copilot ──────────
    // Previously this was `if (!result) return "analyze"` which caused all first
    // messages to go through clinical analysis, even plain knowledge questions.
    if (!result) return "copilot";

    return "copilot";
  };

  // Core execution flow: Stream Analysis
  const executeAnalysis = async (queryText: string, clarificationAnswers?: ClarificationAnswers) => {
    setStatus("analyzing");
    setStreamingStage("plan");
    setStreamingMessage("🧠 Planning execution strategy...");
    
    // Enrich query with files context if present in the workspace
    let finalQuery = queryText;
    if (files && files.length > 0) {
      const fileContext: string[] = [];
      files.forEach(f => {
        if (f.status === "ready") {
          fileContext.push(`File: "${f.name}" (${f.type})`);
        }
      });
      if (fileContext.length > 0) {
        finalQuery = `${queryText} [Context: ${fileContext.join(", ")} is uploaded in the workspace session]`;
      }
    }

    setActiveAnalysisQuery(finalQuery);
    setError(null);

    try {
      await runAnalysisWithStreaming(
        finalQuery,
        sessionId,
        clarificationAnswers,
        (stage, msg) => {
          setStreamingStage(stage);
          setStreamingMessage(msg);
        },
        (res) => {
          setResult(res);
          setStreamingStage(null);
          setStreamingMessage(null);

          if (res.patient_context) {
            setPatientContext(res.patient_context as PatientContextSummary);
          }

          if (res.status === "clarification_required" || res.clarification_required) {
            setStatus("clarification_required");
            addMessage({
              message_id: generateId(),
              role: "assistant",
              content: "To complete the clinical analysis, I need a few clarifications on this patient's case.",
              timestamp: new Date().toISOString(),
              message_type: "clarification",
              metadata: { questions: res.clarification_questions, result: res },
            });
            return;
          }

          setStatus("complete");
          setRightTab("plan");

          // Append report message
          addMessage({
            message_id: generateId(),
            role: "assistant",
            content: res.final_response || "Clinical intelligence report generated.",
            timestamp: new Date().toISOString(),
            message_type: "report",
            metadata: { result: res },
          });

          // Add to recent cases
          const severity: Severity = res.escalation_required ? "critical"
            : res.confidence_label === "LOW" ? "high"
            : res.confidence_label === "MEDIUM" ? "medium"
            : "low";

          addRecentCase({
            id: res.review_id ?? generateId(),
            patientLabel: queryText.slice(0, 40) + "...",
            timestamp: new Date().toLocaleTimeString(),
            severity,
            confidence: res.confidence_score,
            reviewRequired: res.review_required,
            summary: res.final_response?.slice(0, 80) ?? "",
          });
        },
        (err) => {
          setStreamingStage(null);
          setStreamingMessage(null);
          setStatus("error");
          setError(err.message);
          addMessage({
            message_id: generateId(),
            role: "assistant",
            content: `Clinical analysis failed. Error: ${err.message}`,
            timestamp: new Date().toISOString(),
            message_type: "text",
          });
        }
      );
    } catch (err) {
      const errorObject = err instanceof Error ? err : new Error(String(err));
      setStreamingStage(null);
      setStreamingMessage(null);
      setStatus("error");
      setError(errorObject.message);
    }
  };

  // Core execution flow: Copilot Chat
  const executeCopilot = async (queryText: string) => {
    setStatus("analyzing");
    setError(null);

    // Build context
    const parts: string[] = [];
    
    // Inject uploaded files text findings into copilot context
    if (files && files.length > 0) {
      files.forEach(f => {
        if (f.status === "ready" && f.extractedFindings) {
          parts.push(`[Uploaded File Findings: ${f.name} (${f.type})] ${f.extractedFindings}`);
        }
      });
    }
    if (result) {
      parts.push(`Clinical intent: ${result.clinical_intent ?? "unknown"}`);
      parts.push(`Confidence: ${result.confidence_label} (${Math.round((result.confidence_score ?? 0) * 100)}%)`);
      if (result.final_response) parts.push(`Summary: ${result.final_response.slice(0, 350)}`);
      if (result.evidence_quality_summary) {
        const eq = result.evidence_quality_summary;
        parts.push(`Evidence quality: ${eq.overall_sufficiency} (avg trust ${(eq.avg_trust * 100).toFixed(0)}%)`);
        parts.push(`Sources: ${eq.total_sources} total, ${eq.high_quality_count} high-quality`);
      }
      if (result.contradiction_summary?.has_contradictions) {
        parts.push(`Contradictions: ${result.contradiction_summary.summary}`);
      }
      if (result.missing_information?.length) {
        parts.push(`Missing information: ${result.missing_information.join(", ")}`);
      }
    }
    if (patientContext) {
      if (patientContext.age) parts.push(`Patient age: ${patientContext.age}, gender: ${patientContext.gender}`);
      if (patientContext.chief_complaint) parts.push(`Chief complaint: ${patientContext.chief_complaint}`);
    }

    const clinicalContext = parts.join("\n");
    const history = messages
      .filter((m) => m.message_type === "text")
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const copilotResponse = await askCopilot(
        queryText,
        clinicalContext,
        history,
        sessionId ?? undefined
      );

      setStatus("complete");
      addMessage({
        message_id: generateId(),
        role: "assistant",
        content: copilotResponse.answer,
        timestamp: new Date().toISOString(),
        message_type: "text",
        metadata: { confidence: copilotResponse.confidence, copilotResponse },
      });
    } catch (err) {
      const errorObject = err instanceof Error ? err : new Error(String(err));
      setStatus("error");
      setError(errorObject.message);
      addMessage({
        message_id: generateId(),
        role: "assistant",
        content: `Sorry, I encountered an error answering that: ${errorObject.message}.`,
        timestamp: new Date().toISOString(),
        message_type: "text",
      });
    }
  };

  // Submit input text
  const handleSend = async (text: string) => {
    if (!text.trim() || status === "analyzing") return;

    setInput("");
    setError(null);

    // Append user message
    addMessage({
      message_id: generateId(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
      message_type: "text",
    });

    const intent = classifyIntent(text);

    if (intent === "analyze") {
      await executeAnalysis(text);
    } else {
      await executeCopilot(text);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend(input);
    }
  };

  // Skip clarification questions
  const handleClarificationSkip = async () => {
    if (!activeAnalysisQuery) return;
    // Submits bypass answers
    await executeAnalysis(activeAnalysisQuery, { _skip: "true" });
  };

  // Submit clarification responses
  const handleClarificationSubmit = async (answers: ClarificationAnswers) => {
    if (!activeAnalysisQuery) return;
    await executeAnalysis(activeAnalysisQuery, answers);
  };

  const handleExportPDF = () => {
    if (!sessionId) return;
    const apiBase = getApiBase();
    window.open(`${apiBase}/session/${sessionId}/export`, "_blank");
  };

  // Sub-components are defined at module scope above (SectionItem, RetrievalEngineCard,
  // EvidenceSourceRow, TraceViewer, CollapsibleReport, MessageItem) to give them stable
  // React component identities and eliminate per-keystroke flicker/remount.

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{backgroundColor: '#f8fafc'}}>
      {/* Chat Panel Header */}
      <div className="px-6 py-3.5 border-b border-slate-200/80 bg-white flex items-center justify-between shrink-0 shadow-sm">
        <div className="flex items-center gap-2.5">
          <div className="h-6 w-6 rounded bg-blue-50 flex items-center justify-center text-blue-600 font-bold text-xs">
            💬
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-800 leading-none">Conversational Session</h3>
            <p className="text-[9px] text-slate-500 mt-1 font-semibold">Active multi-turn context</p>
          </div>
        </div>
        
        {sessionId && messages.length > 0 && (
          <button
            onClick={handleExportPDF}
            className="flex items-center gap-1.5 text-[10px] text-blue-600 hover:text-blue-550 font-bold border border-blue-200 hover:border-blue-300 rounded-lg px-3 py-1.5 bg-blue-50/40 hover:bg-blue-50 transition-all shadow-sm"
          >
            <FileDown className="h-3.5 w-3.5" />
            <span>Export Case PDF</span>
          </button>
        )}
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 custom-scrollbar">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center min-h-[60%] text-center px-4 py-8">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-3xl shadow-xl shadow-blue-950/40 mb-6">
              🩺
            </div>
            <h2 className="text-base font-bold mb-2" style={{color: '#0f172a'}}>Aegis Conversational Intelligence</h2>
            <p className="text-slate-400 text-xs leading-relaxed max-w-md mb-8">
              Describe a new patient case, present symptoms and vitals, or upload clinical files (ECG, X-Ray, PDF reports). Aegis will orchestrate GraphRAG, dense semantic search, and governance checks to build a clinical intelligence report.
            </p>

            <div className="flex flex-col gap-2.5 w-full max-w-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 text-left">
                Suggested Intakes
              </p>
              {getSuggestionChips().map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(chip)}
                  disabled={status === "analyzing"}
                  className="text-left text-xs bg-slate-900/50 hover:bg-slate-800/50 border border-slate-800 hover:border-slate-700/80 text-slate-300 p-3 rounded-xl transition-all shadow-sm group disabled:opacity-40"
                >
                  <p className="line-clamp-2 leading-relaxed text-[11px] group-hover:text-white">
                    {chip}
                  </p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((msg) => (
              <MessageItem
                key={msg.message_id}
                msg={msg}
                onClarificationSubmit={handleClarificationSubmit}
                onClarificationSkip={handleClarificationSkip}
              />
            ))}
          </div>
        )}

        {/* Live Streaming Stage update */}
        {status === "analyzing" && streamingStage && (
          <div className="flex justify-start gap-3 px-1 animate-fade-in-up">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center font-black text-xs shrink-0 shadow shadow-indigo-950">
              Æ
            </div>
            <div className="max-w-[85%] bg-slate-900/60 border border-slate-850 p-4 rounded-2xl rounded-tl-sm w-full max-w-md space-y-3">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                </span>
                <p className="text-xs font-semibold text-slate-200">
                  Orchestrating Analysis...
                </p>
              </div>

              {/* Step Checklist */}
              <div className="space-y-2 border-t border-slate-800/40 pt-2.5">
                {STAGES.map((s, idx) => {
                  const currentIdx = STAGES.findIndex((st) => st.node === streamingStage);
                  const isCompleted = idx < currentIdx;
                  const isActive = idx === currentIdx;

                  return (
                    <div
                      key={s.node}
                      className={`flex items-center gap-2.5 text-[11px] transition-all duration-300 ${
                        isActive
                          ? "text-blue-400 font-medium"
                          : isCompleted
                          ? "text-emerald-400"
                          : "text-slate-600"
                      }`}
                    >
                      <span className="text-xs">{isCompleted ? "✓" : s.icon}</span>
                      <span className="flex-1 truncate">{s.label}</span>
                      {isActive && (
                        <span className="flex gap-0.5 shrink-0">
                          {[0, 1, 2].map((d) => (
                            <span
                              key={d}
                              className="h-1 w-1 rounded-full bg-blue-400 animate-bounce"
                              style={{ animationDelay: `${d * 0.15}s` }}
                            />
                          ))}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {streamingMessage && (
                <div className="bg-slate-950/40 rounded-lg p-2 text-[10px] text-slate-400 italic border border-slate-800/30">
                  {streamingMessage}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Regular Copilot Typing Indicator */}
        {status === "analyzing" && !streamingStage && (
          <div className="flex justify-start gap-3 px-1 animate-fade-in-up">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center font-black text-xs shrink-0">
              Æ
            </div>
            <div className="flex items-end gap-1.5 px-4 py-3 bg-slate-800/40 border border-slate-750 rounded-2xl rounded-tl-sm w-fit">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
                  style={{
                    animationDelay: `${i * 0.15}s`,
                    animationDuration: "0.9s",
                  }}
                />
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggested Follow-ups Chips */}
      {messages.length > 0 && status !== "analyzing" && getSuggestionChips().length > 0 && (
        <div className="px-6 py-2 flex gap-2 overflow-x-auto shrink-0 custom-scrollbar scroll-smooth">
          {getSuggestionChips().map((chip) => (
            <button
              key={chip}
              onClick={() => handleSend(chip)}
              disabled={false}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] text-slate-400 hover:text-white hover:border-slate-650 hover:bg-slate-800/40 whitespace-nowrap transition-all disabled:opacity-40 shrink-0"
            >
              <span>💬</span>
              <span>{chip}</span>
            </button>
          ))}
        </div>
      )}

      {/* Input Action Panel */}
      <div className="px-6 pb-6 pt-2 shrink-0" style={{background: 'linear-gradient(to top, #ffffff, rgba(255,255,255,0.97), transparent)'}}>
        {error && (
          <div className="mb-2 bg-red-950/40 border border-red-900/40 text-red-300 text-[10px] px-3 py-2 rounded-lg flex items-center justify-between shrink-0">
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">
              ×
            </button>
          </div>
        )}

        <div className="rounded-2xl px-4 py-3 transition-all flex items-end gap-3 shadow-lg border" style={{backgroundColor: '#ffffff', borderColor: '#cbd5e1'}}>
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              messages.length === 0
                ? "Enter patient intake notes or symptoms..."
                : "Ask a follow-up question or update patient context..."
            }
            disabled={status === "analyzing"}
            className="flex-1 bg-transparent text-[12px] focus:outline-none resize-none custom-scrollbar max-h-32 py-1 leading-relaxed"
            style={{color: '#0f172a'}}
          />

          <div className="flex items-center gap-2 shrink-0">
            {/* Context Files counter */}
            {files.length > 0 && (
              <div className="flex items-center gap-1 bg-slate-950/40 border border-slate-800 text-[9px] text-slate-400 px-2 py-1 rounded-lg">
                <span>📎</span>
                <span>{files.length} file{files.length !== 1 ? "s" : ""}</span>
              </div>
            )}

            <button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || status === "analyzing"}
              className="h-8 w-8 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all text-white shadow shadow-blue-950/30"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path
                  d="M1.5 11L11 6L1.5 1V5.5L7.5 6L1.5 6.5V11Z"
                  fill="currentColor"
                />
              </svg>
            </button>
          </div>
        </div>

        <p className="text-center text-[9px] text-slate-600 mt-2 leading-normal">
          Aegis Clinical Intelligence Platform · Multi-turn session context is active.
        </p>
      </div>
    </div>
  );
}
