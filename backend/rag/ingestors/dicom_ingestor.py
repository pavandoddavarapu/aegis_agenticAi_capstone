"""
dicom_ingestor.py — PLACEHOLDER for DICOM medical imaging ingestion.

Future responsibilities:
  - Load DICOM files (.dcm) using pydicom
  - Extract structured patient metadata (without PII in payload)
  - Extract radiology report text from DICOM tags
  - Decode pixel arrays for vision model input
  - Support series and study-level aggregation

Planned integrations:
  - pydicom (DICOM file parsing)
  - SimpleITK (volumetric medical image processing)
  - Cornerstone.js (frontend DICOM viewer)
  - Radiology AI models (for CT/MRI/X-Ray classification)

Status: MULTIMODAL-READY PLACEHOLDER
"""
from typing import List
from backend.rag.schemas import ExtractedPage
from backend.utils.logger import logger


def ingest_dicom(filepath: str, filename: str) -> List[ExtractedPage]:
    """
    Placeholder for DICOM radiology ingestion pipeline.

    Future implementation will:
      1. Load .dcm file using pydicom
      2. Extract DICOM metadata tags (modality, study date, body part)
      3. Extract embedded report text (tag 0040,A730 or 0008,103E)
      4. Decode pixel arrays for imaging AI models
      5. Store de-identified metadata with the embedding

    Args:
        filepath: Absolute path to the DICOM file.
        filename: Original filename (.dcm).

    Returns:
        Empty list until implemented.
    """
    logger.warning(
        f"[DICOM Ingestor] DICOM ingestion not yet implemented for '{filename}'. "
        "Returning empty result. Will be implemented with pydicom + radiology AI."
    )
    return []
