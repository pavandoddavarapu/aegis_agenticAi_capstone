"""
orchestration_planner.py — Adaptive Orchestration Planner (Phase 12)

Replaces decision_agent.py as the first LangGraph node.

Key architectural change:
  BEFORE: decision_agent → classifies query → routes to static workflow
  AFTER:  orchestration_planner → understands clinical intent →
          checks information sufficiency → creates dynamic ExecutionPlan →
          routes to clarification OR proceeds to execution

BACKWARD COMPATIBILITY:
  This agent still writes ALL Phase 4.5 decision fields to state:
    - query_type, query_intent_confidence, risk_level
    - selected_workflow, retrieval_strategy, validation_policy
    - reflection_strategy, confidence_threshold, max_retries
    - source_priority, context_budget_tokens
    - escalation_required, escalation_reason, decision_trace
  All downstream agents (query_agent, retrieval_agent, reasoning_agent,
  validation_agent, supervisor_agent) continue to work unchanged.

NEW Phase 12 state writes:
  - clinical_intent: ClinicalIntent enum value
  - execution_plan: serialized ExecutionPlan dict
  - clarification_required: bool
  - clarification_questions: List[Dict]
  - missing_information: List[str]
  - patient_context: Dict

Design:
  - make_decision() from decision_layer.py is called FIRST (full backward compat)
  - Clinical intent is derived from query + classification result
  - InformationSufficiencyEngine checks for missing clinical context
  - ExecutionPlan is constructed from all gathered intelligence
"""
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Optional
from openai import OpenAI

from backend.models.state       import AgentState
from backend.decision           import make_decision
from backend.decision.schemas   import RiskLevel, WorkflowType
from backend.decision.execution_plan import (
    AgentCapability, ClinicalIntent, EvidenceStrategy,
    ExecutionPlan, ExecutionStep, GovernancePolicy,
    PatientContext, QuestionPriority, RetrievalDepth,
    RePlanTrigger,
)
from backend.decision.information_sufficiency_engine import (
    check_sufficiency, SufficiencyReport,
)
from backend.decision.clarification_engine import (
    format_questions_for_api, should_skip_clarification,
)
from backend.utils.logger import logger
from backend.utils.groq_pool import groq_chat_with_retry


PLANNER_MODEL = "llama-3.1-8b-instant" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"
# Absolute hard cap: regardless of max_retries setting, never allow more than this
ABSOLUTE_MAX_RETRIES = 6


ORCHESTRATOR_SYSTEM_PROMPT = """You are the Aegis Clinical AI Orchestrator, the central intelligence brain of a multi-agent clinical decision support system.
Your job is to examine the patient's case, the execution history, and the outputs of the various specialized agents, and decide which agent to invoke next.

You must choose exactly one of the following agents:
1. "clarify": Use this only if critical information is missing from the patient case (e.g. age, chief complaint) and we must ask the clinician for clarification. (Skip if the query is a greeting or general medical knowledge).
2. "query_understand": Use this first to analyze the query, expand medical acronyms, and generate search query variants.
3. "retrieve": Use this to fetch evidence from medical guidelines, neo4j graph databases, and similar cases.
4. "research": Use this to perform live PubMed research. You should often run this in parallel with "retrieve".
4. "evidence_eval": Use this to score and filter the retrieved documents for quality and relevance.
5. "contradiction_check": Use this to check for clinical contradictions or conflicts in the retrieved guidelines.
6. "reason": Use this to synthesize all evidence and write a structured clinical response.
7. "validate": Use this to evaluate the clinical response for grounding, safety, and completeness.
8. "reflect": Use this if validation fails, to diagnose the issue and expand retrieval for a retry.
9. "finalize": Use this when the clinical response is fully validated and ready, or if max retries have been reached, to apply governance checks and complete the workflow.

Guidelines for decision-making:
- Start with "query_understand" to analyze and rewrite the query.
- Once query variants are ready, invoke "retrieve" to fetch evidence.
- Once evidence is retrieved, invoke "evidence_eval" to score it.
- Once evaluated, check for contradictions using "contradiction_check".
- Once contradictions are analyzed, invoke "reason" to generate a clinical reasoning output.
- Once reasoning is generated, invoke "validate" to calculate a validation confidence score.
- IMPORTANT: If validation_score is null/None or validation_feedback is empty, it means validation has NOT been run yet. You MUST run "validate" before "finalize".
- If validation score passes the threshold (e.g. >= 0.70), choose "finalize" to complete the workflow.
- If validation fails, choose "reflect" to broaden search and retry (unless max retries are reached, in which case choose "finalize").
- If the user query is a simple greeting or general conversation, you can bypass the agent steps and go straight to "finalize" (or "reason" if you need to output the message first).

Your output MUST be a JSON object with two fields:
{
  "next_agent": "<agent_name>",
  "reasoning": "<brief explanation of why you selected this agent based on current state>"
}
"""


def _determine_fallback_agent(state: AgentState) -> str:
    """Fallback rules in case the LLM fails or makes an invalid choice."""
    path = state.get("workflow_path", [])
    selected_wf = state.get("selected_workflow", "")
    
    # 1. Clarification check
    clarification_required = state.get("clarification_required", False)
    clarification_answers = state.get("clarification_answers", {})
    if (clarification_required and 
        not clarification_answers and 
        "clarify" not in path and 
        selected_wf != "research"):
        return "clarify"
        
    # 2. Sequential fallback logic based on the last executed spoke node
    # Clean the path to exclude "plan" and "clarify" nodes
    completed = [node for node in path if node not in ("plan", "clarify")]
    
    if not completed:
        return "query_understand"
        
    last_node = completed[-1]
    
    if last_node == "query_understand":
        return ["retrieve", "research"]
    elif last_node in ["retrieve", "research"]:
        # Since retrieve and research run in parallel, they both route back to plan.
        # We only move to evidence_eval when BOTH are in the path. Or rather, just move to evidence_eval.
        # Actually, in LangGraph, after parallel execution, the graph state merges and calls 'plan' again.
        # But wait, 'path' will have both. So if both are in path, we proceed.
        if "retrieve" in completed and "research" in completed:
            return "evidence_eval"
        return "evidence_eval" # Fallback if only one runs
        return "evidence_eval"
    elif last_node == "evidence_eval":
        return "contradiction_check"
    elif last_node == "contradiction_check":
        return "reason"
    elif last_node == "reason":
        return "validate"
    elif last_node == "validate":
        # Check validation results — None means validate hasn't run yet
        score = state.get("validation_score", None)
        threshold = state.get("confidence_threshold", 0.70)
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 2)

        # If score is None (not yet validated), this branch shouldn't be triggered,
        # but guard it anyway
        if score is None:
            return "validate"
        if score < threshold and retry_count < max_retries:
            return "reflect"
        return "finalize"
    elif last_node == "reflect":
        return "retrieve"
        
    return "finalize"


def llm_orchestrate(state: AgentState) -> tuple[str, str]:
    """Invoke the Orchestrator LLM to decide the next step dynamically."""
    query = state.get("query", "")
    workflow_path = state.get("workflow_path", [])
    
    query_variants = state.get("query_variants", [])
    retrieved_docs = state.get("retrieved_docs", [])
    evidence_scores = state.get("evidence_scores", [])
    contradiction_report = state.get("contradiction_report")
    reasoning_output = state.get("reasoning_output", "")
    validation_score = state.get("validation_score", None)
    validation_score_display = f"{validation_score:.3f}" if validation_score is not None else "NOT YET RUN"
    validation_feedback = state.get("validation_feedback", "")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    clarification_required = state.get("clarification_required", False)
    clarification_questions = state.get("clarification_questions", [])
    clarification_answers = state.get("clarification_answers", {})
    
    state_summary = f"""### Current Execution State:
- Original Query: {query}
- Execution History (workflow_path): {workflow_path}
- Retry Count: {retry_count} / {max_retries}

- Query Variants Generated: {len(query_variants)} variants
- Retrieved Documents: {len(retrieved_docs)} docs
- Evidence Evaluated: {"Yes" if evidence_scores else "No"}
- Contradictions Analyzed: {"Yes" if contradiction_report else "No"}
- Clinical Reasoning Output: {"Yes (preview below)" if reasoning_output else "No"}
  Preview: {reasoning_output[:200] + '...' if reasoning_output else 'None'}
- Validation Score: {validation_score_display} (Threshold: {state.get('confidence_threshold', 0.70)}) — NOTE: 'NOT YET RUN' means you MUST run 'validate' before 'finalize'.
- Validation Feedback: {validation_feedback if validation_feedback else 'None'}
- Clarification Required: {clarification_required}
- Clarification Questions: {clarification_questions}
- Clarification Answers Received: {clarification_answers}
"""

    prompt = f"""You are the Aegis Clinical AI Orchestrator. Given the following execution state, decide which agent to run next.

{state_summary}

Choose the next agent from: ["clarify", "query_understand", "retrieve", "research", "evidence_eval", "contradiction_check", "reason", "validate", "reflect", "finalize"]
(You may return a list like ["retrieve", "research"] to run them in parallel if both evidence retrieval and live internet research are needed.)
Respond ONLY with the JSON object format specified in system instructions.
"""

    try:
        # Use key pool — rotates key automatically on 429 or connection errors
        response = groq_chat_with_retry(
            model=PLANNER_MODEL,
            messages=[
                {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        data = json.loads(response.choices[0].message.content)
        next_agent = data.get("next_agent", "")
        if isinstance(next_agent, str):
            next_agent = next_agent.strip()
        reasoning = data.get("reasoning", "").strip()
        return next_agent, reasoning
    except Exception as exc:
        logger.warning(f"[OrchestratorLLM] LLM decision failed: {exc}")
        return "", str(exc)


# ═════════════════════════════════════════════════════════════════════════════
# Clinical Intent Detection
# ═════════════════════════════════════════════════════════════════════════════

# Map from WorkflowType signals + query patterns to ClinicalIntent
_INTENT_SIGNAL_MAP: Dict[ClinicalIntent, List[str]] = {
    ClinicalIntent.EMERGENCY_TRIAGE: [
        r"\bSTEMI\b", r"\bchest\s+pain\b", r"\brespiratory\s+arrest\b",
        r"\bshock\b", r"\bseptic\b", r"\bGCS\s*[<≤]\s*\d\b",
        r"\bunresponsive\b", r"\banaphylax\w*\b", r"\bstroke\b",
        r"\bemergency\b", r"\bcritical\b", r"\blife.threatening\b",
    ],
    ClinicalIntent.MEDICATION_REVIEW: [
        r"\bdose\b", r"\bdosage\b", r"\binteraction\b", r"\bcontraindicated?\b",
        r"\bprescri[bp]\w*\b", r"\bswitch(?:ing)?\s+(?:from|to)\b",
        r"\bdrug\s+review\b", r"\bmedication\s+reconciliation\b",
    ],
    ClinicalIntent.DIAGNOSTIC_WORKUP: [
        r"\bdifferential\b", r"\bdiagnos(?:e|is)\b", r"\bworkup\b",
        r"\brule\s+out\b", r"\bsymptoms?\s+of\b", r"\bpossible\b",
        r"\bsuspect(?:ed)?\b",
    ],
    ClinicalIntent.TREATMENT_PLANNING: [
        r"\btreatment\b", r"\btherapy\b", r"\bmanagement\b",
        r"\bprotocol\b", r"\bfirst.?line\b", r"\bintervention\b",
    ],
    ClinicalIntent.RESEARCH_LOOKUP: [
        r"\blatest\s+(?:evidence|guideline|research)\b",
        r"\bcurrent\s+(?:guidelines?|evidence)\b", r"\bwhat\s+does\s+research\b",
        r"\b202[3-9]\b.*\b(?:study|trial|evidence)\b",
    ],
    ClinicalIntent.LITERATURE_SYNTHESIS: [
        r"\bsystematic\s+review\b", r"\bmeta.?analysis\b", r"\bcochrane\b",
        r"\bevidence\s+synthesis\b", r"\bliterature\s+review\b",
    ],
    ClinicalIntent.SIMILAR_CASE_SEARCH: [
        r"\bsimilar\s+(?:case|patient)\b", r"\bpatient\s+like\b",
        r"\bcase\s+(?:of|report)\b", r"\bpresenting\s+with\b",
    ],
    ClinicalIntent.RISK_STRATIFICATION: [
        r"\brisk\s+stratif\w*\b", r"\brisk\s+score\b",
        r"\bprognosis\b", r"\boutcome\b", r"\bsurvival\b",
    ],
    ClinicalIntent.MONITORING_FOLLOW_UP: [
        r"\bfollow.?up\b", r"\bmonitoring\b", r"\bresponse\s+to\s+treatment\b",
        r"\bpost.?op\b", r"\brecovery\b",
    ],
}


def _detect_clinical_intent(
    query: str,
    workflow_type: WorkflowType,
    risk_level: RiskLevel,
) -> ClinicalIntent:
    """
    Detect clinical intent using signal matching + workflow type.
    Falls back to mapping WorkflowType → ClinicalIntent if signals are weak.
    """
    # Emergency shortcut
    if risk_level == RiskLevel.CRITICAL:
        return ClinicalIntent.EMERGENCY_TRIAGE

    query_lower = query.lower()
    best_intent  = None
    best_score   = 0

    for intent, patterns in _INTENT_SIGNAL_MAP.items():
        hits = sum(1 for p in patterns if re.search(p, query_lower, re.IGNORECASE))
        score = hits / len(patterns)
        if score > best_score:
            best_score = score
            best_intent = intent

    # Fallback: map WorkflowType → ClinicalIntent
    if best_score < 0.05 or best_intent is None:
        _WORKFLOW_INTENT_MAP = {
            WorkflowType.EMERGENCY:    ClinicalIntent.EMERGENCY_TRIAGE,
            WorkflowType.MEDICATION:   ClinicalIntent.MEDICATION_REVIEW,
            WorkflowType.CLINICAL:     ClinicalIntent.DIAGNOSTIC_WORKUP,
            WorkflowType.DIAGNOSIS:    ClinicalIntent.DIAGNOSTIC_WORKUP,
            WorkflowType.TREATMENT:    ClinicalIntent.TREATMENT_PLANNING,
            WorkflowType.RESEARCH:     ClinicalIntent.RESEARCH_LOOKUP,
            WorkflowType.LITERATURE:   ClinicalIntent.LITERATURE_SYNTHESIS,
            WorkflowType.SIMILAR_CASE: ClinicalIntent.SIMILAR_CASE_SEARCH,
            WorkflowType.TEMPORAL:     ClinicalIntent.RESEARCH_LOOKUP,
        }
        best_intent = _WORKFLOW_INTENT_MAP.get(workflow_type, ClinicalIntent.UNKNOWN)

    logger.info(
        f"[OrchestrationPlanner] Clinical intent: {best_intent.value} "
        f"(score={best_score:.3f})"
    )
    return best_intent


# ═════════════════════════════════════════════════════════════════════════════
# Patient Context Extraction
# ═════════════════════════════════════════════════════════════════════════════

def _extract_patient_context(query: str) -> PatientContext:
    """Extract structured patient data from query text."""
    ctx = PatientContext()

    # Age
    age_match = re.search(
        r"\b(\d{1,3})[\s-]?(?:year[\s-]?old|yo|yrs?)\b", query, re.IGNORECASE
    )
    if age_match:
        ctx.age = age_match.group(1)

    # Gender
    if re.search(r"\b(?:male|man|gentleman)\b", query, re.IGNORECASE):
        ctx.gender = "male"
    elif re.search(r"\b(?:female|woman|lady)\b", query, re.IGNORECASE):
        ctx.gender = "female"

    # Chief complaint (first symptom-like phrase)
    cc_match = re.search(
        r"(?:presenting\s+with|c/o|complaining\s+of|has)\s+([^,\.;]{10,80})",
        query, re.IGNORECASE
    )
    if cc_match:
        ctx.chief_complaint = cc_match.group(1).strip()

    # Presence flags
    ctx.vitals_present = bool(re.search(
        r"\b(?:BP|HR|SpO2|O2\s+sat|blood\s+pressure|heart\s+rate|temperature)\b",
        query, re.IGNORECASE
    ))
    ctx.medications_present = bool(re.search(
        r"\b(?:on|taking|prescribed)\s+\w+(?:mg|mcg)?\b|medications?\s*:", query, re.IGNORECASE
    ))
    ctx.allergies_present = bool(re.search(
        r"\b(?:allerg|NKDA)\w*\b", query, re.IGNORECASE
    ))
    ctx.history_present = bool(re.search(
        r"\b(?:history\s+of|PMH|known\s+case\s+of)\b", query, re.IGNORECASE
    ))
    ctx.ecg_present = bool(re.search(r"\b(?:ECG|EKG|ST.?elevation)\b", query, re.IGNORECASE))
    ctx.labs_present = bool(re.search(
        r"\b(?:troponin|CBC|BMP|HbA1c|creatinine|WBC|haemoglobin)\b", query, re.IGNORECASE
    ))

    # Extract conditions
    condition_patterns = [
        r"\b(?:hypertension|diabetes|CAD|CHF|CKD|COPD|asthma|AF|AFib|"
        r"hypothyroidism|hyperthyroidism|epilepsy|cancer|malignancy)\b"
    ]
    for p in condition_patterns:
        matches = re.findall(p, query, re.IGNORECASE)
        ctx.extracted_conditions.extend(matches)

    return ctx


# ═════════════════════════════════════════════════════════════════════════════
# Execution Plan Builder
# ═════════════════════════════════════════════════════════════════════════════

def _build_evidence_strategy(
    plan_trace:     Dict,
    clinical_intent: ClinicalIntent,
    risk_level:     RiskLevel,
) -> EvidenceStrategy:
    """Determine which retrieval sources to activate."""
    use_graph    = plan_trace.get("graph_retrieval", False)
    use_research = plan_trace.get("internet_retrieval", False)
    use_cases    = plan_trace.get("case_retrieval", False)
    use_multi    = plan_trace.get("multimodal_enabled", False)

    # Deep retrieval for emergencies and complex diagnostics
    if risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
        depth = RetrievalDepth.DEEP
    elif clinical_intent in (ClinicalIntent.LITERATURE_SYNTHESIS, ClinicalIntent.RESEARCH_LOOKUP):
        depth = RetrievalDepth.DEEP
    else:
        depth = RetrievalDepth.STANDARD

    return EvidenceStrategy(
        use_graph         = use_graph,
        use_semantic      = True,   # always
        use_research      = use_research,
        use_multimodal    = use_multi,
        use_similar_cases = use_cases,
        retrieval_depth   = depth,
    )


def _build_required_capabilities(
    clinical_intent: ClinicalIntent,
    evidence_strategy: EvidenceStrategy,
    risk_level: RiskLevel,
) -> List[AgentCapability]:
    """Determine which agent capabilities are required."""
    required = [
        AgentCapability.QUERY_UNDERSTANDING,
        AgentCapability.SEMANTIC_RETRIEVAL,
        AgentCapability.EVIDENCE_EVALUATION,
        AgentCapability.CONTRADICTION_CHECK,
        AgentCapability.CLINICAL_REASONING,
        AgentCapability.VALIDATION,
        AgentCapability.GOVERNANCE,
    ]
    if evidence_strategy.use_graph:
        required.append(AgentCapability.GRAPH_RETRIEVAL)
    if evidence_strategy.use_research:
        required.append(AgentCapability.RESEARCH_RETRIEVAL)
    if evidence_strategy.use_similar_cases:
        required.append(AgentCapability.SIMILAR_CASE_LOOKUP)
    if evidence_strategy.use_multimodal:
        required.append(AgentCapability.MULTIMODAL_ANALYSIS)
    if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        required.append(AgentCapability.REFLECTION)
    return required


def _build_execution_plan(
    query:           str,
    clinical_intent: ClinicalIntent,
    decision_plan,   # DecisionPlan from existing make_decision()
    sufficiency:     Optional[SufficiencyReport],
    patient_ctx:     PatientContext,
) -> ExecutionPlan:
    """Construct the ExecutionPlan from all gathered intelligence."""
    risk_level   = decision_plan.risk.level
    plan_trace   = decision_plan.decision_trace
    risk_score   = decision_plan.risk.score

    ev_strategy  = _build_evidence_strategy(plan_trace, clinical_intent, risk_level)
    required_cap = _build_required_capabilities(clinical_intent, ev_strategy, risk_level)

    # Optional capabilities (nice-to-have but not critical)
    optional_cap = []
    if not ev_strategy.use_research and risk_level != RiskLevel.LOW:
        optional_cap.append(AgentCapability.RESEARCH_RETRIEVAL)

    # Clarification
    clarification_required = False
    clarification_questions = []
    missing_information = []
    proceed_with_caveat = ""

    if sufficiency and not sufficiency.can_proceed:
        clarification_required = True
        clarification_questions = sufficiency.clarification_questions
        missing_information = sufficiency.missing_critical + sufficiency.missing_important
        proceed_with_caveat = sufficiency.proceed_with_caveat
    elif sufficiency:
        missing_information = sufficiency.missing_important + sufficiency.missing_optional
        if sufficiency.proceed_with_caveat:
            proceed_with_caveat = sufficiency.proceed_with_caveat

    # Governance policy
    gov_policy = GovernancePolicy(
        escalation_threshold = decision_plan.workflow.escalation_threshold,
        require_human_review = decision_plan.escalation_required,
        review_severity      = "critical" if risk_level == RiskLevel.CRITICAL else "standard",
        audit_level          = "enhanced" if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "standard",
    )

    # Goal description
    goal_descriptions = {
        ClinicalIntent.EMERGENCY_TRIAGE:    "Rapid emergency triage and immediate intervention guidance",
        ClinicalIntent.DIAGNOSTIC_WORKUP:   "Differential diagnosis generation and diagnostic reasoning",
        ClinicalIntent.TREATMENT_PLANNING:  "Evidence-based treatment protocol selection",
        ClinicalIntent.MEDICATION_REVIEW:   "Medication safety review and drug interaction analysis",
        ClinicalIntent.RESEARCH_LOOKUP:     "Current evidence and guideline retrieval",
        ClinicalIntent.LITERATURE_SYNTHESIS: "Systematic evidence synthesis from literature",
        ClinicalIntent.SIMILAR_CASE_SEARCH: "Similar clinical case identification and comparison",
        ClinicalIntent.RISK_STRATIFICATION: "Clinical risk scoring and prognosis assessment",
        ClinicalIntent.MONITORING_FOLLOW_UP: "Treatment monitoring and follow-up assessment",
        ClinicalIntent.UNKNOWN:             "General clinical intelligence analysis",
    }

    plan = ExecutionPlan(
        clinical_intent         = clinical_intent,
        goal                    = clinical_intent.value,
        goal_description        = goal_descriptions.get(clinical_intent, "Clinical analysis"),
        patient_context         = patient_ctx,
        required_capabilities   = required_cap,
        optional_capabilities   = optional_cap,
        evidence_strategy       = ev_strategy,
        clarification_required  = clarification_required,
        clarification_questions = clarification_questions,
        missing_information     = missing_information,
        proceed_with_caveat     = proceed_with_caveat,
        governance_policy       = gov_policy,
        replan_triggers         = [
            RePlanTrigger.EVIDENCE_QUALITY_DROP,
            RePlanTrigger.CONTRADICTION_DETECTED,
            RePlanTrigger.CONFIDENCE_LOW,
            RePlanTrigger.VALIDATION_FAILED,
        ],
        max_replan_iterations   = decision_plan.max_retries,
        risk_level_value        = risk_level.value,
        risk_score              = risk_score,
        emergency_override      = (risk_level == RiskLevel.CRITICAL),
        plan_trace              = {
            "decision_trace":   plan_trace,
            "workflow_type":    decision_plan.workflow.workflow_type.value,
            "confidence_threshold": decision_plan.confidence_threshold,
        },
    )
    return plan


# ═════════════════════════════════════════════════════════════════════════════
# Public Agent Node
# ═════════════════════════════════════════════════════════════════════════════

def orchestration_planner(state: AgentState) -> dict:
    """
    Phase 12 Orchestration Planner — LangGraph node.

    Replaces decision_agent.py as the first node in the graph.
    Writes all Phase 4.5 fields (backward compat) + Phase 12 fields.

    Reads:   state["query"], state["clarification_answers"]
    Writes:  All Phase 4.5 decision fields + Phase 12 orchestration fields
    """
    query                = state.get("query", "").strip()
    clarification_answers = state.get("clarification_answers", {})
    replan_count         = state.get("replan_count", 0)
    clarification_count  = state.get("retry_count", 0)  # reuse retry for clarity loops

    # ── Loop Control: Detect subsequent executions ────────────────────────────
    completed_spokes = [node for node in state.get("workflow_path", []) if node not in ("plan", "clarify")]
    is_subsequent = len(completed_spokes) > 0

    if is_subsequent:
        # Guardrail 1: Hard absolute retry cap (catches runaway loops even if max_retries misconfigured)
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 2)
        effective_max = min(max_retries, ABSOLUTE_MAX_RETRIES)
        if retry_count >= effective_max:
            logger.warning(
                f"[OrchestrationPlanner] Max retries reached ({retry_count}/{effective_max}). "
                f"Routing directly to finalize."
            )
            return {
                "next_agent": "finalize",
                "workflow_path": ["plan"],
            }

        # Guardrail 2: Hard agent error recovery exit (prevents infinite loop on LLM/API failure)
        if state.get("error"):
            logger.warning(
                f"[OrchestrationPlanner] Error detected in state: '{state.get('error')}'. "
                "Routing directly to finalize to prevent loops."
            )
            return {
                "next_agent": "finalize",
                "workflow_path": ["plan"],
            }

        selected_wf = state.get("selected_workflow", "")
        clinical_int = state.get("clinical_intent", "")
        
        # Fast-path: bypass LLM orchestration for research/general workflow for speed
        if selected_wf == "research" or clinical_int in ("research_lookup", "literature_synthesis") or state.get("execution_plan", {}).get("goal") == "general_medical_knowledge":
            next_agent = _determine_fallback_agent(state)
            if next_agent == "clarify":
                next_agent = "query_understand"
            logger.info(f"[OrchestrationPlanner] Subsequent planning run. Research workflow detected. Bypassing LLM orchestrator for speed. Next: '{next_agent}'")
            return {
                "next_agent": next_agent,
                "workflow_path": ["plan"],
            }

        logger.info("[OrchestrationPlanner] Subsequent planning run. Using deterministic sequential routing.")
        next_agent = _determine_fallback_agent(state)
        reasoning = f"Deterministic sequential routing selected: {next_agent}"

        # Safety guardrails
        if selected_wf == "research" and next_agent == "clarify":
            next_agent = "query_understand"
            reasoning = "Overridden clarify choice for research workflow."

        logger.info(f"[OrchestrationPlanner] Next agent: '{next_agent}'. Reason: {reasoning}")
        
        return {
            "next_agent": next_agent,
            "workflow_path": ["plan"],
        }

    logger.info(f"[OrchestrationPlanner] Initial planning for: '{query[:80]}'")

    if not query:
        logger.warning("[OrchestrationPlanner] Empty query — using clinical defaults.")
        return _default_state_update()

    # ── Step 0a: Conversational / greeting fast-path ──────────────────────────
    query_lower = query.lower().strip()
    is_conversational = (
        len(query_lower) < 15 or 
        any(g in query_lower for g in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"])
    ) and not any(k in query_lower for k in [
        "bp", "hr", "spo2", "vitals", "intake", "history", "diagnos", "treatment", "pain", "symptom", "stemi", "chest"
    ])

    if is_conversational:
        logger.info("[OrchestrationPlanner] Conversational query detected — fast-tracking response.")
        return {
            "query_type":              "clinical",
            "query_intent_confidence": 1.0,
            "risk_level":              "low",
            "selected_workflow":       "clinical",
            "retrieval_strategy":      "hybrid",
            "validation_policy":       "standard",
            "confidence_threshold":    0.72,
            "reflection_strategy":     "moderate",
            "max_retries":             2,
            "source_priority":         "guideline_first",
            "context_budget_tokens":   3500,
            "escalation_required":     False,
            "escalation_reason":       "",
            "decision_trace":          {},
            "clinical_intent":         "unknown",
            "execution_plan":          {"goal": "conversational response"},
            "clarification_required":  False,
            "clarification_questions": [],
            "missing_information":     [],
            "patient_context":         {},
            "replan_count":            0,
            "replan_reasons":          [],
            "monitor_events":          [],
            "workflow_path":           ["plan"],
            "bypass_graph":            True,
            "reasoning_output":        "Hello! How can I assist you with your patient cases today?",
            "final_response":          "Hello! How can I assist you with your patient cases today?",
            "validation_score":        1.0,
            "next_agent":              "finalize",
        }

    # ── Step 0b: General medical knowledge question fast-path ─────────────────
    # Detects questions like "what are the symptoms of sinusitis?",
    # "how does metformin work?", "explain the pathophysiology of PE", etc.
    # These do NOT require a specific patient — no clarification should be asked.
    _GENERAL_Q_STARTERS = re.compile(
        r"^(what\b|how\b|why\b|when\b|is\b|are\b|can\b|does\b|do\b|"
        r"explain\b|define\b|tell\s+me\b|describe\b|list\b|which\b|"
        r"who\b|where\b|what'?s\b|how'?s\b)",
        re.IGNORECASE,
    )
    _PATIENT_SIGNALS = re.compile(
        r"\b(\d+[\s-]*(year|yr|y\.?o|month|week|day)s?[\s-]*(old)?|"
        r"male|female|man\b|woman\b|boy\b|girl\b|"
        r"patient\s+(is|has|with|presents)|presenting\s+with|chief\s+complaint|"
        r"past\s+(medical\s+)?history|vitals|blood\s+pressure|"
        r"bp\s*[\d:\/]+|heart\s+rate|hr\s*\d+|o2\s*(sat)?|"
        r"temperature\s*\d+|my\s+patient|case\s+(of|report)|"
        r"admitted|icu\b|er\b|intake)\b",
        re.IGNORECASE,
    )

    # Normalize query for matching typos
    normalized_query_lower = query_lower.replace("synus", "sinus").replace("symtoms", "symptoms").replace("symptomns", "symptoms").strip()

    # Search for question starters or keywords (symptoms, treatment, causes, pathophysiology, side effects, etc.) anywhere
    _GENERAL_KEYWORDS = re.compile(
        r"\b(symptoms?|symtoms|treatment|therapy|pathophysiology|causes?|side\s*effects?|dosage|dose|interactions|contraindications|guideline|evidence|definition|explain|describe)\b",
        re.IGNORECASE
    )

    is_general_knowledge = (
        (bool(_GENERAL_Q_STARTERS.match(normalized_query_lower)) or bool(_GENERAL_KEYWORDS.search(normalized_query_lower)) or len(normalized_query_lower.split()) <= 4)
        and not bool(_PATIENT_SIGNALS.search(normalized_query_lower))
    )

    if is_general_knowledge:
        logger.info(
            f"[OrchestrationPlanner] General knowledge query detected — "
            f"bypassing sufficiency check: '{query[:60]}'"
        )
        return {
            "query_type":              "research",
            "query_intent_confidence": 0.95,
            "risk_level":              "low",
            "selected_workflow":       "research",
            "retrieval_strategy":      "semantic",
            "validation_policy":       "standard",
            "confidence_threshold":    0.70,
            "reflection_strategy":     "moderate",
            "max_retries":             1,
            "source_priority":         "guideline_first",
            "context_budget_tokens":   4000,
            "escalation_required":     False,
            "escalation_reason":       "",
            "decision_trace":          {},
            "clinical_intent":         "research_lookup",
            "execution_plan":          {
                "goal": "general_medical_knowledge",
                "clinical_intent": "research_lookup",
                "risk_level": "low",
            },
            "clarification_required":  False,   # ← key: never ask for patient details
            "clarification_questions": [],
            "missing_information":     [],
            "patient_context":         {},
            "replan_count":            0,
            "replan_reasons":          [],
            "monitor_events":          [],
            "workflow_path":           ["plan"],
            "next_agent":              "query_understand",
        }

    # ── Step 1: Existing make_decision() — preserves ALL Phase 4.5 behavior ──
    try:
        decision_plan = make_decision(query=query)
    except Exception as exc:
        logger.exception(f"[OrchestrationPlanner] make_decision failed: {exc}")
        return _default_state_update()

    risk_level    = decision_plan.risk.level
    workflow_type = decision_plan.workflow.workflow_type

    # ── Step 2: Detect clinical intent ────────────────────────────────────────
    clinical_intent = _detect_clinical_intent(query, workflow_type, risk_level)

    # ── Step 3: Extract patient context ───────────────────────────────────────
    patient_ctx = _extract_patient_context(query)
    
    # Merge existing patient context if present in state (Phase 13)
    existing_ctx_dict = state.get("patient_context") or {}
    if existing_ctx_dict:
        if not patient_ctx.age and existing_ctx_dict.get("age"):
            patient_ctx.age = existing_ctx_dict["age"]
        if not patient_ctx.gender and existing_ctx_dict.get("gender"):
            patient_ctx.gender = existing_ctx_dict["gender"]
        if not patient_ctx.chief_complaint and existing_ctx_dict.get("chief_complaint"):
            patient_ctx.chief_complaint = existing_ctx_dict["chief_complaint"]
        if not patient_ctx.symptom_duration and existing_ctx_dict.get("symptom_duration"):
            patient_ctx.symptom_duration = existing_ctx_dict["symptom_duration"]
            
        patient_ctx.vitals_present = patient_ctx.vitals_present or existing_ctx_dict.get("vitals_present", False)
        patient_ctx.medications_present = patient_ctx.medications_present or existing_ctx_dict.get("medications_present", False)
        patient_ctx.allergies_present = patient_ctx.allergies_present or existing_ctx_dict.get("allergies_present", False)
        patient_ctx.history_present = patient_ctx.history_present or existing_ctx_dict.get("history_present", False)
        patient_ctx.ecg_present = patient_ctx.ecg_present or existing_ctx_dict.get("ecg_present", False)
        patient_ctx.labs_present = patient_ctx.labs_present or existing_ctx_dict.get("labs_present", False)
        patient_ctx.imaging_present = patient_ctx.imaging_present or existing_ctx_dict.get("imaging_present", False)
        
        # Merge conditions
        for cond in existing_ctx_dict.get("extracted_conditions", []):
            if cond not in patient_ctx.extracted_conditions:
                patient_ctx.extracted_conditions.append(cond)
        
        # Merge medications
        for med in existing_ctx_dict.get("extracted_medications", []):
            if med not in patient_ctx.extracted_medications:
                patient_ctx.extracted_medications.append(med)
                
        # Merge vitals
        existing_vitals = existing_ctx_dict.get("extracted_vitals") or {}
        for k, v in existing_vitals.items():
            if k not in patient_ctx.extracted_vitals:
                patient_ctx.extracted_vitals[k] = v

    # ── Step 4: Information sufficiency check ─────────────────────────────────
    emergency_override = (risk_level == RiskLevel.CRITICAL)
    skip_clarification = should_skip_clarification(
        replan_count        = replan_count,
        clarification_count = clarification_count,
        risk_level          = risk_level.value,
    )

    sufficiency: Optional[SufficiencyReport] = None
    clarification_required  = False
    clarification_questions_list = []
    missing_information     = []

    if not skip_clarification:
        try:
            sufficiency = check_sufficiency(
                query            = query,
                clinical_intent  = clinical_intent,
                emergency_override = emergency_override,
            )

            if sufficiency and not sufficiency.can_proceed and not clarification_answers:
                clarification_required = True

            clarification_questions_list = format_questions_for_api(
                sufficiency.clarification_questions if sufficiency else []
            )
            missing_information = (
                (sufficiency.missing_critical + sufficiency.missing_important)
                if sufficiency else []
            )
        except Exception as exc:
            logger.warning(f"[OrchestrationPlanner] Sufficiency check failed: {exc}")

    # ── Step 5: Build ExecutionPlan ────────────────────────────────────────────
    try:
        exec_plan = _build_execution_plan(
            query           = query,
            clinical_intent = clinical_intent,
            decision_plan   = decision_plan,
            sufficiency     = sufficiency,
            patient_ctx     = patient_ctx,
        )
        exec_plan_dict = exec_plan.to_summary_dict()
        # Store full plan too (for downstream use)
        exec_plan_dict["_full"] = exec_plan.model_dump()
    except Exception as exc:
        logger.warning(f"[OrchestrationPlanner] ExecutionPlan build failed: {exc}")
        exec_plan_dict = {"goal": clinical_intent.value, "error": str(exc)}

    logger.info(
        f"[OrchestrationPlanner] Plan complete: "
        f"intent={clinical_intent.value} "
        f"risk={risk_level.value} "
        f"clarification_required={clarification_required} "
        f"missing={missing_information[:3]}"
    )

    return {
        # ── ALL Phase 4.5 fields (backward compatible) ─────────────────────
        "query_type":              decision_plan.classification.primary_type.value,
        "query_intent_confidence": decision_plan.classification.intent_confidence,
        "risk_level":              risk_level.value,
        "selected_workflow":       workflow_type.value,
        "retrieval_strategy":      decision_plan.retrieval_strategy.value,
        "validation_policy":       decision_plan.validation_strictness.value,
        "confidence_threshold":    decision_plan.confidence_threshold,
        "reflection_strategy":     decision_plan.reflection_strategy.value,
        "max_retries":             decision_plan.max_retries,
        "source_priority":         decision_plan.source_priority.value,
        "context_budget_tokens":   decision_plan.context_budget_tokens,
        "escalation_required":     decision_plan.escalation_required,
        "escalation_reason":       decision_plan.escalation_reason,
        "decision_trace":          decision_plan.decision_trace,
        # ── Phase 12 new fields ────────────────────────────────────────────
        "clinical_intent":         clinical_intent.value,
        "execution_plan":          exec_plan_dict,
        "clarification_required":  clarification_required,
        "clarification_questions": clarification_questions_list,
        "missing_information":     missing_information,
        "patient_context":         patient_ctx.model_dump(),
        "replan_count":            replan_count,
        "replan_reasons":          state.get("replan_reasons", []),
        "monitor_events":          state.get("monitor_events", []),
        # Graph path
        "workflow_path":           ["plan"],
        "next_agent":              "clarify" if clarification_required else "query_understand",
    }


def _default_state_update() -> dict:
    """Safe default state when planner fails or receives empty query."""
    return {
        "query_type":              "clinical",
        "query_intent_confidence": 0.5,
        "risk_level":              "low",
        "selected_workflow":       "clinical",
        "retrieval_strategy":      "hybrid",
        "validation_policy":       "standard",
        "confidence_threshold":    0.72,
        "reflection_strategy":     "moderate",
        "max_retries":             2,
        "source_priority":         "guideline_first",
        "context_budget_tokens":   3500,
        "escalation_required":     False,
        "escalation_reason":       "",
        "decision_trace":          {},
        "clinical_intent":         "unknown",
        "execution_plan":          {},
        "clarification_required":  False,
        "clarification_questions": [],
        "missing_information":     [],
        "patient_context":         {},
        "replan_count":            0,
        "replan_reasons":          [],
        "monitor_events":          [],
        "workflow_path":           ["plan"],
    }
