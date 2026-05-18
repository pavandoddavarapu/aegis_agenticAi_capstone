"""
retriever.py — Evidence retrieval engine for medical queries.

For every retrieved chunk:
  - similarity score (raw cosine)
  - confidence label ("high" / "medium" / "low")
  - full source attribution
  - section context

These power validation agents, reflection loops,
and adaptive routing — later.
"""
from typing import List
from backend.rag.embeddings import embed_query
from backend.rag.qdrant_store import search
from backend.rag.schemas import RetrievalResult, RetrievalResponse
from backend.rag.utils import confidence_label
from backend.utils.logger import logger


def retrieve_evidence(query: str, top_k: int = 5) -> RetrievalResponse:
    """
    Retrieve the top-k most relevant medical evidence chunks for a query.

    Pipeline:
      1. Embed the query using the same model used at ingestion.
      2. Search Qdrant for nearest cosine neighbors.
      3. Attach confidence labels to each result.
      4. Return structured RetrievalResponse.

    Args:
        query: Natural language medical query.
        top_k: Number of evidence chunks to return.

    Returns:
        RetrievalResponse with results, scores, confidence, and source metadata.
    """
    logger.info(f"[Retriever] Query: '{query}' | top_k={top_k}")

    # Step 1: Embed the query
    query_vector = embed_query(query)
    if not query_vector:
        logger.error("[Retriever] Failed to embed query.")
        return RetrievalResponse(
            query=query,
            results=[],
            total_results=0,
            retrieval_metadata={"error": "Embedding failed"},
        )

    # Step 2: Search Qdrant
    raw_results = search(query_vector, top_k=top_k)
    logger.info(f"[Retriever] Found {len(raw_results)} results")

    # Step 3: Build structured results with confidence
    results: List[RetrievalResult] = []
    for hit in raw_results:
        payload = hit["payload"]
        score = hit["score"]

        results.append(RetrievalResult(
            text=payload.get("text", ""),
            score=round(score, 4),
            confidence=confidence_label(score),
            source=payload.get("source", "unknown"),
            page=payload.get("page", 0),
            section=payload.get("section"),
            document_type=payload.get("document_type", "medical_report"),
            timestamp=payload.get("timestamp", ""),
            metadata={
                "chunk_index":  payload.get("chunk_index"),
                "total_chunks": payload.get("total_chunks"),
            },
        ))

    return RetrievalResponse(
        query=query,
        results=results,
        total_results=len(results),
        retrieval_metadata={
            "model":   "sentence-transformers/all-MiniLM-L6-v2",
            "top_k":   top_k,
            "collection": "medical_docs",
        },
    )
