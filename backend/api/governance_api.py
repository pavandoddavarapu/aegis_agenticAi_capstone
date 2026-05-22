"""
governance_api.py — Governance & HITL API Endpoints (Phase 9)

Provides:
  GET  /governance/reviews/pending
    Returns all outputs currently held pending clinician review.

  GET  /governance/reviews/{review_id}
    Returns a specific review record with current status.

  POST /governance/reviews/{review_id}/action
    Submit a clinician review action (approve/reject/override/retry).
    Body: { action, reviewed_by, notes, override_text? }

  GET  /governance/audit
    Returns the audit log history (queryable by event_type).

  GET  /governance/stats
    Dashboard summary stats: pending count, approval rate, etc.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.governance.review_engine     import ReviewAction, ReviewStatus
from backend.governance.audit_logger      import AuditEvent
from backend.agents.supervisor_agent      import _get_engines
from backend.utils.logger                import logger

router = APIRouter(prefix="/governance", tags=["Governance & HITL"])


# ── Request / Response models ─────────────────────────────────────────────────

class ReviewActionRequest(BaseModel):
    action:        ReviewAction
    reviewed_by:   str
    notes:         Optional[str] = None
    override_text: Optional[str] = None  # Required when action == OVERRIDE


class ReviewActionResponse(BaseModel):
    review_id:    str
    request_id:   str
    status:       str
    reviewed_by:  Optional[str]
    notes:        Optional[str]
    final_output: Optional[str]
    message:      str


class AuditQueryParams(BaseModel):
    limit:      int  = 100
    event_type: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/reviews/pending",
    summary="List all outputs pending clinician review",
)
async def list_pending_reviews():
    """Return all review records with status=PENDING_REVIEW."""
    _, review_engine, _ = _get_engines()
    pending = review_engine.list_pending()
    return {
        "count":   len(pending),
        "reviews": pending,
    }


@router.get(
    "/reviews/all",
    summary="List all review records",
)
async def list_all_reviews():
    """Return complete review history (all statuses)."""
    _, review_engine, _ = _get_engines()
    return {
        "count":   len(review_engine._store),
        "reviews": review_engine.list_all(),
    }


@router.get(
    "/reviews/{review_id}",
    summary="Get a specific review record",
)
async def get_review(review_id: str):
    """Return a specific ReviewRecord by its UUID."""
    _, review_engine, _ = _get_engines()
    record = review_engine.get_review(review_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review not found: {review_id}",
        )
    return record.to_dict()


@router.post(
    "/reviews/{review_id}/action",
    response_model=ReviewActionResponse,
    summary="Submit a clinician review action",
)
async def submit_review_action(
    review_id: str,
    body:      ReviewActionRequest,
) -> ReviewActionResponse:
    """
    Submit a clinician review: approve, reject, override, or request retry.

    Human decision always wins.
    All actions are logged to the immutable audit trail.
    """
    _, review_engine, _ = _get_engines()

    record = review_engine.get_review(review_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review not found: {review_id}",
        )

    if record.status != ReviewStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review already actioned with status: {record.status.value}",
        )

    try:
        updated = await review_engine.submit_review(
            review_id=review_id,
            action=body.action,
            reviewed_by=body.reviewed_by,
            notes=body.notes,
            override_text=body.override_text,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    logger.info(
        f"[GovernanceAPI] Review actioned: review_id={review_id} "
        f"action={body.action.value} by={body.reviewed_by}"
    )

    return ReviewActionResponse(
        review_id=review_id,
        request_id=updated.request_id,
        status=updated.status.value,
        reviewed_by=updated.reviewed_by,
        notes=updated.clinician_notes,
        final_output=updated.final_output() if updated.status in (
            ReviewStatus.APPROVED, ReviewStatus.OVERRIDDEN
        ) else None,
        message=f"Review {body.action.value} recorded. Audit trail updated.",
    )


@router.get(
    "/audit",
    summary="Query the governance audit log",
)
async def get_audit_log(
    limit:      int            = 100,
    event_type: Optional[str] = None,
):
    """Query the PostgreSQL audit log with optional event_type filter."""
    _, _, audit_logger = _get_engines()
    events = await audit_logger.get_audit_history(limit=limit, event_type=event_type)
    return {
        "count":  len(events),
        "events": events,
    }


@router.get(
    "/audit/pending",
    summary="Pending reviews from audit log (DB-backed)",
)
async def get_pending_from_audit():
    """Return pending reviews from PostgreSQL (persists across restarts)."""
    _, _, audit_logger = _get_engines()
    pending = await audit_logger.get_pending_reviews()
    return {
        "count":   len(pending),
        "pending": pending,
    }


@router.get(
    "/stats",
    summary="Governance dashboard summary stats",
)
async def get_governance_stats():
    """Summary statistics for the governance dashboard."""
    _, review_engine, _ = _get_engines()
    all_reviews = review_engine.list_all()

    pending    = sum(1 for r in all_reviews if r["status"] == "pending_review")
    approved   = sum(1 for r in all_reviews if r["status"] == "approved")
    rejected   = sum(1 for r in all_reviews if r["status"] == "rejected")
    overridden = sum(1 for r in all_reviews if r["status"] == "overridden")
    retried    = sum(1 for r in all_reviews if r["status"] == "retry_requested")

    total_actioned = approved + rejected + overridden
    approval_rate  = round(approved / total_actioned, 3) if total_actioned > 0 else None

    return {
        "total_reviews":   len(all_reviews),
        "pending":         pending,
        "approved":        approved,
        "rejected":        rejected,
        "overridden":      overridden,
        "retry_requested": retried,
        "approval_rate":   approval_rate,
        "severity_breakdown": {
            "critical": sum(1 for r in all_reviews if r.get("severity") == "critical"),
            "high":     sum(1 for r in all_reviews if r.get("severity") == "high"),
            "medium":   sum(1 for r in all_reviews if r.get("severity") == "medium"),
        },
    }
