"use client";

import React, { useState } from "react";
import {
  Network, Database, Cpu, Layers, ShieldCheck, Activity, Search, Eye,
  FileText, Microscope, Stethoscope, BrainCircuit, Workflow, Zap, Shield,
  BookOpen, GitBranch, BarChart3, RefreshCw, Users, Lock, Globe
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
const TABS = [
  { id: "overview",       icon: Layers,       label: "System Overview" },
  { id: "agents",         icon: BrainCircuit, label: "AI Agents" },
  { id: "rag",            icon: Search,       label: "Hybrid RAG" },
  { id: "multimodal",     icon: Eye,          label: "Multimodal" },
  { id: "governance",     icon: Shield,       label: "Governance & Safety" },
  { id: "usecases",       icon: Stethoscope,  label: "Clinical Use Cases" },
  { id: "techstack",      icon: Cpu,          label: "Tech Stack" },
];

export default function ArchitectureDashboard() {
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <div className="h-screen overflow-y-auto bg-background text-foreground font-sans">
      {/* HERO */}
      <div className="relative overflow-hidden border-b border-white/5 bg-gradient-to-b from-slate-900 to-[#070b14] pt-20 pb-14">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-700/20 rounded-full blur-3xl" />
          <div className="absolute top-10 right-1/4 w-[400px] h-[400px] bg-violet-700/15 rounded-full blur-3xl" />
        </div>
        <div className="relative z-10 max-w-6xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-bold uppercase tracking-widest mb-6">
            <Cpu className="w-3.5 h-3.5" /> Phase 13 · Complete System Reference
          </div>
          <h1 className="text-5xl md:text-6xl font-black tracking-tight mb-5 bg-clip-text text-transparent bg-gradient-to-br from-white via-slate-200 to-indigo-400">
            Aegis Clinical AI
          </h1>
          <p className="text-lg text-slate-400 max-w-3xl mx-auto leading-relaxed">
            A <strong className="text-white">13-Phase multi-agent orchestration system</strong> for zero-hallucination clinical decision support. Combines LangGraph agentic workflows, hybrid RAG retrieval, multimodal pipelines, and human-in-the-loop governance.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 mt-8">
            {["LangGraph", "FastAPI", "Next.js 15", "Qdrant", "Neo4j", "Groq / Llama-3", "PubMed Live", "HITL Governance"].map(t => (
              <span key={t} className="px-3 py-1 rounded-full border border-slate-700 bg-slate-800/60 text-slate-300 text-xs font-semibold">{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* NAV */}
      <div className="sticky top-0 z-50 bg-background/90 backdrop-blur-xl border-b border-border">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex items-center gap-1 overflow-x-auto">
            {TABS.map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-4 px-3 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                  activeTab === tab.id
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-slate-500 hover:text-slate-300"
                }`}>
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* CONTENT */}
      <div className="max-w-6xl mx-auto px-6 py-12">

        {/* ═══ OVERVIEW ════════════════════════════════════════════════════════ */}
        {activeTab === "overview" && (
          <div className="space-y-14 animate-in fade-in duration-500">
            <SectionHeader title="13-Phase Agentic DAG" sub="Every patient query executes through a directed acyclic graph of specialist agents. No step is skipped — the Orchestrator decides." />

            <div className="grid md:grid-cols-3 gap-4">
              {PHASES.map((p, i) => (
                <div key={i} className={`p-4 rounded-xl border transition-all ${p.highlight ? "border-indigo-500/40 bg-indigo-500/5" : "border-slate-800 bg-slate-900/40"}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-slate-800 text-slate-400">Phase {p.phase}</span>
                    {p.highlight && <span className="text-[9px] font-bold text-indigo-400 uppercase">Core</span>}
                  </div>
                  <h3 className="font-bold text-white text-sm mb-1">{p.title}</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">{p.desc}</p>
                </div>
              ))}
            </div>

            <div className="p-8 rounded-2xl border border-slate-800 bg-slate-900/30">
              <h3 className="font-bold text-lg mb-6 flex items-center gap-2"><GitBranch className="text-indigo-400 w-5 h-5" /> High-Level Architecture Flow</h3>
              <div className="grid md:grid-cols-5 gap-2 items-center text-center text-xs font-semibold">
                {[
                  { label: "User Query", bg: "bg-slate-800", text: "text-slate-200" },
                  { label: "→", bg: "", text: "text-slate-600" },
                  { label: "Orchestration Planner", bg: "bg-indigo-900/40", text: "text-indigo-300" },
                  { label: "→", bg: "", text: "text-slate-600" },
                  { label: "Parallel Retrieval\n(Qdrant + Neo4j + PubMed)", bg: "bg-emerald-900/30", text: "text-emerald-300" },
                ].map((b, i) => b.bg
                  ? <div key={i} className={`${b.bg} ${b.text} rounded-lg py-3 px-2 whitespace-pre-line`}>{b.label}</div>
                  : <div key={i} className={`${b.text} text-2xl`}>{b.label}</div>
                )}
                <div className="md:col-span-5 flex items-center justify-center gap-2 mt-2 text-slate-600 text-xl font-bold">↓</div>
                {[
                  { label: "Evidence Evaluator\n& Contradiction Check", bg: "bg-amber-900/30", text: "text-amber-300" },
                  { label: "→", bg: "", text: "text-slate-600" },
                  { label: "Clinical Reasoning\n& Validation", bg: "bg-violet-900/30", text: "text-violet-300" },
                  { label: "→", bg: "", text: "text-slate-600" },
                  { label: "Governance Review\n& Final Response", bg: "bg-rose-900/30", text: "text-rose-300" },
                ].map((b, i) => b.bg
                  ? <div key={i} className={`${b.bg} ${b.text} rounded-lg py-3 px-2 whitespace-pre-line`}>{b.label}</div>
                  : <div key={i} className={`${b.text} text-2xl`}>{b.label}</div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ═══ AGENTS ══════════════════════════════════════════════════════════ */}
        {activeTab === "agents" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="The 9 Autonomous Agents" sub="Each agent has a dedicated system prompt, specialized tools, and a fixed responsibility in the LangGraph DAG. The Orchestration Planner decides execution order dynamically." />

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
              {AGENTS.map((a, i) => (
                <div key={i} className="p-5 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-slate-600 transition-colors flex flex-col gap-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Agent {i + 1}</span>
                      <h3 className="font-bold text-white mt-0.5">{a.name}</h3>
                    </div>
                    <a.icon className={`w-5 h-5 shrink-0 mt-1 ${a.color}`} />
                  </div>
                  <p className="text-sm text-slate-400 leading-relaxed">{a.desc}</p>
                  <div className="flex flex-wrap gap-1.5 mt-auto pt-2 border-t border-slate-800">
                    {a.tags.map(t => (
                      <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-semibold">{t}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="p-6 rounded-2xl border border-amber-500/20 bg-amber-500/5">
              <h3 className="font-bold text-amber-300 mb-3 flex items-center gap-2"><Zap className="w-4 h-4" /> Adaptive Execution: The Orchestrator&apos;s Rules</h3>
              <div className="grid md:grid-cols-2 gap-3 text-sm text-slate-300">
                {[
                  "Always starts with Query Understanding — even simple queries need variant generation.",
                  "Runs Retrieve + Live Research in parallel when risk level is HIGH or CRITICAL.",
                  "Skips Reflection and goes straight to Finalize if max_retries is reached.",
                  "Triggers Clarification only for ambiguous clinical queries — never for greetings.",
                  "The Validation Agent is mandatory before Finalize — it can never be bypassed.",
                  "Escalation is auto-triggered if risk_score > escalation_threshold (configurable per workflow).",
                ].map((r, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-amber-400 shrink-0 font-bold">→</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ═══ RAG ═════════════════════════════════════════════════════════════ */}
        {activeTab === "rag" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="Hybrid RAG Retrieval Architecture" sub="Aegis fires three concurrent retrieval engines, fuses all results with Reciprocal Rank Fusion (RRF), reranks with a BGE Cross-Encoder, then filters via trust-based Source Policy." />

            <div className="grid md:grid-cols-3 gap-6">
              {RAG_ENGINES.map((e, i) => (
                <div key={i} className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 flex flex-col gap-3 hover:border-indigo-500/40 transition-colors">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: e.iconBg }}>
                    <e.icon className="w-5 h-5" style={{ color: e.iconColor }} />
                  </div>
                  <h3 className="font-bold text-white">{e.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{e.desc}</p>
                  <div className="mt-auto space-y-1.5 pt-3 border-t border-slate-800">
                    <p className="text-[10px] uppercase tracking-widest font-bold text-slate-500">When It&apos;s Used</p>
                    {e.useCases.map((u, j) => (
                      <div key={j} className="flex items-start gap-1.5 text-xs text-slate-300">
                        <span className="text-indigo-400 shrink-0">·</span> {u}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2"><Layers className="text-indigo-400 w-5 h-5" /> RRF Fusion + Cross-Encoder Reranking</h3>
                {[
                  { step: "1", label: "Dense Recall", detail: "BGE-Large-En-v1.5 cosine similarity → top 20 chunks from Qdrant" },
                  { step: "2", label: "Sparse Recall", detail: "BM25 keyword search → top 20 chunks (catches exact medical term matches)" },
                  { step: "3", label: "Graph Recall", detail: "Neo4j Cypher traversal → relational entities and trial connections" },
                  { step: "4", label: "RRF Fusion", detail: "Reciprocal Rank Fusion merges all 3 pools → deduplicated 40-chunk candidate list" },
                  { step: "5", label: "Cross-Encoder Rerank", detail: "BGE-Reranker scores all 40 candidates → selects top 8-12 by relevance" },
                  { step: "6", label: "Source Policy Filter", detail: "Trust multipliers and authority boosts applied; low-trust chunks dropped" },
                ].map(s => (
                  <div key={s.step} className="flex gap-3 py-2.5 border-b border-slate-800 last:border-0">
                    <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-black flex items-center justify-center">{s.step}</span>
                    <div>
                      <span className="font-semibold text-white text-sm">{s.label}: </span>
                      <span className="text-slate-400 text-sm">{s.detail}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2"><ShieldCheck className="text-emerald-400 w-5 h-5" /> Source Trust Hierarchy</h3>
                {[
                  { source: "WHO / NICE / NIH Guidelines", score: "0.95+", mult: "1.20x", color: "text-emerald-400" },
                  { source: "Cochrane Systematic Reviews", score: "0.90", mult: "1.15x + 0.12 boost", color: "text-emerald-400" },
                  { source: "Randomized Clinical Trials", score: "0.85", mult: "1.10x", color: "text-blue-400" },
                  { source: "NEJM / Lancet / JAMA", score: "0.85", mult: "+0.08 boost", color: "text-blue-400" },
                  { source: "Observational Studies", score: "0.75", mult: "0.95x", color: "text-amber-400" },
                  { source: "Expert Opinion / Case Reports", score: "0.65", mult: "0.85x", color: "text-orange-400" },
                  { source: "Unverified Internet Sources", score: "0.45", mult: "DROPPED (< 0.85 floor)", color: "text-red-400" },
                ].map((s, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
                    <span className="text-sm text-slate-300">{s.source}</span>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className={`text-xs font-bold ${s.color}`}>{s.score}</span>
                      <span className="text-[10px] text-slate-500">{s.mult}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ═══ MULTIMODAL ══════════════════════════════════════════════════════ */}
        {activeTab === "multimodal" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="Multimodal Clinical File Processing" sub="Aegis automatically detects and routes uploaded clinical files through specialized AI pipelines before they reach the LLM." />

            <div className="grid md:grid-cols-3 gap-6">
              {[
                {
                  icon: Activity, color: "text-red-400", bg: "bg-red-500/10 border-red-500/30",
                  title: "ECG Waveform Pipeline",
                  steps: ["Raw ECG file uploaded (.ecg, .csv, .png)", "Waveform digitization + feature extraction", "Pattern detection: STEMI, A-Fib, PVC, PR intervals", "Confidence-scored findings injected into patient context", "Emergency flag raised if lethal arrhythmia detected"],
                },
                {
                  icon: Microscope, color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/30",
                  title: "Radiology AI Pipeline",
                  steps: ["X-Ray / MRI / CT upload (.png, .jpg, .dcm)", "GPT-4o Vision modality classification", "Automated finding detection: infiltrates, effusions, nodules, fractures", "Structured radiology report generated with confidence score", "Embedded into patient context for LLM reasoning"],
                },
                {
                  icon: FileText, color: "text-violet-400", bg: "bg-violet-500/10 border-violet-500/30",
                  title: "Clinical OCR Pipeline",
                  steps: ["PDF, lab report, or discharge summary uploaded", "Primary extraction via PaddleOCR", "If confidence < 70%, auto-fallback to Tesseract", "If still < 60%, escalated to GPT-4o-Vision", "Tabular lab values (e.g. HbA1c: 8.2%) parsed and structured"],
                },
              ].map((p, i) => (
                <div key={i} className={`p-5 rounded-2xl border ${p.bg}`}>
                  <div className="flex items-center gap-2 mb-4">
                    <p.icon className={`w-6 h-6 ${p.color}`} />
                    <h3 className="font-bold text-white">{p.title}</h3>
                  </div>
                  <ol className="space-y-2">
                    {p.steps.map((s, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm">
                        <span className="shrink-0 w-4 h-4 rounded-full bg-slate-800 text-slate-400 text-[9px] font-black flex items-center justify-center">{j+1}</span>
                        <span className="text-slate-300">{s}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
              <h3 className="font-bold text-white mb-3 flex items-center gap-2"><Layers className="text-indigo-400 w-5 h-5"/> Modality Router</h3>
              <p className="text-slate-400 text-sm leading-relaxed">When a file is uploaded, the <code className="text-indigo-300 bg-indigo-900/30 px-1 rounded">ImageIngestor</code> automatically classifies the modality using a vision model. ECG files are routed to <code className="text-red-300 bg-red-900/30 px-1 rounded">EcgPipeline</code>, X-Rays to <code className="text-blue-300 bg-blue-900/30 px-1 rounded">RadiologyPipeline</code>, and text/PDFs to <code className="text-violet-300 bg-violet-900/30 px-1 rounded">OcrPipeline</code>. All extracted data is fused into the patient context before the retrieval agents run — so the LLM always has both image-derived and text-derived evidence available simultaneously.</p>
            </div>
          </div>
        )}

        {/* ═══ GOVERNANCE ══════════════════════════════════════════════════════ */}
        {activeTab === "governance" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="Human-in-the-Loop Governance" sub="Every high-risk AI output is intercepted before delivery. Clinicians can approve, reject, override, or request a retry directly from the Governance Dashboard." />

            <div className="grid md:grid-cols-2 gap-6">
              <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2"><Shield className="text-rose-400 w-5 h-5" /> Escalation Triggers</h3>
                {[
                  { trigger: "LOW_CONFIDENCE_SCORE", desc: "Validation score < 0.60 after maximum retries" },
                  { trigger: "MEDICATION_CONTRAINDICATION", desc: "Drug-drug interaction flagged by graph traversal" },
                  { trigger: "EMERGENCY_RISK", desc: "Risk engine scores critical (> 0.85) on the risk scale" },
                  { trigger: "CONTRADICTION_DETECTED", desc: "Evidence sources directly contradict each other" },
                  { trigger: "MISSING_CRITICAL_INFO", desc: "Patient context missing required data for safe synthesis" },
                  { trigger: "HALLUCINATION_RISK", desc: "Grounding score below minimum safety threshold" },
                ].map(e => (
                  <div key={e.trigger} className="flex items-start gap-3 py-2.5 border-b border-slate-800 last:border-0">
                    <code className="text-[9px] font-black text-amber-400 bg-amber-900/20 px-1.5 py-0.5 rounded shrink-0">{e.trigger}</code>
                    <span className="text-sm text-slate-400">{e.desc}</span>
                  </div>
                ))}
              </div>

              <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2"><Users className="text-violet-400 w-5 h-5" /> Clinician Actions</h3>
                {[
                  { action: "✅ Approve", desc: "AI output is accepted as clinically sound and released to the patient record." },
                  { action: "❌ Reject", desc: "Output is discarded. The case is logged for reprocessing or manual review." },
                  { action: "✏️ Override", desc: "Clinician replaces the AI output with their own corrected clinical text." },
                  { action: "🔄 Request Retry", desc: "Triggers a full re-run of the orchestration graph with a broader retrieval scope." },
                ].map(a => (
                  <div key={a.action} className="py-3 border-b border-slate-800 last:border-0">
                    <div className="font-semibold text-white text-sm">{a.action}</div>
                    <p className="text-sm text-slate-400 mt-0.5">{a.desc}</p>
                  </div>
                ))}
                <div className="mt-4 p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                  <p className="text-xs text-indigo-300">All governance actions are written to an immutable audit log with actor identity, timestamp, and decision context — providing a full HITL audit trail.</p>
                </div>
              </div>
            </div>

            <div className="grid md:grid-cols-3 gap-4">
              {[
                { icon: Lock, title: "Validation Strictness Levels", items: ["RELAXED (0.55) — Research queries", "STANDARD (0.70) — General clinical", "STRICT (0.82) — Medications/procedures", "CRITICAL (0.95) — Emergency/drug safety"] },
                { icon: BarChart3, title: "Workflow Risk Tiers", items: ["LOW — Informational, no clinical impact", "MEDIUM — Outpatient clinical decisions", "HIGH — Inpatient / procedural decisions", "CRITICAL — Life-threatening emergencies"] },
                { icon: RefreshCw, title: "Reflection Strategies", items: ["MINIMAL — 1 retry, accept partial evidence", "MODERATE — 2 retries, query expansion", "AGGRESSIVE — 3 retries + HyDE + live search", "EMERGENCY — 1 retry then immediate escalate"] },
              ].map((c, i) => (
                <div key={i} className="p-5 rounded-2xl border border-slate-800 bg-slate-900/30">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2"><c.icon className="text-indigo-400 w-4 h-4"/>{c.title}</h3>
                  <ul className="space-y-1.5">
                    {c.items.map((it, j) => <li key={j} className="text-xs text-slate-400 flex items-start gap-1.5"><span className="text-slate-600 shrink-0">·</span>{it}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ USE CASES ═══════════════════════════════════════════════════════ */}
        {activeTab === "usecases" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="Clinical Use Cases" sub="Aegis dynamically adapts its workflow, retrieval strategy, and safety thresholds based on the nature of each clinical query." />

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
              {USE_CASES.map((u, i) => (
                <div key={i} className="p-5 rounded-2xl border border-slate-800 bg-slate-900/40 flex flex-col gap-3">
                  <div className="flex items-start justify-between">
                    <span className="text-3xl">{u.emoji}</span>
                    <span className={`text-[9px] font-black uppercase px-2 py-1 rounded border ${u.riskColor}`}>{u.risk} RISK</span>
                  </div>
                  <h3 className="font-bold text-white">{u.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{u.desc}</p>
                  <div className="pt-3 border-t border-slate-800 space-y-1">
                    <p className="text-[9px] uppercase tracking-widest font-bold text-slate-500">Workflow Activated</p>
                    <div className="flex flex-wrap gap-1.5">
                      {u.tags.map(t => <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">{t}</span>)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ TECH STACK ══════════════════════════════════════════════════════ */}
        {activeTab === "techstack" && (
          <div className="space-y-10 animate-in fade-in duration-500">
            <SectionHeader title="Full Technology Stack" sub="Every layer of Aegis — from the LLM backbone to the CI/CD pipeline — is engineered for reliability, observability, and clinical safety." />

            <div className="grid md:grid-cols-2 gap-6">
              {TECH_LAYERS.map((layer, i) => (
                <div key={i} className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30">
                  <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
                    <layer.icon className={`w-4 h-4 ${layer.color}`} />{layer.title}
                  </h3>
                  <div className="space-y-2">
                    {layer.items.map((it, j) => (
                      <div key={j} className="flex items-start gap-3">
                        <code className="text-xs font-bold text-indigo-300 bg-indigo-900/20 px-1.5 py-0.5 rounded shrink-0 min-w-[120px]">{it.name}</code>
                        <span className="text-sm text-slate-400">{it.role}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ─── Data ────────────────────────────────────────────────────────────────────

const PHASES = [
  { phase: "1-4", title: "Telemetry & Core RAG", highlight: false, desc: "Event bus, vector ingestion, embedding pipeline, Qdrant setup." },
  { phase: "5", title: "Observability", highlight: false, desc: "TelemetryBus, TelemetryStorage, per-node latency tracking." },
  { phase: "6", title: "Query Intelligence", highlight: false, desc: "Query classification, multi-hop variant generation, intent detection." },
  { phase: "7", title: "Advanced Retrieval", highlight: true, desc: "Hybrid RRF fusion, BGE reranker, HyDE expansion, compression pipeline." },
  { phase: "8", title: "Multimodal", highlight: false, desc: "ECG pipeline, radiology AI, OCR with PaddleOCR/Tesseract fallback." },
  { phase: "9", title: "Governance (HITL)", highlight: true, desc: "Escalation engine, clinician review portal, audit log." },
  { phase: "10-11", title: "Auth & Rate Limiting", highlight: false, desc: "JWT auth, API key management, per-route rate limiting." },
  { phase: "12", title: "Adaptive Orchestration", highlight: true, desc: "OrchestrationPlanner, ExecutionPlan, ContradictionAnalyzer, SufficiencyEngine." },
  { phase: "13", title: "Conversational Copilot", highlight: true, desc: "Multi-turn patient sessions, ClinicalCopilot chat, session memory." },
];

const AGENTS = [
  { name: "Orchestration Planner", icon: BrainCircuit, color: "text-indigo-400", tags: ["LangGraph", "Routing", "Risk Engine"], desc: "The master supervisor. Reads the full patient context and decides which agent runs next. Builds a dynamic ExecutionPlan specifying retrieval depth, validation strictness, and escalation thresholds for this specific query." },
  { name: "Query Understanding Agent", icon: Search, color: "text-blue-400", tags: ["Llama-3-70b", "NLP", "Expansion"], desc: "Analyzes the raw query, expands medical abbreviations (e.g. STEMI, CKD-5), generates 3-5 semantically diverse query variants for retrieval, and infers missing clinical context to fill into the patient record." },
  { name: "Retrieval Agent", icon: Database, color: "text-emerald-400", tags: ["Async", "Parallel Execution", "Tool Calling"], desc: "Executes the Decision Plan by firing concurrent async tool calls to Qdrant (dense+sparse), Neo4j (Cypher traversal), and PubMed (live API). Gathers up to 40 raw candidate chunks into a shared context pool." },
  { name: "Evidence Evaluator", icon: BarChart3, color: "text-amber-400", tags: ["Critique", "Trust Scoring", "Quality"], desc: "Scores each retrieved chunk for relevance, recency, source authority, and trust. Computes a high_quality_count (quality >= 0.75) and an overall_sufficiency rating. If evidence is 'weak', it flags to the orchestrator." },
  { name: "Contradiction Analyzer", icon: Zap, color: "text-orange-400", tags: ["Cross-Source", "Conflict Detection"], desc: "Compares evidence chunks from different sources for clinical contradictions. Computes a severity penalty, identifies which sources conflict, and sets escalation_required=True if contradictions cannot be resolved automatically." },
  { name: "Reasoning Agent", icon: FileText, color: "text-violet-400", tags: ["Synthesis", "Llama-3-70b", "Structured Output"], desc: "The final LLM call. Takes the validated, filtered, high-quality evidence and generates a structured clinical report broken into sections (Diagnosis, Evidence, Recommendations, Caveats). Each claim is grounded to a source." },
  { name: "Validation Agent", icon: ShieldCheck, color: "text-green-400", tags: ["Grounding", "Safety", "Mandatory"], desc: "Evaluates the reasoning output for: evidence coverage, grounding score, source diversity, temporal coverage, and contradiction flags. Computes a composite validation_score. If it fails, triggers the Reflection Agent." },
  { name: "Reflection Agent", icon: RefreshCw, color: "text-rose-400", tags: ["Self-Healing", "HyDE", "Retry"], desc: "Activated on validation failure. Analyzes which sub-score failed (e.g. low source diversity), reformulates the query using HyDE (Hypothetical Document Embeddings), and forces a broader retrieval sweep before re-validation." },
  { name: "Supervisor Agent", icon: Eye, color: "text-slate-400", tags: ["Monitor", "Continuous", "Checkpoints"], desc: "Runs continuously in the background during execution. Monitors evidence sufficiency at each checkpoint and can trigger emergency escalation proactively — before the Validation Agent even runs — if critical signals are detected." },
];

const RAG_ENGINES = [
  {
    icon: Database, iconBg: "rgba(16,185,129,0.1)", iconColor: "#34d399",
    title: "Dense + Sparse Hybrid (Qdrant)",
    desc: "BGE-Large-En-v1.5 generates 1024-dimensional query embeddings for cosine similarity. BM25 sparse search runs in parallel to catch exact medical term matches that semantic search might miss. Both results are merged with RRF.",
    useCases: ["Broad symptom search ('fever + rash + joint pain')", "Similar past patient case matching", "Clinical guideline lookup by topic", "Drug information retrieval"],
  },
  {
    icon: Network, iconBg: "rgba(99,102,241,0.1)", iconColor: "#818cf8",
    title: "GraphRAG — Neo4j Cypher",
    desc: "Multi-hop graph traversal across a knowledge graph of clinical trials, drug nodes, disease entities, and treatment edges. Finds non-obvious multi-step relationships that vector search cannot discover.",
    useCases: ["Drug-drug interaction chains ('Warfarin + Azithromycin')", "Clinical trial eligibility matching", "Disease-treatment pathway discovery", "Comorbidity relationship analysis"],
  },
  {
    icon: Globe, iconBg: "rgba(59,130,246,0.1)", iconColor: "#60a5fa",
    title: "Live Research — PubMed APIs",
    desc: "Real-time calls to the National Library of Medicine (NLM) E-utilities API. Fetches recent systematic reviews, RCT abstracts, and clinical evidence that doesn't yet exist in the static vector database.",
    useCases: ["Novel treatments for rare diseases", "Most recent COVID-19 / Long-COVID evidence", "Post-market drug safety signals", "Emerging infectious disease protocols"],
  },
];

const USE_CASES = [
  { emoji: "🚨", title: "Emergency Triage", risk: "CRITICAL", riskColor: "bg-red-900/30 text-red-400 border-red-600/30", desc: "Patient presenting with ST elevations and acute chest pain. Aegis uses EMERGENCY workflow with CRITICAL strictness (0.95 threshold), HYBRID_STRICT retrieval, and single-retry policy for maximum speed with safety.", tags: ["EMERGENCY workflow", "1-retry limit", "Auto-escalation"] },
  { emoji: "💊", title: "Pharmacological Audit", risk: "HIGH", riskColor: "bg-orange-900/30 text-orange-400 border-orange-600/30", desc: "Checking contraindications for a patient on Warfarin prescribed a macrolide antibiotic. Neo4j graph traversal finds the drug-drug interaction chain. MEDICATION workflow with STRICT validation (0.82) is activated.", tags: ["MEDICATION workflow", "Neo4j traversal", "STRICT validation"] },
  { emoji: "🔍", title: "Rare Disease Matching", risk: "MEDIUM", riskColor: "bg-amber-900/30 text-amber-400 border-amber-600/30", desc: "Patient with undifferentiated auto-immune symptoms. SIMILAR_CASE workflow activates, embedding vitals and finding semantic matches in historical EHRs. Live PubMed search fetches latest orphan disease studies.", tags: ["SIMILAR_CASE workflow", "Case memory search", "PubMed live"] },
  { emoji: "📊", title: "Literature Synthesis", risk: "LOW", riskColor: "bg-blue-900/30 text-blue-400 border-blue-600/30", desc: "Physician querying the latest consensus on Long-COVID treatment. LITERATURE workflow fires INTERNET_AUGMENTED retrieval with AGGRESSIVE reflection (3 retries), synthesizing a meta-analysis from 15+ recent papers.", tags: ["LITERATURE workflow", "Internet augmented", "AGGRESSIVE reflection"] },
  { emoji: "🩻", title: "Radiology Review", risk: "HIGH", riskColor: "bg-orange-900/30 text-orange-400 border-orange-600/30", desc: "Chest X-Ray uploaded alongside clinical notes. RadiologyPipeline runs GPT-4o Vision to detect infiltrates, then Aegis cross-references findings with pneumonia guidelines from Qdrant and computes treatment plan.", tags: ["MULTIMODAL workflow", "GPT-4o Vision", "Guideline cross-reference"] },
  { emoji: "📝", title: "Discharge Summarization", risk: "LOW", riskColor: "bg-blue-900/30 text-blue-400 border-blue-600/30", desc: "Generating a patient-friendly discharge letter from structured clinical data. CLINICAL workflow with RELAXED validation (0.55) allows faster processing. OCR pipeline extracts data from uploaded lab PDFs automatically.", tags: ["CLINICAL workflow", "RELAXED validation", "OCR pipeline"] },
];

const TECH_LAYERS = [
  {
    icon: BrainCircuit, color: "text-indigo-400", title: "AI / LLM Layer",
    items: [
      { name: "Llama-3.1-70b", role: "Primary reasoning and synthesis model via Groq API" },
      { name: "Llama-3.1-8b", role: "Fast orchestration decisions and query classification" },
      { name: "BGE-Large-En-v1.5", role: "1024-dim embedding model for vector search" },
      { name: "BGE-Reranker", role: "Cross-encoder reranking of retrieved candidates" },
      { name: "GPT-4o Vision", role: "Multimodal fallback for radiology and OCR" },
    ],
  },
  {
    icon: Database, color: "text-emerald-400", title: "Data & Storage Layer",
    items: [
      { name: "Qdrant", role: "Production vector database for dense + sparse hybrid search" },
      { name: "Neo4j", role: "Graph database for clinical trial + drug-disease knowledge graph" },
      { name: "PostgreSQL", role: "Primary telemetry and governance audit log storage" },
      { name: "Redis", role: "Hot-path caching for telemetry aggregates and session state" },
    ],
  },
  {
    icon: Workflow, color: "text-violet-400", title: "Orchestration Layer",
    items: [
      { name: "LangGraph", role: "Directed acyclic graph (DAG) orchestration for all agents" },
      { name: "FastAPI", role: "Async Python REST API with streaming SSE support" },
      { name: "asyncio", role: "Concurrent parallel tool execution within the Retrieval Agent" },
      { name: "TelemetryBus", role: "Async event bus for non-blocking observability emission" },
    ],
  },
  {
    icon: Globe, color: "text-blue-400", title: "Frontend & Deployment",
    items: [
      { name: "Next.js 15", role: "React App Router with server + client component split" },
      { name: "Zustand", role: "Lightweight global state management for workspace + telemetry" },
      { name: "Vercel", role: "Frontend hosting with automatic CI/CD on main branch push" },
      { name: "HuggingFace Spaces", role: "Backend API hosting with GPU/CPU tier auto-scaling" },
    ],
  },
  {
    icon: ShieldCheck, color: "text-rose-400", title: "Safety & Observability",
    items: [
      { name: "Sentry SDK", role: "Error tracking, performance tracing, and alerting" },
      { name: "GroundingEngine", role: "Hallucination scoring using evidence-output overlap" },
      { name: "FailureAnalytics", role: "Pattern detection across escalation and error telemetry" },
      { name: "Governance API", role: "HITL review endpoints with full audit trail persistence" },
    ],
  },
  {
    icon: BookOpen, color: "text-amber-400", title: "Research & Ingestion",
    items: [
      { name: "PubMed E-utilities", role: "Live NLM API for real-time systematic review retrieval" },
      { name: "ClinicalTrials.gov", role: "Trial data ingested into Neo4j for 40+ disease categories" },
      { name: "PaddleOCR", role: "Primary OCR engine for clinical document text extraction" },
      { name: "Tesseract OCR", role: "Fallback OCR when PaddleOCR confidence drops below 70%" },
    ],
  },
];

// ─── UI Helpers ───────────────────────────────────────────────────────────────

function SectionHeader({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-3xl font-bold text-white mb-2">{title}</h2>
      <p className="text-slate-400 leading-relaxed max-w-3xl">{sub}</p>
    </div>
  );
}
