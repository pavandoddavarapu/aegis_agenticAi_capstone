"""
supervisor_agent.py — Supervisor Agent (Phase 9 — HITL Governance)

Phase 9 upgrade:
  - finalize_response now calls EscalationEngine to evaluate
    whether the output must be held for human review.
  - If review required: output is marked PENDING_REVIEW, a ReviewRecord
    is created, and the response signals the caller to poll the
    governance API for completion.
  - If no review needed: output is auto-cleared and returned normally.
  - All decisions logged to the audit trail.
"""
from __future__ import annotations

import uuid
from backend.models.state            import AgentState
from backend.governance.escalation_engine import EscalationEngine
from backend.governance.review_engine     import ReviewEngine, ReviewStatus
from backend.governance.audit_logger      import AuditLogger, AuditEvent
from backend.utils.logger                import logger


# ── Fallback constants (used only if state fields are missing) ────────────────
_DEFAULT_CONFIDENCE_THRESHOLD = 0.70
_DEFAULT_MAX_RETRIES          = 2


# ── Shared singletons (module-level, initialised lazily) ─────────────────────
_escalation_engine: EscalationEngine | None = None
_review_engine:     ReviewEngine     | None = None
_audit_logger:      AuditLogger      | None = None


def _get_engines():
    global _escalation_engine, _review_engine, _audit_logger
    if _audit_logger is None:
        _audit_logger      = AuditLogger()
        _review_engine     = ReviewEngine(audit_logger=_audit_logger)
        _escalation_engine = EscalationEngine()
    return _escalation_engine, _review_engine, _audit_logger


# ── Routing Decisions ─────────────────────────────────────────────────────────

ROUTE_REASON   = "reason"
ROUTE_VALIDATE = "validate"
ROUTE_REFLECT  = "reflect"
ROUTE_END      = "end"


# ── Phase 12: Continuous Monitor Thresholds ───────────────────────────────────
_EVIDENCE_SUFFICIENCY_REFLECT_THRESHOLD = "weak"     # reflect if sufficiency <= this
_CONTRADICTION_ESCALATE_THRESHOLD       = "critical"  # escalate if contradiction severity >= this


def _continuous_monitor_check(state: AgentState) -> dict:
    """
    Phase 12: Continuous supervisor monitoring.

    Examines evidence quality and contradiction signals from Phase 12 nodes.
    Returns a dict with monitoring decisions:
      {
        "should_reflect": bool,      # trigger reflection
        "should_escalate": bool,     # trigger governance escalation
        "reflect_reason": str,       # reason for reflection
        "monitor_event": dict,       # event to append to monitor_events
      }
    """
    evidence_summary  = state.get("evidence_quality_summary", {})
    contradiction_rep = state.get("contradiction_report") or {}
    image_confidence  = state.get("image_confidence", 1.0)
    retry_count       = state.get("retry_count", 0)
    max_retries       = int(state.get("max_retries", _DEFAULT_MAX_RETRIES))

    should_reflect    = False
    should_escalate   = False
    reflect_reason    = ""

    # Signal 1: Evidence quality too low
    overall_sufficiency = evidence_summary.get("overall_sufficiency", "unknown")
    avg_quality         = evidence_summary.get("avg_quality", 0.0)

    if overall_sufficiency in ("insufficient",) and retry_count < max_retries:
        should_reflect = True
        reflect_reason = f"Evidence sufficiency insufficient (avg_quality={avg_quality:.3f})"

    # Signal 2: Contradiction severity critical
    contradiction_severity = contradiction_rep.get("overall_severity", "none")
    if contradiction_severity == _CONTRADICTION_ESCALATE_THRESHOLD:
        should_escalate = True
        reflect_reason = (reflect_reason + " | " if reflect_reason else "") + \
                         "Critical contradiction detected in evidence sources"

    # Signal 3: Very low image confidence (if multimodal present)
    visual_ctx = state.get("visual_context", "")
    if visual_ctx and image_confidence < 0.40 and retry_count < max_retries:
        should_reflect = True
        reflect_reason = (reflect_reason + " | " if reflect_reason else "") + \
                         f"Low multimodal confidence ({image_confidence:.2f})"

    monitor_event = {
        "checkpoint":              "supervisor_post_validation",
        "evidence_sufficiency":    overall_sufficiency,
        "avg_evidence_quality":    round(avg_quality, 3),
        "contradiction_severity":  contradiction_severity,
        "image_confidence":        image_confidence,
        "should_reflect":          should_reflect,
        "should_escalate":         should_escalate,
        "reflect_reason":          reflect_reason,
    }

    return {
        "should_reflect":  should_reflect,
        "should_escalate": should_escalate,
        "reflect_reason":  reflect_reason,
        "monitor_event":   monitor_event,
    }


def supervisor_router(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph.

    Phase 12 upgrade: reads Phase 12 continuous monitoring signals
    (evidence quality, contradiction severity) IN ADDITION to the
    existing confidence threshold and retry logic.

    All Phase 4.5 behavior is preserved exactly.
    """
    score       = state.get("validation_score", 0.0)
    retry_count = state.get("retry_count", 0)
    error       = state.get("error")

    threshold   = float(state.get("confidence_threshold",  _DEFAULT_CONFIDENCE_THRESHOLD))
    max_retries = int(state.get("max_retries",             _DEFAULT_MAX_RETRIES))

    trace = state.get("_trace")

    # Phase 12: Check continuous monitoring signals
    monitoring = _continuous_monitor_check(state)

    logger.info(
        f"[Supervisor] Routing: score={score:.3f} threshold={threshold:.3f} "
        f"retry={retry_count}/{max_retries} error={error} "
        f"evidence_ok={state.get('evidence_quality_summary', {}).get('overall_sufficiency', 'n/a')} "
        f"contradictions={state.get('contradiction_report', {}).get('has_contradictions', False)}"
    )

    if error and score == 0.0 and not state.get("retrieved_docs"):
        logger.warning("[Supervisor] Hard error detected → ending workflow.")
        if trace:
            trace.record_routing(decision=ROUTE_END, reason=f"Hard error: {error}", score=0.0)
        return ROUTE_END

    if score >= threshold:
        logger.info(f"[Supervisor] Confidence OK ({score:.3f} ≥ {threshold:.3f}) → end")
        if trace:
            trace.record_routing(decision=ROUTE_END, reason=f"Confidence OK ({score:.3f} >= {threshold:.3f})", score=score)
        return ROUTE_END

    if retry_count >= max_retries:
        logger.warning(
            f"[Supervisor] Max retries ({max_retries}) exhausted → best-effort end."
        )
        if trace:
            trace.record_routing(decision=ROUTE_END, reason=f"Max retries ({max_retries}) exhausted. Best-effort end.", score=score)
        return ROUTE_END

    # Phase 12: Additional reflect triggers from continuous monitoring
    if monitoring["should_reflect"] and retry_count < max_retries:
        logger.info(
            f"[Supervisor] Continuous monitor triggered reflection: "
            f"{monitoring['reflect_reason']}"
        )
        if trace:
            trace.record_routing(decision=ROUTE_REFLECT, reason=f"Continuous monitor: {monitoring['reflect_reason']}", score=score)
        return ROUTE_REFLECT

    logger.info(
        f"[Supervisor] Confidence LOW ({score:.3f} < {threshold:.3f}) "
        f"→ reflecting (attempt {retry_count + 1}/{max_retries})"
    )
    if trace:
        trace.record_routing(decision=ROUTE_REFLECT, reason=f"Confidence LOW ({score:.3f} < {threshold:.3f})", score=score)
    return ROUTE_REFLECT


# ── Response Finaliser ────────────────────────────────────────────────────────

def finalize_response(state: AgentState) -> dict:
    """
    Final node — compose response and run governance escalation check.

    Phase 9: After composing the AI output, the EscalationEngine evaluates
    whether the output must be held for human review. If yes, a ReviewRecord
    is created and the response is marked PENDING_REVIEW. If no, the output
    is auto-cleared and returned normally.

    Note: This function is synchronous (LangGraph requirement for sync nodes).
    Async governance ops (DB writes) use fire-and-forget or are deferred.
    """
    if state.get("bypass_graph", False):
        return {
            "final_response": state.get("final_response", ""),
            "reasoning_output": state.get("reasoning_output", ""),
            "validation_score": state.get("validation_score", 1.0),
            "validation_feedback": state.get("validation_feedback", "Bypassed validation for conversational query."),
            "workflow_path": state.get("workflow_path", []) + ["finalize"],
        }

    reasoning     = state.get("reasoning_output", "No reasoning generated.")
    score         = state.get("validation_score", 0.0)
    retry_count   = state.get("retry_count", 0)
    workflow_type = state.get("selected_workflow", "clinical")
    risk_level    = state.get("risk_level", "low")
    escalation    = state.get("escalation_required", False)
    query         = state.get("query", "")

    if score >= 0.85:
        conf_label = "HIGH"
    elif score >= 0.65:
        conf_label = "MEDIUM"
    else:
        conf_label = "LOW"

    disclaimer = (
        "\n\n⚕️ This is AI-assisted analysis. Final clinical decisions require physician judgment."
    )

    escalation_note = (
        "\n\n🚨 ESCALATION FLAG: This query has been flagged for human clinical "
        "review due to elevated risk level. Output should be verified by a "
        "qualified clinician before clinical use."
        if escalation else ""
    )

    ai_output = (
        f"## Clinical Analysis [{workflow_type.upper()} | Risk: {risk_level.upper()}]\n\n"
        f"{reasoning}"
        f"{escalation_note}"
        f"{disclaimer}"
    )

    # ── Phase 9: Governance Escalation Check ─────────────────────────────────
    esc_engine, review_engine, audit_logger = _get_engines()
    esc_decision = esc_engine.evaluate(dict(state))

    review_required = False # Disabled per user request (was: esc_decision.requires_review and esc_decision.blocking)
    review_id       = None
    review_status   = "not_required"

    if review_required:
        # Create a ReviewRecord (synchronously for now; async audit log is fire-and-forget)
        rid = str(uuid.uuid4())
        import asyncio

        # Create record in-memory synchronously
        from backend.governance.review_engine import ReviewRecord, ReviewStatus
        from datetime import datetime, timezone
        record = ReviewRecord(
            review_id=rid,
            request_id=rid,
            query_preview=query[:200],
            ai_output=ai_output,
            workflow_type=workflow_type,
            confidence=score,
            severity=esc_decision.severity,
            escalation_reasons=esc_decision.reasons,
        )
        review_engine._store[rid] = record
        review_id     = rid
        review_status = ReviewStatus.PENDING_REVIEW.value

        # Replace the final output with a holding message
        final_response = (
            f"## ⏳ OUTPUT PENDING REVIEW\n\n"
            f"**Review ID:** `{rid}`\n"
            f"**Severity:** {esc_decision.severity.upper()}\n"
            f"**Reason:** {esc_decision.description}\n\n"
            f"This output has been flagged for mandatory clinician review "
            f"before it can be returned. A qualified reviewer must approve, "
            f"reject, or override this response.\n\n"
            f"Use `GET /governance/review/{rid}` to check status."
        )

        logger.warning(
            f"[Supervisor] Output HELD for review. "
            f"review_id={rid} severity={esc_decision.severity}"
        )

    else:
        # Auto-cleared — return the AI output directly
        final_response = ai_output
        if esc_decision.requires_review:
            # Advisory (non-blocking) escalation — attach note but don't hold
            final_response += (
                f"\n\n📋 ADVISORY REVIEW: This output was flagged for advisory review "
                f"(non-blocking). Reasons: {', '.join(esc_decision.reasons)}"
            )
            review_status = "advisory"

    path_entries = ["finalize"]
    if review_required:
        path_entries.append("HELD_FOR_REVIEW")
    elif escalation:
        path_entries.append("ESCALATED")

    logger.info(
        f"[Supervisor] Finalised. confidence={conf_label} ({score:.3f}) "
        f"retries={retry_count} workflow={workflow_type} "
        f"review_required={review_required} review_id={review_id}"
    )

    return {
        "final_response":  final_response,
        "validation_score": score,
        "validation_feedback": state.get("validation_feedback", ""),
        "review_required": review_required,
        "review_id":       review_id,
        "review_status":   review_status,
        "reviewed_by":     None,
        "clinician_notes": None,
        "approved_output": None,
        "workflow_path":   path_entries,
    }
