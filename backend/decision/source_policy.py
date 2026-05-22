"""
source_policy.py — Source Priority Engine (Phase 4.5)

Architecture:
  Source priority is NOT a static sorted list.
  It is a policy object that:
    1. Assigns trust multipliers per source type and document type.
    2. Filters sources below a minimum trust threshold.
    3. Reweights reranker scores during retrieval fusion.

  Each SourcePriorityPolicy is workflow-specific.
  The reranker calls `apply_source_policy(chunk, policy)` to adjust
  the chunk's effective score before final ranking.

Trust score hierarchy (approximate):
  WHO / NIH / NICE guidelines      → 0.95+
  Cochrane / systematic reviews    → 0.90
  RCT (peer-reviewed)              → 0.85
  Observational study              → 0.75
  Case report / expert opinion     → 0.65
  Internet (unvalidated)           → 0.45
  Unknown                          → 0.55
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.decision.schemas import SourcePriority
from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Source Type Registry
# ═════════════════════════════════════════════════════════════════════════════

# Trust multipliers per document_type tag.
# Applied as: effective_score = base_score * trust_multiplier
DOCUMENT_TYPE_TRUST: Dict[str, float] = {
    "clinical_guideline":    1.20,
    "systematic_review":     1.15,
    "meta_analysis":         1.15,
    "randomised_trial":      1.10,
    "clinical_trial":        1.08,
    "research_paper":        1.00,
    "observational_study":   0.95,
    "case_report":           0.85,
    "expert_opinion":        0.80,
    "clinical_note":         0.90,
    "radiology_report":      0.92,
    "lab_report":            0.92,
    "medical_report":        0.90,
    "internet_search":       0.60,
    "unknown":               0.80,
}

# Source name keyword → trust boost. Applied additively.
SOURCE_KEYWORD_BOOSTS: Dict[str, float] = {
    "who":          0.10,
    "nih":          0.10,
    "nice":         0.10,
    "cdc":          0.08,
    "cochrane":     0.12,
    "nejm":         0.08,
    "lancet":       0.08,
    "jama":         0.08,
    "bmj":          0.07,
    "pubmed":       0.05,
    "medline":      0.05,
}

# Recency multipliers (applied to doc year-based recency score)
RECENCY_WEIGHTS_BY_POLICY: Dict[SourcePriority, float] = {
    SourcePriority.RECENCY_WEIGHTED: 0.30,   # strong recency weighting
    SourcePriority.BROAD_ACADEMIC:   0.15,   # mild recency preference
    SourcePriority.GUIDELINE_FIRST:  0.05,   # guidelines may be older
    SourcePriority.TRIAL_EVIDENCE:   0.20,   # prefer recent trials
    SourcePriority.LOCAL_RAG:        0.10,
    SourcePriority.TRUSTED_ONLY:     0.05,
}

# Minimum trust score (base chunk trust_score) below which chunks are dropped
MIN_TRUST_BY_POLICY: Dict[SourcePriority, float] = {
    SourcePriority.TRUSTED_ONLY:     0.85,
    SourcePriority.GUIDELINE_FIRST:  0.70,
    SourcePriority.TRIAL_EVIDENCE:   0.65,
    SourcePriority.BROAD_ACADEMIC:   0.50,
    SourcePriority.RECENCY_WEIGHTED: 0.50,
    SourcePriority.LOCAL_RAG:        0.40,
}

# Document types to PRIORITISE (boosted) per policy
PRIORITY_DOCTYPES_BY_POLICY: Dict[SourcePriority, List[str]] = {
    SourcePriority.GUIDELINE_FIRST:  ["clinical_guideline", "systematic_review"],
    SourcePriority.TRIAL_EVIDENCE:   ["randomised_trial", "clinical_trial", "meta_analysis"],
    SourcePriority.BROAD_ACADEMIC:   ["research_paper", "systematic_review", "observational_study"],
    SourcePriority.RECENCY_WEIGHTED: [],          # no type filter — just recency
    SourcePriority.LOCAL_RAG:        [],          # no type filter — trust score gates
    SourcePriority.TRUSTED_ONLY:     [],          # trust_score gate is sufficient
}


# ═════════════════════════════════════════════════════════════════════════════
# Policy Application
# ═════════════════════════════════════════════════════════════════════════════

def _year_recency(pub_year: Optional[int]) -> float:
    """Linear decay from 2025 (1.0) to 2005 (0.0)."""
    if not pub_year:
        return 0.60
    return max(0.0, min(1.0, (pub_year - 2005) / 20.0))


def _source_keyword_boost(source_name: str) -> float:
    """Additive boost from recognized authority sources."""
    name_lower = source_name.lower()
    return sum(v for k, v in SOURCE_KEYWORD_BOOSTS.items() if k in name_lower)


def apply_source_policy(chunk: dict, policy: SourcePriority) -> Optional[float]:
    """
    Apply a SourcePriority policy to a single chunk.

    Returns:
        The adjusted effective score, or None if the chunk should be FILTERED OUT.

    Architecture note:
        This function is called by the hybrid_retriever AFTER RRF fusion and
        BEFORE cross-encoder reranking, giving the reranker the correct
        base signal to work from.
    """
    trust_score  = float(chunk.get("trust_score", 0.60))
    doc_type     = chunk.get("document_type") or "unknown"
    source_name  = chunk.get("source") or ""
    pub_year     = chunk.get("publication_year")
    base_score   = float(chunk.get("rrf_score") or chunk.get("score", 0.50))

    # ── 1. Trust floor filter ─────────────────────────────────────────────────
    min_trust = MIN_TRUST_BY_POLICY.get(policy, 0.40)
    if trust_score < min_trust:
        logger.debug(
            f"[SourcePolicy] Filtered '{source_name}': "
            f"trust={trust_score:.2f} < floor={min_trust:.2f}"
        )
        return None

    # ── 2. Document type multiplier ───────────────────────────────────────────
    type_mult  = DOCUMENT_TYPE_TRUST.get(doc_type, 0.80)

    # ── 3. Priority doctype boost (+15% for preferred types) ─────────────────
    priority_types = PRIORITY_DOCTYPES_BY_POLICY.get(policy, [])
    type_boost = 0.15 if doc_type in priority_types else 0.0

    # ── 4. Source authority keyword boost ────────────────────────────────────
    authority_boost = _source_keyword_boost(source_name)

    # ── 5. Recency weighting ──────────────────────────────────────────────────
    recency_w   = RECENCY_WEIGHTS_BY_POLICY.get(policy, 0.10)
    recency_val = _year_recency(pub_year)

    # ── 6. Composite effective score ─────────────────────────────────────────
    effective = (
        base_score   * 0.55 +
        trust_score  * type_mult * 0.25 +
        recency_val  * recency_w +
        type_boost   * 0.10 +
        authority_boost * 0.10
    )

    return round(min(effective, 1.0), 4)


def filter_and_reprioritise(
    chunks: List[dict],
    policy: SourcePriority,
) -> List[dict]:
    """
    Apply source policy to an entire list of chunks.
    Filters ineligible chunks and re-sorts by effective_score.

    Args:
        chunks: Flat list of chunk dicts (post-RRF, pre-rerank).
        policy: The selected SourcePriority for this workflow.

    Returns:
        Filtered + re-sorted chunks, each with 'effective_score' key set.
    """
    result = []
    for chunk in chunks:
        eff = apply_source_policy(chunk, policy)
        if eff is not None:
            chunk["effective_score"] = eff
            result.append(chunk)

    result.sort(key=lambda c: -c["effective_score"])

    removed = len(chunks) - len(result)
    if removed:
        logger.info(
            f"[SourcePolicy] policy={policy.value}: "
            f"filtered {removed} chunks, {len(result)} remain."
        )
    return result
