"""
workflow_router.py — Adaptive Workflow Routing Engine (Phase 4.5)

Architecture:
  The router is a PRIORITY-WEIGHTED MATCH engine, not a decision tree.
  Each workflow defines:
    - A set of trigger query types it handles (primary + compatible)
    - A base priority score for ambiguous matches
    - A risk compatibility range (e.g., emergency workflow not for LOW risk)

  Resolution strategy when multiple workflows match:
    1. If CRITICAL risk is detected, EMERGENCY workflow always wins.
    2. Otherwise, score each candidate: trigger_match * priority * risk_fit.
    3. Select highest-scoring workflow.
    4. Fall back to CLINICAL if no match scores above threshold.

  Extensibility:
    New workflow types are added to WORKFLOW_SPECS only.
    The scoring algorithm is independent of workflow count.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from backend.decision.schemas import (
    WorkflowType, RiskLevel, RiskAssessment,
    QueryClassification, WorkflowConfig,
)
from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Workflow Match Specifications
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class WorkflowSpec:
    """
    Describes how a workflow is selected by the router.
    Decoupled from WorkflowConfig so routing logic stays independent
    of orchestration configuration.
    """
    workflow_type:          WorkflowType
    primary_triggers:       Set[WorkflowType]   # query types that strongly match
    compatible_triggers:    Set[WorkflowType]   # query types that weakly match
    base_priority:          float               # 0–1, higher = preferred on tie
    min_risk:               Optional[RiskLevel] # None = any risk level
    max_risk:               Optional[RiskLevel] # None = any risk level
    emergency_override:     bool = False        # wins unconditionally on CRITICAL


WORKFLOW_SPECS: List[WorkflowSpec] = [
    WorkflowSpec(
        workflow_type        = WorkflowType.EMERGENCY,
        primary_triggers     = {WorkflowType.EMERGENCY},
        compatible_triggers  = {WorkflowType.CLINICAL, WorkflowType.MEDICATION},
        base_priority        = 1.0,
        min_risk             = RiskLevel.HIGH,
        max_risk             = None,
        emergency_override   = True,
    ),
    WorkflowSpec(
        workflow_type        = WorkflowType.MEDICATION,
        primary_triggers     = {WorkflowType.MEDICATION},
        compatible_triggers  = {WorkflowType.CLINICAL, WorkflowType.DIAGNOSIS},
        base_priority        = 0.85,
        min_risk             = None,
        max_risk             = None,
    ),
    WorkflowSpec(
        workflow_type        = WorkflowType.CLINICAL,
        primary_triggers     = {WorkflowType.CLINICAL, WorkflowType.DIAGNOSIS, WorkflowType.TREATMENT},
        compatible_triggers  = {WorkflowType.MEDICATION, WorkflowType.SIMILAR_CASE},
        base_priority        = 0.75,
        min_risk             = None,
        max_risk             = RiskLevel.HIGH,
    ),
    WorkflowSpec(
        workflow_type        = WorkflowType.RESEARCH,
        primary_triggers     = {WorkflowType.RESEARCH, WorkflowType.TEMPORAL},
        compatible_triggers  = {WorkflowType.LITERATURE},
        base_priority        = 0.70,
        min_risk             = None,
        max_risk             = RiskLevel.MEDIUM,
    ),
    WorkflowSpec(
        workflow_type        = WorkflowType.LITERATURE,
        primary_triggers     = {WorkflowType.LITERATURE},
        compatible_triggers  = {WorkflowType.RESEARCH, WorkflowType.TEMPORAL},
        base_priority        = 0.65,
        min_risk             = None,
        max_risk             = RiskLevel.LOW,
    ),
    WorkflowSpec(
        workflow_type        = WorkflowType.SIMILAR_CASE,
        primary_triggers     = {WorkflowType.SIMILAR_CASE},
        compatible_triggers  = {WorkflowType.CLINICAL, WorkflowType.DIAGNOSIS},
        base_priority        = 0.60,
        min_risk             = None,
        max_risk             = RiskLevel.HIGH,
    ),
]

# Risk level ordinal for comparison
_RISK_ORDINAL: Dict[RiskLevel, int] = {
    RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3,
}

FALLBACK_WORKFLOW = WorkflowType.CLINICAL
MATCH_THRESHOLD   = 0.15   # minimum score to select a non-fallback workflow


# ═════════════════════════════════════════════════════════════════════════════
# Scoring + Selection
# ═════════════════════════════════════════════════════════════════════════════

def _risk_fits(spec: WorkflowSpec, risk: RiskAssessment) -> bool:
    ord_actual = _RISK_ORDINAL[risk.level]
    if spec.min_risk and ord_actual < _RISK_ORDINAL[spec.min_risk]:
        return False
    if spec.max_risk and ord_actual > _RISK_ORDINAL[spec.max_risk]:
        return False
    return True


def _score_workflow(
    spec:     WorkflowSpec,
    clf:      QueryClassification,
    risk:     RiskAssessment,
) -> float:
    """
    Score a workflow spec against the classification and risk assessment.

    Formula:
      score = (trigger_match * 0.60) + (priority * 0.25) + (risk_fit * 0.15)
    """
    if not _risk_fits(spec, risk):
        return 0.0

    all_types = {clf.primary_type} | set(clf.secondary_types)

    # Trigger matching
    primary_match  = bool(spec.primary_triggers & all_types)
    compat_match   = bool(spec.compatible_triggers & all_types)
    trigger_score  = 1.0 if primary_match else (0.50 if compat_match else 0.0)

    # Intent confidence weighting
    trigger_score *= clf.intent_confidence

    risk_fit_score = 1.0   # already filtered above

    return (
        trigger_score * 0.60 +
        spec.base_priority * 0.25 +
        risk_fit_score * 0.15
    )


def select_workflow(
    classification: QueryClassification,
    risk:           RiskAssessment,
    registry:       dict,           # WorkflowType → WorkflowConfig
) -> WorkflowConfig:
    """
    Select the best matching WorkflowConfig for the given classification and risk.

    Emergency override: if risk is CRITICAL and any spec has emergency_override=True,
    that workflow is selected unconditionally.
    """
    # ── Emergency override ────────────────────────────────────────────────────
    if risk.level == RiskLevel.CRITICAL:
        for spec in WORKFLOW_SPECS:
            if spec.emergency_override and spec.workflow_type in registry:
                logger.info(
                    f"[WorkflowRouter] CRITICAL risk → emergency override: "
                    f"{spec.workflow_type.value}"
                )
                return registry[spec.workflow_type]

    # ── Scored selection ──────────────────────────────────────────────────────
    scored = []
    for spec in WORKFLOW_SPECS:
        if spec.workflow_type not in registry:
            continue
        score = _score_workflow(spec, classification, risk)
        scored.append((spec.workflow_type, score))
        logger.debug(
            f"[WorkflowRouter] {spec.workflow_type.value} → score={score:.3f}"
        )

    scored.sort(key=lambda x: -x[1])
    best_type, best_score = scored[0] if scored else (FALLBACK_WORKFLOW, 0.0)

    if best_score < MATCH_THRESHOLD:
        logger.info(
            f"[WorkflowRouter] No confident match (best={best_score:.3f}) "
            f"→ fallback to {FALLBACK_WORKFLOW.value}"
        )
        best_type = FALLBACK_WORKFLOW

    logger.info(
        f"[WorkflowRouter] Selected: {best_type.value} "
        f"(score={best_score:.3f}, risk={risk.level.value})"
    )
    return registry[best_type]
