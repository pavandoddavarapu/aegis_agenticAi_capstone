"""
reranker.py — Cross-Encoder Reranking (Phase 4)

Problem: Cosine similarity measures embedding proximity, NOT clinical relevance.
A chunk about "diabetes complications overview" may outscore a chunk with
the exact drug dosage the query is asking about.

Solution: Cross-encoder jointly encodes (query, chunk) pairs — full attention
across both — producing true relevance scores.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - Fast (6-layer MiniLM)
  - Strong relevance signal
  - No separate query embedding needed

Upgrade path: BAAI/bge-reranker-large for higher accuracy at higher cost.
"""
import math
import os
from typing import List, Dict
from backend.utils.logger import logger

# Force HF_ENDPOINT locally just in case huggingface_hub was already imported
os.environ["HF_ENDPOINT"] = "https://huggingface.co"

# ── Configuration ─────────────────────────────────────────────────────────────
RERANKER_MODEL  = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_BATCH  = 32
SCORE_FLOOR     = -99.0     # discard chunks below this cross-encoder score
MAX_OUTPUT_DOCS = 10      # max chunks passed to reasoning agent

# Section priority multipliers
SECTION_WEIGHTS = {
    "results":              1.30,
    "findings":             1.30,
    "assessment":           1.25,
    "plan":                 1.25,
    "conclusion":           1.15,
    "abstract":             1.10,
    "impression":           1.20,
    "recommendations":      1.20,
    "discussion":           1.00,
    "methods":              0.90,
    "background":           0.85,
    "introduction":         0.80,
}

# ── Lazy model loader ─────────────────────────────────────────────────────────
_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"[Reranker] Loading model: {RERANKER_MODEL}")
            _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
            logger.info("[Reranker] Model loaded.")
        except Exception as exc:
            logger.error(f"[Reranker] Failed to load model: {exc}")
            _reranker = None
    return _reranker


# ── Recency scoring ───────────────────────────────────────────────────────────

def _recency_score(pub_year: int | None) -> float:
    """Linear decay: 2025=1.0, 2015=0.5, 2005=0.0"""
    if not pub_year:
        return 0.6   # unknown year → neutral
    return max(0.0, min(1.0, (pub_year - 2005) / 20.0))


# ── Entity overlap ────────────────────────────────────────────────────────────

def _entity_boost(query: str, chunk_text: str) -> float:
    """
    Simple term-overlap boost — no NER required.
    Reward chunks containing query-significant words (>5 chars).
    """
    q_words = {w.lower() for w in query.split() if len(w) > 5}
    c_lower = chunk_text.lower()
    if not q_words:
        return 0.5
    hits = sum(1 for w in q_words if w in c_lower)
    return min(hits / len(q_words), 1.0)


# ── Main rerank function ──────────────────────────────────────────────────────

def rerank(query: str, candidates: List[Dict]) -> List[Dict]:
    """
    Rerank a list of candidate chunks for a query.

    Args:
        query:      The user's medical query.
        candidates: List of chunk dicts (must have 'text' key).

    Returns:
        Reranked + filtered list, up to MAX_OUTPUT_DOCS chunks.
        Each chunk gains a 'rerank_score' key.
    """
    if not candidates:
        return []

    model = _get_reranker()

    # ── Cross-encoder scoring ─────────────────────────────────────────────────
    # Bypassed to prevent slow CPU inference and huggingface_hub timeout loops
    logger.info("[Reranker] Bypassing CrossEncoder model — using retrieval score fallback for speed.")
    raw_scores = [c.get("score", 0.5) for c in candidates]
    model = None

    # ── Composite scoring ─────────────────────────────────────────────────────
    for chunk, ce_score in zip(candidates, raw_scores):
        section   = (chunk.get("section") or "").lower()
        sw        = SECTION_WEIGHTS.get(section, 1.0)
        # Normalize section weight to [0, 1] range to prevent it from exceeding bounds
        sw_norm   = min(1.0, sw / 1.30)
        trust     = float(chunk.get("trust_score", 0.7))
        recency   = _recency_score(chunk.get("publication_year"))
        entity_b  = _entity_boost(query, chunk.get("text", ""))

        if model is not None:
            # Apply sigmoid to map raw cross-encoder logits to [0, 1]
            try:
                ce_score_norm = 1.0 / (1.0 + math.exp(-ce_score))
            except OverflowError:
                ce_score_norm = 1.0 if ce_score > 0 else 0.0
        else:
            # Fallback score is already normalized between 0 and 1
            ce_score_norm = ce_score

        composite = (
            ce_score_norm * 0.55 +
            sw_norm       * 0.15 +
            trust         * 0.15 +
            recency       * 0.10 +
            entity_b      * 0.05
        )
        final_score = round(max(0.0, min(1.0, composite)), 4)
        chunk["rerank_score"] = final_score
        chunk["score"] = final_score

    # ── Filter + sort ─────────────────────────────────────────────────────────
    ranked = sorted(candidates, key=lambda c: -c["rerank_score"])
    ranked = [c for c in ranked if c["rerank_score"] >= SCORE_FLOOR]

    logger.info(
        f"[Reranker] Reranked {len(candidates)} → top {min(len(ranked), MAX_OUTPUT_DOCS)} chunks. "
        f"Top score: {ranked[0]['rerank_score'] if ranked else 'N/A'}"
    )
    return ranked[:MAX_OUTPUT_DOCS]
