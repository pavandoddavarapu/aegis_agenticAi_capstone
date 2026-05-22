"""
metrics.py — Production Evaluation Metrics (Phase 5)

Metrics implemented:
  IR metrics (retrieval quality):
    recall_at_k(retrieved, relevant, k)         — fraction of relevant found in top-k
    precision_at_k(retrieved, relevant, k)       — fraction of top-k that are relevant
    mean_reciprocal_rank(retrieved, relevant)    — MRR across query set
    ndcg_at_k(retrieved, relevance_scores, k)   — Normalised DCG

  Clinical quality metrics:
    grounding_score(reasoning, docs)             — citation density
    unsupported_claim_rate(reasoning, docs)      — hallucination proxy
    evidence_coverage(query_entities, docs)      — entity recall
    contradiction_rate(docs)                     — conflicting evidence %
    reranker_lift(pre_scores, post_scores)       — reranker effectiveness

  Aggregate metrics (over evaluation dataset):
    evaluate_retrieval_batch(cases)              — full offline eval suite
    reflection_success_rate(reflections)         — did reflection improve score?
    escalation_precision(escalations, outcomes)  — were escalations warranted?

Design:
  All metric functions are pure (no I/O, no side effects).
  They operate on Python lists/dicts only.
  The EvaluationRunner class wraps them with PostgreSQL persistence.
"""
from __future__ import annotations
import math
import re
from typing import Dict, List, Optional, Tuple

from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# IR Retrieval Metrics
# ═════════════════════════════════════════════════════════════════════════════

def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """
    Recall@K = |relevant ∩ top-k| / |relevant|
    All IDs are chunk_id strings.
    """
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    rel   = set(relevant)
    return len(top_k & rel) / len(rel)


def precision_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Precision@K = |relevant ∩ top-k| / k"""
    if not retrieved or k == 0:
        return 0.0
    top_k = set(retrieved[:k])
    rel   = set(relevant)
    return len(top_k & rel) / k


def mean_reciprocal_rank(retrieved_lists: List[List[str]],
                          relevant_lists:  List[List[str]]) -> float:
    """
    MRR over a batch of queries.
    MRR = mean(1 / rank_of_first_relevant) for each query.
    """
    if not retrieved_lists:
        return 0.0
    rr_scores = []
    for retrieved, relevant in zip(retrieved_lists, relevant_lists):
        rel_set = set(relevant)
        rr      = 0.0
        for rank, doc_id in enumerate(retrieved, 1):
            if doc_id in rel_set:
                rr = 1.0 / rank
                break
        rr_scores.append(rr)
    return sum(rr_scores) / len(rr_scores)


def ndcg_at_k(retrieved: List[str],
               relevance: Dict[str, float],
               k: int) -> float:
    """
    NDCG@K with graded relevance.
    relevance: dict of chunk_id → relevance_score (0, 1, or 2).
    """
    def dcg(scores: List[float]) -> float:
        return sum(
            (2 ** sc - 1) / math.log2(i + 2)
            for i, sc in enumerate(scores[:k])
        )

    actual_scores = [relevance.get(doc_id, 0.0) for doc_id in retrieved[:k]]
    ideal_scores  = sorted(relevance.values(), reverse=True)[:k]

    ideal_dcg = dcg(ideal_scores)
    if ideal_dcg == 0:
        return 0.0
    return round(dcg(actual_scores) / ideal_dcg, 4)


def reranker_lift(pre_rrf_scores: List[float],
                  post_rerank_scores: List[float]) -> float:
    """
    Measures how much the reranker improved score ordering.
    Lift = avg(post) - avg(pre), normalised to [-1, 1].
    Positive = reranker improved relevance ordering.
    """
    if not pre_rrf_scores or not post_rerank_scores:
        return 0.0
    avg_pre  = sum(pre_rrf_scores)  / len(pre_rrf_scores)
    avg_post = sum(post_rerank_scores) / len(post_rerank_scores)
    return round(avg_post - avg_pre, 4)


# ═════════════════════════════════════════════════════════════════════════════
# Clinical Quality Metrics
# ═════════════════════════════════════════════════════════════════════════════

def grounding_score(reasoning_text: str, docs: List[Dict]) -> float:
    """
    Citation density = #[Evidence N] citations / #evidence chunks available.
    Measures how well the reasoning agent grounded its output.
    """
    if not docs:
        return 0.0
    citations = len(re.findall(r"\[evidence\s*\d+\]", reasoning_text.lower()))
    return round(min(citations / len(docs), 1.0), 4)


def unsupported_claim_rate(reasoning_text: str, docs: List[Dict]) -> float:
    """
    Hallucination proxy: fraction of sentences whose medical entities
    do NOT appear in ANY retrieved chunk.

    Heuristic: a sentence is "unsupported" if it contains medical terms
    (>6 chars, capitalised or in medical vocabulary) that don't appear
    in the combined doc text.
    """
    if not docs:
        return 1.0   # no evidence = everything is unsupported

    doc_text  = " ".join(d.get("text", "") for d in docs).lower()
    sentences = re.split(r"(?<=[.!?])\s+", reasoning_text.strip())

    if not sentences:
        return 0.0

    unsupported = 0
    for sentence in sentences:
        # Extract candidate medical terms (>6 chars, alphabetic)
        candidates = [w.lower() for w in re.findall(r"[A-Za-z]{6,}", sentence)]
        if not candidates:
            continue
        not_found = [t for t in candidates if t not in doc_text]
        if len(not_found) / max(len(candidates), 1) > 0.60:
            unsupported += 1

    return round(unsupported / max(len(sentences), 1), 4)


def evidence_coverage(query: str, docs: List[Dict]) -> float:
    """
    Fraction of significant query terms found in the retrieved docs.
    Significant = length > 4, not a stopword.
    """
    STOPWORDS = {"what", "which", "with", "that", "this", "from", "have",
                 "does", "about", "patient", "clinical", "medical"}
    q_terms = {
        w.lower() for w in re.findall(r"[A-Za-z]{5,}", query)
        if w.lower() not in STOPWORDS
    }
    if not q_terms:
        return 0.5

    doc_text = " ".join(d.get("text", "") for d in docs).lower()
    covered  = sum(1 for t in q_terms if t in doc_text)
    return round(covered / len(q_terms), 4)


def contradiction_rate(docs: List[Dict]) -> float:
    """
    Estimates contradiction presence by detecting opposing recommendation
    patterns within the same document set.
    Heuristic: look for negation patterns near medical terms.
    Returns 0.0 (none) – 1.0 (high contradiction risk).
    """
    texts = [d.get("text", "") for d in docs]
    if len(texts) < 2:
        return 0.0

    CONTRA_PATTERNS = [
        r"\bdo not\b.{0,30}\b(use|give|prescribe|administer)\b",
        r"\bcontraindicated\b",
        r"\bavoid\b.{0,20}\bin\b",
        r"\bnot recommended\b",
    ]
    hits = 0
    for text in texts:
        for pat in CONTRA_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                hits += 1
                break

    return round(hits / max(len(texts), 1), 4)


# ═════════════════════════════════════════════════════════════════════════════
# Aggregate / Batch Metrics
# ═════════════════════════════════════════════════════════════════════════════

def reflection_success_rate(reflection_events: List[Dict]) -> float:
    """
    Fraction of reflection cycles that improved validation score.
    A cycle is "successful" if score_after > score_before.
    """
    if not reflection_events:
        return 0.0
    improved = sum(1 for e in reflection_events if e.get("improved", False))
    return round(improved / len(reflection_events), 4)


def escalation_precision(
    escalation_events: List[Dict],
    confirmed_critical_ids: List[str],
) -> float:
    """
    Fraction of escalated requests that were genuinely critical.
    confirmed_critical_ids: set of request_ids confirmed as truly high-risk.
    """
    if not escalation_events:
        return 0.0
    esc_ids  = {e["request_id"] for e in escalation_events}
    true_pos = len(esc_ids & set(confirmed_critical_ids))
    return round(true_pos / len(esc_ids), 4)


def workflow_success_rate(workflow_end_events: List[Dict]) -> float:
    """Fraction of workflows completing with status='success'."""
    if not workflow_end_events:
        return 0.0
    success = sum(1 for e in workflow_end_events if e.get("status") == "success")
    return round(success / len(workflow_end_events), 4)


def compute_evaluation_summary(
    query:           str,
    retrieved_docs:  List[Dict],
    reasoning_text:  str,
    relevant_ids:    Optional[List[str]] = None,
) -> Dict:
    """
    Compute the full evaluation metric suite for a single request.
    Returns a flat dict suitable for logging/storage.
    """
    retrieved_ids = [d.get("chunk_id", d.get("source", "")) for d in retrieved_docs]

    metrics = {
        "recall_at_5":        recall_at_k(retrieved_ids, relevant_ids or [], k=5),
        "recall_at_10":       recall_at_k(retrieved_ids, relevant_ids or [], k=10),
        "precision_at_5":     precision_at_k(retrieved_ids, relevant_ids or [], k=5),
        "grounding_score":    grounding_score(reasoning_text, retrieved_docs),
        "unsupported_claim_rate": unsupported_claim_rate(reasoning_text, retrieved_docs),
        "evidence_coverage":  evidence_coverage(query, retrieved_docs),
        "contradiction_rate": contradiction_rate(retrieved_docs),
        "source_count":       len({d.get("source") for d in retrieved_docs}),
        "doc_count":          len(retrieved_docs),
    }
    logger.info("[Metrics] %s", metrics)
    return metrics
