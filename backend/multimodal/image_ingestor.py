"""
image_ingestor.py — Multimodal Image Ingestion System (Phase 8)

Architecture:
  Central entry point for all image inputs.
  Accepts raw image bytes, classifies modality, routes to the
  appropriate pipeline, and returns a unified ImageAnalysisResult
  with:
    - Modality classification + confidence
    - Pipeline-specific findings (OcrResult | EcgFindings | RadiologyFindings)
    - Structured visual_context block ready for agent state injection
    - Emergency escalation flag and reason
    - Retrieval query derived from visual findings (for downstream RAG)
    - Provenance metadata (filename, mime type, size, timestamp)

  Routing:
    Modality.OCR_REPORT       → OcrPipeline
    Modality.OCR_PRESCRIPTION → OcrPipeline (prescription mode)
    Modality.ECG              → EcgPipeline
    Modality.RADIOLOGY        → RadiologyPipeline
    Modality.PATHOLOGY        → OcrPipeline (general text extraction)
    Modality.UNKNOWN          → OcrPipeline (best-effort extraction)

  Safety principles:
    1. Every result has an explicit confidence score.
    2. Emergency flags propagate to the top-level result immediately.
    3. All visual findings are clearly labelled as AI-assisted.
    4. Raw image bytes are NEVER stored; only analysis results persist.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from backend.multimodal.modality_classifier import ModalityClassifier, Modality
from backend.multimodal.ocr_pipeline        import OcrPipeline, OcrResult
from backend.multimodal.ecg_pipeline        import EcgPipeline, EcgFindings
from backend.multimodal.radiology_pipeline  import RadiologyPipeline, RadiologyFindings
from backend.utils.logger                   import logger


# ── Unified analysis result ───────────────────────────────────────────────────

@dataclass
class ImageAnalysisResult:
    """Unified result from any image modality pipeline."""
    filename:           str
    modality:           Modality
    modality_confidence: float

    # Pipeline-specific result (type varies by modality)
    pipeline_result:    Optional[Union[OcrResult, EcgFindings, RadiologyFindings]] = None

    # Formatted context blocks
    visual_context:     str          = ""   # Ready for agent state injection
    retrieval_query:    str          = ""   # Query for downstream RAG augmentation

    # Emergency escalation
    emergency_flag:     bool         = False
    emergency_reason:   Optional[str] = None

    # Overall quality
    analysis_confidence: float       = 0.0
    warnings:            List[str]   = field(default_factory=list)

    # Provenance
    image_hash:         str          = ""
    file_size_bytes:    int          = 0
    analyzed_at:        str          = ""
    pipeline_used:      str          = ""


# ── Retrieval query derivation ────────────────────────────────────────────────

def _derive_retrieval_query(
    modality: Modality,
    result: Optional[Union[OcrResult, EcgFindings, RadiologyFindings]],
    original_query: str = "",
) -> str:
    """Generate a downstream RAG query from visual findings."""
    if modality in (Modality.OCR_REPORT, Modality.OCR_PRESCRIPTION, Modality.PATHOLOGY, Modality.UNKNOWN):
        if isinstance(result, OcrResult) and result.cleaned_text:
            # Use first 300 chars of cleaned text as retrieval seed
            return result.cleaned_text[:300].replace("\n", " ")

    elif modality == Modality.ECG:
        if isinstance(result, EcgFindings):
            parts = []
            if result.rhythm:      parts.append(result.rhythm)
            if result.st_changes and "no obvious" not in result.st_changes.lower():
                parts.append(result.st_changes)
            if result.arrhythmia_flags:
                parts.extend(result.arrhythmia_flags[:2])
            if parts:
                return f"ECG findings: {', '.join(parts)} — clinical significance and management"

    elif modality == Modality.RADIOLOGY:
        if isinstance(result, RadiologyFindings):
            pipeline = RadiologyPipeline()
            return pipeline.generate_retrieval_query(result)

    return original_query or "clinical findings significance and management"


# ── Main Image Ingestor ───────────────────────────────────────────────────────

class ImageIngestor:
    """
    Central multimodal image ingestion and routing engine.

    Usage:
        ingestor = ImageIngestor()
        result = await ingestor.ingest(image_bytes, filename="chest_xray.jpg")
        # result.visual_context → inject into agent state
        # result.retrieval_query → use for downstream RAG
        # result.emergency_flag → route to emergency workflow if True
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key      = api_key or os.getenv("OPENAI_API_KEY", "")
        self._classifier   = ModalityClassifier()
        self._ocr          = OcrPipeline(api_key=self._api_key)
        self._ecg          = EcgPipeline(api_key=self._api_key)
        self._radiology    = RadiologyPipeline(api_key=self._api_key)

    async def ingest(
        self,
        image_bytes:    bytes,
        filename:       str = "upload",
        original_query: str = "",
    ) -> ImageAnalysisResult:
        """
        Full ingestion pipeline:
          1. Encode image to base64
          2. Classify modality
          3. Route to appropriate pipeline
          4. Assemble unified result

        Args:
            image_bytes:    Raw image bytes (PNG / JPG / JPEG)
            filename:       Original filename (used for heuristic classification)
            original_query: The clinical query associated with this image
        """
        logger.info(f"[ImageIngestor] Ingesting '{filename}' ({len(image_bytes)} bytes)")

        # Compute provenance hash
        image_hash    = hashlib.sha256(image_bytes).hexdigest()[:16]
        analyzed_at   = datetime.now(timezone.utc).isoformat()
        image_b64     = base64.b64encode(image_bytes).decode("utf-8")

        # Step 1: Classify modality
        modality, modality_confidence = await self._classifier.classify(filename, image_b64)
        logger.info(f"[ImageIngestor] Classified as {modality.value} (conf={modality_confidence:.2f})")

        # Step 2: Route to pipeline
        pipeline_result  = None
        visual_context   = ""
        analysis_confidence = 0.0
        pipeline_used    = "none"
        warnings: List[str] = []

        try:
            if modality == Modality.ECG:
                pipeline_used   = "ecg_pipeline"
                ecg_findings    = await self._ecg.analyze(image_b64)
                pipeline_result = ecg_findings
                visual_context  = self._ecg.to_context_block(ecg_findings)
                analysis_confidence = ecg_findings.confidence
                warnings.extend(ecg_findings.warnings)

            elif modality == Modality.RADIOLOGY:
                pipeline_used    = "radiology_pipeline"
                rad_findings     = await self._radiology.analyze(image_b64, filename)
                pipeline_result  = rad_findings
                visual_context   = self._radiology.to_context_block(rad_findings)
                analysis_confidence = rad_findings.confidence
                warnings.extend(rad_findings.warnings)

            else:
                # OCR pipeline for: OCR_REPORT, OCR_PRESCRIPTION, PATHOLOGY, UNKNOWN
                pipeline_used   = "ocr_pipeline"
                ocr_result      = await self._ocr.extract(image_bytes, image_b64)
                pipeline_result = ocr_result
                visual_context  = self._ocr.to_context_block(ocr_result)
                analysis_confidence = ocr_result.confidence
                warnings.extend(ocr_result.warnings)

        except Exception as exc:
            logger.exception(f"[ImageIngestor] Pipeline execution failed: {exc}")
            warnings.append(f"Pipeline error: {exc}")

        # Step 3: Derive retrieval query from visual findings
        retrieval_query = _derive_retrieval_query(modality, pipeline_result, original_query)

        # Step 4: Extract emergency flags
        emergency_flag   = False
        emergency_reason = None

        if isinstance(pipeline_result, EcgFindings):
            emergency_flag   = pipeline_result.emergency_flag
            emergency_reason = pipeline_result.emergency_reason
        elif isinstance(pipeline_result, RadiologyFindings):
            emergency_flag   = pipeline_result.emergency_flag
            emergency_reason = pipeline_result.emergency_reason

        result = ImageAnalysisResult(
            filename=filename,
            modality=modality,
            modality_confidence=modality_confidence,
            pipeline_result=pipeline_result,
            visual_context=visual_context,
            retrieval_query=retrieval_query,
            emergency_flag=emergency_flag,
            emergency_reason=emergency_reason,
            analysis_confidence=analysis_confidence,
            warnings=warnings,
            image_hash=image_hash,
            file_size_bytes=len(image_bytes),
            analyzed_at=analyzed_at,
            pipeline_used=pipeline_used,
        )

        logger.info(
            f"[ImageIngestor] Ingestion complete: modality={modality.value} "
            f"pipeline={pipeline_used} confidence={analysis_confidence:.2f} "
            f"emergency={emergency_flag}"
        )
        return result

    def to_state_dict(self, result: ImageAnalysisResult) -> Dict[str, Any]:
        """Convert ingestion result to partial AgentState dict."""
        return {
            "visual_context":       result.visual_context,
            "image_modality":       result.modality.value,
            "image_confidence":     result.analysis_confidence,
            "image_emergency_flag": result.emergency_flag,
            "image_emergency_reason": result.emergency_reason or "",
            "retrieval_query_override": result.retrieval_query,
        }
