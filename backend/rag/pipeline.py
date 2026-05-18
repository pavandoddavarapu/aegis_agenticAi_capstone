"""
pipeline.py — Core ingestion pipeline orchestrator.

Orchestrates the full ingestion flow:
  Extract → Chunk → Embed → Store

This becomes the central ingestion engine.
Called by the Upload API after file type detection.
"""
import os
import tempfile
from typing import List

from backend.rag.schemas import PipelineResult
from backend.rag.chunker import chunk_pages
from backend.rag.embeddings import embed_texts
from backend.rag.qdrant_store import store_chunks
from backend.rag.ingestors.pdf_ingestor import ingest_pdf
from backend.rag.ingestors.image_ingestor import ingest_image
from backend.rag.ingestors.ocr_ingestor import ingest_ocr
from backend.rag.ingestors.dicom_ingestor import ingest_dicom
from backend.utils.logger import logger


def run_pipeline(filepath: str, filename: str, document_type: str) -> PipelineResult:
    """
    Execute the full ingestion pipeline for a single document.

    Steps:
      1. Route to the correct ingestor based on document_type.
      2. Chunk extracted pages using medical-section-aware chunking.
      3. Embed all chunks using the configured embedding model.
      4. Store vectors + payloads in Qdrant.
      5. Return a structured PipelineResult summary.

    Args:
        filepath:      Absolute path to the temporary file on disk.
        filename:      Original uploaded filename (used as source attribution).
        document_type: One of 'pdf' | 'image' | 'dicom'

    Returns:
        PipelineResult with counts and status.
    """
    logger.info(f"[Pipeline] Starting ingestion: '{filename}' (type={document_type})")

    # ── Step 1: Ingest ──────────────────────────────────────────────────────────
    if document_type == "pdf":
        pages = ingest_pdf(filepath, filename)
    elif document_type == "image":
        pages = ingest_image(filepath, filename)
    elif document_type == "dicom":
        pages = ingest_dicom(filepath, filename)
    else:
        # Attempt OCR as fallback for unknown types
        logger.warning(f"[Pipeline] Unknown type '{document_type}', attempting OCR fallback.")
        pages = ingest_ocr(filepath, filename)

    if not pages:
        logger.warning(f"[Pipeline] No pages extracted from '{filename}'")
        return PipelineResult(
            source=filename,
            pages_extracted=0,
            chunks_created=0,
            chunks_stored=0,
            document_type=document_type,
            status="no_content",
        )

    # ── Step 2: Chunk ───────────────────────────────────────────────────────────
    chunks = chunk_pages(pages)
    if not chunks:
        logger.warning(f"[Pipeline] Chunking produced 0 chunks for '{filename}'")
        return PipelineResult(
            source=filename,
            pages_extracted=len(pages),
            chunks_created=0,
            chunks_stored=0,
            document_type=document_type,
            status="no_chunks",
        )

    # ── Step 3: Embed ───────────────────────────────────────────────────────────
    chunk_texts = [c.text for c in chunks]
    vectors = embed_texts(chunk_texts)

    # ── Step 4: Store ───────────────────────────────────────────────────────────
    stored = store_chunks(chunks, vectors)

    logger.info(
        f"[Pipeline] Completed '{filename}': "
        f"{len(pages)} pages → {len(chunks)} chunks → {stored} stored"
    )

    return PipelineResult(
        source=filename,
        pages_extracted=len(pages),
        chunks_created=len(chunks),
        chunks_stored=stored,
        document_type=document_type,
        status="success",
    )
