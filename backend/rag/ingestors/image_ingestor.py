"""
image_ingestor.py — PLACEHOLDER for medical image ingestion.

Future responsibilities:
  - Medical photograph extraction
  - Clinical image preprocessing
  - Integration with vision models (GPT-4V, LLaVA, MedVLP)
  - Image captioning for RAG context injection

Status: MULTIMODAL-READY PLACEHOLDER
"""
from typing import List
from backend.rag.schemas import ExtractedPage
from backend.utils.logger import logger


def ingest_image(filepath: str, filename: str) -> List[ExtractedPage]:
    """
    Placeholder for image ingestion pipeline.

    Future implementation will:
      1. Load image using Pillow
      2. Run OCR (PaddleOCR / Tesseract)
      3. Optionally run vision LLM for captioning
      4. Return structured page text

    Args:
        filepath: Absolute path to the image file.
        filename: Original filename.

    Returns:
        Empty list until implemented.
    """
    logger.warning(
        f"[Image Ingestor] Image ingestion not yet implemented for '{filename}'. "
        "Returning empty result. This will be implemented with OCR + vision model support."
    )
    return []
