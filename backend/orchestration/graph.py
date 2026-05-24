"""
graph.py — Adaptive Evidence-Aware Orchestration Graph (Phase 12)

Phase 12 upgrades:
  - NODE_DECIDE replaced by NODE_PLAN (OrchestrationPlanner)
  - NODE_CLARIFY added: handles pre-execution clarification loop
  - NODE_EVID_EVAL added: evidence quality scoring (EvidenceEvaluator)
  - NODE_CONTRADICT added: contradiction detection (ContradictionAnalyzer)
  - Conditional routing from planner: clarify OR query_understand
  - Continuous supervisor monitoring via evidence quality signals
  - All Phase 5/9/11 observability, governance, telemetry PRESERVED

Graph topology:
  plan
    ↓ [_plan_router]
    ├── clarify → plan (loop with answers, max 3 iter)
    └── query_understand
              ↓
           retrieve
              ↓
           evidence_eval        [NEW Phase 12]
              ↓
           contradiction_check  [NEW Phase 12]
              ↓
           reason
              ↓
           validate
              ↓
           [supervisor_router]
              ├── reflect → retrieve (re-enters, as before)
              └── end    → finalize (governance + HITL preserved)

Backward compat:
  - All existing node names kept (query_understand, retrieve, reason,
    validate, reflect, finalize)
  - All state field reads by existing agents unchanged
  - OrchestrationPlanner writes all Phase 4.5 fields identically
"""
import uuid
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END

from backend.models.state               import AgentState
from backend.agents.orchestration_planner import orchestration_planner   # Phase 12
from backend.agents.query_agent         import query_agent
from backend.agents.retrieval_agent     import retrieval_agent
from backend.agents.reasoning_agent     import reasoning_agent
from backend.agents.validation_agent    import validation_agent
from backend.agents.reflection_agent    import reflection_agent
from backend.agents.supervisor_agent    import (
    supervisor_router,
    finalize_response,
    ROUTE_REFLECT,
    ROUTE_END,
)
from backend.telemetry.orchestration_trace import OrchestrationTrace
from backend.utils.logger import logger


# ── Node name constants ───────────────────────────────────────────────────────
NODE_PLAN      = "plan"              # Phase 12: OrchestrationPlanner (replaces "decide")
NODE_CLARIFY   = "clarify"           # Phase 12: Clarification loop
NODE_QUERY     = "query_understand"
NODE_RETRIEVE  = "retrieve"
NODE_RESEARCH  = "research"          # NEW Phase 13: Live internet research
NODE_EVID_EVAL = "evidence_eval"     # Phase 12: EvidenceEvaluator
NODE_CONTRADICT = "contradiction_check"  # Phase 12: ContradictionAnalyzer
NODE_REASON    = "reason"
NODE_VALIDATE  = "validate"
NODE_REFLECT   = "reflect"
NODE_FINALIZE  = "finalize"

# Routing constants for plan_router
ROUTE_CLARIFY          = "clarify"
ROUTE_QUERY_UNDERSTAND = "query_understand"
ROUTE_BYPASS           = "route_bypass"


# ═════════════════════════════════════════════════════════════════════════════
# Phase 12 New Agent Node Functions
# ═════════════════════════════════════════════════════════════════════════════

def clarification_node(state: AgentState) -> dict:
    """
    Clarification node — presents questions to the caller.

    In the API context this node marks the workflow as requiring clarification.
    The API layer reads clarification_required + clarification_questions and
    returns them to the frontend/caller. The caller submits answers via
    POST /analyze/clarify, which re-runs with clarification_answers filled.

    Within the graph, this node simply marks questions as pending and
    marks clarification_resolved=False so the planner re-routes to
    query_understand on the next iteration (with answers).
    """
    questions = state.get("clarification_questions", [])
    logger.info(
        f"[ClarificationNode] {len(questions)} clarification questions pending."
    )

    # In single-pass mode: if we reach here, questions are already set.
    # We mark as NOT resolved — the graph will exit here and the API
    # returns the questions to the caller.
    # On re-submission with answers, planner routes to query_understand directly.
    return {
        "clarification_required": True,
        "workflow_path": [NODE_CLARIFY],
        # Signal the API that we stopped at clarification
        "final_response": None,
        "error": None,
    }


async def research_node(state: AgentState) -> dict:
    """
    Executes live internet research in parallel with static retrieval.
    """
    from backend.research.research_agent import ResearchAgent
    
    query = state.get("query", "")
    logger.info(f"[ResearchNode] Starting live research for query: {query}")
    
    agent = ResearchAgent()
    # Can use strict_rct if required by intent, but default to False
    research_context = await agent.run_research(query, strict_rct=False)
    
    return {
        "live_research_context": research_context,
        "workflow_path": [NODE_RESEARCH],
    }


async def evidence_eval_node(state: AgentState) -> dict:
    """
    Evidence Evaluation node — scores all retrieved sources.

    Runs AFTER retrieval, BEFORE reasoning.
    Annotates docs with quality scores and produces EvidenceQualitySummary.
    Low-quality sources (overall_quality < 0.30) are flagged for exclusion.

    Reads:  retrieved_docs, graph_context, live_research_context,
            similar_cases_context, visual_context, image_confidence
    Writes: evidence_scores, evidence_quality_summary
    """
    from backend.evaluation.evidence_evaluator import (
        evaluate_evidence, evidence_scores_to_dict_list
    )

    docs              = state.get("retrieved_docs", [])
    graph_ctx         = state.get("graph_context", "")
    research_ctx      = state.get("live_research_context", "")
    visual_ctx        = state.get("visual_context", "")
    similar_ctx       = state.get("similar_cases_context", "")
    image_confidence  = state.get("image_confidence", 1.0)
    image_modality    = state.get("image_modality", "unknown")
    query             = state.get("query", "")

    logger.info(
        f"[EvidenceEvalNode] Evaluating {len(docs)} docs + "
        f"graph={'yes' if graph_ctx else 'no'} "
        f"research={'yes' if research_ctx else 'no'} "
        f"visual={'yes' if visual_ctx else 'no'}"
    )

    try:
        scores, summary = evaluate_evidence(
            docs             = docs,
            query            = query,
            graph_context    = graph_ctx,
            research_context = research_ctx,
            visual_context   = visual_ctx,
            image_confidence = image_confidence,
            image_modality   = image_modality,
            similar_cases    = similar_ctx,
        )

        scores_dict = evidence_scores_to_dict_list(scores)
        summary_dict = summary.to_dict()

        # Emit monitoring event
        monitor_events = list(state.get("monitor_events", []))
        monitor_events.append({
            "checkpoint": "evidence_eval",
            "overall_sufficiency": summary.overall_sufficiency,
            "avg_quality": summary.avg_quality,
            "filtered_count": summary.filtered_count,
        })

        return {
            "evidence_scores":          scores_dict,
            "evidence_quality_summary": summary_dict,
            "monitor_events":           monitor_events,
            "workflow_path":            [NODE_EVID_EVAL],
        }

    except Exception as exc:
        logger.exception(f"[EvidenceEvalNode] Failed: {exc}")
        return {
            "evidence_scores":          [],
            "evidence_quality_summary": {"overall_sufficiency": "unknown", "avg_quality": 0.0},
            "workflow_path":            [NODE_EVID_EVAL],
        }


async def contradiction_check_node(state: AgentState) -> dict:
    """
    Contradiction Analysis node — detects conflicts between evidence sources.

    Runs AFTER evidence_eval, BEFORE reasoning.
    Detects drug recommendation conflicts, diagnostic conflicts,
    multimodal vs textual conflicts.
    Applies confidence penalty to final score if contradictions found.

    Reads:  retrieved_docs, evidence_scores, graph_context, etc.
    Writes: contradiction_report
    """
    from backend.evaluation.contradiction_analyzer import analyze_contradictions

    docs              = state.get("retrieved_docs", [])
    graph_ctx         = state.get("graph_context", "")
    research_ctx      = state.get("live_research_context", "")
    visual_ctx        = state.get("visual_context", "")
    evidence_scores   = state.get("evidence_scores", [])

    logger.info(f"[ContradictionNode] Analyzing {len(docs)} docs for contradictions.")

    try:
        # Convert evidence_scores dicts back to light objects for trust lookup
        class _EvidenceScoreLite:
            def __init__(self, d: Dict[str, Any]):
                self.source_id   = d.get("source_id", "")
                self.trust_score = d.get("trust_score", 0.70)

        ev_objects = [_EvidenceScoreLite(d) for d in evidence_scores]

        report = analyze_contradictions(
            docs             = docs,
            evidence_scores  = ev_objects,
            graph_context    = graph_ctx,
            research_context = research_ctx,
            visual_context   = visual_ctx,
        )
        report_dict = report.to_dict()

        # Emit monitoring event
        monitor_events = list(state.get("monitor_events", []))
        monitor_events.append({
            "checkpoint":    "contradiction_check",
            "has_contradictions": report.has_contradictions,
            "severity":      report.overall_severity,
            "penalty":       report.total_penalty,
            "escalate":      report.escalation_required,
        })

        # If contradiction requires escalation, trigger it
        current_escalation = state.get("escalation_required", False)
        new_escalation = current_escalation or report.escalation_required
        new_reason = state.get("escalation_reason", "")
        if report.escalation_required and not current_escalation:
            new_reason = (
                new_reason + " | " if new_reason else ""
            ) + f"Critical contradiction: {report.summary}"

        return {
            "contradiction_report":  report_dict,
            "monitor_events":        monitor_events,
            "escalation_required":   new_escalation,
            "escalation_reason":     new_reason,
            "workflow_path":         [NODE_CONTRADICT],
        }

    except Exception as exc:
        logger.exception(f"[ContradictionNode] Failed: {exc}")
        return {
            "contradiction_report": {"has_contradictions": False, "overall_severity": "none"},
            "workflow_path":        [NODE_CONTRADICT],
        }


# ═════════════════════════════════════════════════════════════════════════════
# Routing Functions
# ═════════════════════════════════════════════════════════════════════════════

def _plan_router(state: AgentState) -> str:
    """
    Conditional edge from plan node.
    Routes to the agent specified in state["next_agent"].
    """
    trace = state.get("_trace")
    next_agent = state.get("next_agent")
    
    if not next_agent:
        # Fallback to finalize if next_agent is somehow missing
        next_agent = "finalize"
        
    logger.info(f"[PlanRouter] → {next_agent}")
    if trace:
        trace.record_routing(decision=next_agent, reason=f"Orchestrator selected next step: {next_agent}", score=1.0)
        
    return next_agent


# ═════════════════════════════════════════════════════════════════════════════
# Graph Builder
# ═════════════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    logger.info("[Graph] Building Aegis Phase 12 adaptive evidence-aware workflow...")

    from backend.telemetry.agent_telemetry import instrument_agent

    graph = StateGraph(AgentState)

    # ── Register all nodes ────────────────────────────────────────────────────
    # Phase 12 new nodes
    graph.add_node(NODE_PLAN,       instrument_agent(NODE_PLAN)(orchestration_planner))
    graph.add_node(NODE_CLARIFY,    instrument_agent(NODE_CLARIFY)(clarification_node))
    graph.add_node(NODE_EVID_EVAL,  instrument_agent(NODE_EVID_EVAL)(evidence_eval_node))
    graph.add_node(NODE_CONTRADICT, instrument_agent(NODE_CONTRADICT)(contradiction_check_node))
    # Existing nodes (preserved)
    graph.add_node(NODE_QUERY,      instrument_agent(NODE_QUERY)(query_agent))
    graph.add_node(NODE_RETRIEVE,   instrument_agent(NODE_RETRIEVE)(retrieval_agent))
    graph.add_node(NODE_RESEARCH,   instrument_agent(NODE_RESEARCH)(research_node))
    graph.add_node(NODE_REASON,     instrument_agent(NODE_REASON)(reasoning_agent))
    graph.add_node(NODE_VALIDATE,   instrument_agent(NODE_VALIDATE)(validation_agent))
    graph.add_node(NODE_REFLECT,    instrument_agent(NODE_REFLECT)(reflection_agent))
    graph.add_node(NODE_FINALIZE,   instrument_agent(NODE_FINALIZE)(finalize_response))

    # ── Entry point: OrchestrationPlanner runs first ──────────────────────────
    graph.set_entry_point(NODE_PLAN)

    # ── Conditional: planner routes dynamically to the selected next agent ────
    graph.add_conditional_edges(
        NODE_PLAN,
        _plan_router,
        {
            "clarify":             NODE_CLARIFY,
            "query_understand":    NODE_QUERY,
            "retrieve":            NODE_RETRIEVE,
            "research":            NODE_RESEARCH,
            "evidence_eval":       NODE_EVID_EVAL,
            "contradiction_check": NODE_CONTRADICT,
            "reason":              NODE_REASON,
            "validate":            NODE_VALIDATE,
            "reflect":             NODE_REFLECT,
            "finalize":            NODE_FINALIZE,
        },
    )

    # ── Clarification node → finalize (stops and returns questions to API) ────
    # When clarification is needed, the workflow stops at clarify and the API
    # returns the questions. Re-submission with answers bypasses clarification.
    graph.add_edge(NODE_CLARIFY, END)

    # ── Spoke nodes: Route back to the HUB (NODE_PLAN) after execution ────────
    graph.add_edge(NODE_QUERY,      NODE_PLAN)
    graph.add_edge(NODE_RETRIEVE,   NODE_PLAN)
    graph.add_edge(NODE_RESEARCH,   NODE_PLAN)
    graph.add_edge(NODE_EVID_EVAL,  NODE_PLAN)
    graph.add_edge(NODE_CONTRADICT, NODE_PLAN)
    graph.add_edge(NODE_REASON,     NODE_PLAN)
    graph.add_edge(NODE_VALIDATE,   NODE_PLAN)
    graph.add_edge(NODE_REFLECT,    NODE_PLAN)

    # ── Finalize → END ────────────────────────────────────────────────────────
    graph.add_edge(NODE_FINALIZE, END)

    compiled = graph.compile()
    logger.info("[Graph] Phase 12 adaptive evidence-aware workflow compiled successfully.")
    return compiled


# ── Singleton compiled graph ──────────────────────────────────────────────────
aegis_graph = build_graph()


# ═════════════════════════════════════════════════════════════════════════════
# Initial State Factory
# ═════════════════════════════════════════════════════════════════════════════

def _initial_state(
    query: str,
    request_id: str,
    trace: OrchestrationTrace,
    session_id: str | None = None,
) -> AgentState:
    """Return a fully-initialised AgentState for a new request."""
    patient_context_dict = {}
    history_list = []

    if session_id:
        try:
            from backend.session.session_store import session_store
            session = session_store.get(session_id)
            if session:
                apc = session.patient_context
                if apc:
                    patient_context_dict = {
                        "age": apc.age,
                        "gender": apc.gender,
                        "chief_complaint": apc.chief_complaint,
                        "symptom_duration": None,
                        "vitals_present": bool(apc.vitals),
                        "medications_present": bool(apc.medications),
                        "allergies_present": bool(apc.allergies),
                        "history_present": bool(apc.extracted_conditions),
                        "ecg_present": bool(apc.ecg_findings),
                        "labs_present": bool(apc.lab_values),
                        "imaging_present": bool(apc.imaging_findings),
                        "extracted_conditions": list(apc.extracted_conditions),
                        "extracted_medications": list(apc.medications),
                        "extracted_vitals": dict(apc.vitals),
                    }
                history_list = session.get_recent_history()
                logger.info(
                    f"[Graph] Loaded context from session {session_id}: "
                    f"conditions={len(apc.extracted_conditions)}, history={len(history_list)}"
                )
        except Exception as exc:
            logger.warning(f"[Graph] Error loading session {session_id} for initial state: {exc}")

    return {
        # ── Internal telemetry context (not serialised to API) ────────────────
        "_request_id":             request_id,
        "_trace":                  trace,
        # ── Input ────────────────────────────────────────────────────────────
        "query":                   query,
        # ── Phase 4.5 decision fields ─────────────────────────────────────────
        "query_type":              "",
        "query_intent_confidence": 0.0,
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
        # ── Phase 4 query understanding ───────────────────────────────────────
        "query_variants":          [],
        "query_plan":              [],
        # ── Retrieval ─────────────────────────────────────────────────────────
        "retrieved_docs":          [],
        "compressed_context":      "",
        "graph_context":           "",
        "similar_cases_context":   "",
        "live_research_context":   "",
        # ── Multimodal ────────────────────────────────────────────────────────
        "visual_context":          "",
        "image_modality":          "unknown",
        "image_confidence":        1.0,
        "image_emergency_flag":    False,
        "image_emergency_reason":  "",
        # ── Reasoning ────────────────────────────────────────────────────────
        "reasoning_output":        "",
        # ── Validation ───────────────────────────────────────────────────────
        "validation_score":        None,   # None = not yet validated; float = scored
        "validation_feedback":     "",
        # ── Reflection ───────────────────────────────────────────────────────
        "retry_count":             0,
        "reflection_notes":        "",
        # ── Observability ─────────────────────────────────────────────────────
        "workflow_path":           [],
        # ── Output ───────────────────────────────────────────────────────────
        "final_response":          None,
        "error":                   None,
        # ── Phase 9: Governance ───────────────────────────────────────────────
        "review_required":         False,
        "review_id":               None,
        "review_status":           "not_required",
        "reviewed_by":             None,
        "clinician_notes":         None,
        "approved_output":         None,
        # ── Phase 12: Orchestration Planner ───────────────────────────────────
        "clinical_intent":         "unknown",
        "execution_plan":          {},
        "clarification_required":  False,
        "clarification_questions": [],
        "clarification_answers":   {},
        "missing_information":     [],
        "patient_context":         patient_context_dict,
        # ── Phase 12: Evidence Evaluation ────────────────────────────────────
        "evidence_scores":         [],
        "evidence_quality_summary": {},
        "contradiction_report":    None,
        # ── Phase 12: Continuous Monitoring ──────────────────────────────────
        "monitor_events":          [],
        "replan_count":            0,
        "replan_reasons":          [],
        # ── Phase 13: Conversational Sessions ─────────────────────────────────
        "session_id":              session_id,
        "conversation_history":    history_list,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Workflow Runner
# ═════════════════════════════════════════════════════════════════════════════

async def run_workflow(
    query: str,
    session_id: str | None = None,
    clarification_answers: Dict[str, str] | None = None,
) -> AgentState:
    """
    Execute the full Phase 12 adaptive evidence-aware agentic workflow.

    Phase 12 adds:
      - OrchestrationPlanner as entry node (replaces DecisionAgent)
      - Pre-execution information sufficiency check
      - Clarification loop if needed (graph exits at clarify node)
      - EvidenceEvaluator after retrieval
      - ContradictionAnalyzer before reasoning
      - Continuous supervisor monitoring events

    Phase 13 adds:
      - session_id continuity parameter to load context & history

    Args:
        query:                  The clinical query / patient case.
        session_id:             Optional conversational session ID.
        clarification_answers:  If provided, bypasses clarification routing.

    Returns:
        Final AgentState with all outputs.
    """
    request_id = str(uuid.uuid4())
    stub_plan   = {"query_type": "", "selected_workflow": "",
                   "risk_level": "", "confidence_threshold": 0.72}
    trace       = OrchestrationTrace(request_id, query, stub_plan)
    trace.start()

    state = _initial_state(query, request_id, trace, session_id=session_id)

    # Inject clarification answers if provided (enables bypassing clarification)
    if clarification_answers:
        state["clarification_answers"] = clarification_answers

    logger.info(
        f"[Graph] Starting Phase 12/13 workflow: id={request_id} "
        f"session_id={session_id} query='{query[:80]}'"
    )

    final = await aegis_graph.ainvoke(state)

    # Finalise trace
    trace_summary = trace.finalise(final)
    final["_trace_summary"] = trace_summary
    final["_request_id"]    = request_id

    logger.info(
        f"[Graph] Workflow complete. id={request_id} "
        f"path={final.get('workflow_path')} | "
        f"intent={final.get('clinical_intent', 'unknown')} | "
        f"risk={final.get('risk_level')} | "
        f"evidence_sufficiency={(final.get('evidence_quality_summary') or {}).get('overall_sufficiency', 'n/a')} | "
        f"contradictions={(final.get('contradiction_report') or {}).get('has_contradictions', False)} | "
        f"confidence={(final.get('validation_score') or 0.0):.3f} | "
        f"clarification_required={final.get('clarification_required', False)} | "
        f"total_ms={trace_summary.get('total_ms')}"
    )
    return final


async def run_workflow_stream(
    query: str,
    session_id: str | None = None,
    clarification_answers: Dict[str, str] | None = None,
):
    """
    Stream the execution of the Phase 12/13 agentic workflow.
    Yields dictionary events:
      - {"event": "stage", "node": str}
      - {"event": "complete", "state": AgentState}
    """
    request_id = str(uuid.uuid4())
    stub_plan   = {"query_type": "", "selected_workflow": "",
                   "risk_level": "", "confidence_threshold": 0.72}
    trace       = OrchestrationTrace(request_id, query, stub_plan)
    trace.start()

    state = _initial_state(query, request_id, trace, session_id=session_id)

    if clarification_answers:
        state["clarification_answers"] = clarification_answers

    logger.info(
        f"[Graph] Starting streaming Phase 12/13 workflow: id={request_id} "
        f"session_id={session_id} query='{query[:80]}'"
    )

    final_state = state
    async for event in aegis_graph.astream(state):
        if not event:
            continue
        node_name = list(event.keys())[0]
        yield {"event": "stage", "node": node_name}
        
        # Merge the node output
        node_output = event[node_name]
        for k, v in node_output.items():
            if k == "workflow_path":
                final_state["workflow_path"] = list(final_state.get("workflow_path", [])) + v
            else:
                final_state[k] = v

    # Finalise trace
    trace_summary = trace.finalise(final_state)
    final_state["_trace_summary"] = trace_summary
    final_state["_request_id"]    = request_id

    logger.info(f"[Graph] Streaming workflow complete. id={request_id}")
    yield {"event": "complete", "state": final_state}
