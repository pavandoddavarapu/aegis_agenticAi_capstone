"""
bm25_store.py — Sparse BM25 retrieval engine (Phase 4)

Complements dense Qdrant retrieval with exact keyword matching.
Critical for medical queries with precise terminology:
  "metformin 1000mg", "ICD-10 E11.65", "SGLT2 inhibitor"
  — terms that dense embeddings may dilute.

Strategy:
  - Corpus loaded lazily from Qdrant on first search.
  - In-memory BM25 index (rank_bm25).
  - Auto-refreshes every REFRESH_INTERVAL_SECONDS.
  - Medical-aware tokenizer preserves compound terms.
"""
import re
import time
import threading
from typing import List, Tuple, Dict, Any

from rank_bm25 import BM25Okapi
from backend.utils.logger import logger

# ── Configuration ─────────────────────────────────────────────────────────────
REFRESH_INTERVAL_SECONDS = 1800   # rebuild every 30 min
MAX_BM25_DOCS            = 50_000  # cap corpus size


# ── Medical tokenizer ─────────────────────────────────────────────────────────

def _medical_tokenize(text: str) -> List[str]:
    """
    Tokenizer that preserves medical compound terms.
    Examples kept intact: 'type-2-diabetes', 'ACE-inhibitor', 'HbA1c'
    """
    text   = text.lower()
    tokens = re.findall(r"[a-z0-9]+(?:[-/][a-z0-9]+)*", text)
    # Also split on camelCase-style medical abbreviations
    expanded = []
    for t in tokens:
        if len(t) > 1:
            expanded.append(t)
    return expanded


# ── BM25 Index Singleton ──────────────────────────────────────────────────────

class BM25Store:
    """Thread-safe BM25 index with lazy loading and auto-refresh."""

    def __init__(self):
        self._bm25:        BM25Okapi | None = None
        self._corpus:      List[str]        = []
        self._payloads:    List[Dict]       = []
        self._last_built:  float            = 0.0
        self._lock         = threading.Lock()

    # ── Index building ────────────────────────────────────────────────────────

    def _needs_refresh(self) -> bool:
        return (time.time() - self._last_built) > REFRESH_INTERVAL_SECONDS

    def build_from_qdrant(self, limit: int = MAX_BM25_DOCS) -> int:
        """Load corpus from Qdrant and build BM25 index."""
        from backend.rag.qdrant_store import _get_client, COLLECTION_NAME

        logger.info("[BM25] Building index from Qdrant corpus...")
        client = _get_client()

        try:
            # Scroll all points from Qdrant
            records, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.error(f"[BM25] Qdrant scroll failed: {exc}")
            return 0

        corpus   = []
        payloads = []
        for record in records:
            text = record.payload.get("text", "")
            if text.strip():
                corpus.append(text)
                payloads.append({**record.payload, "_qdrant_id": str(record.id)})

        if not corpus:
            logger.warning("[BM25] Empty corpus — BM25 index not built.")
            return 0

        tokenized      = [_medical_tokenize(t) for t in corpus]
        self._bm25     = BM25Okapi(tokenized, k1=1.5, b=0.75)
        self._corpus   = corpus
        self._payloads = payloads
        self._last_built = time.time()

        logger.info(f"[BM25] Index built with {len(corpus)} documents.")
        return len(corpus)

    def _ensure_index(self):
        """Build or refresh index if needed (thread-safe)."""
        if self._bm25 is None or self._needs_refresh():
            with self._lock:
                if self._bm25 is None or self._needs_refresh():
                    self.build_from_qdrant()

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        BM25 keyword search.

        Returns:
            List of dicts with 'payload' and 'bm25_score' keys.
        """
        self._ensure_index()

        if self._bm25 is None:
            logger.warning("[BM25] Index unavailable — returning empty.")
            return []

        tokens = _medical_tokenize(query)
        if not tokens:
            return []

        scores  = self._bm25.get_scores(tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]

        results = []
        for idx in top_idx:
            if scores[idx] <= 0:
                continue
            results.append({
                "payload":    self._payloads[idx],
                "bm25_score": float(scores[idx]),
            })

        logger.info(f"[BM25] Query '{query[:50]}' → {len(results)} results")
        return results

    def invalidate(self):
        """Force rebuild on next search (call after new ingestion)."""
        self._last_built = 0.0
        logger.info("[BM25] Index marked for rebuild.")


# ── Module-level singleton ────────────────────────────────────────────────────
bm25_store = BM25Store()
