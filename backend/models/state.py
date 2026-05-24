"""
state.py — Shared AgentState for the LangGraph Workflow.

Versioning:
  Phase 1: query, retrieved_docs, reasoning_output
  Phase 3: validation_score, validation_feedback, retry_count,
           reflection_notes, workflow_path, final_response, error
  Phase 4: query_type, query_variants, query_plan, compressed_context
  Phase 4.5: full decision layer fields (query_intent_confidence,
             risk_level, selected_workflow, retrieval_strategy,
             validation_policy, reflection_strategy, source_priority,
             confidence_threshold, max_retries, context_budget_tokens,
             escalation_required, escalation_reason, decision_trace)
  Phase 8: multimodal fields (visual_context, image_modality,
           image_confidence, image_emergency_flag, image_emergency_reason)
  Phase 9: governance fields (review_required, review_id, review_status,
           reviewed_by, clinician_notes, approved_output)
  Phase 12: orchestration planner fields (clinical_intent, execution_plan,
            clarification_required, clarification_questions,
            clarification_answers, missing_information, patient_context),
            evidence evaluation fields (evidence_scores,
            evidence_quality_summary, contradiction_report),
            continuous monitoring fields (monitor_events, replan_count,
            replan_reasons)

State propagation strategy:
  - Each agent node returns a PARTIAL dict — only the keys it owns.
  - LangGraph merges these partials into the running state.
  - workflow_path uses Annotated[List, operator.add] so each node
    appends its name rather than overwriting the trace list.
  - All decision layer keys are strings (not enums) so they serialise
    cleanly into the API response without custom encoders.
  - confidence_threshold in state overrides the static config.py threshold,
    giving the decision layer full control over validation strictness.
"""
import operator
from typing import TypedDict, List, Dict, Any, Annotated, Optional


class AgentState(TypedDict):
    # ══════════════════════════════════════════════════════════════════════
    # INPUT
    # ══════════════════════════════════════════════════════════════════════
    query: str                     # may be acronym-expanded by QueryAgent

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 4.5 — DECISION LAYER OUTPUT
    # Written by: decision_agent (node 0)
    # Read by:    ALL downstream nodes to configure their behaviour
    # ══════════════════════════════════════════════════════════════════════

    # Classification
    query_type:              str       # primary WorkflowType value (e.g. "emergency")
    query_intent_confidence: float     # 0.0 – 1.0 classification certainty

    # Risk
    risk_level:              str       # RiskLevel value ("low"|"medium"|"high"|"critical")

    # Selected workflow
    selected_workflow:       str       # WorkflowType value

    # Retrieval configuration (read by RetrievalAgent)
    retrieval_strategy:      str       # RetrievalStrategy value
    source_priority:         str       # SourcePriority value
    context_budget_tokens:   int       # token limit for compressor

    # Validation configuration (read by ValidationAgent + SupervisorAgent)
    validation_policy:       str       # ValidationStrictness value
    confidence_threshold:    float     # dynamic threshold (overrides config.py default)

    # Reflection configuration (read by ReflectionAgent + SupervisorAgent)
    reflection_strategy:     str       # ReflectionStrategy value
    max_retries:             int       # dynamic max retries (overrides config.py default)

    # Escalation (read by SupervisorAgent + API layer)
    escalation_required:     bool
    escalation_reason:       str

    # Full decision trace (serialised into API response)
    decision_trace:          Dict[str, Any]

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 4 — QUERY UNDERSTANDING OUTPUT
    # Written by: query_agent (node 1)
    # ══════════════════════════════════════════════════════════════════════
    query_variants:          List[str]  # rewritten / HyDE / sub-queries
    query_plan:              List[str]  # retrieval strategy list from QueryAgent

    # ══════════════════════════════════════════════════════════════════════
    # RETRIEVAL LAYER
    # Written by: retrieval_agent (node 2)
    # ══════════════════════════════════════════════════════════════════════
    retrieved_docs:          List[Dict[str, Any]]  # hybrid-retrieved + reranked
    compressed_context:      str                   # token-budgeted evidence block
    graph_context:           str                   # Neo4j relational facts
    similar_cases_context:   str                   # episodic clinical memory
    live_research_context:   str                   # temporary PubMed evidence

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 8 — MULTIMODAL LAYER
    # Written by: image_ingestor (pre-retrieval node)
    # Read by:    retrieval_agent, reasoning_agent, validation_agent
    # ══════════════════════════════════════════════════════════════════════
    visual_context:          str                   # ECG / Radiology / OCR extracted findings
    image_modality:          str                   # Modality enum value
    image_confidence:        float                 # Pipeline analysis confidence
    image_emergency_flag:    bool                  # True if life-threatening pattern detected
    image_emergency_reason:  str                   # Human-readable emergency description

    # ══════════════════════════════════════════════════════════════════════
    # REASONING LAYER
    # Written by: reasoning_agent (node 3)
    # ══════════════════════════════════════════════════════════════════════
    reasoning_output:        str

    # ══════════════════════════════════════════════════════════════════════
    # VALIDATION LAYER
    # Written by: validation_agent (node 4)
    # ══════════════════════════════════════════════════════════════════════
    validation_score:        float
    validation_feedback:     str

    # ══════════════════════════════════════════════════════════════════════
    # REFLECTION / RETRY
    # Written by: reflection_agent, supervisor
    # ══════════════════════════════════════════════════════════════════════
    retry_count:             int
    reflection_notes:        str

    # ══════════════════════════════════════════════════════════════════════
    # OBSERVABILITY — append-only trace of nodes visited
    # ══════════════════════════════════════════════════════════════════════
    workflow_path:           Annotated[List[str], operator.add]

    # ══════════════════════════════════════════════════════════════════════
    # OUTPUT
    # ══════════════════════════════════════════════════════════════════════
    final_response:          Optional[str]
    error:                   Optional[str]

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 9 — HITL GOVERNANCE
    # Written by: finalize_response node (supervisor)
    # Read by:    API layer, governance dashboard
    # ══════════════════════════════════════════════════════════════════════
    review_required:         bool            # True → output held for review
    review_id:               Optional[str]   # UUID of ReviewRecord
    review_status:           str             # ReviewStatus value
    reviewed_by:             Optional[str]   # Clinician identifier
    clinician_notes:         Optional[str]   # Clinician review notes
    approved_output:         Optional[str]   # Final output after review

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 12 — ORCHESTRATION PLANNER
    # Written by: orchestration_planner (node 0, replaces decision_agent)
    # Read by:    graph.py routing, API layer, frontend
    # ══════════════════════════════════════════════════════════════════════
    clinical_intent:         str             # ClinicalIntent enum value (e.g. "emergency_triage")
    execution_plan:          Dict[str, Any]  # serialized ExecutionPlan (first-class object)
    clarification_required:  bool            # planner determined clarification needed
    clarification_questions: List[Dict[str, Any]]  # pending clarification questions
    clarification_answers:   Dict[str, str]  # submitted answers by clinician
    missing_information:     List[str]       # detected missing clinical elements
    patient_context:         Dict[str, Any]  # structured extracted patient data

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 12 — EVIDENCE EVALUATION LAYER
    # Written by: evidence_eval_node (after retrieval)
    # Read by:    reasoning_agent (uses filtered/scored docs),
    #             validation_agent (reads evidence_quality_summary),
    #             supervisor_agent (triggers re-plan if insufficient)
    # ══════════════════════════════════════════════════════════════════════
    evidence_scores:         List[Dict[str, Any]]  # per-source EvidenceScore dicts
    evidence_quality_summary: Dict[str, Any]       # EvidenceQualitySummary dict
    contradiction_report:    Optional[Dict[str, Any]]  # ContradictionReport dict

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 12 — CONTINUOUS SUPERVISOR MONITORING
    # Written by: evidence_eval, contradiction, supervisor nodes
    # Read by:    supervisor_router for proactive re-planning
    # ══════════════════════════════════════════════════════════════════════
    monitor_events:          List[Dict[str, Any]]  # monitoring events during execution
    replan_count:            int             # how many adaptive re-plans occurred
    replan_reasons:          List[str]       # reasons for each re-plan
    next_agent:              Optional[str]   # Phase 12+: Next agent selected by the dynamic LLM planner

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 13 — CONVERSATIONAL SESSIONS
    # ══════════════════════════════════════════════════════════════════════
    session_id:              Optional[str]
    conversation_history:    List[Dict[str, str]]  # list of past messages {"role": "user/assistant", "content": "..."}

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 14 — GUARDRAILS
    # Written by: agentic.py API layer (input) + finalize (output/clinical)
    # Read by:    API response, governance dashboard, audit logger
    # ══════════════════════════════════════════════════════════════════════
    guardrails_triggered:    List[str]       # list of guardrail IDs that fired
    guardrails_summary:      Optional[Dict[str, Any]]  # full guardrail report
    input_pii_found:         bool            # True if PII was scrubbed from input
    input_pii_types:         List[str]       # types of PII detected/removed
