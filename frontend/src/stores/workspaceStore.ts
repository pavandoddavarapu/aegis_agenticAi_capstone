// stores/workspaceStore.ts — Global workspace state (Zustand)
// Phase 13: Added session management, conversation messages, and sessionId

import { create } from "zustand";
import {
  PatientIntake,
  UploadedFile,
  AnalysisResult,
  AnalysisStatus,
  RecentCase,
  ConversationMessage,
  PatientContextSummary,
} from "@/types/clinical";

const defaultIntake: PatientIntake = {
  vitals: {
    age: "",
    gender: "",
    weight: "",
    bloodPressureSystolic: "",
    bloodPressureDiastolic: "",
    heartRate: "",
    oxygenSaturation: "",
    temperature: "",
  },
  symptoms: {
    chestPain: false,
    shortnessOfBreath: false,
    dizziness: false,
    fever: false,
    palpitations: false,
    syncope: false,
    edema: false,
    freeText: "",
  },
  history: {
    diabetes: false,
    hypertension: false,
    cad: false,
    stroke: false,
    chf: false,
    ckd: false,
    medications: "",
    allergies: "",
  },
  clinicianNotes: "",
};

interface WorkspaceStore {
  // ── Intake state ────────────────────────────────────────────────────────────
  intake: PatientIntake;
  updateIntake: (updates: Partial<PatientIntake>) => void;
  resetIntake: () => void;

  // ── File uploads ────────────────────────────────────────────────────────────
  files: UploadedFile[];
  addFile: (file: UploadedFile) => void;
  updateFile: (id: string, updates: Partial<UploadedFile>) => void;
  removeFile: (id: string) => void;

  // ── Analysis state ──────────────────────────────────────────────────────────
  status: AnalysisStatus;
  result: AnalysisResult | null;
  setStatus: (status: AnalysisStatus) => void;
  setResult: (result: AnalysisResult | null) => void;

  // ── Recent cases ────────────────────────────────────────────────────────────
  recentCases: RecentCase[];
  addRecentCase: (c: RecentCase) => void;

  // ── UI state ─────────────────────────────────────────────────────────────────
  showWorkflowTrace: boolean;
  toggleWorkflowTrace: () => void;
  activeSection: string;
  setActiveSection: (s: string) => void;

  // ── Phase 13: Session Management ─────────────────────────────────────────────
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
  clearSession: () => void;

  // ── Phase 13: Conversation Messages ──────────────────────────────────────────
  messages: ConversationMessage[];
  addMessage: (msg: ConversationMessage) => void;
  clearMessages: () => void;

  // ── Phase 13: Patient Context (dynamically populated from analysis) ───────────
  patientContext: PatientContextSummary | null;
  setPatientContext: (ctx: PatientContextSummary | null) => void;

  // ── Phase 13: Right panel tab ─────────────────────────────────────────────────
  rightTab: "plan" | "evidence" | "governance" | "copilot";
  setRightTab: (tab: "plan" | "evidence" | "governance" | "copilot") => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  // ── Intake ──────────────────────────────────────────────────────────────────
  intake: defaultIntake,
  updateIntake: (updates) =>
    set((state) => ({ intake: { ...state.intake, ...updates } })),
  resetIntake: () => set({
    intake: defaultIntake,
    files: [],
    result: null,
    status: "idle",
    messages: [],
    patientContext: null,
  }),

  // ── Files ───────────────────────────────────────────────────────────────────
  files: [],
  addFile: (file) => set((state) => ({ files: [...state.files, file] })),
  updateFile: (id, updates) =>
    set((state) => ({
      files: state.files.map((f) => (f.id === id ? { ...f, ...updates } : f)),
    })),
  removeFile: (id) =>
    set((state) => ({ files: state.files.filter((f) => f.id !== id) })),

  // ── Analysis ─────────────────────────────────────────────────────────────────
  status: "idle",
  result: null,
  setStatus: (status) => set({ status }),
  setResult: (result) => set({ result }),

  // ── Recent Cases ─────────────────────────────────────────────────────────────
  recentCases: [],
  addRecentCase: (c) =>
    set((state) => ({ recentCases: [c, ...state.recentCases].slice(0, 10) })),

  // ── UI ───────────────────────────────────────────────────────────────────────
  showWorkflowTrace: false,
  toggleWorkflowTrace: () =>
    set((state) => ({ showWorkflowTrace: !state.showWorkflowTrace })),
  activeSection: "summary",
  setActiveSection: (activeSection) => set({ activeSection }),

  // ── Phase 13: Session ─────────────────────────────────────────────────────────
  sessionId: null,
  setSessionId: (sessionId) => set({ sessionId }),
  clearSession: () => set({
    sessionId: null,
    messages: [],
    patientContext: null,
    result: null,
    status: "idle",
  }),

  // ── Phase 13: Conversation Messages ──────────────────────────────────────────
  messages: [],
  addMessage: (msg) =>
    set((state) => ({
      messages: [...state.messages, msg].slice(-100), // keep last 100 messages
    })),
  clearMessages: () => set({ messages: [] }),

  // ── Phase 13: Patient Context ─────────────────────────────────────────────────
  patientContext: null,
  setPatientContext: (patientContext) => set({ patientContext }),

  // ── Phase 13: Right Panel Tab ─────────────────────────────────────────────────
  rightTab: "plan",
  setRightTab: (rightTab) => set({ rightTab }),
}));
