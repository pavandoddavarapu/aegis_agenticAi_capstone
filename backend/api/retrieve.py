"""
retrieve.py — Evidence Retrieval API.

POST /retrieve
  Input:  { "query": "Signs of myocardial infarction", "top_k": 5 }
  Output: Evidence chunks with scores, confidence, and source attribution.

These results later feed:
  - Validation agents
  - Reflection loops
  - Adaptive routing
  - Decision layers
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.rag.retriever import retrieve_evidence
from backend.rag.schemas import RetrievalResponse
from backend.utils.logger import logger

router = APIRouter(prefix="/retrieve", tags=["retrieve"])


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language medical query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of evidence chunks to return")


@router.post("/", response_model=RetrievalResponse)
def retrieve(request: RetrievalRequest):
    """
    Retrieve the most relevant medical evidence chunks for a given query.

    Uses cosine similarity search over the Qdrant 'medical_docs' collection.
    Every result includes:
      - text:       The relevant evidence passage
      - score:      Raw cosine similarity (0.0 – 1.0)
      - confidence: "high" / "medium" / "low" label
      - source:     Filename of origin document
      - page:       Page number within the document
      - section:    Detected medical section (e.g. "diagnosis", "findings")
    """
    logger.info(f"[Retrieve API] Query: '{request.query}' | top_k={request.top_k}")

    try:
        response = retrieve_evidence(query=request.query, top_k=request.top_k)
    except Exception as e:
        logger.error(f"[Retrieve API] Retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval error: {str(e)}")

    logger.info(f"[Retrieve API] Returning {response.total_results} results")
    return response
