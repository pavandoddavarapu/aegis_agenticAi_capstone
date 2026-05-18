from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime


# ─── Ingestion Schemas ─────────────────────────────────────────────────────────

class ExtractedPage(BaseModel):
    """Raw extracted page from any ingestor."""
    page: int
    text: str
    source: str
    document_type: str = "medical_report"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A single semantic/section-aware text chunk with full provenance."""
    chunk_id: str
    text: str
    source: str
    page: int
    section: Optional[str] = None
    document_type: str = "medical_report"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Retrieval Schemas ─────────────────────────────────────────────────────────

class RetrievalResult(BaseModel):
    """A single retrieved evidence chunk with confidence."""
    text: str
    score: float
    confidence: str           # "high" / "medium" / "low"
    source: str
    page: int
    section: Optional[str] = None
    document_type: str
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    """Full retrieval API response payload."""
    query: str
    results: List[RetrievalResult]
    total_results: int
    retrieval_metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Upload Schemas ─────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Response returned after a successful document upload."""
    status: str
    filename: str
    document_type: str
    chunks_stored: int
    message: str


# ─── Pipeline Schemas ───────────────────────────────────────────────────────────

class PipelineResult(BaseModel):
    """Summary result returned by the pipeline orchestrator."""
    source: str
    pages_extracted: int
    chunks_created: int
    chunks_stored: int
    document_type: str
    status: str = "success"
