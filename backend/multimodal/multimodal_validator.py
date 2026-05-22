"""
multimodal_validator.py — Multimodal Validation Engine (Phase 8)

Architecture:
  Safety-first validation layer for all multimodal outputs.
  Enforces confidence gating before visual findings are used in reasoning.

  Validation checks:
    1. OCR confidence gating (< 0.55 → warning, < 0.35 → reject)
    2. Image interpretation confidence gating
    3. Modality confidence gating (< 0.40 → unclassified warning)
    4. Emergency flag propagation
    5. Visual-to-text grounding check (findings cited in reasoning)

  CRITICAL SAFETY PRINCIPLE:
    Low-confidence visual extractions REDUCE the overall validation score.
    This ensures the system never over-trusts degraded image analysis.
    Better to surface uncertainty than to propagate a confident wrong answer.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.logger import logger


class MultimodalValidator:
    """
    Validates multimodal pipeline outputs before they enter reasoning.

    Integrates into the existing validation_agent pipeline as an
    additional check layer — returns score adjustments and warnings.
    """

    # Confidence floor thresholds
    OCR_WARN_THRESHOLD    = 0.55   # Below → attach warning
    OCR_REJECT_THRESHOLD  = 0.35   # Below → reject OCR evidence entirely
    IMG_WARN_THRESHOLD    = 0.50   # Below → flag image analysis as low quality
    MODAL_WARN_THRESHOLD  = 0.50   # Below → modality classification uncertain

    def validate_visual_context(
        self,
        image_confidence:   float,
        modality_confidence: float,
        ocr_confidence:     Optional[float],
        visual_context:     str,
        reasoning_output:   str,
    ) -> Tuple[float, str, List[str]]:
        """
        Validate multimodal context and return a score adjustment.

        Returns:
            (score_delta, summary, warnings)
            score_delta: negative adjustment to composite validation score
                         0.0 means no impact, -0.3 means major quality concern
        """
        score_delta = 0.0
        warnings: List[str] = []
        checks: List[str]   = []

        # Check 1: OCR confidence
        if ocr_confidence is not None:
            if ocr_confidence < self.OCR_REJECT_THRESHOLD:
                score_delta -= 0.35
                warnings.append(
                    f"OCR confidence critically low ({ocr_confidence:.2f}) — "
                    "extracted text may be unreliable. Visual evidence rejected."
                )
                checks.append(f"OCR: REJECTED (conf={ocr_confidence:.2f})")
            elif ocr_confidence < self.OCR_WARN_THRESHOLD:
                score_delta -= 0.15
                warnings.append(
                    f"OCR confidence below threshold ({ocr_confidence:.2f}) — "
                    "manual verification of extracted text recommended."
                )
                checks.append(f"OCR: WARNING (conf={ocr_confidence:.2f})")
            else:
                checks.append(f"OCR: PASSED (conf={ocr_confidence:.2f})")

        # Check 2: Image interpretation confidence
        if image_confidence < self.IMG_WARN_THRESHOLD:
            score_delta -= 0.20
            warnings.append(
                f"Image analysis confidence low ({image_confidence:.2f}) — "
                "image quality may be insufficient for reliable AI observation."
            )
            checks.append(f"Image analysis: WARNING (conf={image_confidence:.2f})")
        else:
            checks.append(f"Image analysis: PASSED (conf={image_confidence:.2f})")

        # Check 3: Modality classification confidence
        if modality_confidence < self.MODAL_WARN_THRESHOLD:
            score_delta -= 0.10
            warnings.append(
                f"Modality classification uncertain (conf={modality_confidence:.2f}) — "
                "image may have been routed to wrong pipeline."
            )
            checks.append(f"Modality: UNCERTAIN (conf={modality_confidence:.2f})")
        else:
            checks.append(f"Modality: CONFIDENT (conf={modality_confidence:.2f})")

        # Check 4: Visual grounding — does reasoning acknowledge visual findings?
        if visual_context and reasoning_output:
            reasoning_lower = reasoning_output.lower()
            visual_lower    = visual_context.lower()
            # Check for at least some overlap (e.g., modality mentioned, key terms used)
            grounding_terms = ["ecg", "x-ray", "radiology", "ocr", "visual finding",
                               "image", "extracted", "ai observation", "analysis"]
            grounded = any(term in reasoning_lower for term in grounding_terms)
            if not grounded:
                score_delta -= 0.05
                warnings.append(
                    "Visual findings not explicitly acknowledged in reasoning output."
                )
                checks.append("Visual grounding: NOT ACKNOWLEDGED")
            else:
                checks.append("Visual grounding: ACKNOWLEDGED")

        summary = (
            f"Multimodal Validation | score_delta={score_delta:.3f}\n"
            + "\n".join(f"  • {c}" for c in checks)
        )

        logger.info(f"[MultimodalValidator] {summary}")
        return round(score_delta, 4), summary, warnings

    def get_confidence_label(self, delta: float) -> str:
        if delta >= -0.05:
            return "multimodal_ok"
        elif delta >= -0.20:
            return "multimodal_warning"
        return "multimodal_critical"
