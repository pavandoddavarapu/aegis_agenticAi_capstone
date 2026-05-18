"""
ocr_ingestor.py — PLACEHOLDER for OCR-based document ingestion.

Future responsibilities:
  - Scanned medical document processing
  - Handwritten clinical note digitization
  - Layout-aware OCR for forms and tables

Planned integrations:
  - PaddleOCR (fast, multilingual)
  - Tesseract (open source, reliable)
  - Azure Document Intelligence (for structured forms)
  - AWS Textract (for clinical document layouts)

Status: MULTIMODAL-READY PLACEHOLDER
"""
from typing import List
from backend.rag.schemas import ExtractedPage
from backend.utils.logger import logger


def ingest_ocr(filepath: str, filename: str) -> List[ExtractedPage]:
    """
    Placeholder for OCR-based ingestion pipeline.

    Future implementation will:
      1. Load scanned PDF or image
      2. Run layout detection (DocLayout-YOLO or PaddleOCR layout)
      3. Apply OCR engine per region
      4. Reassemble structured text with page context

    Args:
        filepath: Absolute path to the scanned file.
        filename: Original filename.

    Returns:
        Empty list until implemented.
    """
    logger.warning(
        f"[OCR Ingestor] OCR ingestion not yet implemented for '{filename}'. "
        "Returning empty result. Will be implemented with PaddleOCR / Tesseract."
    )
    return []
