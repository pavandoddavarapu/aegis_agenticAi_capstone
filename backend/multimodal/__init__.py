"""
backend/multimodal — Phase 8: Multimodal Clinical Intelligence

Modality-aware orchestration subsystem.
Routes images to correct pipelines, extracts clinical findings,
and integrates with the existing hybrid retrieval infrastructure.

Modalities supported:
  - OCR: Scanned reports, prescriptions, discharge summaries
  - ECG: Waveform interpretation, rhythm analysis, ST-changes
  - Radiology: X-ray, CT, MRI, Ultrasound observation extraction

Integration:
  - Findings feed into graph, semantic, and research retrieval
  - Temporary visual context injected into agent state
  - Modality-aware validation with confidence gating
"""
from backend.multimodal.modality_classifier import ModalityClassifier, Modality
from backend.multimodal.image_ingestor import ImageIngestor

__all__ = ["ModalityClassifier", "Modality", "ImageIngestor"]
