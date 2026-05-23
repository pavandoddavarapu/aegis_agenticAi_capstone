"""
embeddings.py — Modular text embedding engine for the RAG pipeline.

Model: all-MiniLM-L6-v2 (Local via SentenceTransformers)
  - Replaces OpenAI to avoid 'insufficient_quota' billing errors.
  - Generates 384-dimensional embeddings (matches existing Qdrant schemas).
"""
from typing import List
from functools import lru_cache
import os

from sentence_transformers import SentenceTransformer
from backend.utils.logger import logger

# ─── Model Configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# ─── Singleton model loader ────────────────────────────────────────────────────
_model: SentenceTransformer = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"[Embeddings] Loading local model: {EMBEDDING_MODEL_NAME}")
        # Automatically downloads and caches the model
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate dense vector embeddings for a list of text strings locally.
    """
    if not texts:
        return []

    model = _get_model()
    logger.info(f"[Embeddings] Generating local embeddings for {len(texts)} text(s)...")
    
    try:
        # Generate embeddings (returns numpy array)
        embeddings = model.encode(texts, convert_to_numpy=True)
        # Convert to list of python floats
        vectors = embeddings.tolist()
        logger.info(f"[Embeddings] Done. Extracted {len(vectors)} vectors locally.")
        return vectors
    except Exception as e:
        logger.error(f"[Embeddings] Local Embedding Error: {e}")
        return []

@lru_cache(maxsize=512)
def embed_query(query: str) -> tuple:
    result = embed_texts([query])
    return tuple(result[0]) if result else ()

def embed_query_list(query: str) -> List[float]:
    return list(embed_query(query))
