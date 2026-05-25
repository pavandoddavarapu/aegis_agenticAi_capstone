"""
session_api.py — Conversational Session Management Endpoints (Phase 13)

Endpoints:
  POST   /session/              — Create a new conversational patient session
  GET    /session/{session_id}  — Retrieve session state
  DELETE /session/{session_id}  — Delete a session
  GET    /session/stats         — Session store statistics (for monitoring)

Sessions enable multi-turn conversational orchestration:
  - Patient context accumulates across analysis turns
  - Copilot questions reference prior findings without re-running analysis
  - Clarification state persists between turns
"""
import io
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fpdf import FPDF

from backend.models.session import ConversationalPatientSession, ConversationMessage, AccumulatedPatientContext
from backend.session.session_store import session_store
from backend.utils.logger import logger

router = APIRouter(prefix="/session", tags=["session"])


# ── Response Models ────────────────────────────────────────────────────────────

class SessionSummary(BaseModel):
    session_id:       str
    created_at:       str
    last_active:      str
    turn_count:       int
    analysis_count:   int
    has_patient_context: bool
    has_last_analysis:   bool
    message_count:    int
    clarification_pending: bool
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    patient_context: Optional[AccumulatedPatientContext] = None


class SessionCreateResponse(BaseModel):
    session_id:    str
    created_at:    str
    message:       str = "Session created successfully"


class SessionStatsResponse(BaseModel):
    total_sessions: int
    max_sessions:   int
    ttl_hours:      int


# ── Helper ─────────────────────────────────────────────────────────────────────

def _session_to_summary(session: ConversationalPatientSession) -> SessionSummary:
    return SessionSummary(
        session_id            = session.session_id,
        created_at            = session.created_at,
        last_active           = session.last_active,
        turn_count            = session.turn_count,
        analysis_count        = session.analysis_count,
        has_patient_context   = bool(session.patient_context.to_context_string().strip()),
        has_last_analysis     = session.last_analysis is not None,
        message_count         = len(session.messages),
        clarification_pending = session.clarification_pending,
        conversation_history  = session.messages,
        patient_context       = session.patient_context,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=SessionCreateResponse,
    summary="Create a new conversational patient session",
)
async def create_session() -> SessionCreateResponse:
    """
    Create a new conversational patient session.

    Returns a session_id that should be passed in subsequent:
    - POST /analyze/ calls (as body.session_id)
    - POST /analyze/copilot/ calls (as body.session_id)

    Sessions expire after 2 hours of inactivity.
    Max 500 concurrent sessions (oldest evicted when limit reached).
    """
    session = session_store.create()
    logger.info(f"[SessionAPI] Created session: {session.session_id}")
    return SessionCreateResponse(
        session_id = session.session_id,
        created_at = session.created_at,
    )


@router.get(
    "/stats",
    response_model=SessionStatsResponse,
    summary="Session store statistics",
)
async def get_stats() -> SessionStatsResponse:
    """Return current session store statistics."""
    stats = session_store.stats()
    return SessionStatsResponse(**stats)


@router.get(
    "/{session_id}",
    response_model=SessionSummary,
    summary="Get session state",
)
async def get_session(session_id: str) -> SessionSummary:
    """
    Retrieve the current state of a conversational session.

    Returns session metadata including:
    - turn_count: how many messages have been exchanged
    - analysis_count: how many full analysis runs have been done
    - has_patient_context: whether patient data has been accumulated
    - has_last_analysis: whether analysis results are available for copilot
    - clarification_pending: whether clarification questions are waiting
    """
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error":      "Session not found or expired",
                "session_id": session_id,
                "message":    "Sessions expire after 2 hours of inactivity. Create a new session.",
            },
        )
    return _session_to_summary(session)


@router.delete(
    "/{session_id}",
    summary="Delete a session",
)
async def delete_session(session_id: str) -> Dict[str, str]:
    """
    Delete a conversational session and all its accumulated patient context.

    Use when:
    - Doctor finishes with a patient case
    - Doctor starts a completely new patient case
    - Privacy requires clearing session data
    """
    deleted = session_store.delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "Session not found", "session_id": session_id},
        )
    logger.info(f"[SessionAPI] Deleted session: {session_id}")
    return {"message": "Session deleted", "session_id": session_id}


class PremiumPDF(FPDF):
    def header(self):
        # Draw a top banner only on page 1
        if self.page_no() == 1:
            self.set_fill_color(3, 105, 161) # Indigo/Blue
            self.rect(0, 0, 210, 40, 'F')
            self.set_text_color(255, 255, 255)
            self.set_font('helvetica', 'B', 20)
            self.cell(0, 15, 'AEGIS CLINICAL AI', new_x="LMARGIN", new_y="NEXT", align='C')
            self.set_font('helvetica', 'I', 11)
            self.cell(0, 5, 'Conversational Patient Case & Decision Support Report', new_x="LMARGIN", new_y="NEXT", align='C')
            self.ln(15)
        else:
            self.set_font('helvetica', 'B', 8)
            self.set_text_color(100, 116, 139)
            self.cell(0, 10, 'AEGIS CLINICAL DECISION SUPPORT REPORT', new_x="LMARGIN", new_y="NEXT", align='L')
            self.set_draw_color(226, 232, 240)
            self.line(10, 20, 200, 20)
            self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(100, 116, 139)
        self.set_draw_color(226, 232, 240)
        self.line(10, 282, 200, 282)
        self.cell(0, 10, f'CONFIDENTIAL | Printed on {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} | Page {self.page_no()}/{{nb}}', align='C')

def sanitize_text(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "₂": "2",
        "₃": "3",
        "°": " deg ",
        "µ": "u",
        "±": "+/-",
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "📋": "",
        "⚕️": "",
        "🔬": "",
        "🫀": "",
        "🩻": "",
        "📄": "",
        "🚨": "[ALERT]",
        "💊": "[Medication]",
        "💉": "[Injection]",
        "📚": "[Reference]",
        "📊": "[Chart]",
        "🔍": "[Search]",
        "⚖️": "[Scale]",
        "📈": "[Trend]",
        "⚡": "[Fast]",
        "✓": "[OK]",
        "🧠": "[Brain]",
        "🩺": "[Steth]",
        "🛡️": "[Shield]",
        "🏛": "[Gov]",
        "🧩": "[Arch]",
    }
    cleaned = text
    for k, v in replacements.items():
        cleaned = cleaned.replace(k, v)
    return cleaned.encode("latin-1", errors="replace").decode("latin-1")


@router.get(
    "/{session_id}/export",
    summary="Export session conversation history to a PDF document",
)
async def export_session(session_id: str):
    """
    Generate and stream a beautifully styled PDF of the conversational patient session,
    including the active patient context state and full transcript.
    """
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Session not found or expired",
                "session_id": session_id,
            },
        )

    pdf = PremiumPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Left Margin offset for page 1
    pdf.set_y(45)
    pdf.set_text_color(15, 23, 42) # Slate-900
    
    # Session Details
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(40, 6, "Session Reference:")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, sanitize_text(session.session_id), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(40, 6, "Report Date:")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    
    # Patient Context Section
    pdf.set_fill_color(241, 245, 249) # slate-100
    pdf.set_draw_color(203, 213, 225) # slate-300
    pdf.set_text_color(15, 23, 42)
    
    # Context Box Header
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 8, " CLINICAL PATIENT CONTEXT STATE", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    
    # Demographics Info
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Age:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(50, 7, sanitize_text(session.patient_context.age or "N/A"))
    
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(30, 7, "Gender:")
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(session.patient_context.gender or "N/A"), border='R', new_x="LMARGIN", new_y="NEXT")
    
    # Chief Complaint
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Chief Complaint:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(session.patient_context.chief_complaint or "N/A"), border='R', new_x="LMARGIN", new_y="NEXT")
    
    # Vitals
    vitals = session.patient_context.vitals or {}
    vitals_parts = []
    if vitals.get("bp"): vitals_parts.append(f"BP: {vitals.get('bp')}")
    if vitals.get("hr"): vitals_parts.append(f"HR: {vitals.get('hr')} bpm")
    if vitals.get("o2"): vitals_parts.append(f"SpO2: {vitals.get('o2')}")
    if vitals.get("temp"): vitals_parts.append(f"Temp: {vitals.get('temp')}C")
    if vitals.get("rr"): vitals_parts.append(f"RR: {vitals.get('rr')} /min")
    vitals_str = " | ".join(vitals_parts) if vitals_parts else "N/A"
    
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Vitals:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(vitals_str), border='R', new_x="LMARGIN", new_y="NEXT")
    
    # Lists
    symptoms = ", ".join(session.patient_context.symptoms) or "None"
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Symptoms:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(symptoms), border='R', new_x="LMARGIN", new_y="NEXT")
    
    meds = ", ".join(session.patient_context.medications) or "None"
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Medications:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(meds), border='R', new_x="LMARGIN", new_y="NEXT")
    
    allergies = ", ".join(session.patient_context.allergies) or "None"
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 7, "  Allergies:", border='L')
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 7, sanitize_text(allergies), border='R', new_x="LMARGIN", new_y="NEXT")
    
    # Multimodal findings
    ecg = session.patient_context.ecg_findings
    if ecg:
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(40, 7, "  ECG Findings:", border='L')
        pdf.set_font("helvetica", "", 9)
        pdf.cell(0, 7, sanitize_text(ecg), border='R', new_x="LMARGIN", new_y="NEXT")
        
    imaging = session.patient_context.imaging_findings
    if imaging:
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(40, 7, "  Imaging Findings:", border='L')
        pdf.set_font("helvetica", "", 9)
        pdf.cell(0, 7, sanitize_text(imaging), border='R', new_x="LMARGIN", new_y="NEXT")
        
    # Closing Context Border
    pdf.cell(0, 1, "", border='T', new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)
    
    # Conversation Transcript
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(3, 105, 161)
    pdf.cell(0, 8, "CONVERSATION TRANSCRIPT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(3, 105, 161)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    if not session.messages:
        pdf.set_font("helvetica", "I", 10)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 10, "No conversational interactions recorded in this session.", new_x="LMARGIN", new_y="NEXT")
    else:
        for msg in session.messages:
            role = msg.role
            content = msg.content
            mtype = msg.message_type
            
            # Format Timestamp
            t_str = msg.timestamp
            try:
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                time_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                time_display = t_str
                
            pdf.ln(2)
            
            if role == "user":
                # Clinician Box
                pdf.set_fill_color(248, 250, 252) # Slate-50
                pdf.set_draw_color(226, 232, 240)
                pdf.set_text_color(15, 23, 42)
                
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, f" Clinician [{time_display}]", border='TLR', fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("helvetica", "", 9.5)
                pdf.multi_cell(0, 5, sanitize_text(content), border='LRB', fill=True, new_x="LMARGIN", new_y="NEXT")
            else:
                # Aegis AI Box
                pdf.set_fill_color(240, 249, 255) # Light Sky Blue-50
                pdf.set_draw_color(186, 230, 253) # Sky Blue-200
                pdf.set_text_color(3, 105, 161)
                
                label = " Aegis AI Assistant"
                if mtype == "report":
                    label = " Aegis Clinical Intelligence Report"
                elif mtype == "clarification":
                    label = " Aegis Clarification Request"
                    
                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 6, f"{label} [{time_display}]", border='TLR', fill=True, new_x="LMARGIN", new_y="NEXT")
                
                pdf.set_text_color(15, 23, 42)
                pdf.set_font("helvetica", "", 9.5)
                pdf.multi_cell(0, 5, sanitize_text(content), border='LRB', fill=True, new_x="LMARGIN", new_y="NEXT")
                
            pdf.ln(2)

    pdf_bytes = pdf.output()
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=aegis_session_{session_id}.pdf"
        }
    )
