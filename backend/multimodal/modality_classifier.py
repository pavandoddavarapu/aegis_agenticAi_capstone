"""
modality_classifier.py — Multimodal Modality Classifier (Phase 8)

Architecture:
  Inspects uploaded images and determines which clinical pipeline
  should process them. Uses a combination of:
    1. Filename and MIME-type heuristics (cheap, instant)
    2. GPT-4o Vision zero-shot classification (authoritative fallback)

  This is the router/dispatcher for the entire multimodal subsystem.
  Modality determines:
    - which OCR/vision pipeline executes
    - which orchestration workflow is selected
    - which risk level is assigned
    - which evidence retrieval follows

Modalities:
  OCR_REPORT     → scanned clinical document (discharge summary, pathology)
  OCR_PRESCRIPTION → handwritten or printed prescription
  ECG            → electrocardiogram waveform image
  RADIOLOGY      → X-ray, CT, MRI, ultrasound screenshot
  PATHOLOGY      → histology slide or pathology report image
  UNKNOWN        → could not classify; falls back to generic OCR
"""
from __future__ import annotations

import base64
import io
import os
import re
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from backend.utils.logger import logger


# ── Modality taxonomy ─────────────────────────────────────────────────────────

class Modality(str, Enum):
    OCR_REPORT       = "ocr_report"       # Scanned clinical document
    OCR_PRESCRIPTION = "ocr_prescription" # Rx / medication prescription
    ECG              = "ecg"              # Electrocardiogram waveform
    RADIOLOGY        = "radiology"        # X-ray / CT / MRI / ultrasound
    PATHOLOGY        = "pathology"        # Histology / pathology image
    UNKNOWN          = "unknown"          # Fallback — generic OCR


# ── Keyword-based heuristic classifier ───────────────────────────────────────

_FILENAME_SIGNALS: Dict[Modality, list[str]] = {
    Modality.ECG:          ["ecg", "ekg", "electrocardiogram", "cardiac_trace", "waveform"],
    Modality.RADIOLOGY:    ["xray", "x-ray", "chest_ap", "mri", "ct_scan", "ct-scan",
                            "ultrasound", "sono", "fetus", "dicom"],
    Modality.PATHOLOGY:    ["histology", "pathology", "biopsy", "slide", "stain", "hem"],
    Modality.OCR_PRESCRIPTION: ["rx", "prescription", "script", "medication_order"],
    Modality.OCR_REPORT:   ["report", "discharge", "summary", "note", "clinical", "lab"],
}


def _classify_by_filename(filename: str) -> Optional[Modality]:
    """Fast heuristic: scan filename for modality signals."""
    lower = filename.lower().replace(" ", "_")
    for modality, signals in _FILENAME_SIGNALS.items():
        if any(sig in lower for sig in signals):
            return modality
    return None


# ── Vision-based classifier via GPT-4o ───────────────────────────────────────

_VISION_CLASSIFY_PROMPT = """You are a medical image triage specialist.
Classify the uploaded image into EXACTLY ONE of these categories:
  - ecg (electrocardiogram / cardiac rhythm strip)
  - radiology (X-ray, CT, MRI, ultrasound)
  - pathology (histology slide, microscopy image)
  - ocr_prescription (printed or handwritten prescription)
  - ocr_report (medical report, discharge summary, lab result)
  - unknown (cannot determine)

Respond with ONLY the category string. No explanation. No punctuation.
"""


async def _classify_via_vision(image_b64: str, api_key: str) -> Optional[Modality]:
    """Use GPT-4o vision to classify modality when heuristics fail."""
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o",
            "max_tokens": 10,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text",       "text": _VISION_CLASSIFY_PROMPT},
                        {"type": "image_url",  "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip().lower()
            # Map response to Modality
            mapping = {
                "ecg":              Modality.ECG,
                "radiology":        Modality.RADIOLOGY,
                "pathology":        Modality.PATHOLOGY,
                "ocr_prescription": Modality.OCR_PRESCRIPTION,
                "ocr_report":       Modality.OCR_REPORT,
                "unknown":          Modality.UNKNOWN,
            }
            return mapping.get(raw, Modality.UNKNOWN)
    except Exception as exc:
        logger.warning(f"[ModalityClassifier] Vision classification failed: {exc}")
        return None


# ── Public classifier interface ───────────────────────────────────────────────

class ModalityClassifier:
    """
    Two-stage modality classifier.

    Stage 1: Filename-based heuristics (0 ms, no API cost)
    Stage 2: GPT-4o Vision zero-shot (fallback, ~500 ms)
    """

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY", "")

    async def classify(
        self,
        filename: str,
        image_b64: Optional[str] = None,
    ) -> Tuple[Modality, float]:
        """
        Returns (Modality, confidence).
        confidence = 1.0 (filename hit) | 0.85 (vision) | 0.4 (fallback)
        """
        # Stage 1: filename
        modality = _classify_by_filename(filename)
        if modality is not None:
            logger.info(f"[ModalityClassifier] Filename hit → {modality.value}")
            return modality, 1.0

        # Stage 2: vision
        if image_b64 and self._api_key:
            modality = await _classify_via_vision(image_b64, self._api_key)
            if modality is not None:
                logger.info(f"[ModalityClassifier] Vision classification → {modality.value}")
                return modality, 0.85

        logger.warning(f"[ModalityClassifier] Could not classify '{filename}' — defaulting to UNKNOWN")
        return Modality.UNKNOWN, 0.4
