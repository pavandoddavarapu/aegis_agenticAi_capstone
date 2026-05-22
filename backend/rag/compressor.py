"""
compressor.py — Contextual Compression (Phase 4)

Problem: Top-8 chunks × 512 tokens = 4096 tokens of mixed signal noise.
Irrelevant surrounding text dilutes the LLM's attention on key evidence.

Solution: Per-chunk sentence-level relevance filtering + token budget control.

Pipeline:
  1. Sentence-level relevance scoring (query ↔ sentence cosine)
  2. Keep sentences above threshold — discard noise
  3. Deduplicate near-identical chunks
  4. Enforce token budget (proportional to rerank_score)

Optimizations (v2):
  - Single batched embed call: all sentences across ALL chunks embedded together.
  - Query vector computed once and reused (via embed_query_list cache).
  - Numpy dot-product cosine for fast vectorised similarity.
"""
import re
from typing import List, Dict

import numpy as np
import tiktoken
from backend.rag.embeddings import embed_query_list, embed_texts
from backend.utils.logger   import logger

# ── Configuration ─────────────────────────────────────────────────────────────
SENTENCE_RELEVANCE_THRESHOLD = 0.30   # cosine threshold per sentence
MAX_CONTEXT_TOKENS           = 3500   # total token budget for context
DEDUP_THRESHOLD              = 0.92   # cosine similarity → near-duplicate

_tokenizer = tiktoken.get_encoding("cl100k_base")


# ── Sentence splitter ─────────────────────────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    """Simple sentence splitter that works without NLTK."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


# ── Fast vectorised cosine ─────────────────────────────────────────────────────

def _cosine_matrix(query_vec: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity of a single query vector against a matrix of row vectors.
    Both query_vec and mat rows assumed pre-normalised (all-MiniLM normalizes by default).
    """
    return mat @ query_vec   # dot product == cosine when pre-normalised


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(chunks: List[Dict], q_vec: List[float]) -> List[Dict]:
    """
    Remove near-duplicate chunks using a single batched embed call.
    All chunk texts are embedded together to avoid N separate calls.
    """
    if len(chunks) <= 1:
        return chunks

    try:
        texts = [c.get("text", "")[:512] for c in chunks]
        vecs  = np.array(embed_texts(texts), dtype=np.float32)
        # Normalise rows so dot product == cosine
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms

        kept = [0]  # always keep the top-scored chunk
        for i in range(1, len(chunks)):
            # Check against all already-kept vectors
            sims = vecs[kept] @ vecs[i]
            if sims.max() < DEDUP_THRESHOLD:
                kept.append(i)

        deduped = [chunks[i] for i in kept]
        removed = len(chunks) - len(deduped)
        if removed:
            logger.info(f"[Compressor] Removed {removed} duplicate chunks.")
        return deduped

    except Exception as exc:
        logger.warning(f"[Compressor] Deduplication failed: {exc}")
        return chunks


# ── Token budget ──────────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    return len(_tokenizer.encode(text))


def _trim_to_tokens(text: str, max_tokens: int) -> str:
    tokens = _tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _tokenizer.decode(tokens[:max_tokens])


# ── Public entry point ────────────────────────────────────────────────────────

def compress_context(query: str, chunks: List[Dict]) -> str:
    """
    Full compression pipeline — all embeddings in ONE batched call:
      1. Embed query + all sentences across all chunks together.
      2. Deduplicate near-identical chunks.
      3. Sentence-level relevance filtering per chunk.
      4. Token budget allocation proportional to rerank_score.
      5. Build final numbered evidence block.

    Args:
        query:  The medical query.
        chunks: Reranked chunk dicts (should have 'rerank_score').

    Returns:
        A formatted, compressed context string ready for the LLM prompt.
    """
    if not chunks:
        return "No evidence retrieved."

    logger.info(f"[Compressor] Compressing {len(chunks)} chunks for query.")

    # ── Step 1: Embed query (cached via lru_cache) ────────────────────────────
    q_vec_list = embed_query_list(query)
    q_vec = np.array(q_vec_list, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm > 0:
        q_vec = q_vec / q_norm

    # ── Step 2: Deduplicate ───────────────────────────────────────────────────
    chunks = deduplicate(chunks, q_vec_list)

    # ── Step 3: Batch-embed ALL sentences across ALL chunks at once ───────────
    # Collect sentences and their chunk ownership
    chunk_sentence_map: List[List[str]] = []
    all_sentences: List[str] = []
    sent_offsets: List[int] = []   # starting index in all_sentences per chunk

    for chunk in chunks:
        sents = _split_sentences(chunk.get("text", ""))
        sent_offsets.append(len(all_sentences))
        chunk_sentence_map.append(sents)
        all_sentences.extend(sents)

    # Single embed call for everything
    if all_sentences:
        try:
            all_vecs = np.array(embed_texts(all_sentences), dtype=np.float32)
            # Pre-normalise
            norms = np.linalg.norm(all_vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            all_vecs = all_vecs / norms
        except Exception as exc:
            logger.warning(f"[Compressor] Batch sentence embed failed: {exc}; keeping full text.")
            all_vecs = None
    else:
        all_vecs = None

    # Assign compressed text per chunk
    for ci, chunk in enumerate(chunks):
        sents = chunk_sentence_map[ci]
        if len(sents) <= 2 or all_vecs is None:
            chunk["compressed_text"] = chunk.get("text", "")
            continue

        offset = sent_offsets[ci]
        s_vecs = all_vecs[offset: offset + len(sents)]
        sims   = _cosine_matrix(q_vec, s_vecs)
        kept   = [s for s, sim in zip(sents, sims) if sim >= SENTENCE_RELEVANCE_THRESHOLD]
        chunk["compressed_text"] = " ".join(kept) if kept else chunk.get("text", "")

    # ── Step 4: Token budget allocation ──────────────────────────────────────
    total_score = sum(c.get("rerank_score", 1.0) for c in chunks) or 1.0
    remaining   = MAX_CONTEXT_TOKENS
    evidence_blocks = []

    for i, chunk in enumerate(chunks, 1):
        if remaining <= 0:
            break
        weight = chunk.get("rerank_score", 1.0) / total_score
        budget = max(int(weight * MAX_CONTEXT_TOKENS), 80)
        budget = min(budget, remaining)

        text      = _trim_to_tokens(chunk["compressed_text"], budget)
        used      = _count_tokens(text)
        remaining -= used

        conf    = chunk.get("confidence", "medium")
        score   = chunk.get("rerank_score", chunk.get("score", 0))
        source  = chunk.get("source", "unknown")
        page    = chunk.get("page", 0)
        section = chunk.get("section") or "general"

        evidence_blocks.append(
            f"[Evidence {i}] "
            f"confidence={conf}, score={score:.3f}, "
            f"source={source}, page={page}, section={section}\n"
            f"{text}"
        )

    context = "\n\n".join(evidence_blocks)
    total_used = MAX_CONTEXT_TOKENS - remaining
    logger.info(
        f"[Compressor] Output: {len(evidence_blocks)} blocks, "
        f"~{total_used} tokens."
    )
    return context
