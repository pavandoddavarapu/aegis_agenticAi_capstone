"use client";

import { useEffect, useState } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { createSession } from "@/services/analysisService";
import PatientContextSidebar from "@/components/workspace/PatientContextSidebar";
import ConversationalChatPanel from "@/components/workspace/ConversationalChatPanel";
import ExecutionPlanViewer from "@/components/workspace/ExecutionPlanViewer";
import EvidenceScorecard from "@/components/workspace/EvidenceScorecard";
import ContradictionAlert from "@/components/workspace/ContradictionAlert";
import GovernancePanel from "@/components/workspace/GovernancePanel";

export default function WorkspacePage() {
  const {
    sessionId,
    setSessionId,
    status,
    result,
    rightTab,
    setRightTab,
  } = useWorkspaceStore();

  const [isRightPanelOpen, setIsRightPanelOpen] = useState(false);

  // Initialize session on mount if not already initialized
  useEffect(() => {
    async function initSession() {
      if (!sessionId) {
        try {
          const sid = await createSession();
          if (sid) {
            setSessionId(sid);
          }
        } catch (err) {
          console.error("Failed to initialize conversational patient session:", err);
        }
      }
    }
    initSession();
  }, [sessionId, setSessionId]);

  return (
    <div className="h-screen w-full flex flex-col bg-background text-foreground overflow-hidden font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800/70 bg-slate-900/50 backdrop-blur-sm z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-700 flex items-center justify-center font-black text-sm shadow-md shadow-blue-900/40 select-none">
            Æ
          </div>
          <div>
            <h1 className="text-xs font-bold tracking-tight">Aegis Clinical Intelligence Platform</h1>
            <p className="text-[9px] text-slate-500">
              Conversational Multi-Agent Orchestration · Phase 13
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {sessionId && (
            <div className="flex items-center gap-1.5 border border-indigo-900/40 bg-indigo-950/20 rounded-lg px-2.5 py-1 text-[10px] text-indigo-300">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              <span>Session: {sessionId.slice(0, 8)}...</span>
            </div>
          )}

          {status === "analyzing" && (
            <div className="flex items-center gap-1.5 border border-blue-900/30 bg-blue-900/20 rounded-lg px-2.5 py-1 text-[10px] text-blue-300">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
              <span>Orchestrating...</span>
            </div>
          )}

          <a
            href="/governance"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700 rounded-lg px-3 py-1 transition-all"
          >
            🏛 Governance Review
          </a>
          <a
            href="/architecture"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700 rounded-lg px-3 py-1 transition-all"
          >
            🧩 Architecture
          </a>
          <a
            href="/dashboard"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700 rounded-lg px-3 py-1 transition-all"
          >
            📊 Metrics Dashboard
          </a>
          <button
            onClick={() => setIsRightPanelOpen(!isRightPanelOpen)}
            className="text-[10px] text-indigo-400 hover:text-indigo-300 border border-indigo-900/50 hover:border-indigo-700 rounded-lg px-3 py-1 transition-all ml-2 bg-indigo-950/20"
          >
            {isRightPanelOpen ? "▶ Hide Intelligence" : "◀ Show Intelligence"}
          </button>
        </div>
      </header>

      {/* Main Workspace Panels Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANEL: Patient Context Sidebar */}
        <PatientContextSidebar />

        {/* CENTER PANEL: Primary Conversational Workspace */}
        <div className="flex-1 flex flex-col border-r border-slate-800/60 overflow-hidden bg-slate-950/10">
          <ConversationalChatPanel />
        </div>

        {/* RIGHT PANEL: Intelligence Tabs (Plan, Evidence, Governance) */}
        {isRightPanelOpen && (
          <div className="w-[340px] shrink-0 flex flex-col bg-slate-900/25 overflow-hidden border-l border-slate-800/60 animate-in slide-in-from-right-8 duration-300">
            {/* Tabs bar */}
          <div className="flex border-b border-slate-850 shrink-0">
            {(["plan", "evidence", "governance"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className={`flex-1 py-3 text-[10px] font-bold uppercase tracking-[0.1em] transition-all duration-200 select-none ${
                  rightTab === tab
                    ? "text-white border-b border-blue-500 bg-slate-900/50"
                    : "text-slate-500 hover:text-slate-350"
                }`}
              >
                {tab === "plan" ? "🗂 Plan" : tab === "evidence" ? "⚖️ Evidence" : "🏛 Governance"}
              </button>
            ))}
          </div>

          {/* Tab content area */}
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar space-y-4">
            {result ? (
              <>
                {/* PLAN tab */}
                {rightTab === "plan" && (
                  <>
                    <ExecutionPlanViewer
                      plan={result.execution_plan_summary ?? null}
                      intent={result.clinical_intent}
                    />

                    {/* Information Gaps (Missing info) */}
                    {result.missing_information && result.missing_information.length > 0 && (
                      <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3.5">
                        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500 mb-2 flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                          Clinical Gaps Detected
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {result.missing_information.map((item) => (
                            <span
                              key={item}
                              className="text-[9px] px-2 py-0.5 rounded-md bg-amber-950/20 border border-amber-900/30 text-amber-400 capitalize"
                            >
                              {item.replace(/_/g, " ")}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Agent state checkpoints monitoring */}
                    {result.monitor_events && result.monitor_events.length > 0 && (
                      <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3.5">
                        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500 mb-2 flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse" />
                          Supervisor Monitor Log
                        </p>
                        <div className="space-y-2 font-mono text-[9px] text-slate-400">
                          {result.monitor_events.slice(-4).map((ev, idx) => {
                            const e = ev as Record<string, any>;
                            return (
                              <div key={idx} className="flex justify-between items-center py-0.5 border-b border-slate-850 last:border-0">
                                <span className="capitalize text-slate-500 truncate max-w-[150px]">
                                  {String(e.checkpoint ?? "").replace(/_/g, " ")}
                                </span>
                                <span
                                  className={
                                    e.overall_sufficiency === "weak" || e.overall_sufficiency === "insufficient"
                                      ? "text-red-400"
                                      : "text-emerald-400"
                                  }
                                >
                                  {String(e.overall_sufficiency ?? e.has_contradictions ?? "OK")}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* EVIDENCE tab */}
                {rightTab === "evidence" && (
                  <>
                    <EvidenceScorecard summary={result.evidence_quality_summary ?? null} />
                    <ContradictionAlert summary={result.contradiction_summary ?? null} />

                    {/* Top Evidence list */}
                    {result.evidence && result.evidence.length > 0 && (
                      <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3.5">
                        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500 mb-2.5">
                          Retrieved Evidence Sources ({result.evidence_count})
                        </p>
                        <div className="space-y-2">
                          {result.evidence.slice(0, 10).map((ev, i) => (
                            <div key={i} className="flex items-start gap-2 border-b border-slate-850 pb-2 last:border-0 last:pb-0">
                              <span
                                className={`mt-0.5 shrink-0 text-[8px] font-extrabold px-1.5 py-0.5 rounded ${
                                  ev.confidence === "HIGH"
                                    ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
                                    : ev.confidence === "MEDIUM"
                                    ? "bg-amber-950 text-amber-400 border border-amber-900"
                                    : "bg-slate-800 text-slate-500"
                                }`}
                              >
                                {Math.round(ev.score * 100)}%
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="text-[9px] text-slate-400 font-medium truncate">
                                  {ev.source} · p.{ev.page}
                                </p>
                                <p className="text-[9px] text-slate-500 leading-normal line-clamp-2 mt-0.5">
                                  {ev.text}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* GOVERNANCE tab */}
                {rightTab === "governance" && <GovernancePanel />}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center text-center h-[60%] p-6">
                <span className="text-3xl mb-3 opacity-60">🧠</span>
                <p className="text-xs font-semibold text-slate-350">Intelligence Inactive</p>
                <p className="text-[10px] text-slate-500 leading-relaxed mt-1 max-w-[200px] mx-auto">
                  Aegis analysis details will populate here once you start the patient intake in the chat workspace.
                </p>
              </div>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
