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
import time
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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
