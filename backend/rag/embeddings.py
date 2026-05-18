"""
embeddings.py — Modular text embedding engine for the RAG pipeline.

Initial model: sentence-transformers/all-MiniLM-L6-v2
  - Fast, free, lightweight
  - 384-dimensional dense vectors
  - Excellent for semantic similarity on medical text

Design: Keep fully modular — swap model in one place later.
Future models:
  - pritamdeka/S-PubMedBert-MS-MARCO (domain-specific medical)
  - OpenAI text-embedding-3-small (via API)
  - Cohere embed-v3-medical
"""
from typing import List
from sentence_transformers import SentenceTransformer
from backend.utils.logger import logger

# ─── Model Configuration ───────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# ─── Singleton model loader ────────────────────────────────────────────────────
_model: SentenceTransformer = None


def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model as a singleton to avoid repeated init."""
    global _model
    if _model is None:
        logger.info(f"[Embeddings] Loading model: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info(f"[Embeddings] Model loaded. Dimension: {EMBEDDING_DIMENSION}")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate dense vector embeddings for a list of text strings.

    Args:
        texts: List of text strings to embed (e.g. chunk texts).

    Returns:
        List of float vectors, one per input text.
    """
    if not texts:
        return []

    model = _get_model()
    logger.info(f"[Embeddings] Embedding {len(texts)} text(s)...")
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    logger.info(f"[Embeddings] Done. Shape: {vectors.shape}")
    return vectors.tolist()


def embed_query(query: str) -> List[float]:
    """
    Embed a single query string for similarity search.

    Args:
        query: The user's natural language medical query.

    Returns:
        A single float vector (384 dimensions).
    """
    result = embed_texts([query])
    return result[0] if result else []
