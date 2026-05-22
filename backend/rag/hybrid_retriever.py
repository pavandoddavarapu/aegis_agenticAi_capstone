"""
hybrid_retriever.py — Hybrid Dense + Sparse Retrieval with RRF (Phase 4)

Combines:
  1. Dense retrieval (Qdrant ANN cosine)
  2. Sparse retrieval (BM25 keyword matching)
  3. Reciprocal Rank Fusion (merges ranked lists)
  4. Cross-encoder reranking (precision pass)

Why hybrid beats dense-only in medicine:
  Dense: "metformin" ≈ "antidiabetic agent" (semantic match ✓)
  BM25:  "metformin 1000mg twice daily" (exact term match ✓)
  Hybrid: catches both — highest recall.

Optimizations (v2):
  - Dense retrieval for primary query + variants run in parallel
    via ThreadPoolExecutor — eliminates serial latency.
  - BM25 runs concurrently with dense retrieval (separate thread).
  - Reduced FUSION_TOP_K from 30 → 20 to shrink cross-encoder load.
  - Uses embed_query_list (LRU-cached) so the query is only encoded once
    even when called repeatedly within a single workflow.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from collections import defaultdict

from backend.rag.retriever   import retrieve_evidence
from backend.rag.bm25_store  import bm25_store
from backend.rag.reranker    import rerank
from backend.utils.logger    import logger

# ── RRF Configuration ─────────────────────────────────────────────────────────
RRF_K            = 60     # RRF smoothing constant (standard = 60)
DENSE_WEIGHT     = 0.60   # dense retrieval contribution
SPARSE_WEIGHT    = 0.40   # BM25 contribution
DENSE_CANDIDATES = 20     # how many dense results to fetch per query
SPARSE_CANDIDATES= 20     # how many BM25 results to fetch
FUSION_TOP_K     = 20     # pool size after fusion → fed to reranker (was 30)

# Max extra query variants to use (caps extra dense calls)
MAX_VARIANTS = 2


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def _rrf_fuse(
    dense_results:  List[Dict],
    sparse_results: List[Dict],
) -> List[Dict]:
    """
    Merge dense + sparse result lists using Reciprocal Rank Fusion.

    Both lists are ranked (index 0 = best).
    RRF score = Σ weight_i / (k + rank_i)

    Returns:
        Deduplicated, merged list sorted by RRF score (descending).
        Each item is the original chunk dict + 'rrf_score' key.
    """
    rrf_scores: Dict[str, float]  = defaultdict(float)
    chunk_map:  Dict[str, Dict]   = {}

    # Dense pass
    for rank, chunk in enumerate(dense_results):
        key = _chunk_key(chunk)
        rrf_scores[key] += DENSE_WEIGHT * (1.0 / (RRF_K + rank + 1))
        chunk_map[key]   = chunk

    # Sparse pass
    for rank, chunk in enumerate(sparse_results):
        key = _chunk_key(chunk)
        rrf_scores[key] += SPARSE_WEIGHT * (1.0 / (RRF_K + rank + 1))
        if key not in chunk_map:
            chunk_map[key] = chunk

    # Build merged list
    merged = []
    for key, rrf_score in sorted(rrf_scores.items(), key=lambda x: -x[1]):
        chunk = chunk_map[key].copy()
        chunk["rrf_score"] = round(rrf_score, 6)
        merged.append(chunk)

    return merged[:FUSION_TOP_K]


def _chunk_key(chunk: Dict) -> str:
    """Stable identity key for deduplication."""
    source = chunk.get("source") or chunk.get("payload", {}).get("source", "")
    page   = chunk.get("page")   or chunk.get("payload", {}).get("page", 0)
    idx    = chunk.get("metadata", {}).get("chunk_index") or \
             chunk.get("payload", {}).get("chunk_index", 0)
    text   = (chunk.get("text") or "")[:50]
    return f"{source}::{page}::{idx}::{text}"


# ── Dense result normalizer ───────────────────────────────────────────────────

def _normalize_dense(dense_response) -> List[Dict]:
    """Convert RetrievalResponse objects to plain dicts."""
    return [
        {
            "text":          r.text,
            "score":         max(0.0, min(1.0, float(r.score))),
            "confidence":    r.confidence,
            "source":        r.source,
            "page":          r.page,
            "section":       r.section,
            "document_type": r.document_type,
            "timestamp":     r.timestamp,
            "metadata":      r.metadata,
            "trust_score":   0.75,  # default — upgraded when trust_score stored
        }
        for r in dense_response.results
    ]


def _normalize_sparse(sparse_results: List[Dict]) -> List[Dict]:
    """Convert BM25 results (payload-wrapped) to flat dicts."""
    normalized = []
    for item in sparse_results:
        p = item.get("payload", {})
        bm25_raw_score = float(item.get("bm25_score", 0))
        # Soft-cap BM25 score to [0.0, 1.0] range
        normalized_score = bm25_raw_score / (bm25_raw_score + 8.0) if bm25_raw_score > 0 else 0.0
        normalized.append({
            "text":          p.get("text", ""),
            "score":         round(normalized_score, 4),
            "confidence":    "medium",
            "source":        p.get("source", "unknown"),
            "page":          p.get("page", 0),
            "section":       p.get("section"),
            "document_type": p.get("document_type", "medical_report"),
            "timestamp":     p.get("timestamp", ""),
            "metadata":      {
                "chunk_index":  p.get("chunk_index"),
                "total_chunks": p.get("total_chunks"),
            },
            "trust_score":   0.70,
        })
    return normalized


# ── Public entry point ────────────────────────────────────────────────────────

def hybrid_retrieve(
    query: str,
    query_variants: List[str] | None = None,
    top_k_final: int = 8,
) -> List[Dict[str, Any]]:
    """
    Full hybrid retrieval pipeline — dense + BM25 in parallel:
        Dense(query + variants) ∥ BM25(query) → RRF fusion → Cross-encoder rerank

    Args:
        query:          Primary query string.
        query_variants: Additional query forms (rewritten, HyDE, sub-queries).
                        Used to enrich dense retrieval.
        top_k_final:    Number of chunks to return after reranking.

    Returns:
        Reranked list of chunk dicts, each with 'rerank_score'.
    """
    variants = (query_variants or [])[:MAX_VARIANTS]
    all_dense_queries = [query] + variants

    logger.info(
        f"[HybridRetriever] Query: '{query[:60]}' "
        f"| variants={len(variants)}"
    )

    dense_results: List[Dict] = []
    sparse_results: List[Dict] = []

    # ── Parallel: dense (all queries) + BM25 run simultaneously ──────────────
    def _dense_fetch(q: str, top_k: int) -> List[Dict]:
        try:
            resp = retrieve_evidence(query=q, top_k=top_k)
            return _normalize_dense(resp)
        except Exception as exc:
            logger.error(f"[HybridRetriever] Dense retrieval error for '{q[:40]}': {exc}")
            return []

    def _sparse_fetch() -> List[Dict]:
        try:
            raw = bm25_store.search(query, top_k=SPARSE_CANDIDATES)
            return _normalize_sparse(raw)
        except Exception as exc:
            logger.error(f"[HybridRetriever] BM25 retrieval error: {exc}")
            return []

    # Build futures: one per dense query + one for BM25
    futures_map = {}
    with ThreadPoolExecutor(max_workers=len(all_dense_queries) + 1) as pool:
        for i, q in enumerate(all_dense_queries):
            top_k = DENSE_CANDIDATES if i == 0 else 10
            futures_map[pool.submit(_dense_fetch, q, top_k)] = ("dense", i)

        futures_map[pool.submit(_sparse_fetch)] = ("sparse", -1)

        for future in as_completed(futures_map):
            kind, idx = futures_map[future]
            try:
                result = future.result()
            except Exception as exc:
                logger.error(f"[HybridRetriever] Future error ({kind}[{idx}]): {exc}")
                result = []

            if kind == "dense":
                dense_results.extend(result)
            else:
                sparse_results = result

    logger.info(
        f"[HybridRetriever] Dense: {len(dense_results)} | "
        f"Sparse: {len(sparse_results)}"
    )

    # ── RRF Fusion ─────────────────────────────────────────────────────────────
    if not dense_results and not sparse_results:
        logger.warning("[HybridRetriever] Both retrievers returned empty results.")
        return []

    fused = _rrf_fuse(dense_results, sparse_results)
    logger.info(f"[HybridRetriever] After RRF fusion: {len(fused)} candidates")

    # ── Cross-encoder reranking ────────────────────────────────────────────────
    reranked = rerank(query=query, candidates=fused)
    final    = reranked[:top_k_final]

    logger.info(
        f"[HybridRetriever] Final {len(final)} chunks. "
        f"Top rerank_score: {final[0]['rerank_score'] if final else 'N/A'}"
    )
    return final
