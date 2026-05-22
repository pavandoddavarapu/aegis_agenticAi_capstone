"""
agentic.py — Agentic Analysis API Endpoint (Phase 13)

Phase 12 additions:
  - AnalyzeRequest: optional clarification_answers field
  - AnalyzeResponse: Phase 12 fields (clinical_intent, execution_plan_summary,
    clarification_required, clarification_questions, missing_information,
    evidence_quality_summary, contradiction_summary, replan_count)
  - New endpoint: POST /analyze/clarify — submit clarification answers
  - run_workflow() called with clarification_answers when provided

Phase 13 additions:
  - AnalyzeRequest: optional session_id field for conversational continuity
  - AnalyzeResponse: optional session_id field returned
  - Session state automatically updated after each successful analysis run
  - Backward compatible: session_id is fully optional

Backward compatible:
  - All Phase 3-9 response fields preserved
  - POST /analyze/ signature unchanged
  - New fields are Optional with safe defaults
"""
import time
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from backend.orchestration.graph import run_workflow, run_workflow_stream
from backend.utils.logger import logger
from backend.api.rate_limiter import limiter
from backend.session.session_store import session_store   # Phase 13


router = APIRouter(prefix="/analyze", tags=["agentic"])


# ── Request / Response Schemas ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Medical / clinical query or free-text patient case description.",
        examples=["65-year-old male with crushing chest pain radiating to left arm, BP 160/100, HR 95, history of hypertension and diabetes on Metformin..."],
    )
    # Phase 12: optional clarification answers
    clarification_answers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional: answers to clarification questions. Key=question_id, value=answer.",
    )
    # Phase 13: optional session ID for conversational continuity
    session_id: Optional[str] = Field(
        default=None,
        description="Optional: session ID for persistent multi-turn patient context.",
    )


class ClarifyRequest(BaseModel):
    """Request for the /analyze/clarify endpoint."""
    query: str = Field(..., min_length=1, max_length=8000)
    clarification_answers: Dict[str, str] = Field(
        ...,
        description="Answers to clarification questions. Key=question_id, value=answer.",
    )
    # Phase 13: optional session ID
    session_id: Optional[str] = Field(
        default=None,
        description="Optional: session ID for persistent multi-turn patient context.",
    )


class EvidenceItem(BaseModel):
    text:          str
    score:         float
    confidence:    str
    source:        str
    page:          int
    section:       Optional[str] = None
    document_type: str


class AnalyzeResponse(BaseModel):
    # ── Core output ───────────────────────────────────────────────────────────
    query:             str
    reasoning:         str
    final_response:    str

    # ── Phase 4: Query Understanding ────────────────────────────────────────
    query_type:        str
    query_variants:    List[str]
    query_plan:        List[str]

    # ── Evidence layer ────────────────────────────────────────────────────────
    evidence:          List[EvidenceItem]
    evidence_count:    int

    # ── Validation layer ──────────────────────────────────────────────────────
    confidence_score:  float
    confidence_label:  str
    validation_detail: str

    # ── Agentic metadata ──────────────────────────────────────────────────────
    workflow_trace:    List[str]
    retry_count:       int
    reflection_notes:  str
    processing_ms:     int

    # ── Status ───────────────────────────────────────────────────────────────
    status:            str
    error:             Optional[str] = None

    # ── Phase 9: Governance ──────────────────────────────────────────────────
    review_required:    bool         = False
    review_id:          Optional[str] = None
    review_status:      str          = "not_required"
    escalation_required: bool        = False

    # ── Phase 12: Orchestration Intelligence (all Optional for backward compat)
    clinical_intent:         str          = "unknown"
    execution_plan_summary:  Optional[Dict[str, Any]] = None
    clarification_required:  bool         = False
    clarification_questions: List[Dict[str, Any]] = Field(default_factory=list)
    missing_information:     List[str]    = Field(default_factory=list)
    evidence_quality_summary: Optional[Dict[str, Any]] = None
    contradiction_summary:   Optional[Dict[str, Any]] = None
    replan_count:            int          = 0
    patient_context:         Optional[Dict[str, Any]] = None
    monitor_events:          List[Dict[str, Any]] = Field(default_factory=list)
    # Phase 13: session ID echo
    session_id:              Optional[str] = None
    trace_summary:           Optional[Dict[str, Any]] = None


# ── Helper ─────────────────────────────────────────────────────────────────────

def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.60:
        return "MEDIUM"
    return "LOW"


def _build_response(query: str, final_state: dict, elapsed_ms: int) -> AnalyzeResponse:
    """Build AnalyzeResponse from final workflow state."""

    # ── Phase 1-9 fields ─────────────────────────────────────────────────────
    reasoning         = final_state.get("reasoning_output", "")
    final_response    = final_state.get("final_response", "")
    docs              = final_state.get("retrieved_docs", [])
    score             = final_state.get("validation_score", 0.0)
    validation_detail = final_state.get("validation_feedback", "")
    workflow_trace    = final_state.get("workflow_path", [])
    retry_count       = final_state.get("retry_count", 0)
    reflection_notes  = final_state.get("reflection_notes", "")
    error             = final_state.get("error")
    query_type        = final_state.get("query_type", "unknown")
    query_variants    = final_state.get("query_variants", [])
    query_plan        = final_state.get("query_plan", [])
    review_required   = final_state.get("review_required", False)
    review_id         = final_state.get("review_id")
    review_status     = final_state.get("review_status", "not_required")
    escalation_req    = final_state.get("escalation_required", False)

    # ── Phase 12 fields ───────────────────────────────────────────────────────
    clinical_intent    = final_state.get("clinical_intent", "unknown")
    exec_plan          = final_state.get("execution_plan", {})
    clarification_req  = final_state.get("clarification_required", False)
    clarif_questions   = final_state.get("clarification_questions", [])
    missing_info       = final_state.get("missing_information", [])
    ev_quality         = final_state.get("evidence_quality_summary", {}) or {}
    contradiction_rep  = final_state.get("contradiction_report") or {}
    replan_count       = final_state.get("replan_count", 0)
    patient_ctx        = final_state.get("patient_context", {}) or {}
    monitor_events     = final_state.get("monitor_events", [])

    # ExecutionPlan summary (exclude _full for API cleanliness)
    plan_summary = {k: v for k, v in exec_plan.items() if k != "_full"} if exec_plan else None

    # Contradiction summary (compact)
    contradiction_summary = None
    if contradiction_rep:
        contradiction_summary = {
            "has_contradictions": contradiction_rep.get("has_contradictions", False),
            "overall_severity":   contradiction_rep.get("overall_severity", "none"),
            "total_penalty":      contradiction_rep.get("total_penalty", 0.0),
            "escalation_required": contradiction_rep.get("escalation_required", False),
            "summary":            contradiction_rep.get("summary", ""),
            "contradiction_count": contradiction_rep.get("contradiction_count", 0),
        }

    # Build evidence items
    evidence = [
        EvidenceItem(
            text          = d.get("text", ""),
            score         = d.get("score", 0),
            confidence    = d.get("confidence", "unknown"),
            source        = d.get("source", "unknown"),
            page          = d.get("page", 0),
            section       = d.get("section"),
            document_type = d.get("document_type", "medical_report"),
        )
        for d in docs
    ]

    # Determine status — Phase 12: clarification_required gets its own status
    if clarification_req:
        status = "clarification_required"
    elif error and not reasoning:
        status = "error"
    elif score < 0.60:
        status = "partial"
    else:
        status = "success"

    return AnalyzeResponse(
        query             = query,
        reasoning         = reasoning,
        final_response    = final_response or reasoning,
        query_type        = query_type,
        query_variants    = query_variants,
        query_plan        = query_plan,
        evidence          = evidence,
        evidence_count    = len(evidence),
        confidence_score  = round(score, 4),
        confidence_label  = _confidence_label(score),
        validation_detail = validation_detail,
        workflow_trace    = workflow_trace,
        retry_count       = retry_count,
        reflection_notes  = reflection_notes,
        processing_ms     = elapsed_ms,
        status            = status,
        error             = error,
        # Phase 9: Governance
        review_required      = review_required,
        review_id            = review_id,
        review_status        = review_status,
        escalation_required  = escalation_req,
        # Phase 12: Orchestration Intelligence
        clinical_intent          = clinical_intent,
        execution_plan_summary   = plan_summary,
        clarification_required   = clarification_req,
        clarification_questions  = clarif_questions,
        missing_information      = missing_info,
        evidence_quality_summary = ev_quality if ev_quality else None,
        contradiction_summary    = contradiction_summary,
        replan_count             = replan_count,
        patient_context          = patient_ctx if patient_ctx else None,
        monitor_events           = monitor_events,
        trace_summary            = final_state.get("_trace_summary"),
        # session_id is injected by the endpoint, not here
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/", response_model=AnalyzeResponse, summary="Agentic Clinical Analysis (Phase 13)")
@limiter.limit("30/minute")
async def analyze(
    request: Request,
    body: AnalyzeRequest,
) -> AnalyzeResponse:
    """
    Run the full adaptive evidence-aware agentic clinical analysis workflow.

    Phase 12 Workflow:
      1. OrchestrationPlanner  — understand clinical intent + check information sufficiency
      2. [Clarification Gate]  — if information insufficient, return questions (status=clarification_required)
      3. QueryAgent            — query understanding + expansion
      4. RetrievalAgent        — graph + semantic + research + multimodal retrieval
      5. EvidenceEvaluator     — quality-score every evidence source
      6. ContradictionAnalyzer — detect conflicts between evidence sources
      7. ReasoningAgent        — grounded clinical synthesis
      8. ValidationAgent       — confidence scoring + grounding check
      9. [Supervisor Monitor]  — proactive re-planning if evidence quality drops
      10. Finalize             — HITL governance + audit

    Phase 13 additions:
      - session_id: optional persistent session for multi-turn continuity
      - Session state updated automatically after each successful run

    If the response has status='clarification_required':
      - clarification_questions contains targeted questions
      - Call POST /analyze/clarify with the answers to continue
    """
    query = body.query.strip()
    clarification_answers = body.clarification_answers or {}
    session_id = body.session_id

    logger.info(
        f"[AnalyzeAPI] Received query: '{query[:80]}' "
        f"clarification_answers={bool(clarification_answers)} "
        f"session_id={session_id}"
    )

    start_ms = time.time()

    try:
        final_state = await run_workflow(
            query                  = query,
            session_id             = session_id,
            clarification_answers  = clarification_answers if clarification_answers else None,
        )
        elapsed_ms = int((time.time() - start_ms) * 1000)

        response = _build_response(query, final_state, elapsed_ms)
        response.session_id = session_id  # echo session_id back

        # ── Phase 13: Update session state if session_id provided ──────────────────
        if session_id:
            session = session_store.get(session_id)
            if session:
                session.add_message("user",      query,                    message_type="text")
                session.add_message("assistant",  response.final_response,  message_type="report", metadata={"result": response.dict()})
                session.update_from_analysis(final_state)
                session_store.update(session)
                logger.info(f"[AnalyzeAPI] Updated session {session_id} (turn {session.turn_count})")

        logger.info(
            f"[AnalyzeAPI] Done. status={response.status} "
            f"confidence={response.confidence_score:.3f} "
            f"intent={response.clinical_intent} "
            f"clarification={response.clarification_required} "
            f"elapsed={elapsed_ms}ms"
        )
        return response

    except Exception as exc:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        logger.exception(f"[AnalyzeAPI] Unhandled error: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error":       str(exc),
                "query":       query,
                "elapsed_ms":  elapsed_ms,
                "message":     "Agentic workflow encountered an unhandled error.",
            },
        )


@router.post("/clarify/", response_model=AnalyzeResponse, summary="Submit Clarification Answers")
@limiter.limit("30/minute")
async def analyze_with_clarification(
    request: Request,
    body: ClarifyRequest,
) -> AnalyzeResponse:
    """
    Phase 12: Submit clarification answers and continue analysis.

    Use this endpoint when POST /analyze/ returns:
      status = 'clarification_required'

    Steps:
      1. POST /analyze/ — get clarification_questions
      2. Clinician fills in answers (question_id → answer_text)
      3. POST /analyze/clarify/ — system proceeds with enriched context

    The clarification_answers are merged into the query as structured context,
    and the workflow proceeds to execution (bypassing the clarification gate).
    """
    from backend.decision.clarification_engine import resolve_clarification
    from backend.decision.execution_plan import ClarificationQuestion, QuestionCategory, QuestionPriority

    query = body.query.strip()
    answers = body.clarification_answers
    session_id = body.session_id

    logger.info(
        f"[ClarifyAPI] Received clarification: query='{query[:60]}' "
        f"num_answers={len(answers)} session_id={session_id}"
    )

    start_ms = time.time()

    try:
        # Run workflow with clarification answers pre-loaded
        final_state = await run_workflow(
            query                 = query,
            session_id            = session_id,
            clarification_answers = answers,
        )
        elapsed_ms = int((time.time() - start_ms) * 1000)

        response = _build_response(query, final_state, elapsed_ms)
        response.session_id = session_id  # echo session_id back

        # ── Phase 13: Update session state if session_id provided ──────────────────
        if session_id:
            session = session_store.get(session_id)
            if session:
                session.add_message("user", f"Provided clarification: {answers}", message_type="text")
                session.add_message("assistant", response.final_response, message_type="report", metadata={"result": response.dict()})
                session.update_from_analysis(final_state)
                session_store.update(session)
                logger.info(f"[ClarifyAPI] Updated session {session_id} after clarification (turn {session.turn_count})")

        logger.info(
            f"[ClarifyAPI] Done. status={response.status} "
            f"confidence={response.confidence_score:.3f} "
            f"elapsed={elapsed_ms}ms"
        )
        return response

    except Exception as exc:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        logger.exception(f"[ClarifyAPI] Unhandled error: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error":       str(exc),
                "query":       query,
                "elapsed_ms":  elapsed_ms,
                "message":     "Clarification workflow encountered an unhandled error.",
            },
        )


NODE_STAGE_MESSAGES = {
    "plan": "🧠 Planning execution strategy...",
    "clarify": "❓ Waiting for clinical clarification...",
    "query_understand": "🔍 Analyzing query intent & expanding vocabulary...",
    "retrieve": "📂 Retrieving from GraphRAG, dense semantic vectors, and literature databases...",
    "evidence_eval": "📊 Evaluating evidence quality & freshness...",
    "contradiction_check": "⚖️ Checking evidence for cross-source contradictions...",
    "reason": "📝 Synthesizing clinical reasoning report...",
    "validate": "🩺 Validating output safety & grounding...",
    "reflect": "🔄 Reflecting on feedback and initiating adaptive replan...",
    "finalize": "🛡️ Applying governance review & audit logging...",
}


@router.post("/stream/", summary="Streaming Agentic Analysis (Phase 13D)")
@limiter.limit("30/minute")
async def analyze_stream(
    request: Request,
    body: AnalyzeRequest,
):
    """
    Run the agentic workflow and stream progress events + final result via Server-Sent Events (SSE).
    """
    query = body.query.strip()
    clarification_answers = body.clarification_answers or {}
    session_id = body.session_id

    logger.info(
        f"[AnalyzeStreamAPI] Received query: '{query[:80]}' "
        f"clarification_answers={bool(clarification_answers)} "
        f"session_id={session_id}"
    )

    async def sse_generator():
        start_ms = time.time()
        try:
            async for chunk in run_workflow_stream(
                query=query,
                session_id=session_id,
                clarification_answers=clarification_answers if clarification_answers else None,
            ):
                event_type = chunk["event"]
                if event_type == "stage":
                    node = chunk["node"]
                    msg = NODE_STAGE_MESSAGES.get(node, f"Executing {node} stage...")
                    payload = {"event": "stage", "node": node, "message": msg}
                    yield f"data: {json.dumps(payload)}\n\n"
                elif event_type == "complete":
                    final_state = chunk["state"]
                    elapsed_ms = int((time.time() - start_ms) * 1000)
                    response = _build_response(query, final_state, elapsed_ms)
                    response.session_id = session_id

                    # ── Update session state if session_id provided ──
                    if session_id:
                        session = session_store.get(session_id)
                        if session:
                            session.add_message("user", query, message_type="text")
                            session.add_message("assistant", response.final_response, message_type="report", metadata={"result": response.dict()})
                            session.update_from_analysis(final_state)
                            session_store.update(session)
                            logger.info(f"[AnalyzeStreamAPI] Updated session {session_id} (turn {session.turn_count})")

                    # Yield complete event with dict representation of response
                    payload = {"event": "complete", "result": response.dict()}
                    yield f"data: {json.dumps(payload)}\n\n"
        except Exception as exc:
            logger.exception(f"[AnalyzeStreamAPI] Error during streaming: {exc}")
            err_payload = {"event": "error", "message": str(exc)}
            yield f"data: {json.dumps(err_payload)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
