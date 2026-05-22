"""
embeddings.py — Modular text embedding engine for the RAG pipeline.

Model: OpenAI text-embedding-3-small (via API)
  - Blazing fast API, zero local GPU requirements.
  - Dimensions truncated to 384 to maintain compatibility with existing Qdrant schemas.
"""
from typing import List
from functools import lru_cache
import os

from openai import OpenAI
from backend.utils.logger import logger

# ─── Model Configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSION = 384

# ─── Singleton model loader ────────────────────────────────────────────────────
_client: OpenAI = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        logger.info("[Embeddings] Initializing OpenAI Client for embeddings")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_key":
            logger.warning("[Embeddings] OPENAI_API_KEY is missing or invalid in .env! This will fail.")
        _client = OpenAI(api_key=api_key)
    return _client

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate dense vector embeddings for a list of text strings using OpenAI.
    """
    if not texts:
        return []

    client = _get_client()
    logger.info(f"[Embeddings] Calling OpenAI API to embed {len(texts)} text(s)...")
    
    try:
        response = client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL_NAME,
            dimensions=EMBEDDING_DIMENSION
        )
        # Sort results by index just in case OpenAI returns out of order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        vectors = [item.embedding for item in sorted_data]
        logger.info(f"[Embeddings] Done. Extracted {len(vectors)} vectors.")
        return vectors
    except Exception as e:
        logger.error(f"[Embeddings] OpenAI API Error: {e}")
        return []

@lru_cache(maxsize=512)
def embed_query(query: str) -> tuple:
    result = embed_texts([query])
    return tuple(result[0]) if result else ()

def embed_query_list(query: str) -> List[float]:
    return list(embed_query(query))
