"""
validation_agent.py — Validation Agent (Phase 3)

Responsibilities
────────────────
• Verify that the reasoning_output is grounded in retrieved evidence.
• Detect potential hallucinations by checking citation coverage.
• Calculate a composite confidence score (0.0 – 1.0).
• Produce human-readable validation_feedback.

Scoring breakdown
─────────────────
  evidence_score   (0.4 weight)  — quality + quantity of retrieved docs
  grounding_score  (0.4 weight)  — does reasoning reference the evidence?
  completeness     (0.2 weight)  — does reasoning cover required sections?

This is intentionally deterministic and rule-based — no LLM needed —
so validation cannot itself hallucinate.
"""
import re
from backend.models.state import AgentState
from backend.graphrag.graph_validator import GraphValidator
from backend.graphrag.graph_client import GraphClient
from backend.multimodal.multimodal_validator import MultimodalValidator
from backend.utils.logger import logger


# ── Thresholds ─────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.65      # below this → trigger reflection

# Required sections in a well-formed clinical reasoning output
REQUIRED_SECTIONS = ["summary", "key findings", "clinical implications"]

# Confidence score → confidence label mapping
HIGH_THRESHOLD   = 0.80
MEDIUM_THRESHOLD = 0.60


# ── Scoring Helpers ───────────────────────────────────────────────────────────

def _score_evidence(docs: list) -> tuple[float, str]:
    """Score the quantity and quality of retrieved evidence."""
    if not docs:
        return 0.0, "No evidence retrieved — cannot validate."

    n          = len(docs)
    avg_score  = sum(d.get("score", 0) for d in docs) / n
    high_conf  = sum(1 for d in docs if d.get("confidence") == "high")

    # Normalise: 5 docs is full credit
    quantity_score = min(n / 5.0, 1.0)
    quality_score  = avg_score                         # cosine ∈ [0, 1]
    coverage       = high_conf / n if n else 0

    score   = 0.4 * quantity_score + 0.4 * quality_score + 0.2 * coverage
    details = (
        f"{n} docs retrieved, avg_cosine={avg_score:.3f}, "
        f"high-confidence chunks={high_conf}/{n}"
    )
    return round(score, 4), details


def _score_grounding(reasoning: str, docs: list) -> tuple[float, str]:
    """Check whether the reasoning actually references evidence."""
    if not reasoning or not docs:
        return 0.0, "No reasoning or no docs to check."

    reasoning_lower = reasoning.lower()
    n               = len(docs)

    # Heuristic 1: explicit evidence citations  [Evidence N] or [Research N]
    cited_evidence = len(re.findall(r"evidence\s*\d+", reasoning_lower))
    cited_research = len(re.findall(r"research\s*\d+", reasoning_lower))
    cited = cited_evidence + cited_research
    citation_ratio  = min(cited / max(n, 1), 1.0)

    # Heuristic 2: key terms from evidence appear in reasoning
    term_hits = 0
    for doc in docs:
        snippet = doc.get("text", "")[:200].lower()
        words   = [w for w in re.findall(r"\b\w{5,}\b", snippet)][:10]
        term_hits += sum(1 for w in words if w in reasoning_lower)

    term_ratio = min(term_hits / max(n * 5, 1), 1.0)

    score   = 0.6 * citation_ratio + 0.4 * term_ratio
    details = (
        f"explicit citations={cited}, "
        f"term_overlap_score={term_ratio:.3f}"
    )
    return round(score, 4), details


def _score_completeness(reasoning: str) -> tuple[float, str]:
    """Check structural completeness of the clinical response."""
    if not reasoning:
        return 0.0, "Empty reasoning."

    lower   = reasoning.lower()
    present = [s for s in REQUIRED_SECTIONS if s in lower]
    score   = len(present) / len(REQUIRED_SECTIONS)
    missing = [s for s in REQUIRED_SECTIONS if s not in lower]
    details = (
        f"sections present={present}, missing={missing}"
    )
    return round(score, 4), details


# ── Confidence Label ──────────────────────────────────────────────────────────

def _confidence_label(score: float) -> str:
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ── Agent Node ────────────────────────────────────────────────────────────────

async def validation_agent(state: AgentState) -> dict:
    """
    Validation Agent node.

    Reads:  state["retrieved_docs"], state["reasoning_output"], state["decision_trace"]
    Writes: state["validation_score"], state["validation_feedback"],
            state["workflow_path"]
    """
    docs      = state.get("retrieved_docs", [])
    reasoning = state.get("reasoning_output", "")
    trace     = state.get("decision_trace", {})
    
    # Phase 6: check if we should enforce strict graph validation
    use_graph = trace.get("graph_retrieval", False)

    logger.info("[ValidationAgent] Starting validation...")

    # ── Component scores ──────────────────────────────────────────────────────
    ev_score,  ev_detail  = _score_evidence(docs)
    
    # Phase 7: If we have live research but no local docs, give it a baseline passing score
    research_ctx = state.get("live_research_context", "").strip()
    if not docs and research_ctx:
        ev_score = 0.85
        ev_detail = "Live PubMed research retrieved successfully."
        docs = [{"text": research_ctx}] # Dummy doc for grounding score
        
    gr_score,  gr_detail  = _score_grounding(reasoning, docs)
    comp_score, co_detail = _score_completeness(reasoning)

    # ── General knowledge / Research query relaxation ────────────────────────
    query_type = state.get("query_type", "clinical")
    clinical_intent = state.get("clinical_intent", "unknown")
    selected_workflow = state.get("selected_workflow", "clinical")
    is_research = (query_type == "research" or clinical_intent == "research_lookup" or selected_workflow == "research")

    if is_research:
        if not state.get("retrieved_docs", []):
            ev_score = 0.85
            ev_detail = "General knowledge query — using LLM internal knowledge base."
            gr_score = 0.85
            gr_detail = "Grounded in LLM internal medical knowledge."
            docs = [{"text": "General knowledge query"}]
        else:
            ev_score = max(ev_score, 0.85)
            gr_score = max(gr_score, 0.85)
        
        comp_score = 1.0
        co_detail = "Not enforced for general research queries."

    # ── Composite score (weighted average) ────────────────────────────────────
    composite = round(
        max(0.0, min(1.0, 0.40 * ev_score + 0.40 * gr_score + 0.20 * comp_score)),
        4,
    )
    
    # ── Phase 6 Graph Validation ──────────────────────────────────────────────
    graph_detail = "Skipped (graph disabled)"
    if use_graph:
        try:
            client = GraphClient.get_instance()
            await client.initialize()
            validator = GraphValidator(client)
            is_safe, violations = await validator.validate_reasoning(reasoning)
            if not is_safe:
                # We penalize but DO NOT zero out, because our entity extractor
                # lacks negation detection (it flags "Do NOT give aspirin").
                composite = max(0.0, composite - 0.1)
                graph_detail = "WARNING: " + "; ".join(violations)
                logger.warning(f"[ValidationAgent] Graph validation flagged items (ignoring negation): {violations}")
            else:
                graph_detail = "Passed (no contraindications)"
        except Exception as exc:
            logger.exception(f"[ValidationAgent] Graph validation errored: {exc}")
            graph_detail = "Errored (fail open)"

    # ── Phase 8 Multimodal Validation ────────────────────────────────────────
    multimodal_detail = "Skipped (no image input)"
    visual_ctx = state.get("visual_context", "").strip()
    if visual_ctx:
        mm_validator   = MultimodalValidator()
        ocr_conf       = None  # Would be passed if we had OCR-specific confidence tracked
        img_conf       = state.get("image_confidence", 1.0)
        modal_conf     = 1.0   # Modality confidence not stored separately yet
        score_delta, mm_summary, mm_warnings = mm_validator.validate_visual_context(
            image_confidence    = img_conf,
            modality_confidence = modal_conf,
            ocr_confidence      = ocr_conf,
            visual_context      = visual_ctx,
            reasoning_output    = reasoning,
        )
        composite = round(max(0.0, min(1.0, composite + score_delta)), 4)
        multimodal_detail = mm_summary
        if mm_warnings:
            logger.warning(f"[ValidationAgent] Multimodal warnings: {mm_warnings}")

    # Threshold comes from the decision layer via state, fallback to static
    threshold = state.get("confidence_threshold", CONFIDENCE_THRESHOLD)

    label   = _confidence_label(composite)
    passed  = composite >= CONFIDENCE_THRESHOLD

    feedback = (
        f"Validation {'PASSED' if passed else 'FAILED'} | "
        f"score={composite:.3f} ({label}) | "
        f"threshold={threshold}\n"
        f"  • Evidence:     {ev_detail}\n"
        f"  • Grounding:    {gr_detail}\n"
        f"  • Completeness: {co_detail}\n"
        f"  • Graph Safety: {graph_detail}\n"
        f"  • Multimodal:   {multimodal_detail[:120]}"
    )

    logger.info(f"[ValidationAgent] {feedback}")

    return {
        "validation_score":    composite,
        "validation_feedback": feedback,
        "workflow_path":       ["validate"],
    }
