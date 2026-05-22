"""
multimodal_api.py — Multimodal Clinical Intelligence API Endpoint (Phase 8)

Provides:
  POST /api/v1/analyze-image
    Accepts an uploaded image file + optional clinical query.
    Runs the full multimodal ingestion pipeline and returns:
      - Modality classification
      - Pipeline findings (OCR / ECG / Radiology)
      - Emergency flag
      - Retrieval query derived from visual findings
      - Visual context block

  POST /api/v1/query-with-image
    Accepts image + query and runs the FULL LangGraph agentic pipeline
    with multimodal context injection.

Design:
  - Images are processed in-memory (never persisted to disk)
  - Only analysis results are returned (not image bytes)
  - Emergency flags surface immediately in response metadata
  - All responses include explicit AI disclaimer
"""
from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.multimodal.image_ingestor import ImageIngestor
from backend.utils.logger import logger

router = APIRouter(prefix="/api/v1", tags=["Multimodal Clinical Intelligence"])


# ── Response models ───────────────────────────────────────────────────────────

class ImageAnalysisResponse(BaseModel):
    filename:            str
    modality:            str
    modality_confidence: float
    analysis_confidence: float
    emergency_flag:      bool
    emergency_reason:    Optional[str]
    visual_context:      str
    retrieval_query:     str
    pipeline_used:       str
    image_hash:          str
    warnings:            list[str]
    disclaimer:          str = (
        "These findings are AI-assisted observations only and do NOT constitute "
        "a clinical diagnosis. All findings require verification by a qualified "
        "medical professional."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/analyze-image",
    response_model=ImageAnalysisResponse,
    summary="Analyze a medical image (ECG / X-ray / Scanned Report)",
    description=(
        "Accepts an uploaded medical image (PNG/JPG/JPEG), classifies its modality, "
        "and runs the appropriate clinical intelligence pipeline (OCR, ECG, Radiology). "
        "Returns structured AI observations — NOT a clinical diagnosis."
    ),
)
async def analyze_image(
    file: UploadFile = File(..., description="Medical image file (PNG/JPG/JPEG)"),
    query: Optional[str] = Form(
        None,
        description="Optional clinical query to contextualize the image analysis",
    ),
) -> ImageAnalysisResponse:
    """Analyze a medical image through the multimodal intelligence pipeline."""

    # Validate file type
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "application/octet-stream"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Accepted: PNG, JPG, JPEG",
        )

    # Validate file size (max 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large. Maximum size: 10MB",
        )

    logger.info(
        f"[MultimodalAPI] Image upload: filename={file.filename} "
        f"size={len(contents)} bytes query='{(query or '')[:60]}'"
    )

    try:
        ingestor = ImageIngestor()
        result   = await ingestor.ingest(
            image_bytes    = contents,
            filename       = file.filename or "upload",
            original_query = query or "",
        )

        if result.emergency_flag:
            logger.warning(
                f"[MultimodalAPI] ⚠ EMERGENCY FLAG: {result.emergency_reason} "
                f"for file {file.filename}"
            )

        return ImageAnalysisResponse(
            filename            = result.filename,
            modality            = result.modality.value,
            modality_confidence = result.modality_confidence,
            analysis_confidence = result.analysis_confidence,
            emergency_flag      = result.emergency_flag,
            emergency_reason    = result.emergency_reason,
            visual_context      = result.visual_context,
            retrieval_query     = result.retrieval_query,
            pipeline_used       = result.pipeline_used,
            image_hash          = result.image_hash,
            warnings            = result.warnings,
        )

    except Exception as exc:
        logger.exception(f"[MultimodalAPI] Image analysis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image analysis pipeline failed: {str(exc)}",
        )
