"use client";

import React, { useState } from 'react';
import { 
  Network, 
  Database, 
  Cpu, 
  Layers, 
  ShieldCheck, 
  Activity, 
  Search, 
  Eye, 
  FileText, 
  Microscope,
  Stethoscope,
  ChevronDown,
  BrainCircuit,
  Workflow
} from 'lucide-react';

export default function ArchitectureDashboard() {
  const [activeTab, setActiveTab] = useState('orchestration');

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white font-sans selection:bg-indigo-500/30 overflow-x-hidden">
      
      {/* HERO SECTION */}
      <div className="relative overflow-hidden border-b border-white/5 bg-slate-900/50 pt-24 pb-16">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay"></div>
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-full blur-[120px] pointer-events-none opacity-40">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-600 rounded-full mix-blend-screen opacity-50"></div>
          <div className="absolute top-1/3 right-1/4 w-96 h-96 bg-violet-600 rounded-full mix-blend-screen opacity-50"></div>
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-semibold uppercase tracking-wider mb-6">
            <Cpu className="w-4 h-4" /> System Architecture & Capabilities
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 bg-clip-text text-transparent bg-gradient-to-br from-white via-slate-200 to-slate-500">
            Aegis Clinical AI
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-3xl mx-auto leading-relaxed">
            A multi-agent, high-concurrency clinical orchestration system built on LangGraph, FastAPI, and Next.js. Engineered for zero-hallucination medical decision support.
          </p>
        </div>
      </div>

      {/* NAVIGATION */}
      <div className="sticky top-0 z-50 bg-[#0a0e1a]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-center gap-6 overflow-x-auto no-scrollbar">
            {[
              { id: 'orchestration', icon: Workflow, label: 'Agentic Orchestration' },
              { id: 'retrieval', icon: Search, label: 'Parallel Retrieval' },
              { id: 'multimodal', icon: Eye, label: 'Multimodal Processing' },
              { id: 'usecases', icon: Stethoscope, label: 'Clinical Use Cases' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                  activeTab === tab.id 
                    ? 'border-indigo-500 text-indigo-400' 
                    : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="max-w-7xl mx-auto px-6 py-12">
        
        {/* ─── TAB 1: ORCHESTRATION ────────────────────────────────────────── */}
        {activeTab === 'orchestration' && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
            
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div>
                <h2 className="text-3xl font-bold mb-4">Multi-Agent LangGraph Orchestration</h2>
                <p className="text-slate-400 leading-relaxed mb-6">
                  Aegis operates on a highly structured <strong>13-Phase directed acyclic graph (DAG)</strong> built with LangGraph. Instead of a single LLM prompt, the query passes through specialized autonomous agents, each evaluating, retrieving, or critiquing the previous step.
                </p>
                <div className="space-y-4">
                  {[
                    { title: "Decision Router", desc: "Classifies the query (Emergency, Research, Clinical) and builds an execution plan." },
                    { title: "Parallel Retrieval", desc: "Forks execution to query Vector DB, Graph DB, and Internet simultaneously." },
                    { title: "Validation & Reflection", desc: "Critiques evidence quality. If hallucination risk is high, it re-plans and fetches more data." },
                    { title: "Governance Engine", desc: "Triggers Human-In-The-Loop escalation for critical risks." }
                  ].map((feature, i) => (
                    <div key={i} className="flex gap-4 p-4 rounded-xl bg-slate-900/50 border border-white/5">
                      <div className="shrink-0 w-8 h-8 rounded-full bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold">
                        {i + 1}
                      </div>
                      <div>
                        <h4 className="font-semibold text-white">{feature.title}</h4>
                        <p className="text-sm text-slate-400">{feature.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-slate-900/80 p-8 shadow-2xl">
                <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-purple-500/5"></div>
                <div className="relative space-y-3">
                  {/* Visual Node Graph */}
                  <Node icon={BrainCircuit} title="1. Query Understanding" color="blue" />
                  <div className="w-0.5 h-6 bg-slate-700 mx-auto"></div>
                  <Node icon={Network} title="2. Workflow Router" color="indigo" />
                  <div className="w-0.5 h-6 bg-slate-700 mx-auto"></div>
                  <div className="flex gap-4 justify-center">
                    <Node icon={Database} title="3a. Qdrant Dense" color="emerald" compact />
                    <Node icon={Network} title="3b. Neo4j Graph" color="emerald" compact />
                    <Node icon={Search} title="3c. PubMed Live" color="emerald" compact />
                  </div>
                  <div className="flex justify-center gap-4">
                    <div className="w-0.5 h-6 bg-slate-700"></div>
                  </div>
                  <Node icon={ShieldCheck} title="4. Evidence Validator" color="amber" />
                  <div className="w-0.5 h-6 bg-slate-700 mx-auto relative">
                    <div className="absolute top-1/2 left-4 flex items-center text-xs text-amber-500">
                      <ChevronDown className="rotate-90 w-3 h-3" /> Retry if score &lt; 0.7
                    </div>
                  </div>
                  <Node icon={FileText} title="5. Clinical Reasoning" color="purple" />
                </div>
              </div>
            </div>

          </div>
        )}

        {/* ─── TAB 2: RETRIEVAL ────────────────────────────────────────────── */}
        {activeTab === 'retrieval' && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
            
            <div className="text-center max-w-3xl mx-auto mb-12">
              <h2 className="text-3xl font-bold mb-4">Triple-Engine Parallel Retrieval</h2>
              <p className="text-slate-400 leading-relaxed">
                Aegis doesn't rely on a single vector search. It executes highly concurrent searches across three distinct architectural paradigms, fusing the results using Reciprocal Rank Fusion (RRF).
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
              <ArchitectureCard 
                icon={Database} 
                title="Dense + Sparse (Qdrant)" 
                tags={['Semantic', 'BM25', 'Fast']}
                description="Encodes clinical queries using BGE-Large-En-v1.5 and performs vector cosine similarity alongside BM25 sparse keyword matching for exact medical terminologies."
              />
              <ArchitectureCard 
                icon={Network} 
                title="GraphRAG (Neo4j)" 
                tags={['Ontology', 'Cypher', 'Relationships']}
                description="Traverses a heavily connected graph of clinical trials, drugs, and diseases. Excellent for multi-hop queries like 'What drugs interact with X that treat Y?'"
              />
              <ArchitectureCard 
                icon={Search} 
                title="Live Research (PubMed)" 
                tags={['Real-time', 'Systematic', 'APIs']}
                description="Dynamically queries the National Library of Medicine (PubMed) APIs to pull in the absolute latest systematic reviews for edge-case diseases."
              />
            </div>

            <div className="mt-12 p-8 rounded-2xl bg-gradient-to-r from-slate-900 to-indigo-950/30 border border-indigo-500/20">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <Layers className="text-indigo-400" /> Cross-Encoder Reranking & Trust Policies
              </h3>
              <p className="text-slate-300 leading-relaxed mb-6">
                After the parallel engines return ~40 candidate chunks, Aegis passes them through a BGE-Reranker model. But before final selection, a <strong>Source Policy Engine</strong> applies Trust Multipliers:
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatBox label="WHO / NICE Guidelines" value="1.20x" sub="Trust Multiplier" />
                <StatBox label="Cochrane Reviews" value="+0.12" sub="Keyword Boost" />
                <StatBox label="Clinical Trials" value="1.08x" sub="Document Type Boost" />
                <StatBox label="Unverified Internet" filter value="Dropped" sub="If score < 0.85" />
              </div>
            </div>

          </div>
        )}

        {/* ─── TAB 3: MULTIMODAL ─────────────────────────────────────────── */}
        {activeTab === 'multimodal' && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
             <div className="grid md:grid-cols-2 gap-12 items-center">
               <div className="order-2 md:order-1 relative rounded-2xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl">
                  <div className="flex flex-col gap-4">
                    <div className="p-4 rounded-xl border border-blue-500/30 bg-blue-500/10 flex items-center gap-4">
                      <Activity className="text-blue-400 w-8 h-8" />
                      <div>
                        <h4 className="font-bold text-blue-200">ECG Waveform Analysis</h4>
                        <p className="text-xs text-blue-300/70">Detects STEMI, Atrial Fibrillation, PVCs</p>
                      </div>
                    </div>
                    <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 flex items-center gap-4">
                      <Microscope className="text-emerald-400 w-8 h-8" />
                      <div>
                        <h4 className="font-bold text-emerald-200">Radiology (X-Ray / MRI)</h4>
                        <p className="text-xs text-emerald-300/70">Infiltrates, effusions, fractures</p>
                      </div>
                    </div>
                    <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-500/10 flex items-center gap-4">
                      <FileText className="text-purple-400 w-8 h-8" />
                      <div>
                        <h4 className="font-bold text-purple-200">Clinical OCR (Tesseract/Paddle)</h4>
                        <p className="text-xs text-purple-300/70">Extracts tabular lab results seamlessly</p>
                      </div>
                    </div>
                  </div>
               </div>
               
               <div className="order-1 md:order-2">
                 <h2 className="text-3xl font-bold mb-4">Multimodal AI Pipelines</h2>
                 <p className="text-slate-400 leading-relaxed mb-6">
                   Aegis isn't just text. The <code>backend/multimodal</code> package processes raw clinical files before they ever reach the LLM. 
                 </p>
                 <ul className="space-y-4">
                   <li className="flex gap-3 text-slate-300">
                     <ShieldCheck className="text-indigo-400 shrink-0" />
                     <span><strong>Modality Router:</strong> Automatically classifies uploaded images (ECG vs. X-Ray vs. Lab PDF) using a vision model, routing it to the specialized parsing pipeline.</span>
                   </li>
                   <li className="flex gap-3 text-slate-300">
                     <ShieldCheck className="text-indigo-400 shrink-0" />
                     <span><strong>Fallback Chains:</strong> If PaddleOCR confidence drops below 70%, the system automatically falls back to Tesseract, and finally GPT-4o-Vision to ensure critical lab values are never misread.</span>
                   </li>
                   <li className="flex gap-3 text-slate-300">
                     <ShieldCheck className="text-indigo-400 shrink-0" />
                     <span><strong>Data Fusion:</strong> Extracted metrics (like EF 35% or PR interval) are injected directly into the LLM's patient context window alongside semantic text evidence.</span>
                   </li>
                 </ul>
               </div>
             </div>
          </div>
        )}

        {/* ─── TAB 4: USE CASES ──────────────────────────────────────────── */}
        {activeTab === 'usecases' && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
             
             <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
               <UseCaseCard 
                 title="Emergency Triage"
                 risk="CRITICAL"
                 description="Patient presenting with acute chest pain and ST elevations. Aegis enforces the 'EMERGENCY' workflow, limiting retries for speed and restricting retrieval strictly to guidelines."
               />
               <UseCaseCard 
                 title="Pharmacological Audit"
                 risk="HIGH"
                 description="Checking contraindications for a patient on Warfarin prescribed a new macrolide antibiotic. Uses GraphRAG to traverse drug-drug interaction nodes."
               />
               <UseCaseCard 
                 title="Rare Disease Matching"
                 risk="MEDIUM"
                 description="Patient with undiagnosed auto-immune symptoms. The 'SIMILAR_CASE' workflow activates, embedding the patient's vitals and finding semantic matches in past electronic health records."
               />
               <UseCaseCard 
                 title="Discharge Summarization"
                 risk="LOW"
                 description="Generating a patient-friendly discharge letter. Relaxed validation strictness allows faster processing while ensuring readability."
               />
               <UseCaseCard 
                 title="Trial Matching"
                 risk="MEDIUM"
                 description="Identifying if an oncology patient is eligible for active clinical trials by running their pathology OCR results against the Neo4j trials graph."
               />
               <UseCaseCard 
                 title="Literature Synthesis"
                 risk="LOW"
                 description="A physician querying the latest consensus on Long-COVID treatments. Aegis hits the live PubMed API to pull abstract datasets and synthesizes a meta-analysis."
               />
             </div>

          </div>
        )}

      </div>
    </div>
  );
}

// ─── UTILITY COMPONENTS ──────────────────────────────────────────────────────

function Node({ icon: Icon, title, color, compact = false }: any) {
  const colors = {
    blue: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
    indigo: 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    amber: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
    purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
  };
  
  return (
    <div className={`flex items-center gap-3 p-3 rounded-xl border shadow-sm mx-auto w-fit ${compact ? 'px-4' : 'w-64'} ${colors[color as keyof typeof colors]}`}>
      <Icon className="w-5 h-5 shrink-0" />
      <span className="font-semibold text-sm">{title}</span>
    </div>
  );
}

function ArchitectureCard({ icon: Icon, title, description, tags }: any) {
  return (
    <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-700/50 hover:border-indigo-500/50 transition-colors group">
      <div className="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
        <Icon className="w-6 h-6 text-indigo-400" />
      </div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <div className="flex flex-wrap gap-2 mb-4">
        {tags.map((tag: string) => (
          <span key={tag} className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
            {tag}
          </span>
        ))}
      </div>
      <p className="text-sm text-slate-400 leading-relaxed">{description}</p>
    </div>
  );
}

function StatBox({ label, value, sub, filter }: any) {
  return (
    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-700/50 text-center">
      <div className={`text-2xl font-black mb-1 ${filter ? 'text-red-400' : 'text-white'}`}>{value}</div>
      <div className="text-xs font-bold text-slate-300 mb-0.5">{label}</div>
      <div className="text-[10px] text-slate-500 uppercase tracking-widest">{sub}</div>
    </div>
  );
}

function UseCaseCard({ title, risk, description }: any) {
  const riskColor = 
    risk === 'CRITICAL' ? 'bg-red-500/10 text-red-400 border-red-500/30' :
    risk === 'HIGH' ? 'bg-orange-500/10 text-orange-400 border-orange-500/30' :
    risk === 'MEDIUM' ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' :
    'bg-blue-500/10 text-blue-400 border-blue-500/30';

  return (
    <div className="p-6 rounded-2xl bg-slate-900/40 border border-slate-800 hover:bg-slate-900/80 transition-colors flex flex-col">
      <div className="flex items-start justify-between mb-4">
        <h3 className="font-bold text-lg text-white">{title}</h3>
        <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded border ${riskColor}`}>
          {risk} RISK
        </span>
      </div>
      <p className="text-sm text-slate-400 leading-relaxed mt-auto">{description}</p>
    </div>
  );
}
