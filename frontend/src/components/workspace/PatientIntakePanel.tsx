"use client";
// components/workspace/PatientIntakePanel.tsx — Phase 12 evolved: structured intake + SufficiencyGauge

import { useMemo } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { FileUploadZone } from "./FileUploadZone";
import SufficiencyGauge from "./SufficiencyGauge";

// ── Field definitions ──────────────────────────────────────────────────────

const symptomList = [
  { key: "chestPain",           label: "Chest Pain",          icon: "❤️" },
  { key: "shortnessOfBreath",   label: "Dyspnea",             icon: "🫁" },
  { key: "dizziness",           label: "Dizziness",           icon: "🌀" },
  { key: "fever",               label: "Fever",               icon: "🌡️" },
  { key: "palpitations",        label: "Palpitations",        icon: "💓" },
  { key: "syncope",             label: "Syncope",             icon: "⚡" },
  { key: "edema",               label: "Leg Edema",           icon: "🦵" },
];

const historyList = [
  { key: "diabetes",            label: "Diabetes",            icon: "🩸" },
  { key: "hypertension",        label: "Hypertension",        icon: "📈" },
  { key: "cad",                 label: "CAD",                 icon: "❤️" },
  { key: "stroke",              label: "Stroke/TIA",          icon: "🧠" },
  { key: "chf",                 label: "Heart Failure",       icon: "💔" },
  { key: "ckd",                 label: "CKD",                 icon: "🫘" },
];

// ── Sub-components ─────────────────────────────────────────────────────────

function SectionLabel({ children, dot = "blue" }: { children: React.ReactNode; dot?: string }) {
  const dotColors: Record<string, string> = {
    blue: "bg-blue-400", violet: "bg-violet-400", amber: "bg-amber-400",
    red: "bg-red-400", emerald: "bg-emerald-400", cyan: "bg-cyan-400",
  };
  return (
    <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-2.5 flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColors[dot] ?? dotColors.blue}`} />
      {children}
    </p>
  );
}

function VitalInput({
  label, value, onChange, placeholder, unit, type = "number",
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; unit?: string; type?: string;
}) {
  const hasValue = value.trim() !== "";
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] text-slate-400 font-medium">{label}</label>
      <div className={`relative flex items-center rounded-lg border transition-colors ${
        hasValue
          ? "border-blue-500/40 bg-slate-800/70"
          : "border-slate-700/60 bg-slate-800/40 hover:border-slate-600/60"
      }`}>
        <input
          type={type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-transparent px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none"
        />
        {unit && (
          <span className="absolute right-2 text-[10px] text-slate-500 pointer-events-none">{unit}</span>
        )}
        {hasValue && (
          <span className="absolute right-6 text-[9px] text-emerald-500 pointer-events-none">✓</span>
        )}
      </div>
    </div>
  );
}

function ToggleBadge({
  label, icon, active, onClick, color = "blue",
}: {
  label: string; icon: string; active: boolean;
  onClick: () => void; color?: "blue" | "red" | "amber";
}) {
  const activeStyles = {
    blue:  "bg-blue-600/30 border-blue-500/50 text-blue-300",
    red:   "bg-red-600/20 border-red-500/50 text-red-300",
    amber: "bg-amber-600/20 border-amber-500/50 text-amber-300",
  };
  const inactiveStyle = "bg-slate-800/40 border-slate-700/40 text-slate-500 hover:border-slate-600 hover:text-slate-400";

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 border rounded-lg px-2 py-1.5 text-[10px] font-medium transition-all ${
        active ? activeStyles[color] : inactiveStyle
      }`}
    >
      <span className="text-[11px]">{icon}</span>
      <span>{label}</span>
      {active && <span className="ml-0.5 text-[9px]">✓</span>}
    </button>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function PatientIntakePanel() {
  const { intake, updateIntake } = useWorkspaceStore();
  const { vitals, symptoms, history } = intake;

  const setVital  = (key: string, val: string) => updateIntake({ vitals: { ...vitals, [key]: val } });
  const toggleSym = (key: string) => updateIntake({ symptoms: { ...symptoms, [key]: !symptoms[key as keyof typeof symptoms] } });
  const toggleHx  = (key: string) => updateIntake({ history: { ...history, [key]: !history[key as keyof typeof history] } });

  // ── Compute sufficiency fields for gauge ─────────────────────────────────
  const sufficiencyFields = useMemo(() => [
    { key: "age",      label: "Age",      icon: "👤", filled: !!vitals.age,                                          weight: 3 },
    { key: "gender",   label: "Gender",   icon: "⚧️", filled: !!vitals.gender,                                       weight: 2 },
    { key: "bp",       label: "BP",       icon: "📊", filled: !!vitals.bloodPressureSystolic,                        weight: 3 },
    { key: "hr",       label: "HR",       icon: "💓", filled: !!vitals.heartRate,                                    weight: 2 },
    { key: "o2",       label: "O₂",       icon: "🫁", filled: !!vitals.oxygenSaturation,                            weight: 2 },
    { key: "symptoms", label: "Symptoms", icon: "🩺", filled: Object.entries(symptoms).some(([k,v]) => k !== "freeText" && v === true), weight: 3 },
    { key: "history",  label: "PMH",      icon: "📋", filled: Object.entries(history).some(([k,v]) => typeof v === "boolean" && v), weight: 2 },
    { key: "meds",     label: "Meds",     icon: "💊", filled: !!history.medications,                                 weight: 2 },
    { key: "notes",    label: "Notes",    icon: "📝", filled: (intake.clinicianNotes?.length ?? 0) > 20,             weight: 3 },
  ], [vitals, symptoms, history, intake.clinicianNotes]);

  return (
    <div className="h-full flex flex-col gap-3 overflow-y-auto pr-1 custom-scrollbar">

      {/* Sufficiency Gauge */}
      <SufficiencyGauge fields={sufficiencyFields} />

      {/* Patient Information */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
        <SectionLabel dot="blue">Patient Information</SectionLabel>
        <div className="grid grid-cols-2 gap-2.5">
          <VitalInput label="Age" value={vitals.age} onChange={v => setVital("age", v)} placeholder="55" unit="yrs" />
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-400 font-medium">Gender</label>
            <select
              value={vitals.gender}
              onChange={e => setVital("gender", e.target.value)}
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs text-white focus:outline-none transition-colors ${
                vitals.gender ? "border-blue-500/40 bg-slate-800/70" : "border-slate-700/60 bg-slate-800/40"
              }`}
            >
              <option value="">Select...</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>
          <VitalInput label="Weight" value={vitals.weight} onChange={v => setVital("weight", v)} placeholder="70" unit="kg" />
          <VitalInput label="O₂ Saturation" value={vitals.oxygenSaturation} onChange={v => setVital("oxygenSaturation", v)} placeholder="98" unit="%" />
        </div>
      </div>

      {/* Vital Signs */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
        <SectionLabel dot="cyan">Vital Signs</SectionLabel>
        <div className="grid grid-cols-2 gap-2.5">
          <VitalInput label="Systolic BP"  value={vitals.bloodPressureSystolic}  onChange={v => setVital("bloodPressureSystolic", v)}  placeholder="120" unit="mmHg" />
          <VitalInput label="Diastolic BP" value={vitals.bloodPressureDiastolic} onChange={v => setVital("bloodPressureDiastolic", v)} placeholder="80"  unit="mmHg" />
          <VitalInput label="Heart Rate"   value={vitals.heartRate}              onChange={v => setVital("heartRate", v)}              placeholder="72"  unit="bpm"  />
          <VitalInput label="Temperature"  value={vitals.temperature}            onChange={v => setVital("temperature", v)}            placeholder="37.0" unit="°C" />
        </div>

        {/* Vitals summary bar */}
        {(vitals.bloodPressureSystolic && vitals.heartRate) && (
          <div className="mt-3 flex items-center gap-3 px-2.5 py-2 rounded-lg bg-slate-800/40 border border-slate-700/30">
            {vitals.bloodPressureSystolic && (
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-slate-500">BP</span>
                <span className={`text-[11px] font-bold ${
                  Number(vitals.bloodPressureSystolic) > 140 ? "text-red-400" :
                  Number(vitals.bloodPressureSystolic) < 90  ? "text-amber-400" :
                  "text-emerald-400"
                }`}>{vitals.bloodPressureSystolic}/{vitals.bloodPressureDiastolic || "?"}</span>
              </div>
            )}
            {vitals.heartRate && (
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-slate-500">HR</span>
                <span className={`text-[11px] font-bold ${
                  Number(vitals.heartRate) > 100 ? "text-amber-400" :
                  Number(vitals.heartRate) < 50  ? "text-amber-400" :
                  "text-emerald-400"
                }`}>{vitals.heartRate} bpm</span>
              </div>
            )}
            {vitals.oxygenSaturation && (
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-slate-500">SpO₂</span>
                <span className={`text-[11px] font-bold ${
                  Number(vitals.oxygenSaturation) < 92 ? "text-red-400" :
                  Number(vitals.oxygenSaturation) < 95 ? "text-amber-400" :
                  "text-emerald-400"
                }`}>{vitals.oxygenSaturation}%</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Presenting Symptoms */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
        <SectionLabel dot="red">Presenting Symptoms</SectionLabel>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {symptomList.map(s => (
            <ToggleBadge
              key={s.key}
              label={s.label}
              icon={s.icon}
              active={symptoms[s.key as keyof typeof symptoms] as boolean}
              onClick={() => toggleSym(s.key)}
              color="red"
            />
          ))}
        </div>
        <textarea
          value={symptoms.freeText}
          onChange={e => updateIntake({ symptoms: { ...symptoms, freeText: e.target.value } })}
          placeholder="Additional symptoms, onset, duration, character, radiation, timing..."
          rows={2}
          className="w-full bg-slate-800/40 border border-slate-700/50 rounded-lg px-2.5 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500/40 resize-none transition-colors"
        />
      </div>

      {/* Medical History */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
        <SectionLabel dot="amber">Medical History</SectionLabel>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {historyList.map(h => (
            <ToggleBadge
              key={h.key}
              label={h.label}
              icon={h.icon}
              active={history[h.key as keyof typeof history] as boolean}
              onClick={() => toggleHx(h.key)}
              color="amber"
            />
          ))}
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-400 font-medium flex items-center gap-1.5">
              <span>💊</span> Current Medications
            </label>
            <textarea
              value={history.medications}
              onChange={e => updateIntake({ history: { ...history, medications: e.target.value } })}
              placeholder="e.g. Metformin 500mg BD, Atorvastatin 20mg OD, Aspirin 75mg OD..."
              rows={2}
              className={`w-full rounded-lg border px-2.5 py-2 text-xs text-white placeholder-slate-600 focus:outline-none resize-none transition-colors ${
                history.medications
                  ? "border-blue-500/40 bg-slate-800/70"
                  : "border-slate-700/50 bg-slate-800/40 focus:border-blue-500/40"
              }`}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-400 font-medium flex items-center gap-1.5">
              <span>⚠️</span> Known Allergies
            </label>
            <input
              value={history.allergies}
              onChange={e => updateIntake({ history: { ...history, allergies: e.target.value } })}
              placeholder="e.g. Penicillin, Sulfonamides — or NKDA"
              className={`w-full rounded-lg border px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none transition-colors ${
                history.allergies
                  ? "border-blue-500/40 bg-slate-800/70"
                  : "border-slate-700/50 bg-slate-800/40 focus:border-blue-500/40"
              }`}
            />
          </div>
        </div>
      </div>

      {/* Clinician Notes */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
        <SectionLabel dot="violet">Clinical Notes / Presenting Complaint</SectionLabel>
        <textarea
          value={intake.clinicianNotes}
          onChange={e => updateIntake({ clinicianNotes: e.target.value })}
          placeholder="Describe the presenting complaint, clinical context, specific concerns or questions for the AI...&#10;&#10;e.g. 65-year-old male with crushing chest pain radiating to left arm, 2 hours onset, diaphoresis, BP 160/100..."
          rows={5}
          className={`w-full rounded-lg border px-2.5 py-2 text-xs text-white placeholder-slate-600 focus:outline-none resize-none transition-colors leading-relaxed ${
            (intake.clinicianNotes?.length ?? 0) > 20
              ? "border-blue-500/40 bg-slate-800/70"
              : "border-slate-700/50 bg-slate-800/40 focus:border-blue-500/40"
          }`}
        />
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[10px] text-slate-600">{intake.clinicianNotes?.length ?? 0} characters</span>
          {(intake.clinicianNotes?.length ?? 0) < 20 && (
            <span className="text-[10px] text-amber-600">Add at least 20 chars for better analysis</span>
          )}
        </div>
      </div>

      {/* File Upload */}
      <FileUploadZone />
    </div>
  );
}
