"use client";

import { useWorkspaceStore } from "@/stores/workspaceStore";
import { FileUploadZone } from "./FileUploadZone";

export default function PatientContextSidebar() {
  const { sessionId, patientContext, clearSession } = useWorkspaceStore();

  return (
    <div className="w-[320px] shrink-0 border-r border-slate-800/60 bg-slate-900/40 flex flex-col h-full overflow-hidden">
      {/* Session Header */}
      <div className="p-4 border-b border-slate-800/50 flex flex-col gap-2 shrink-0">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
            Clinical Context
          </p>
          {sessionId && (
            <button
              onClick={clearSession}
              className="text-[10px] text-slate-400 hover:text-red-400 font-medium px-2 py-0.5 border border-slate-700/50 hover:border-red-900/40 rounded-md transition-all bg-slate-950/20"
            >
              Reset Session
            </button>
          )}
        </div>
        {sessionId ? (
          <div className="flex items-center gap-1.5 py-1 px-2 rounded-lg bg-indigo-950/30 border border-indigo-800/30 w-fit">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-[9px] font-mono text-indigo-300">
              ID: {sessionId.slice(0, 8)}...
            </span>
          </div>
        ) : (
          <div className="text-[10px] text-slate-500 italic">No active session</div>
        )}
      </div>

      {/* Sidebar Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        
        {/* Patient Demographics & Vitals */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/30 p-3.5 space-y-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
            🧑 Patient Profile
          </p>
          
          {patientContext ? (
            <div className="space-y-2.5">
              {/* Demo grid */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-950/30 rounded-lg p-2 border border-slate-800/30">
                  <p className="text-[9px] text-slate-500 uppercase">Age</p>
                  <p className="text-xs font-bold text-slate-200">{patientContext.age ?? "N/A"}</p>
                </div>
                <div className="bg-slate-950/30 rounded-lg p-2 border border-slate-800/30">
                  <p className="text-[9px] text-slate-500 uppercase">Gender</p>
                  <p className="text-xs font-bold text-slate-200 capitalize">{patientContext.gender ?? "N/A"}</p>
                </div>
              </div>

              {/* Chief complaint */}
              {patientContext.chief_complaint && (
                <div className="bg-slate-950/30 rounded-lg p-2 border border-slate-800/30">
                  <p className="text-[9px] text-slate-500 uppercase">Chief Complaint</p>
                  <p className="text-xs font-medium text-slate-300 leading-normal">
                    {patientContext.chief_complaint}
                  </p>
                </div>
              )}

              {/* Vitals */}
              {patientContext.vitals && Object.keys(patientContext.vitals).length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[9px] font-bold uppercase text-slate-600">Vitals Measurements</p>
                  <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                    {Object.entries(patientContext.vitals).map(([k, v]) => (
                      <div key={k} className="flex justify-between py-1 px-1.5 rounded bg-slate-950/10 border border-slate-850">
                        <span className="text-slate-500 capitalize">{k.replace(/([A-Z])/g, " $1")}</span>
                        <span className="font-mono text-slate-200 font-bold">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-[10px] text-slate-500 italic">No patient profile data extracted yet.</p>
          )}
        </div>

        {/* Clinical History & Findings */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/30 p-3.5 space-y-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
            📋 Findings & History
          </p>

          {patientContext ? (
            <div className="space-y-3">
              {/* Conditions */}
              {patientContext.extracted_conditions && patientContext.extracted_conditions.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[9px] uppercase text-slate-600 font-bold">Conditions</p>
                  <div className="flex flex-wrap gap-1">
                    {patientContext.extracted_conditions.map((c) => (
                      <span key={c} className="text-[9px] px-2 py-0.5 rounded bg-blue-950/20 border border-blue-900/40 text-blue-300 capitalize">
                        {c.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Symptoms */}
              {patientContext.symptoms && patientContext.symptoms.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[9px] uppercase text-slate-600 font-bold">Symptoms</p>
                  <div className="flex flex-wrap gap-1">
                    {patientContext.symptoms.map((s) => (
                      <span key={s} className="text-[9px] px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Medications */}
              {patientContext.medications && patientContext.medications.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[9px] uppercase text-slate-600 font-bold">Medications</p>
                  <div className="flex flex-wrap gap-1">
                    {patientContext.medications.map((m) => (
                      <span key={m} className="text-[9px] px-2 py-0.5 rounded bg-violet-950/20 border border-violet-900/40 text-violet-300">
                        {m}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Multimodal context findings */}
              {(patientContext.ecg_findings || patientContext.imaging_findings) && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[9px] uppercase text-slate-600 font-bold">Diagnostic Upload Summaries</p>
                  {patientContext.ecg_findings && (
                    <div className="text-[9px] leading-relaxed text-slate-400 bg-slate-950/30 p-2 rounded-lg border border-slate-850">
                      <span className="font-bold text-red-400">ECG:</span> {patientContext.ecg_findings}
                    </div>
                  )}
                  {patientContext.imaging_findings && (
                    <div className="text-[9px] leading-relaxed text-slate-400 bg-slate-950/30 p-2 rounded-lg border border-slate-850">
                      <span className="font-bold text-blue-400">Imaging:</span> {patientContext.imaging_findings}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="text-[10px] text-slate-500 italic">No clinical history accumulated.</p>
          )}
        </div>

        {/* File Upload Zone */}
        <FileUploadZone />

      </div>
    </div>
  );
}
