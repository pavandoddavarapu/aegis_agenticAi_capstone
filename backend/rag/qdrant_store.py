"""
qdrant_store.py — Qdrant vector store interface for the RAG pipeline.

Collection: medical_docs
Payload structure per point:
  {
    "text":          str,     # chunk text
    "source":        str,     # filename
    "page":          int,     # page number
    "section":       str,     # detected medical section or null
    "document_type": str,     # e.g. "medical_report"
    "timestamp":     str,     # ISO 8601 ingestion time
    "chunk_index":   int,     # position in document
    "total_chunks":  int,     # total chunks for this document
  }
"""
import uuid
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from backend.rag.schemas import Chunk
from backend.rag.embeddings import EMBEDDING_DIMENSION
from backend.utils.logger import logger

# ─── Configuration ─────────────────────────────────────────────────────────────
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "medical_docs"

# ─── Qdrant Client Singleton ───────────────────────────────────────────────────
_client: QdrantClient = None


def _get_client() -> QdrantClient:
    """Lazy-initialize Qdrant client as a singleton."""
    global _client
    if _client is None:
        logger.info(f"[Qdrant Store] Connecting to Qdrant at {QDRANT_URL}")
        _client = QdrantClient(url=QDRANT_URL, timeout=60)
    return _client


def ensure_collection() -> None:
    """
    Create the 'medical_docs' collection if it does not exist.
    Called once at pipeline startup.
    """
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in existing:
        logger.info(f"[Qdrant Store] Creating collection '{COLLECTION_NAME}'")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"[Qdrant Store] Collection '{COLLECTION_NAME}' created.")
    else:
        logger.info(f"[Qdrant Store] Collection '{COLLECTION_NAME}' already exists.")


def store_chunks(chunks: List[Chunk], vectors: List[List[float]]) -> int:
    """
    Upsert chunk vectors and payloads into Qdrant.

    Args:
        chunks: List of Chunk objects (text + metadata).
        vectors: Corresponding list of embedding vectors.

    Returns:
        Number of points successfully stored.
    """
    if not chunks or not vectors:
        return 0

    client = _get_client()
    ensure_collection()

    points: List[PointStruct] = []
    for chunk, vector in zip(chunks, vectors):
        payload: Dict[str, Any] = {
            "text":          chunk.text,
            "source":        chunk.source,
            "page":          chunk.page,
            "section":       chunk.section,
            "document_type": chunk.document_type,
            "timestamp":     chunk.timestamp,
            "chunk_index":   chunk.chunk_index,
            "total_chunks":  chunk.total_chunks,
        }
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        ))

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info(f"[Qdrant Store] Stored {len(points)} chunks into '{COLLECTION_NAME}'")
    return len(points)


def search(query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Perform a cosine similarity search in the medical_docs collection.

    Args:
        query_vector: The embedded query vector.
        top_k:        Number of top results to return.

    Returns:
        List of result dicts with score + payload fields.
    """
    client = _get_client()
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        with_vectors=False,
    )

    return [
        {
            "score":   hit.score,
            "payload": hit.payload,
        }
        for hit in results.points
    ]
