"""
session.py — Conversational Patient Session Models (Phase 13)

Defines the persistent multi-turn session that tracks:
  - Full conversation message history
  - Accumulated patient context across turns
  - Snapshots of each analysis run's key findings
  - Pending clarification state

Design:
  - Sessions are keyed by session_id (UUID string)
  - Session TTL: 2 hours of inactivity
  - Patient context ACCUMULATES (not replaced) across turns
  - Last analysis snapshot is always kept for copilot context
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Conversation Message ───────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    """A single message in the multi-turn conversation."""
    message_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    role:         str                                    # "user" | "assistant" | "system"
    content:      str                                    # text content
    timestamp:    str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    message_type: str = "text"                           # "text"|"report"|"research"|"clarification"
    metadata:     Dict[str, Any] = Field(default_factory=dict)


# ── Accumulated Patient Context ────────────────────────────────────────────────

class AccumulatedPatientContext(BaseModel):
    """
    Patient demographics and clinical data accumulated across ALL conversation turns.

    Merge strategy:
      - Demographics (age, gender): keep first non-null value
      - Lists (symptoms, medications, conditions): union across turns
      - Strings (ECG findings, imaging): keep most recent non-empty value
      - Vitals dict: merge, prefer later values (more recent measurement)
    """
    age:                  Optional[str] = None
    gender:               Optional[str] = None
    chief_complaint:      Optional[str] = None

    # Vitals dict (key: "bp" | "hr" | "o2" | "temp" | "rr", value: string reading)
    vitals:               Dict[str, str] = Field(default_factory=dict)

    # Accumulated lists (union across turns)
    symptoms:             List[str] = Field(default_factory=list)
    extracted_conditions: List[str] = Field(default_factory=list)
    medications:          List[str] = Field(default_factory=list)
    allergies:            List[str] = Field(default_factory=list)

    # Uploaded file types (e.g. ["ecg", "xray", "pdf"])
    uploaded_file_types:  List[str] = Field(default_factory=list)

    # Multimodal findings (updated when new uploads are analyzed)
    ecg_findings:         Optional[str] = None
    imaging_findings:     Optional[str] = None
    ocr_findings:         Optional[str] = None

    # Lab values accumulated
    lab_values:           Dict[str, str] = Field(default_factory=dict)

    # Graph knowledge accumulated from Neo4j
    graph_knowledge:      str = ""

    def merge(self, new_context: Dict[str, Any]) -> None:
        """Merge new patient context into this accumulated state."""
        # Demographics — keep first non-null
        if not self.age and new_context.get("age"):
            self.age = str(new_context["age"])
        if not self.gender and new_context.get("gender"):
            self.gender = str(new_context["gender"])
        if not self.chief_complaint and new_context.get("chief_complaint"):
            self.chief_complaint = str(new_context["chief_complaint"])

        # Vitals — merge and overwrite
        new_vitals = new_context.get("vitals") or {}
        for k, v in new_vitals.items():
            if v:
                self.vitals[k] = str(v)

        # Symptoms — union
        new_symptoms = new_context.get("symptoms", [])
        for sym in new_symptoms:
            if sym and sym not in self.symptoms:
                self.symptoms.append(sym)

        # Conditions — union
        new_conditions = new_context.get("extracted_conditions", [])
        for cond in new_conditions:
            if cond and cond not in self.extracted_conditions:
                self.extracted_conditions.append(cond)

        # Medications — union
        new_meds = new_context.get("medications", [])
        for med in new_meds:
            if med and med not in self.medications:
                self.medications.append(med)

        # Allergies — union
        new_allergies = new_context.get("allergies", [])
        for alg in new_allergies:
            if alg and alg not in self.allergies:
                self.allergies.append(alg)

        # File types — union
        new_files = new_context.get("uploaded_file_types", [])
        for ftype in new_files:
            if ftype and ftype not in self.uploaded_file_types:
                self.uploaded_file_types.append(ftype)

        # Multimodal findings — keep most recent
        if new_context.get("ecg_findings"):
            self.ecg_findings = new_context["ecg_findings"]
        if new_context.get("imaging_findings"):
            self.imaging_findings = new_context["imaging_findings"]
        if new_context.get("ocr_findings"):
            self.ocr_findings = new_context["ocr_findings"]

        # Labs — merge and overwrite
        new_labs = new_context.get("lab_values") or {}
        for k, v in new_labs.items():
            if v:
                self.lab_values[k] = str(v)

        # Graph knowledge
        if new_context.get("graph_knowledge"):
            self.graph_knowledge = new_context["graph_knowledge"]

    def to_context_string(self) -> str:
        """
        Serialize patient context to a compact string for LLM context injection.
        Stays under ~400 tokens.
        """
        parts = []
        if self.age or self.gender:
            demo = " ".join(filter(None, [self.age and f"{self.age}yo", self.gender]))
            parts.append(f"Patient: {demo}")
        if self.chief_complaint:
            parts.append(f"Chief complaint: {self.chief_complaint}")
        if self.vitals:
            vitals_str = ", ".join(f"{k}={v}" for k, v in self.vitals.items())
            parts.append(f"Vitals: {vitals_str}")
        if self.symptoms:
            parts.append(f"Symptoms: {', '.join(self.symptoms[:6])}")
        if self.extracted_conditions:
            parts.append(f"Conditions: {', '.join(self.extracted_conditions[:6])}")
        if self.medications:
            parts.append(f"Medications: {', '.join(self.medications[:5])}")
        if self.allergies:
            parts.append(f"Allergies: {', '.join(self.allergies[:3])}")
        if self.ecg_findings:
            parts.append(f"ECG: {self.ecg_findings[:200]}")
        if self.imaging_findings:
            parts.append(f"Imaging: {self.imaging_findings[:200]}")
        if self.lab_values:
            lab_str = ", ".join(f"{k}={v}" for k, v in list(self.lab_values.items())[:5])
            parts.append(f"Labs: {lab_str}")
        return "\n".join(parts)


# ── Analysis Snapshot ──────────────────────────────────────────────────────────

class AnalysisSnapshot(BaseModel):
    """
    Compact snapshot of key findings from a single analysis run.
    Stored in the session for copilot context access without re-running analysis.
    """
    timestamp:               str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    clinical_intent:         str = "unknown"
    risk_level:              str = "unknown"
    confidence_score:        float = 0.0
    confidence_label:        str = "LOW"
    evidence_sufficiency:    str = "unknown"       # strong | adequate | weak | insufficient
    has_contradictions:      bool = False
    contradiction_summary:   Optional[str] = None
    escalation_required:     bool = False
    missing_information:     List[str] = Field(default_factory=list)
    key_findings:            str = ""              # first 500 chars of final_response
    evidence_source_count:   int = 0
    high_quality_count:      int = 0
    replan_count:            int = 0

    # Full evidence quality summary dict (for detailed copilot questions)
    evidence_quality_summary: Dict[str, Any] = Field(default_factory=dict)

    def to_context_string(self) -> str:
        """Serialize snapshot for LLM context injection (~300 tokens)."""
        parts = [
            f"Clinical intent: {self.clinical_intent.replace('_', ' ')}",
            f"Risk level: {self.risk_level}",
            f"Confidence: {self.confidence_label} ({self.confidence_score:.0%})",
            f"Evidence quality: {self.evidence_sufficiency} ({self.evidence_source_count} sources, {self.high_quality_count} high-quality)",
        ]
        if self.has_contradictions and self.contradiction_summary:
            parts.append(f"Contradictions: {self.contradiction_summary[:200]}")
        if self.escalation_required:
            parts.append("⚠️ Escalation required")
        if self.missing_information:
            parts.append(f"Missing info: {', '.join(self.missing_information[:4])}")
        if self.key_findings:
            parts.append(f"Key findings: {self.key_findings[:300]}")
        return "\n".join(parts)


# ── Conversational Patient Session ─────────────────────────────────────────────

class ConversationalPatientSession(BaseModel):
    """
    Persistent multi-turn clinical conversation session.

    Lifecycle:
      - Created: POST /session/
      - Updated: Each /analyze/ or /analyze/copilot/ call appends to messages
      - Expired: 2 hours of inactivity (TTL cleanup in session_store)
      - Deleted: DELETE /session/{session_id}
    """
    session_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at:   str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_active:  str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Full conversation history (bounded to last 50 messages in production)
    messages: List[ConversationMessage] = Field(default_factory=list)

    # Accumulated patient context (merges across turns)
    patient_context: AccumulatedPatientContext = Field(
        default_factory=AccumulatedPatientContext
    )

    # Most recent analysis snapshot (for copilot context)
    last_analysis: Optional[AnalysisSnapshot] = None

    # Session statistics
    turn_count:       int = 0
    analysis_count:   int = 0

    # Pending clarification state
    clarification_pending:  bool = False
    pending_query:          Optional[str] = None
    pending_questions:      List[Dict[str, Any]] = Field(default_factory=list)

    def add_message(self, role: str, content: str, message_type: str = "text",
                    metadata: Dict[str, Any] | None = None) -> ConversationMessage:
        """Append a message to the conversation history."""
        msg = ConversationMessage(
            role=role,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self.turn_count += 1
        self.last_active = datetime.utcnow().isoformat()
        return msg

    def update_from_analysis(self, agent_state: Dict[str, Any]) -> None:
        """
        Merge analysis results into the session's persistent state.
        Called after each successful analysis run.
        """
        # Merge patient context
        new_ctx = agent_state.get("patient_context") or {}
        self.patient_context.merge(new_ctx)

        # Build analysis snapshot
        ev_summary = agent_state.get("evidence_quality_summary") or {}
        contradiction = agent_state.get("contradiction_report") or {}
        score = float(agent_state.get("validation_score") or 0.0)

        self.last_analysis = AnalysisSnapshot(
            clinical_intent      = agent_state.get("clinical_intent", "unknown"),
            risk_level           = agent_state.get("risk_level", "unknown"),
            confidence_score     = score,
            confidence_label     = "HIGH" if score >= 0.80 else ("MEDIUM" if score >= 0.60 else "LOW"),
            evidence_sufficiency = ev_summary.get("overall_sufficiency", "unknown"),
            has_contradictions   = contradiction.get("has_contradictions", False),
            contradiction_summary = contradiction.get("summary"),
            escalation_required  = agent_state.get("escalation_required", False),
            missing_information  = agent_state.get("missing_information", []),
            key_findings         = (agent_state.get("final_response") or "")[:500],
            evidence_source_count = ev_summary.get("total_sources", 0),
            high_quality_count   = ev_summary.get("high_quality_count", 0),
            replan_count         = agent_state.get("replan_count", 0),
            evidence_quality_summary = ev_summary,
        )

        self.analysis_count += 1
        self.last_active = datetime.utcnow().isoformat()

    def build_copilot_context(self) -> str:
        """
        Build a compact context string for the copilot LLM.
        Combines patient context + last analysis snapshot.
        Target: ~700 tokens total.
        """
        parts = []
        patient_str = self.patient_context.to_context_string()
        if patient_str.strip():
            parts.append(f"## Patient Context\n{patient_str}")

        if self.last_analysis:
            parts.append(f"## Last Analysis\n{self.last_analysis.to_context_string()}")

        if not parts:
            return "No patient analysis has been run in this session yet."

        return "\n\n".join(parts)

    def get_recent_history(self, n: int = 6) -> List[Dict[str, str]]:
        """Return last N messages as {role, content} dicts for LLM context."""
        return [
            {"role": m.role, "content": m.content[:800]}
            for m in self.messages[-n:]
            if m.role in ("user", "assistant")
        ]
