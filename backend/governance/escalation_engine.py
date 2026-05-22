"""
escalation_engine.py — Governance Escalation Engine (Phase 9)

Determines WHEN an AI output requires mandatory human review before
it can be finalized and returned to the user.

Design principles:
  - Rules are simple, explicit, and configurable
  - Conservative: when in doubt, escalate
  - Never blocks the API — outputs are held PENDING_REVIEW, not dropped
  - Each escalation has a machine-readable reason + human description

Escalation triggers (any one of these → escalate):
  1. Risk level is CRITICAL
  2. Validation score below HARD_FLOOR (indicates low confidence answer)
  3. Image emergency flag (ECG STEMI, pneumothorax, etc.)
  4. Explicit hallucination signals in validation feedback
  5. Medication workflow + drug interaction graph violation detected
  6. Max retries exhausted with score still below threshold (uncertain output)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.utils.logger import logger


# ── Configurable thresholds ───────────────────────────────────────────────────

class EscalationConfig:
    """Centralised, environment-configurable escalation thresholds."""
    HARD_CONFIDENCE_FLOOR:   float = 0.50   # Below this → always escalate
    CRITICAL_RISK_AUTO:      bool  = True   # Critical risk level always escalates
    EMERGENCY_IMAGE_AUTO:    bool  = True   # Image emergency flag always escalates
    MAX_RETRY_EXHAUSTED:     bool  = True   # Retries exhausted + low score → escalate
    MEDICATION_GRAPH_FAIL:   bool  = True   # Drug contraindication detected → escalate


# ── Escalation Decision ───────────────────────────────────────────────────────

@dataclass
class EscalationDecision:
    """Result of the escalation engine evaluation."""
    requires_review: bool
    reasons:         List[str]          # Machine-readable trigger labels
    description:     str                # Human-readable single summary
    severity:        str                # "low" | "medium" | "high" | "critical"
    blocking:        bool               # True → output held pending review

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requires_review": self.requires_review,
            "reasons":         self.reasons,
            "description":     self.description,
            "severity":        self.severity,
            "blocking":        self.blocking,
        }


# ── Escalation Engine ─────────────────────────────────────────────────────────

class EscalationEngine:
    """
    Stateless escalation decision engine.

    Call evaluate() with the completed agent state to determine
    whether the output must be held for human review.
    """

    def __init__(self, config: EscalationConfig = None):
        self.cfg = config or EscalationConfig()

    def evaluate(self, state: Dict[str, Any]) -> EscalationDecision:
        """
        Evaluate the completed agent state and return an escalation decision.

        This is called by the supervisor/finalize node BEFORE returning
        the final response to the caller.
        """
        reasons:  List[str] = []
        severity: str       = "low"

        # ── Rule 1: Risk level CRITICAL ────────────────────────────────────
        risk_level = state.get("risk_level", "low")
        if self.cfg.CRITICAL_RISK_AUTO and risk_level == "critical":
            reasons.append("CRITICAL_RISK_LEVEL")
            severity = "critical"

        # ── Rule 2: Validation score below hard floor ──────────────────────
        score = float(state.get("validation_score", 0.0))
        if score < self.cfg.HARD_CONFIDENCE_FLOOR:
            reasons.append(f"LOW_CONFIDENCE_SCORE:{score:.3f}")
            severity = max(severity, "high", key=_sev_rank)

        # ── Rule 3: Image emergency flag ───────────────────────────────────
        if self.cfg.EMERGENCY_IMAGE_AUTO and state.get("image_emergency_flag", False):
            reasons.append("IMAGE_EMERGENCY_FLAG")
            emergency_reason = state.get("image_emergency_reason", "unknown")
            reasons.append(f"EMERGENCY_DETAIL:{emergency_reason}")
            severity = "critical"

        # ── Rule 4: Hallucination / grounding signal in feedback ───────────
        feedback = state.get("validation_feedback", "").lower()
        if "grounding" in feedback and ("failed" in feedback or score < 0.5):
            reasons.append("HALLUCINATION_RISK_SIGNAL")
            severity = max(severity, "high", key=_sev_rank)

        # ── Rule 5: Graph validation failure (drug contraindication) ────────
        if self.cfg.MEDICATION_GRAPH_FAIL and "failed: " in feedback and "contraind" in feedback:
            reasons.append("DRUG_CONTRAINDICATION_GRAPH_FAIL")
            severity = "critical"

        # ── Rule 6: Escalation pre-flagged by decision layer ───────────────
        if state.get("escalation_required", False):
            reasons.append("DECISION_LAYER_ESCALATION")
            escalation_reason = state.get("escalation_reason", "")
            if escalation_reason:
                reasons.append(f"DECISION_REASON:{escalation_reason}")
            severity = max(severity, "high", key=_sev_rank)

        # ── Rule 7: Max retries exhausted with low confidence ──────────────
        retry_count = int(state.get("retry_count", 0))
        max_retries = int(state.get("max_retries", 2))
        if self.cfg.MAX_RETRY_EXHAUSTED and retry_count >= max_retries and score < 0.65:
            reasons.append("MAX_RETRIES_EXHAUSTED_LOW_SCORE")
            severity = max(severity, "medium", key=_sev_rank)

        requires_review = len(reasons) > 0

        # Blocking = output held until review (only for high/critical)
        blocking = severity in ("high", "critical") and requires_review

        if requires_review:
            description = _build_description(reasons, severity, score)
            logger.warning(
                f"[EscalationEngine] ESCALATION REQUIRED | "
                f"severity={severity} blocking={blocking} reasons={reasons}"
            )
        else:
            description = "No escalation required. Output cleared for autonomous finalization."
            logger.info("[EscalationEngine] No escalation required.")

        return EscalationDecision(
            requires_review=requires_review,
            reasons=reasons,
            description=description,
            severity=severity,
            blocking=blocking,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

def _sev_rank(s: str) -> int:
    return _SEVERITY_ORDER.get(s, 0)


def _build_description(reasons: List[str], severity: str, score: float) -> str:
    lines = [f"[{severity.upper()}] Output requires human review before finalization."]
    if "CRITICAL_RISK_LEVEL" in reasons:
        lines.append("→ Query classified as CRITICAL risk.")
    if any("LOW_CONFIDENCE" in r for r in reasons):
        lines.append(f"→ Validation score {score:.3f} is below safety threshold.")
    if "IMAGE_EMERGENCY_FLAG" in reasons:
        lines.append("→ Life-threatening pattern detected in medical image.")
    if "HALLUCINATION_RISK_SIGNAL" in reasons:
        lines.append("→ Grounding validation flagged potential hallucination risk.")
    if "DRUG_CONTRAINDICATION_GRAPH_FAIL" in reasons:
        lines.append("→ Drug contraindication violation detected in knowledge graph.")
    if "DECISION_LAYER_ESCALATION" in reasons:
        lines.append("→ Decision layer pre-flagged this query for escalation.")
    if "MAX_RETRIES_EXHAUSTED_LOW_SCORE" in reasons:
        lines.append("→ Maximum reflection retries reached without sufficient confidence.")
    return " ".join(lines)
