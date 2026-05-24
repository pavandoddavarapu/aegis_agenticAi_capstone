// types/clinical.ts — Core domain types for the Clinical Workspace
// Phase 12: Added orchestration + evidence + clarification types

export type Gender = "male" | "female" | "other";
export type Severity = "critical" | "high" | "medium" | "low" | "none";
export type AnalysisStatus = "idle" | "uploading" | "analyzing" | "complete" | "error" | "clarification_required";

// ── Patient Intake ─────────────────────────────────────────────────────────

export interface PatientVitals {
  age: string;
  gender: Gender | "";
  weight: string;
  bloodPressureSystolic: string;
  bloodPressureDiastolic: string;
  heartRate: string;
  oxygenSaturation: string;
  temperature: string;
}

export interface PatientHistory {
  diabetes: boolean;
  hypertension: boolean;
  cad: boolean;
  stroke: boolean;
  chf: boolean;
  ckd: boolean;
  medications: string;
  allergies: string;
}

export interface PatientSymptoms {
  chestPain: boolean;
  shortnessOfBreath: boolean;
  dizziness: boolean;
  fever: boolean;
  palpitations: boolean;
  syncope: boolean;
  edema: boolean;
  freeText: string;
}

export interface PatientIntake {
  vitals: PatientVitals;
  symptoms: PatientSymptoms;
  history: PatientHistory;
  clinicianNotes: string;
}

// ── File Upload ────────────────────────────────────────────────────────────

export type FileType = "ecg" | "xray" | "pdf" | "lab" | "discharge" | "pathology" | "other";

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: FileType;
  status: "uploading" | "processing" | "ready" | "error";
  progress: number;
  preview?: string;
  extractedFindings?: string;
  emergencyFlag?: boolean;
  confidence?: number;
}

// ── Clinical Analysis Output ───────────────────────────────────────────────

export interface EvidenceItem {
  text: string;
  score: number;
  confidence: string;
  source: string;
  page: number;
  section?: string;
  document_type: string;
}

export interface ResearchPaper {
  pmid?: string;
  title: string;
  abstract?: string;
  year: number;
  publication_types?: string[];
  source: string;
  url?: string;
  evidence_level?: string;
}

export interface ClinicalSection {
  title: string;
  content: string;
  severity?: Severity;
  expandable?: boolean;
}

// ── Phase 12: Clarification Types ─────────────────────────────────────────

export interface ClarificationQuestion {
  question_id: string;
  question_text: string;
  category: string;
  priority: "critical" | "important" | "optional";
  expected_format: string;
  choices: string[];
  hint: string;
  default_if_skipped?: string;
}

export type ClarificationAnswers = Record<string, string>;

// ── Phase 12: Evidence Evaluation Types ───────────────────────────────────

export interface EvidenceScore {
  source_id: string;
  source_type: string;
  source_reference: string;
  tier: string;
  trust_score: number;
  freshness_score: number;
  relevance_score: number;
  grounding_score: number;
  overall_quality: number;
  use_in_reasoning: boolean;
  contradiction_flag: boolean;
}

export interface EvidenceQualitySummary {
  total_sources: number;
  high_quality_count: number;
  medium_quality_count: number;
  low_quality_count: number;
  filtered_count: number;
  avg_trust: number;
  avg_quality: number;
  avg_freshness: number;
  avg_relevance: number;
  has_authoritative: boolean;
  has_systematic_review: boolean;
  overall_sufficiency: "strong" | "adequate" | "weak" | "insufficient" | "unknown";
  sufficiency_score: number;
}

// ── Phase 12: Contradiction Types ─────────────────────────────────────────

export interface ContradictionPairSummary {
  source_a: string;
  source_b: string;
  conflict_type: string;
  description: string;
  severity: string;
  resolution: string;
}

export interface ContradictionSummary {
  has_contradictions: boolean;
  overall_severity: "none" | "minor" | "moderate" | "critical";
  total_penalty: number;
  escalation_required: boolean;
  summary: string;
  contradiction_count: number;
  pairs?: ContradictionPairSummary[];
}

// ── Phase 12: Execution Plan Types ────────────────────────────────────────

export interface EvidenceStrategyFlags {
  use_graph: boolean;
  use_semantic: boolean;
  use_research: boolean;
  use_similar_cases: boolean;
  use_multimodal: boolean;
  retrieval_depth: string;
}

export interface ExecutionPlanSummary {
  plan_id?: string;
  clinical_intent: string;
  goal: string;
  required_capabilities: string[];
  optional_capabilities: string[];
  evidence_strategy: EvidenceStrategyFlags;
  clarification_required: boolean;
  missing_information: string[];
  risk_level: string;
  risk_score: number;
  emergency_override: boolean;
  max_replan_iterations: number;
}

// ── Phase 12: Monitor Event ────────────────────────────────────────────────

export type MonitorEvent = Record<string, string | number | boolean | null>;

// ── Analysis Result (Phase 1–12) ──────────────────────────────────────────

export interface AnalysisResult {
  // Core output
  query: string;
  reasoning: string;
  final_response: string;

  // Query understanding
  query_type: string;
  query_variants: string[];
  query_plan: string[];

  // Evidence
  evidence: EvidenceItem[];
  evidence_count: number;

  // Validation
  confidence_score: number;
  confidence_label: string;
  validation_detail: string;

  // Agentic metadata
  workflow_trace: string[];
  retry_count: number;
  reflection_notes: string;
  processing_ms: number;

  // Governance
  review_required: boolean;
  review_id: string | null;
  review_status: string;
  escalation_required: boolean;

  // Status
  status: string;
  error?: string;

  // Parsed sections (derived client-side)
  sections?: ClinicalSection[];

  // Phase 12: Orchestration Intelligence
  clinical_intent?: string;
  execution_plan_summary?: ExecutionPlanSummary;
  clarification_required?: boolean;
  clarification_questions?: ClarificationQuestion[];
  missing_information?: string[];
  evidence_quality_summary?: EvidenceQualitySummary;
  contradiction_summary?: ContradictionSummary;
  replan_count?: number;
  patient_context?: Record<string, unknown>;
  monitor_events?: MonitorEvent[];

  // Phase 13: Session
  session_id?: string;
  trace_summary?: Record<string, unknown>;
}

export interface RecentCase {
  id: string;
  patientLabel: string;
  timestamp: string;
  severity: Severity;
  confidence: number;
  reviewRequired: boolean;
  summary: string;
}

// ── Phase 13: Conversational Session Types ──────────────────────────────

export type ConversationMessageType = "text" | "report" | "research" | "clarification" | "stage_update";

export interface ConversationMessage {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  message_type: ConversationMessageType;
  metadata?: Record<string, unknown>;
}

export interface PatientContextSummary {
  age?: string;
  gender?: string;
  chief_complaint?: string;
  vitals?: Record<string, string>;
  symptoms?: string[];
  extracted_conditions?: string[];
  medications?: string[];
  ecg_findings?: string;
  imaging_findings?: string;
  uploaded_file_types?: string[];
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  last_active: string;
  turn_count: number;
  analysis_count: number;
  has_patient_context: boolean;
  has_last_analysis: boolean;
  message_count: number;
  clarification_pending: boolean;
  conversation_history?: ConversationMessage[];
  patient_context?: PatientContextSummary;
}

// ── Phase 13: Copilot Types ──────────────────────────────────────────

export interface CopilotRequest {
  question: string;
  clinical_context: string;
  conversation_history: Array<{ role: string; content: string }>;
  session_id?: string;
}

export interface CopilotResponse {
  answer: string;
  sources_used: string[];
  confidence: string;
  processing_ms: number;
  session_id?: string;
}
