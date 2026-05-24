// services/analysisService.ts — API bridge between frontend workspace and Aegis backend
// Phase 13: Added session management, session-aware analysis calls, and copilot API

import { PatientIntake, UploadedFile, AnalysisResult, ClinicalSection, ClarificationAnswers, Severity, CopilotResponse, SessionSummary } from "@/types/clinical";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getErrorMessage(error: unknown, fallback: string): string {
  if (!error) return fallback;
  const errRecord = error as Record<string, unknown>;
  if (typeof errRecord.detail === "string") return errRecord.detail;
  if (Array.isArray(errRecord.detail)) {
    return errRecord.detail.map((d: unknown) => {
      const item = d as Record<string, unknown>;
      const locStr = Array.isArray(item.loc) ? item.loc.join(".") : "field";
      return `${locStr}: ${item.msg ?? "error"}`;
    }).join("; ");
  }
  if (errRecord.detail && typeof errRecord.detail === "object") {
    const detailObj = errRecord.detail as Record<string, unknown>;
    return (detailObj.message as string) || JSON.stringify(errRecord.detail);
  }
  return (errRecord.message as string) || JSON.stringify(error) || fallback;
}

// ── Query builder ──────────────────────────────────────────────────────────

function buildClinicalQuery(intake: PatientIntake, files: UploadedFile[]): string {
  const { vitals, symptoms, history, clinicianNotes } = intake;

  if (clinicianNotes.trim().length > 30) {
    const fileContext: string[] = [];
    if (files.some(f => f.type === "ecg")) fileContext.push("ECG uploaded for analysis");
    if (files.some(f => f.type === "xray")) fileContext.push("Chest X-ray uploaded for analysis");
    if (files.some(f => ["pdf","lab","discharge","pathology"].includes(f.type))) {
      fileContext.push("Clinical documents and lab reports uploaded");
    }
    const suffix = fileContext.length ? ` [Additional context: ${fileContext.join(", ")}]` : "";
    return `${clinicianNotes.trim()}${suffix}. Please provide a comprehensive clinical analysis including: differential diagnosis, immediate risk assessment, contraindication checks against current medications, evidence-based treatment recommendations, and next steps.`;
  }

  const parts: string[] = [];
  if (vitals.age || vitals.gender) {
    parts.push([vitals.age && `${vitals.age}-year-old`, vitals.gender, "patient"].filter(Boolean).join(" "));
  }
  const vitalParts: string[] = [];
  if (vitals.bloodPressureSystolic && vitals.bloodPressureDiastolic)
    vitalParts.push(`BP ${vitals.bloodPressureSystolic}/${vitals.bloodPressureDiastolic} mmHg`);
  if (vitals.heartRate) vitalParts.push(`HR ${vitals.heartRate} bpm`);
  if (vitals.oxygenSaturation) vitalParts.push(`O2 sat ${vitals.oxygenSaturation}%`);
  if (vitalParts.length) parts.push(`Vitals: ${vitalParts.join(", ")}`);
  const activeSymptoms = [
    symptoms.chestPain && "chest pain", symptoms.shortnessOfBreath && "shortness of breath",
    symptoms.dizziness && "dizziness", symptoms.fever && "fever",
    symptoms.palpitations && "palpitations", symptoms.syncope && "syncope",
    symptoms.edema && "lower limb edema",
  ].filter(Boolean);
  if (activeSymptoms.length) parts.push(`Presenting with: ${activeSymptoms.join(", ")}`);
  if (symptoms.freeText) parts.push(symptoms.freeText);
  const conditions = [
    history.diabetes && "diabetes mellitus", history.hypertension && "hypertension",
    history.cad && "coronary artery disease", history.stroke && "prior stroke/TIA",
    history.chf && "congestive heart failure", history.ckd && "chronic kidney disease",
  ].filter(Boolean);
  if (conditions.length) parts.push(`Medical history: ${conditions.join(", ")}`);
  if (history.medications) parts.push(`Medications: ${history.medications}`);
  if (history.allergies) parts.push(`Allergies: ${history.allergies}`);
  const fileTypes = files.map(f => f.type);
  if (fileTypes.includes("ecg")) parts.push("ECG uploaded");
  if (fileTypes.includes("xray")) parts.push("X-ray uploaded");
  return parts.join(". ") + ". Provide comprehensive clinical analysis with differential diagnosis, risk assessment, contraindications, recommendations, and next steps.";
}

// ── Section parser ─────────────────────────────────────────────────────────

function parseSections(response: string): ClinicalSection[] {
  const sections: ClinicalSection[] = [];
  const sectionPatterns = [
    { key: "Patient Summary", title: "Patient Summary", severity: "none" as Severity },
    { key: "Primary Concern", title: "Primary Concerns", severity: "high" as Severity },
    { key: "Differential", title: "Differential Diagnosis", severity: "medium" as Severity },
    { key: "Risk", title: "Risk Assessment", severity: "high" as Severity },
    { key: "Contraindication", title: "Contraindications", severity: "critical" as Severity },
    { key: "Recommendation", title: "Recommendations", severity: "medium" as Severity },
    { key: "Next Step", title: "Next Steps", severity: "low" as Severity },
    { key: "Research", title: "Supporting Evidence", severity: "none" as Severity },
  ];

  const lines = response.split("\n");
  let currentSection = "";
  let currentContent: string[] = [];

  for (const line of lines) {
    const headerMatch = line.match(/^#+\s+(.+)|^\*\*(.+)\*\*/);
    if (headerMatch) {
      if (currentSection && currentContent.length) {
        const pattern = sectionPatterns.find((p) =>
          currentSection.toLowerCase().includes(p.key.toLowerCase())
        );
        sections.push({
          title: pattern?.title ?? currentSection,
          content: currentContent.join("\n").trim(),
          severity: pattern?.severity ?? "none",
          expandable: true,
        });
      }
      currentSection = headerMatch[1] ?? headerMatch[2] ?? "";
      currentContent = [];
    } else if (line.trim()) {
      currentContent.push(line);
    }
  }

  if (currentSection && currentContent.length) {
    sections.push({
      title: currentSection,
      content: currentContent.join("\n").trim(),
      severity: "none",
      expandable: true,
    });
  }

  if (sections.length === 0) {
    sections.push({
      title: "Clinical Analysis",
      content: response,
      severity: "none",
      expandable: false,
    });
  }

  return sections;
}

function augmentResult(data: AnalysisResult): AnalysisResult {
  data.sections = parseSections(data.final_response ?? data.reasoning ?? "");
  return data;
}

// ── Main analysis function ─────────────────────────────────────────────────

export async function runPatientAnalysis(
  intake: PatientIntake,
  files: UploadedFile[],
  clarificationAnswers?: ClarificationAnswers,
  sessionId?: string,
): Promise<AnalysisResult> {
  const query = buildClinicalQuery(intake, files);

  const body: Record<string, unknown> = { query };
  if (clarificationAnswers && Object.keys(clarificationAnswers).length > 0) {
    body.clarification_answers = clarificationAnswers;
  }
  if (sessionId) {
    body.session_id = sessionId;
  }

  const response = await fetch(`${API_BASE}/analyze/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(getErrorMessage(error, "Analysis failed"));
  }

  const data: AnalysisResult = await response.json();
  return augmentResult(data);
}

// ── Phase 12: Clarification answer submission ─────────────────────────────

export async function submitClarificationAnswers(
  query: string,
  answers: ClarificationAnswers,
  sessionId?: string,
): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE}/analyze/clarify/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      clarification_answers: answers,
      ...(sessionId && { session_id: sessionId }),
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(getErrorMessage(error, "Clarification submission failed"));
  }

  const data: AnalysisResult = await response.json();
  return augmentResult(data);
}

// ── Governance helpers ─────────────────────────────────────────────────────

export async function fetchGovernanceStats() {
  const r = await fetch(`${API_BASE}/governance/stats`);
  if (!r.ok) return null;
  return r.json();
}

export async function fetchPendingReviews() {
  const r = await fetch(`${API_BASE}/governance/reviews/pending`);
  if (!r.ok) return { reviews: [] };
  return r.json();
}

// ── Phase 13: Session Management ──────────────────────────────────────────────────

export async function createSession(): Promise<string | null> {
  try {
    const r = await fetch(`${API_BASE}/session/`, { method: "POST" });
    if (!r.ok) return null;
    const data = await r.json();
    return data.session_id ?? null;
  } catch {
    return null;
  }
}

export async function getSessionSummary(sessionId: string): Promise<SessionSummary | null> {
  try {
    const r = await fetch(`${API_BASE}/session/${sessionId}`);
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" });
  } catch {
    // Ignore delete errors
  }
}

// ── Phase 13: Copilot API ──────────────────────────────────────────────────────────

export async function askCopilot(
  question: string,
  clinicalContext: string,
  conversationHistory: Array<{ role: string; content: string }>,
  sessionId?: string,
): Promise<CopilotResponse> {
  const response = await fetch(`${API_BASE}/analyze/copilot/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      clinical_context:     clinicalContext,
      conversation_history: conversationHistory,
      ...(sessionId && { session_id: sessionId }),
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(getErrorMessage(error, "Copilot request failed"));
  }

  return response.json();
}

// ── Phase 13D: Streaming Analysis Service ──────────────────────────────────────────

export async function runAnalysisWithStreaming(
  query: string,
  sessionId: string | null,
  clarificationAnswers?: ClarificationAnswers,
  onStageUpdate?: (stage: string, message: string) => void,
  onComplete?: (result: AnalysisResult) => void,
  onError?: (err: Error) => void,
) {
  try {
    const body: Record<string, unknown> = { query };
    if (sessionId) body.session_id = sessionId;
    if (clarificationAnswers && Object.keys(clarificationAnswers).length > 0) {
      body.clarification_answers = clarificationAnswers;
    }

    const response = await fetch(`${API_BASE}/analyze/stream/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(getErrorMessage(error, "Streaming analysis failed"));
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("Response body is not readable");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const rawData = line.slice(6).trim();
          if (!rawData) continue;

          try {
            const event = JSON.parse(rawData);
            if (event.event === "stage") {
              onStageUpdate?.(event.node, event.message);
            } else if (event.event === "complete") {
              const augmented = augmentResult(event.result);
              onComplete?.(augmented);
            } else if (event.event === "error") {
              throw new Error(event.message);
            }
          } catch (e) {
            console.error("Failed to parse SSE event", e);
          }
        }
      }
    }

    if (buffer.trim() && buffer.startsWith("data: ")) {
      const rawData = buffer.slice(6).trim();
      try {
        const event = JSON.parse(rawData);
        if (event.event === "stage") {
          onStageUpdate?.(event.node, event.message);
        } else if (event.event === "complete") {
          const augmented = augmentResult(event.result);
          onComplete?.(augmented);
        } else if (event.event === "error") {
          throw new Error(event.message);
        }
      } catch {
        // Ignore parse error
      }
    }
  } catch (err) {
    const errorObject = err instanceof Error ? err : new Error(String(err));
    console.error("Streaming error:", errorObject);
    onError?.(errorObject);
  }
}
