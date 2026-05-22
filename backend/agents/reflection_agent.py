"""
reflection_agent.py — Reflection Agent (Phase 3)

Triggered when: validation_score < CONFIDENCE_THRESHOLD

Responsibilities
────────────────
• Diagnose WHY validation failed (low evidence, poor grounding, etc.).
• Expand the query with medical synonyms / related terms.
• Fetch additional evidence (expanded retrieval).
• Store reflection notes so the supervisor can see what changed.
• Increment retry_count to prevent infinite loops.

This is what makes Aegis *adaptive*: it doesn't just fail — it
reasons about failure and tries a smarter approach.
"""
from backend.models.state import AgentState
from backend.rag.hybrid_retriever import hybrid_retrieve
from backend.graphrag.hybrid_graph_retriever import HybridGraphRetriever
from backend.utils.logger import logger


# ── Configuration ─────────────────────────────────────────────────────────────
EXPANDED_TOP_K = 8          # fetch more docs on retry
MAX_RETRIES    = 3


# ── Query Expansion ───────────────────────────────────────────────────────────

# Simple synonym/expansion map for common medical terms.
# In production this would be replaced by an ontology lookup (UMLS, SNOMED-CT).
MEDICAL_EXPANSIONS: dict[str, list[str]] = {
    "heart attack":      ["myocardial infarction", "acute MI", "STEMI", "NSTEMI"],
    "stroke":            ["cerebrovascular accident", "CVA", "ischemic stroke", "TIA"],
    "diabetes":          ["diabetes mellitus", "type 2 diabetes", "hyperglycemia", "T2DM"],
    "hypertension":      ["high blood pressure", "HTN", "elevated BP"],
    "cancer":            ["malignancy", "neoplasm", "carcinoma", "oncology"],
    "pneumonia":         ["lung infection", "pulmonary infection", "respiratory infection"],
    "kidney disease":    ["renal disease", "CKD", "chronic kidney disease", "nephropathy"],
    "heart failure":     ["cardiac failure", "CHF", "congestive heart failure"],
    "copd":              ["chronic obstructive pulmonary disease", "emphysema", "chronic bronchitis"],
    "sepsis":            ["septic shock", "bacteremia", "systemic infection"],
    "asthma":            ["bronchial asthma", "reactive airway disease"],
    "depression":        ["major depressive disorder", "MDD", "clinical depression"],
    "anxiety":           ["generalized anxiety disorder", "GAD", "panic disorder"],
}


def _expand_query(query: str) -> str:
    """
    Expand query with medical synonyms to improve recall.
    Appends related terms to the original query.
    """
    lower_query = query.lower()
    expansions  = []

    for term, synonyms in MEDICAL_EXPANSIONS.items():
        if term in lower_query:
            expansions.extend(synonyms)

    if expansions:
        expanded = f"{query} {' '.join(expansions[:4])}"   # cap at 4 extra terms
        logger.info(f"[ReflectionAgent] Query expanded: '{query}' → '{expanded}'")
        return expanded

    # Generic fallback: broaden with clinical context keywords
    fallback = f"{query} clinical evidence treatment guidelines diagnosis"
    logger.info(f"[ReflectionAgent] Generic expansion applied: '{fallback}'")
    return fallback


# ── Diagnosis Helpers ─────────────────────────────────────────────────────────

def _diagnose_failure(state: AgentState) -> str:
    """Identify the most likely reason validation failed."""
    docs      = state.get("retrieved_docs", [])
    reasoning = state.get("reasoning_output", "")
    score     = state.get("validation_score", 0)
    feedback  = state.get("validation_feedback", "")
    img_conf  = state.get("image_confidence", 1.0)

    if img_conf < 0.40:
        return "LOW_IMAGE_CONFIDENCE"
    if not docs and not state.get("visual_context", ""):
        return "NO_EVIDENCE"
    if not docs:
        return "NO_SEMANTIC_EVIDENCE"
    if len(docs) < 3:
        return "INSUFFICIENT_EVIDENCE"
    if "grounding" in feedback.lower() and score < 0.5:
        return "POOR_GROUNDING"
    if "completeness" in feedback.lower():
        return "INCOMPLETE_REASONING"
    if "multimodal" in feedback.lower() and "warning" in feedback.lower():
        return "MULTIMODAL_QUALITY"
    return "LOW_COMPOSITE_SCORE"


# ── Agent Node ────────────────────────────────────────────────────────────────

async def reflection_agent(state: AgentState) -> dict:
    """
    Reflection Agent node (Phase 6 - Graph Aware).

    Reads:  state["query"], state["retrieved_docs"], state["decision_trace"]
            state["validation_score"], state["validation_feedback"]
    Writes: state["retrieved_docs"] (expanded), state["graph_context"], state["live_research_context"],
            state["retry_count"], state["workflow_path"]
    """
    query       = state.get("query", "")
    retry_count = state.get("retry_count", 0)
    score       = state.get("validation_score", 0)

    logger.info(
        f"[ReflectionAgent] Triggered. retry={retry_count}, "
        f"validation_score={score:.3f}"
    )

    # ── Safety guard ──────────────────────────────────────────────────────────
    if retry_count >= MAX_RETRIES:
        note = (
            f"Max retries ({MAX_RETRIES}) reached. "
            "Returning best available evidence."
        )
        logger.warning(f"[ReflectionAgent] {note}")
        return {
            "reflection_notes": note,
            "retry_count":      retry_count + 1,
            "workflow_path":    ["reflect"],
        }

    # ── Diagnose failure ─────────────────────────────────────────────────────
    cause        = _diagnose_failure(state)
    expanded_q   = _expand_query(query)

    logger.info(f"[ReflectionAgent] Failure cause: {cause}. Re-retrieving...")

    # ── Expanded retrieval (Graph + Semantic + Multimodal) ──────────────────
    trace        = state.get("decision_trace", {})
    use_graph    = trace.get("graph_retrieval", False)
    use_research = trace.get("internet_retrieval", False)
    visual_ctx   = state.get("visual_context", "")

    new_docs              = []
    graph_context         = state.get("graph_context", "")
    live_research_context = state.get("live_research_context", "")
    updated_visual        = visual_ctx  # preserve existing

    # Phase 8: if failure was due to low image confidence, widen semantic search
    if cause == "LOW_IMAGE_CONFIDENCE":
        logger.warning(
            "[ReflectionAgent] Low image confidence — broadening semantic search."
        )
        # expanded_q already adds clinical context keywords

    try:
        import asyncio
        if use_research:
            # Broaden PubMed search
            from backend.research.research_agent import ResearchAgent
            research_agent = ResearchAgent()
            # On reflection, we loosen strict_rct filters to find observational or related data
            new_research = await research_agent.run_research(expanded_q, strict_rct=False)
            if new_research:
                live_research_context += "\n=== EXPANDED RESEARCH ===\n" + new_research
                logger.info(f"[ReflectionAgent] Expanded live research completed.")
        if use_graph:
            retriever = HybridGraphRetriever()
            await retriever.initialize()
            res = await retriever.retrieve(
                query=expanded_q, 
                query_variants=[], 
                top_k=EXPANDED_TOP_K
            )
            new_docs = res.get("retrieved_docs", [])
            # Append new graph relationships to existing ones
            graph_context += "\n" + res.get("graph_context", "")
            logger.info(f"[ReflectionAgent] Expanded graph retrieval completed.")
        else:
            new_docs = await asyncio.to_thread(
                hybrid_retrieve,
                query=expanded_q, 
                query_variants=[],
                top_k_final=EXPANDED_TOP_K
            )
            logger.info(f"[ReflectionAgent] Expanded semantic retrieval returned {len(new_docs)} docs.")
    except Exception as exc:
        logger.exception(f"[ReflectionAgent] Expanded retrieval failed: {exc}")
        new_docs = state.get("retrieved_docs", [])   # keep original

    reflection_notes = (
        f"Retry #{retry_count + 1} | Cause: {cause} | "
        f"Strategy: query expansion + broader retrieval (top_k={EXPANDED_TOP_K}, graph={use_graph}) | "
        f"Expanded query: '{expanded_q[:120]}'"
    )

    return {
        "retrieved_docs":   new_docs,
        "graph_context":    graph_context,
        "live_research_context": live_research_context,
        "reflection_notes": reflection_notes,
        "retry_count":      retry_count + 1,
        "workflow_path":    ["reflect"],
    }
