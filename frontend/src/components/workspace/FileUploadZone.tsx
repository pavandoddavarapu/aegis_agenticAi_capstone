"use client";
// components/workspace/FileUploadZone.tsx

import { useCallback, useState } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { FileType, UploadedFile } from "@/types/clinical";

const ACCEPT_TYPES = ".pdf,.png,.jpg,.jpeg,.ecg,.csv,.txt,.docx";
const MAX_SIZE_MB = 15;

function detectFileType(name: string): FileType {
  const lower = name.toLowerCase();
  if (lower.includes("ecg") || lower.includes("ekg")) return "ecg";
  if (lower.includes("xray") || lower.includes("x-ray") || lower.includes("chest")) return "xray";
  if (lower.includes("lab") || lower.includes("result")) return "lab";
  if (lower.includes("discharge") || lower.includes("summary")) return "discharge";
  if (lower.includes("pathology") || lower.includes("biopsy")) return "pathology";
  if (lower.endsWith(".pdf")) return "pdf";
  return "other";
}

const TYPE_CONFIG: Record<FileType, { icon: string; label: string; color: string }> = {
  ecg: { icon: "📈", label: "ECG", color: "text-red-400 bg-red-900/20 border-red-700/40" },
  xray: { icon: "🩻", label: "X-Ray", color: "text-blue-400 bg-blue-900/20 border-blue-700/40" },
  pdf: { icon: "📄", label: "PDF Report", color: "text-slate-400 bg-slate-800/40 border-slate-600/40" },
  lab: { icon: "🧪", label: "Lab Results", color: "text-emerald-400 bg-emerald-900/20 border-emerald-700/40" },
  discharge: { icon: "📋", label: "Discharge Summary", color: "text-violet-400 bg-violet-900/20 border-violet-700/40" },
  pathology: { icon: "🔬", label: "Pathology", color: "text-orange-400 bg-orange-900/20 border-orange-700/40" },
  other: { icon: "📎", label: "Document", color: "text-slate-400 bg-slate-800/40 border-slate-600/40" },
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function FileUploadZone() {
  const { files, addFile, updateFile, removeFile } = useWorkspaceStore();
  const [dragging, setDragging] = useState(false);

  const processFile = useCallback(
    (file: File) => {
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        alert(`File too large. Max size is ${MAX_SIZE_MB}MB.`);
        return;
      }

      const id = Math.random().toString(36).slice(2);
      const fileType = detectFileType(file.name);

      const uploadedFile: UploadedFile = {
        id,
        name: file.name,
        size: file.size,
        type: fileType,
        status: "uploading",
        progress: 0,
      };

      addFile(uploadedFile);

      // Simulate progressive upload + processing
      let progress = 0;
      const interval = setInterval(() => {
        progress += Math.random() * 25;
        if (progress >= 100) {
          clearInterval(interval);
          updateFile(id, { status: "processing", progress: 100 });
          setTimeout(() => {
            updateFile(id, {
              status: "ready",
              extractedFindings: fileType === "ecg"
                ? "Sinus rhythm detected. Rate 72 bpm. No ST changes visible. QTc within normal limits."
                : fileType === "xray"
                ? "Lung fields clear bilaterally. No consolidation or pleural effusion."
                : `Document processed. ${Math.floor(file.size / 200)} text segments extracted.`,
            });
          }, 1500);
        } else {
          updateFile(id, { progress: Math.min(progress, 99) });
        }
      }, 200);
    },
    [addFile, updateFile]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      Array.from(e.dataTransfer.files).forEach(processFile);
    },
    [processFile]
  );

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      Array.from(e.target.files ?? []).forEach(processFile);
    },
    [processFile]
  );

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-3">
        Upload Clinical Files
      </p>

      {/* Drop zone */}
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer transition-all p-6 ${
          dragging
            ? "border-blue-500 bg-blue-500/10"
            : "border-slate-700 hover:border-slate-600 hover:bg-slate-800/40"
        }`}
      >
        <input type="file" multiple accept={ACCEPT_TYPES} className="hidden" onChange={onInputChange} />
        <div className="text-3xl">📁</div>
        <div className="text-center">
          <p className="text-xs font-medium text-slate-300">Drop files here or click to upload</p>
          <p className="text-[10px] text-slate-500 mt-0.5">ECG · X-Ray · PDF · Lab Reports · Discharge Summaries</p>
          <p className="text-[10px] text-slate-600 mt-0.5">Max {MAX_SIZE_MB}MB per file</p>
        </div>
      </label>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-3 space-y-2">
          {files.map((f) => {
            const cfg = TYPE_CONFIG[f.type];
            return (
              <div key={f.id} className="rounded-lg bg-slate-800/60 border border-slate-700/40 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`text-[10px] font-bold border rounded px-1.5 py-0.5 ${cfg.color}`}>
                      {cfg.icon} {cfg.label}
                    </span>
                    <span className="text-xs text-slate-300 truncate max-w-[140px]">{f.name}</span>
                    <span className="text-[10px] text-slate-500">{formatSize(f.size)}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {f.status === "ready" && <span className="text-emerald-400 text-[10px]">✓ Ready</span>}
                    {f.status === "processing" && <span className="text-amber-400 text-[10px] animate-pulse">⚙ Processing...</span>}
                    {f.status === "error" && <span className="text-red-400 text-[10px]">⚠ Error</span>}
                    <button
                      onClick={() => removeFile(f.id)}
                      className="text-slate-500 hover:text-red-400 transition-colors text-sm"
                    >×</button>
                  </div>
                </div>

                {/* Progress bar */}
                {f.status === "uploading" && (
                  <div className="mt-1.5 h-0.5 rounded-full bg-slate-700 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-200"
                      style={{ width: `${f.progress}%` }}
                    />
                  </div>
                )}

                {/* Extracted findings */}
                {f.status === "ready" && f.extractedFindings && (
                  <p className="mt-1.5 text-[10px] text-slate-400 leading-relaxed">
                    {f.extractedFindings}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
