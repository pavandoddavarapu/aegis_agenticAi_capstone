"""
review_engine.py — HITL Review Engine (Phase 9)

Manages the review lifecycle for escalated AI outputs.

Review states:
  PENDING_REVIEW  → Escalated, awaiting clinician action
  APPROVED        → Clinician approved AI output
  REJECTED        → Clinician rejected AI output (retry or discard)
  OVERRIDDEN      → Clinician provided their own correction
  RETRY_REQUESTED → Clinician asked the system to re-run the query

Lifecycle:
  1. EscalationEngine decides output must be reviewed
  2. ReviewEngine creates a ReviewRecord and stores it in memory
     (in production: Redis with TTL or PostgreSQL)
  3. Clinician calls the review API with their action + notes
  4. ReviewEngine updates the record and emits an AuditLog event
  5. Finalized output carries review metadata in the response

Design:
  - Human decision ALWAYS wins — overrides completely replace AI output
  - Every action is logged immutably to the audit trail
  - In-memory store used here (production: Redis with 24h TTL)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from backend.governance.audit_logger import AuditLogger, AuditEvent
from backend.utils.logger            import logger


# ── Review Status Enum ────────────────────────────────────────────────────────

class ReviewStatus(str, Enum):
    PENDING_REVIEW  = "pending_review"
    APPROVED        = "approved"
    REJECTED        = "rejected"
    OVERRIDDEN      = "overridden"
    RETRY_REQUESTED = "retry_requested"


# ── Review Action (from clinician) ────────────────────────────────────────────

class ReviewAction(str, Enum):
    APPROVE         = "approve"
    REJECT          = "reject"
    OVERRIDE        = "override"     # Clinician provides their own text
    REQUEST_RETRY   = "request_retry"


# ── Review Record ─────────────────────────────────────────────────────────────

@dataclass
class ReviewRecord:
    """Represents one pending or completed review."""
    review_id:        str
    request_id:       str
    query_preview:    str               # First 200 chars — PHI safe
    ai_output:        str               # The AI response needing review
    workflow_type:    str
    confidence:       float
    severity:         str
    escalation_reasons: list[str]

    status:           ReviewStatus       = ReviewStatus.PENDING_REVIEW
    reviewed_by:      Optional[str]      = None
    clinician_notes:  Optional[str]      = None
    clinician_override: Optional[str]    = None  # Clinician's own answer
    reviewed_at:      Optional[str]      = None
    created_at:       str                = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id":          self.review_id,
            "request_id":         self.request_id,
            "query_preview":      self.query_preview,
            "workflow_type":      self.workflow_type,
            "confidence":         self.confidence,
            "severity":           self.severity,
            "escalation_reasons": self.escalation_reasons,
            "status":             self.status.value,
            "reviewed_by":        self.reviewed_by,
            "clinician_notes":    self.clinician_notes,
            "clinician_override": self.clinician_override,
            "reviewed_at":        self.reviewed_at,
            "created_at":         self.created_at,
        }

    def final_output(self) -> str:
        """Return the output to send to the user after review."""
        if self.status == ReviewStatus.OVERRIDDEN and self.clinician_override:
            return (
                f"{self.clinician_override}\n\n"
                f"✅ This response was reviewed and overridden by: {self.reviewed_by}\n"
                f"📝 Clinician notes: {self.clinician_notes or 'None'}"
            )
        if self.status == ReviewStatus.APPROVED:
            return (
                f"{self.ai_output}\n\n"
                f"✅ Reviewed & Approved by: {self.reviewed_by}\n"
                f"📝 Notes: {self.clinician_notes or 'None'}"
            )
        return self.ai_output  # Fallback


# ── Review Engine ─────────────────────────────────────────────────────────────

class ReviewEngine:
    """
    In-memory review store with audit logging.

    In production this would be backed by Redis (TTL = 24h) or PostgreSQL.
    The interface is identical — just swap the _store backend.
    """

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._store: Dict[str, ReviewRecord] = {}   # review_id → ReviewRecord
        self._audit = audit_logger or AuditLogger()

    async def create_review(
        self,
        request_id:         str,
        ai_output:          str,
        query:              str,
        workflow_type:      str,
        confidence:         float,
        severity:           str,
        escalation_reasons: list[str],
    ) -> ReviewRecord:
        """
        Create a new review record for an escalated output.
        Returns the ReviewRecord immediately (caller can return it to client).
        """
        review_id = str(uuid.uuid4())
        record = ReviewRecord(
            review_id=review_id,
            request_id=request_id,
            query_preview=query[:200],
            ai_output=ai_output,
            workflow_type=workflow_type,
            confidence=confidence,
            severity=severity,
            escalation_reasons=escalation_reasons,
        )
        self._store[review_id] = record

        await self._audit.log(
            request_id=request_id,
            event_type=AuditEvent.ESCALATED,
            actor="system",
            severity=severity,
            query_preview=query[:200],
            workflow_type=workflow_type,
            confidence=confidence,
            payload=record.to_dict(),
        )

        logger.info(
            f"[ReviewEngine] Review created: review_id={review_id} "
            f"severity={severity} request_id={request_id}"
        )
        return record

    async def submit_review(
        self,
        review_id:        str,
        action:           ReviewAction,
        reviewed_by:      str,
        notes:            Optional[str] = None,
        override_text:    Optional[str] = None,
    ) -> ReviewRecord:
        """
        Submit a clinician review action.

        Human decision ALWAYS wins. Overrides completely replace AI output.
        Every action is logged to the audit trail.
        """
        record = self._store.get(review_id)
        if not record:
            raise ValueError(f"Review record not found: {review_id}")

        record.reviewed_by     = reviewed_by
        record.clinician_notes = notes
        record.reviewed_at     = datetime.now(timezone.utc).isoformat()

        if action == ReviewAction.APPROVE:
            record.status = ReviewStatus.APPROVED
            audit_event   = AuditEvent.APPROVED

        elif action == ReviewAction.REJECT:
            record.status = ReviewStatus.REJECTED
            audit_event   = AuditEvent.REJECTED

        elif action == ReviewAction.OVERRIDE:
            if not override_text:
                raise ValueError("override_text is required for OVERRIDE action")
            record.status             = ReviewStatus.OVERRIDDEN
            record.clinician_override = override_text
            audit_event               = AuditEvent.OVERRIDE

        elif action == ReviewAction.REQUEST_RETRY:
            record.status = ReviewStatus.RETRY_REQUESTED
            audit_event   = AuditEvent.RETRY_REQUESTED

        else:
            raise ValueError(f"Unknown review action: {action}")

        await self._audit.log(
            request_id=record.request_id,
            event_type=audit_event,
            actor=reviewed_by,
            severity=record.severity,
            query_preview=record.query_preview,
            workflow_type=record.workflow_type,
            confidence=record.confidence,
            notes=notes,
            payload={
                "review_id":     review_id,
                "action":        action.value,
                "override_text": override_text,
            },
        )

        logger.info(
            f"[ReviewEngine] Review submitted: review_id={review_id} "
            f"action={action.value} by={reviewed_by}"
        )
        return record

    def get_review(self, review_id: str) -> Optional[ReviewRecord]:
        """Retrieve a review record by ID."""
        return self._store.get(review_id)

    def list_pending(self) -> list[Dict[str, Any]]:
        """Return all pending reviews (for governance dashboard)."""
        return [
            r.to_dict() for r in self._store.values()
            if r.status == ReviewStatus.PENDING_REVIEW
        ]

    def list_all(self) -> list[Dict[str, Any]]:
        """Return all review records."""
        return [r.to_dict() for r in self._store.values()]
