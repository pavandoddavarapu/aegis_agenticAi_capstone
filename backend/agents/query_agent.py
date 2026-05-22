"""
query_agent.py — Query Understanding Agent (Phase 4)

Transforms a raw medical query into a retrieval-optimised query bundle.

Pipeline (all steps run in sequence):
  1. Acronym expansion        "MI" → "myocardial infarction"
  2. Query classification     factual | comparative | temporal | causal | ...
  3. Query rewriting          grammatically optimised for semantic search
  4. HyDE generation          hypothetical answer → embed for retrieval
  5. Query decomposition      complex → sub-questions (multi-hop)
  6. Ontology expansion       SNOMED synonym injection (rule-based)

Output stored in AgentState:
  query_type, query_variants, query_plan
"""
import os
import re
import asyncio
from typing import List, Tuple
from backend.models.state import AgentState
from backend.utils.logger  import logger
from backend.utils.groq_pool import groq_chat_with_retry

REWRITE_MODEL = "llama-3.1-8b-instant" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"
TEMPERATURE   = 0.1


# ── Step 1: Acronym Expansion ─────────────────────────────────────────────────

MEDICAL_ACRONYMS = {
    "MI": "myocardial infarction", "HTN": "hypertension",
    "DM": "diabetes mellitus", "DM2": "type 2 diabetes mellitus",
    "COPD": "chronic obstructive pulmonary disease",
    "CHF": "congestive heart failure", "CKD": "chronic kidney disease",
    "ACS": "acute coronary syndrome", "DVT": "deep vein thrombosis",
    "PE": "pulmonary embolism", "TIA": "transient ischemic attack",
    "UTI": "urinary tract infection", "GERD": "gastroesophageal reflux disease",
    "STEMI": "ST-elevation myocardial infarction",
    "NSTEMI": "non-ST-elevation myocardial infarction",
    "HbA1c": "glycated haemoglobin A1c", "BP": "blood pressure",
    "HR": "heart rate", "RR": "respiratory rate", "SpO2": "oxygen saturation",
    "CBC": "complete blood count", "BMP": "basic metabolic panel",
    "LFT": "liver function tests", "eGFR": "estimated glomerular filtration rate",
    "ECG": "electrocardiogram", "CT": "computed tomography",
    "MRI": "magnetic resonance imaging", "PCI": "percutaneous coronary intervention",
    "CABG": "coronary artery bypass grafting",
    "RAAS": "renin-angiotensin-aldosterone system",
    "ACE": "angiotensin-converting enzyme",
    "ARB": "angiotensin receptor blocker",
    "SGLT2": "sodium-glucose cotransporter-2",
    "GLP1": "glucagon-like peptide-1", "T2DM": "type 2 diabetes mellitus",
    "T1DM": "type 1 diabetes mellitus", "CAD": "coronary artery disease",
    "PVD": "peripheral vascular disease", "OSA": "obstructive sleep apnea",
}

def _expand_acronyms(query: str) -> str:
    """Replace medical acronyms with full terms."""
    result = query
    for acronym, expansion in MEDICAL_ACRONYMS.items():
        pattern = rf"\b{re.escape(acronym)}\b"
        result  = re.sub(pattern, f"{acronym} ({expansion})", result)
    if result != query:
        logger.info(f"[QueryAgent] Acronyms expanded: '{query}' → '{result[:80]}'")
    return result


# ── Step 2: Query Classification ──────────────────────────────────────────────

QUERY_SIGNALS = {
    "temporal":    ["latest", "recent", "new", "2024", "2023", "current guidelines"],
    "comparative": ["better than", "vs", "versus", "compare", "difference between"],
    "causal":      ["why does", "mechanism", "pathophysiology", "how does"],
    "procedural":  ["how to treat", "treatment protocol", "management of", "dosage"],
    "case_based":  ["patient with", "presenting with", "case of", "years old with"],
    "factual":     ["what is", "define", "what are", "describe"],
}

def _classify_query(query: str) -> str:
    lower = query.lower()
    for qtype, signals in QUERY_SIGNALS.items():
        if any(s in lower for s in signals):
            return qtype
    # Multi-hop: query has many distinct medical concepts
    words = [w for w in lower.split() if len(w) > 4]
    if len(words) > 12:
        return "multi_hop"
    return "factual"


# ── Step 3: Query Rewriting ───────────────────────────────────────────────────

REWRITE_PROMPT = """Rewrite the following medical query to be more precise and 
retrieval-friendly for a medical literature database. 
Remove ambiguity. Keep it concise (max 2 sentences). Return only the rewritten query.

Query: {query}
Rewritten:"""

def _rewrite_query(query: str) -> str:
    try:
        resp = groq_chat_with_retry(
            model=REWRITE_MODEL, temperature=TEMPERATURE,
            messages=[{"role": "user", "content": REWRITE_PROMPT.format(query=query)}],
            max_tokens=120,
        )
        rewritten = resp.choices[0].message.content.strip()
        logger.info(f"[QueryAgent] Rewritten: '{rewritten[:80]}'")
        return rewritten
    except Exception as exc:
        logger.warning(f"[QueryAgent] Rewrite failed: {exc} — using original.")
        return query


# ── Step 4: HyDE (Hypothetical Document Embedding) ───────────────────────────

HYDE_PROMPT = """You are a medical expert. Write a concise 2-3 sentence clinical 
answer to the following question as if it were from a medical textbook.
Be factual and specific. Return only the answer text.

Question: {query}
Answer:"""

def _generate_hyde(query: str) -> str:
    try:
        resp = groq_chat_with_retry(
            model=REWRITE_MODEL, temperature=0.3,
            messages=[{"role": "user", "content": HYDE_PROMPT.format(query=query)}],
            max_tokens=150,
        )
        hyde = resp.choices[0].message.content.strip()
        logger.info(f"[QueryAgent] HyDE generated: '{hyde[:80]}'")
        return hyde
    except Exception as exc:
        logger.warning(f"[QueryAgent] HyDE generation failed: {exc}")
        return ""


# ── Step 5: Query Decomposition ───────────────────────────────────────────────

DECOMPOSE_PROMPT = """Break this complex medical question into 2-3 simpler 
sub-questions that can each be answered from medical literature independently.
Return as a numbered list (1. ... 2. ... 3. ...). No other text.

Question: {query}"""

def _decompose_query(query: str) -> List[str]:
    try:
        resp = groq_chat_with_retry(
            model=REWRITE_MODEL, temperature=0.1,
            messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(query=query)}],
            max_tokens=200,
        )
        raw   = resp.choices[0].message.content.strip()
        lines = [re.sub(r"^\d+\.\s*", "", l).strip()
                 for l in raw.splitlines() if re.match(r"^\d+\.", l.strip())]
        logger.info(f"[QueryAgent] Decomposed into {len(lines)} sub-queries.")
        return lines[:3]
    except Exception as exc:
        logger.warning(f"[QueryAgent] Decomposition failed: {exc}")
        return []


# ── Step 6: Retrieval Plan Selection ─────────────────────────────────────────

def _build_retrieval_plan(query_type: str, query: str) -> List[str]:
    plan = ["dense", "sparse"]   # always hybrid baseline

    if query_type == "temporal":
        plan.append("temporal_filter")
    if query_type in ("causal", "multi_hop"):
        plan.append("decomposed")
    if query_type == "case_based":
        plan.append("case_similarity")
    if query_type in ("comparative", "temporal"):
        plan.append("live_research")

    return plan


# ── Agent Node ────────────────────────────────────────────────────────────────

async def query_agent(state: AgentState) -> dict:
    """
    Query Understanding Agent node.

    Reads:  state["query"]
    Writes: state["query_type"], state["query_variants"],
            state["query_plan"], state["workflow_path"]
    """
    raw_query = state.get("query", "").strip()
    logger.info(f"[QueryAgent] Processing: '{raw_query[:80]}'")

    # Step 1: Acronym expansion
    expanded = _expand_acronyms(raw_query)

    # Step 2: Classification
    query_type = _classify_query(expanded)
    logger.info(f"[QueryAgent] Classified as: {query_type}")

    # Build tasks to run concurrently
    task_keys = []
    coros = []

    # Step 3: Rewrite (always run)
    task_keys.append("rewrite")
    coros.append(asyncio.to_thread(_rewrite_query, expanded))

    # Step 4: HyDE (only for factual / procedural / causal — high ROI)
    run_hyde = query_type in ("factual", "procedural", "causal")
    if run_hyde:
        task_keys.append("hyde")
        coros.append(asyncio.to_thread(_generate_hyde, expanded))

    # Step 5: Decompose (only for multi-hop / comparative)
    run_decompose = query_type in ("multi_hop", "comparative") and len(expanded.split()) > 10
    if run_decompose:
        task_keys.append("decompose")
        coros.append(asyncio.to_thread(_decompose_query, expanded))

    # Run tasks concurrently
    results = await asyncio.gather(*coros)
    results_map = dict(zip(task_keys, results))

    rewritten = results_map.get("rewrite", expanded)
    hyde = results_map.get("hyde", "")
    sub_queries = results_map.get("decompose", [])

    # Step 6: Build retrieval plan
    plan = _build_retrieval_plan(query_type, expanded)

    # Assemble all query variants (deduplicated)
    variants = []
    for v in [expanded, rewritten, hyde] + sub_queries:
        if v and v not in variants and v != raw_query:
            variants.append(v)

    logger.info(
        f"[QueryAgent] Done. type={query_type}, "
        f"variants={len(variants)}, plan={plan}"
    )

    return {
        "query":           expanded,          # use acronym-expanded as base
        "query_type":      query_type,
        "query_variants":  variants,
        "query_plan":      plan,
        "workflow_path":   ["query_understand"],
    }

