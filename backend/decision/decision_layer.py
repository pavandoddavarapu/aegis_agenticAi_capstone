"""
decision_layer.py — Central Orchestration Intelligence (Phase 4.5)

THIS is the brain of the Aegis system.

Architecture:
  make_decision() is the single public entry point.
  It executes a sequential pipeline of independent sub-engines:

    1. QueryClassifier     — multi-label signal + LLM hybrid classification
    2. RiskEngine          — signal-weighted medical risk assessment
    3. WorkflowRouter      — priority-weighted workflow selection
    4. PolicyAssembler     — assembles final orchestration plan
                             (merges workflow base config with risk adjustments)
    5. EscalationEvaluator — decides if HITL escalation is required

  Each sub-engine is stateless and independently testable.
  The Decision Layer does NOT perform retrieval, reasoning, or LLM calls
  unless the query classifier falls below its signal-based confidence
  threshold (in which case it invokes a single cheap LLM call to classify).

Design patterns used:
  - Strategy pattern: QueryClassifier.classify() dispatches to signal or LLM strategy.
  - Policy pattern: PolicyAssembler applies risk overrides to workflow config.
  - Registry pattern: WorkflowRouter consults the WORKFLOW_REGISTRY.
  - Facade pattern: make_decision() hides the multi-step orchestration.

Extensibility:
  - Add new workflows: add to WORKFLOW_REGISTRY and WorkflowSpec list.
  - Add new risk signals: append to signal lists in risk_engine.py.
  - Add new query types: add to WorkflowType enum and signal patterns.
  - Override thresholds: all thresholds are constants at module top level.
"""
from __future__ import annotations
import os
import re
from typing import Dict, List, Optional

from backend.decision.schemas import (
    DecisionPlan, QueryClassification, RiskAssessment,
    WorkflowConfig, WorkflowType, RiskLevel,
    RetrievalStrategy, ReflectionStrategy, ValidationStrictness,
    SourcePriority,
)
from backend.decision.risk_engine    import assess_risk
from backend.decision.workflow_router import select_workflow
from backend.utils.logger            import logger

# Imported lazily to avoid circular imports at module load
_openai_client = None

# ── Classification thresholds ─────────────────────────────────────────────────
SIGNAL_CONFIDENCE_THRESHOLD = 0.65   # below this → invoke LLM classifier
LLM_CLASSIFY_MODEL          = "llama-3.1-8b-instant" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"


# ═════════════════════════════════════════════════════════════════════════════
# 1. Query Classifier
# ═════════════════════════════════════════════════════════════════════════════

# Signal patterns per WorkflowType (multi-label — each is independent)
QUERY_TYPE_SIGNALS: Dict[WorkflowType, List[str]] = {
    WorkflowType.EMERGENCY:    [
        r"\bchest\s+pain\b", r"\bSTEMI\b", r"\bshock\b", r"\brespiratory\s+arrest\b",
        r"\bemergency\b", r"\blife.threatening\b", r"\bcritical\b", r"\bseptic\b",
        r"\bstroke\b", r"\banaphylax\w*\b", r"\bGCS\s*[<≤]\s*\d\b",
    ],
    WorkflowType.MEDICATION:   [
        r"\bdose\b", r"\bdosage\b", r"\binteraction\b", r"\bcontraindicated?\b",
        r"\bdrug\b", r"\bmedication\b", r"\bprescri[bp]\w*\b", r"\bpharma\w*\b",
        r"\bwarfarin\b", r"\bmetformin\b", r"\bheparin\b", r"\bantibiotic\b",
    ],
    WorkflowType.RESEARCH:     [
        r"\blatest\b", r"\b202[3-9]\b", r"\brecent\b", r"\bnew\s+evidence\b",
        r"\bcurrent\s+guidelines?\b", r"\bresearch\b", r"\bstudy\b", r"\btrial\b",
    ],
    WorkflowType.LITERATURE:   [
        r"\bsystematic\s+review\b", r"\bmeta.analysis\b", r"\bcochrane\b",
        r"\bevidence\s+synthesis\b", r"\bliterature\s+review\b", r"\bRCT\b",
    ],
    WorkflowType.SIMILAR_CASE: [
        r"\bsimilar\s+case\b", r"\bpatient\s+with\b", r"\bpresenting\s+with\b",
        r"\bcase\s+of\b", r"\byear.old\b", r"\bcase\s+report\b",
    ],
    WorkflowType.DIAGNOSIS:    [
        r"\bdifferential\b", r"\bdiagnosis\b", r"\bdiagnose\b", r"\bdisease\b",
        r"\bcondition\b", r"\bsymptom\b", r"\bsign\b",
    ],
    WorkflowType.TREATMENT:    [
        r"\btreatment\b", r"\btherapy\b", r"\bmanagement\s+of\b",
        r"\bprotocol\b", r"\bintervention\b", r"\bfirst.line\b",
    ],
    WorkflowType.TEMPORAL:     [
        r"\blatest\b", r"\brecent\b", r"\b202[3-9]\b", r"\bcurrent\b",
        r"\bupdated?\b", r"\bnew\b",
    ],
    WorkflowType.CLINICAL:     [
        r"\bclinical\b", r"\bpatient\b", r"\bhospital\b", r"\bclinic\b",
        r"\bmedical\b", r"\bhealth\b",
    ],
}


def _signal_classify(query: str) -> Dict[WorkflowType, float]:
    """
    Score each WorkflowType by pattern hit rate.
    Returns a dict of WorkflowType → confidence [0, 1].
    """
    q_lower = query.lower()
    scores  = {}
    for wtype, patterns in QUERY_TYPE_SIGNALS.items():
        hits = sum(1 for p in patterns if re.search(p, q_lower, re.IGNORECASE))
        scores[wtype] = round(hits / len(patterns), 4)
    return scores


def _llm_classify(query: str) -> Dict[str, float]:
    """
    LLM-assisted classification fallback.
    Returns {workflow_type_str: confidence} for top-3 types.
    Only invoked when signal classifier confidence is low.
    """
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("[DecisionLayer] API KEY not set — LLM classifier unavailable.")
            return {}
        try:
            from openai import OpenAI
            base_url = "https://api.groq.com/openai/v1" if os.getenv("GROQ_API_KEY") else None
            _openai_client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as exc:
            logger.warning(f"[DecisionLayer] OpenAI/Groq client init failed: {exc}")
            return {}

    type_list = ", ".join(t.value for t in WorkflowType)
    prompt = (
        f"Classify this medical query into 1-3 workflow types from: [{type_list}].\n"
        f"Return JSON: {{\"types\": [\"type1\", \"type2\"], \"confidence\": 0.85}}\n"
        f"Query: {query[:300]}"
    )
    try:
        resp = _openai_client.chat.completions.create(
            model=LLM_CLASSIFY_MODEL, temperature=0.0, max_tokens=80,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        data = json.loads(resp.choices[0].message.content)
        types  = data.get("types", [])
        conf   = float(data.get("confidence", 0.70))
        return {t: conf for t in types}
    except Exception as exc:
        logger.warning(f"[DecisionLayer] LLM classifier failed: {exc}")
        return {}


def classify_query(query: str) -> QueryClassification:
    """
    Multi-label query classifier.
    Strategy: signal-first, LLM fallback on low confidence.
    """
    signal_scores = _signal_classify(query)
    # Sort by score descending
    ranked = sorted(signal_scores.items(), key=lambda x: -x[1])

    primary_type, primary_score = ranked[0] if ranked else (WorkflowType.CLINICAL, 0.3)
    secondary_types = [t for t, s in ranked[1:] if s >= 0.05][:2]

    method = "signal"

    # LLM fallback if confidence is low
    if primary_score < SIGNAL_CONFIDENCE_THRESHOLD:
        logger.info(
            f"[DecisionLayer] Signal confidence {primary_score:.2f} below threshold "
            f"— invoking LLM classifier."
        )
        llm_scores = _llm_classify(query)
        if llm_scores:
            try:
                best_llm = max(llm_scores, key=llm_scores.__getitem__)
                primary_type  = WorkflowType(best_llm)
                primary_score = llm_scores[best_llm]
                secondary_types = [
                    WorkflowType(t) for t in llm_scores
                    if t != best_llm and t in [wt.value for wt in WorkflowType]
                ]
                method = "llm"
            except (ValueError, KeyError):
                pass  # keep signal result

    # Ensure primary_score fallback
    if primary_score < 0.02:
        primary_type  = WorkflowType.CLINICAL
        primary_score = 0.50
        method        = "fallback"

    labels = [primary_type.value] + [t.value for t in secondary_types]
    logger.info(
        f"[DecisionLayer] Classification: primary={primary_type.value} "
        f"conf={primary_score:.2f} method={method} "
        f"secondary={[t.value for t in secondary_types]}"
    )

    # Normalise: raw pattern hit rate is low (max patterns ~12, typical hit 1-2)
    # Scale to [0, 1] with a softer curve so 1 strong hit = ~0.7 confidence
    normalised_confidence = min(primary_score * 5.0, 1.0)

    return QueryClassification(
        primary_type          = primary_type,
        secondary_types       = secondary_types,
        intent_confidence     = round(normalised_confidence, 3),
        labels                = labels,
        classification_method = method,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 2. Policy Assembler
# ═════════════════════════════════════════════════════════════════════════════

def _assemble_policy(
    workflow: WorkflowConfig,
    risk:     RiskAssessment,
) -> Dict:
    """
    Merge workflow base config with risk engine adjustments.
    Returns a dict of final orchestration parameters.
    """
    import dataclasses

    # Confidence threshold: workflow base + risk engine boost (capped at 0.98)
    final_threshold = min(
        workflow.confidence_threshold + risk.confidence_boost,
        0.98,
    )

    # Max retries: risk engine may override upward
    final_retries = max(
        workflow.max_retries,
        risk.max_retries_override or 0,
    )

    # Reflection strategy: escalate if CRITICAL
    reflection = workflow.reflection_strategy
    if risk.level == RiskLevel.CRITICAL and reflection != ReflectionStrategy.EMERGENCY:
        reflection = ReflectionStrategy.EMERGENCY

    # Validation strictness: escalate if CRITICAL or HIGH
    strictness = workflow.validation_strictness
    if risk.level == RiskLevel.CRITICAL:
        strictness = ValidationStrictness.CRITICAL
    elif risk.level == RiskLevel.HIGH and strictness == ValidationStrictness.RELAXED:
        strictness = ValidationStrictness.STANDARD

    return {
        "confidence_threshold":   final_threshold,
        "max_retries":            final_retries,
        "reflection_strategy":    reflection,
        "validation_strictness":  strictness,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. Escalation Evaluator
# ═════════════════════════════════════════════════════════════════════════════

def _evaluate_escalation(
    risk:             RiskAssessment,
    workflow:         WorkflowConfig,
    intent_confidence: float,
) -> tuple[bool, str]:
    """
    Determine if Human-in-the-Loop escalation should be flagged.
    Returns (escalation_required, reason_string).
    """
    if risk.requires_escalation:
        return True, (
            f"Risk score {risk.score:.2f} exceeds escalation threshold "
            f"{workflow.escalation_threshold:.2f}. Factors: "
            + "; ".join(risk.contributing_factors[:3])
        )

    if risk.score >= workflow.escalation_threshold:
        return True, (
            f"Risk score {risk.score:.2f} exceeds workflow "
            f"escalation threshold {workflow.escalation_threshold:.2f}."
        )

    if intent_confidence < 0.30:
        return True, (
            f"Low classification confidence ({intent_confidence:.2f}). "
            "Manual review recommended."
        )

    return False, ""


# ═════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═════════════════════════════════════════════════════════════════════════════

def make_decision(
    query:                  str,
    retrieval_confidence:   float = 0.70,
    contradiction_detected: bool  = False,
    evidence_coverage:      float = 0.70,
) -> DecisionPlan:
    """
    Central orchestration intelligence entry point.

    Executes: classify → assess_risk → select_workflow → assemble_policy
              → evaluate_escalation → build DecisionPlan

    Args:
        query:                  The (acronym-expanded) medical query.
        retrieval_confidence:   Optional: prior retrieval score (for post-retrieval re-evaluation).
        contradiction_detected: Optional: whether contradictions were found.
        evidence_coverage:      Optional: evidence entity coverage score.

    Returns:
        DecisionPlan — the complete orchestration plan for this request.
    """
    from backend.decision.schemas import WORKFLOW_REGISTRY  # avoid circular import

    logger.info(f"[DecisionLayer] Processing: '{query[:80]}'")

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    classification = classify_query(query)

    # ── Step 2: Assess risk ───────────────────────────────────────────────────
    risk = assess_risk(
        query                  = query,
        retrieval_confidence   = retrieval_confidence,
        contradiction_detected = contradiction_detected,
        evidence_coverage      = evidence_coverage,
    )

    # ── Step 3: Select workflow ───────────────────────────────────────────────
    workflow = select_workflow(classification, risk, WORKFLOW_REGISTRY)

    # ── Step 4: Assemble final policy (risk adjustments applied) ──────────────
    policy = _assemble_policy(workflow, risk)

    # ── Step 5: Escalation evaluation ────────────────────────────────────────
    escalation_required, escalation_reason = _evaluate_escalation(
        risk, workflow, classification.intent_confidence
    )

    # ── Step 6: Build DecisionPlan ────────────────────────────────────────────
    plan = DecisionPlan(
        classification        = classification,
        risk                  = risk,
        workflow              = workflow,
        retrieval_strategy    = workflow.retrieval_strategy,
        confidence_threshold  = policy["confidence_threshold"],
        reflection_strategy   = policy["reflection_strategy"],
        validation_strictness = policy["validation_strictness"],
        source_priority       = workflow.source_priority,
        max_retries           = policy["max_retries"],
        context_budget_tokens = workflow.context_budget_tokens,
        escalation_required   = escalation_required,
        escalation_reason     = escalation_reason,
        decision_trace        = {},
    )
    plan.decision_trace = plan.to_trace_dict()

    logger.info(
        f"[DecisionLayer] Plan: workflow={workflow.workflow_type.value} "
        f"risk={risk.level.value} threshold={plan.confidence_threshold:.2f} "
        f"escalate={escalation_required}"
    )
    return plan
