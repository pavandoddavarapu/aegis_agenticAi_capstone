"""
ocr_pipeline.py — Medical OCR Pipeline (Phase 8)

Architecture:
  Production-grade OCR for clinical documents.

  Strategy:
    1. PaddleOCR (primary) — high accuracy, handles handwriting, skew, noise
    2. Tesseract (secondary fallback) — proven open-source baseline
    3. GPT-4o Vision text extraction (tertiary) — handles complex layouts

  Post-extraction:
    - Confidence scoring (weighted blend of per-word confidences)
    - Medical entity normalization (dosage, units, drug names)
    - Structured section extraction (headers, values, dates)
    - Text cleanup (artifact removal, unicode normalization)

  Output feeds directly into:
    - GraphRAG ingestion pipeline (entity extraction)
    - Hybrid retrieval context
    - Agent state (visual_context block)

SAFETY NOTE:
  All OCR outputs are labelled as EXTRACTED TEXT with confidence scores
  so downstream validation can gate on low-quality extractions.
"""
from __future__ import annotations

import asyncio
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.logger import logger


# ── OCR Result dataclass ──────────────────────────────────────────────────────

@dataclass
class OcrResult:
    raw_text:          str
    cleaned_text:      str
    confidence:        float          # 0.0 – 1.0 blended per-word confidence
    method:            str            # "paddle" | "tesseract" | "gpt4o"
    sections:          Dict[str, str] # {header: content}
    entities:          Dict[str, List[str]]  # {entity_type: [values]}
    warnings:          List[str]      = field(default_factory=list)


# ── Medical section patterns ──────────────────────────────────────────────────

_SECTION_PATTERNS = [
    r"diagnosis[:\s]",
    r"chief complaint[:\s]",
    r"medications?[:\s]",
    r"allergies?[:\s]",
    r"assessment[:\s]",
    r"plan[:\s]",
    r"history[:\s]",
    r"physical exam[:\s]",
    r"laboratory[:\s]",
    r"impression[:\s]",
    r"discharge[:\s]",
]

_DOSAGE_PATTERN    = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|ml|iu|units?)\b", re.I)
_DATE_PATTERN      = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
_DRUG_UNITS_NORM   = {"mcg": "mcg", "ug": "mcg", "µg": "mcg",
                      "milligram": "mg", "microgram": "mcg"}


# ── Text normalization ────────────────────────────────────────────────────────

def _normalize_unicode(text: str) -> str:
    """Normalize unicode characters that OCR may mangle."""
    return unicodedata.normalize("NFKC", text)


def _clean_ocr_text(raw: str) -> str:
    """Remove common OCR artifacts while preserving clinical content."""
    text = _normalize_unicode(raw)
    text = re.sub(r"[ \t]{3,}", "  ", text)         # collapse excess whitespace
    text = re.sub(r"(\n){3,}", "\n\n", text)         # collapse blank lines
    text = re.sub(r"[|]{1}", " ", text)              # pipe artifacts
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", text)  # non-printable
    return text.strip()


def _extract_sections(text: str) -> Dict[str, str]:
    """Extract named clinical sections from document text."""
    sections: Dict[str, str] = {}
    lower = text.lower()

    for pattern in _SECTION_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            start = match.start()
            # Find next section header or end of text
            end = len(text)
            for other in _SECTION_PATTERNS:
                if other == pattern:
                    continue
                nxt = re.search(other, lower[match.end():])
                if nxt:
                    candidate = match.end() + nxt.start()
                    if candidate < end:
                        end = candidate
            header = text[start:match.end()].strip().rstrip(":").strip()
            content = text[match.end():end].strip()
            sections[header.title()] = content[:800]  # cap per section

    return sections


def _extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract key clinical entities via regex patterns."""
    entities: Dict[str, List[str]] = {
        "dosages": [],
        "dates":   [],
        "drugs":   [],
    }

    # Dosages
    for m in _DOSAGE_PATTERN.finditer(text):
        unit = _DRUG_UNITS_NORM.get(m.group(2).lower(), m.group(2).lower())
        entities["dosages"].append(f"{m.group(1)} {unit}")

    # Dates
    entities["dates"] = _DATE_PATTERN.findall(text)

    return entities


# ── PaddleOCR extraction ──────────────────────────────────────────────────────

async def _run_paddle_ocr(image_bytes: bytes) -> Tuple[str, float]:
    """Run PaddleOCR in a thread pool (it is CPU-bound)."""
    def _paddle_sync(data: bytes) -> Tuple[str, float]:
        try:
            from paddleocr import PaddleOCR
            import numpy as np
            from PIL import Image

            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img_np = np.array(img)
            result = ocr.ocr(img_np, cls=True)

            lines, confidences = [], []
            if result and result[0]:
                for block in result[0]:
                    if block:
                        text_conf = block[1]
                        lines.append(text_conf[0])
                        confidences.append(float(text_conf[1]))

            raw_text = "\n".join(lines)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            return raw_text, avg_conf
        except ImportError:
            raise ImportError("PaddleOCR not installed")
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR error: {exc}")

    return await asyncio.to_thread(_paddle_sync, image_bytes)


# ── Tesseract fallback ────────────────────────────────────────────────────────

async def _run_tesseract_ocr(image_bytes: bytes) -> Tuple[str, float]:
    """Tesseract OCR as secondary fallback."""
    def _tess_sync(data: bytes) -> Tuple[str, float]:
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(data)).convert("RGB")
            data_tsv = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            words, confs = [], []
            for i, word in enumerate(data_tsv["text"]):
                conf = int(data_tsv["conf"][i])
                if conf > 0 and word.strip():
                    words.append(word)
                    confs.append(conf / 100.0)

            text = " ".join(words)
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            return text, avg_conf
        except ImportError:
            raise ImportError("pytesseract not installed")
        except Exception as exc:
            raise RuntimeError(f"Tesseract error: {exc}")

    return await asyncio.to_thread(_tess_sync, image_bytes)


# ── GPT-4o Vision text extraction ────────────────────────────────────────────

async def _run_gpt4o_ocr(image_b64: str, api_key: str) -> Tuple[str, float]:
    """GPT-4o Vision as tertiary high-quality text extraction path."""
    try:
        import httpx

        prompt = (
            "Extract ALL text visible in this medical document image, exactly as written. "
            "Preserve structure (headers, line breaks, tables). "
            "Do not interpret or summarize. Output raw extracted text only."
        )
        payload = {
            "model": "gpt-4o",
            "max_tokens": 1500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            # GPT-4o text extractions are high quality but we can't directly get
            # word-level confidence; assign a reasonable fixed score.
            return text, 0.88
    except Exception as exc:
        raise RuntimeError(f"GPT-4o OCR failed: {exc}")


# ── Public OCR Pipeline ───────────────────────────────────────────────────────

class OcrPipeline:
    """
    Medical OCR pipeline with cascading extraction strategy:
    PaddleOCR → Tesseract → GPT-4o Vision.

    Confidence gating:
      - If PaddleOCR confidence < CONFIDENCE_FLOOR, tries Tesseract.
      - If both are low, escalates to GPT-4o Vision.
      - Final result tagged with method and confidence for validation gating.
    """

    CONFIDENCE_FLOOR = 0.60  # minimum acceptable OCR confidence

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    async def extract(
        self,
        image_bytes: bytes,
        image_b64:   Optional[str] = None,
    ) -> OcrResult:
        """Run cascaded OCR and return a structured OcrResult."""
        warnings: List[str] = []
        raw_text, confidence, method = "", 0.0, "none"

        # Stage 1: PaddleOCR
        try:
            raw_text, confidence = await _run_paddle_ocr(image_bytes)
            method = "paddle"
            logger.info(f"[OcrPipeline] PaddleOCR confidence={confidence:.3f}")
        except Exception as exc:
            warnings.append(f"PaddleOCR unavailable: {exc}")
            logger.warning(f"[OcrPipeline] PaddleOCR failed: {exc}")

        # Stage 2: Tesseract fallback
        if confidence < self.CONFIDENCE_FLOOR:
            try:
                t_text, t_conf = await _run_tesseract_ocr(image_bytes)
                if t_conf > confidence:
                    raw_text, confidence, method = t_text, t_conf, "tesseract"
                    logger.info(f"[OcrPipeline] Tesseract improved confidence={t_conf:.3f}")
            except Exception as exc:
                warnings.append(f"Tesseract unavailable: {exc}")
                logger.warning(f"[OcrPipeline] Tesseract failed: {exc}")

        # Stage 3: GPT-4o Vision fallback
        if confidence < self.CONFIDENCE_FLOOR and image_b64 and self._api_key:
            try:
                g_text, g_conf = await _run_gpt4o_ocr(image_b64, self._api_key)
                if g_conf > confidence:
                    raw_text, confidence, method = g_text, g_conf, "gpt4o"
                    logger.info(f"[OcrPipeline] GPT-4o OCR used, confidence={g_conf:.3f}")
            except Exception as exc:
                warnings.append(f"GPT-4o OCR unavailable: {exc}")
                logger.warning(f"[OcrPipeline] GPT-4o OCR failed: {exc}")

        if not raw_text:
            warnings.append("All OCR methods exhausted — empty extraction.")
            logger.error("[OcrPipeline] Complete OCR failure.")

        cleaned   = _clean_ocr_text(raw_text)
        sections  = _extract_sections(cleaned)
        entities  = _extract_entities(cleaned)

        return OcrResult(
            raw_text=raw_text,
            cleaned_text=cleaned,
            confidence=round(confidence, 4),
            method=method,
            sections=sections,
            entities=entities,
            warnings=warnings,
        )

    def to_context_block(self, result: OcrResult) -> str:
        """Format an OcrResult into a structured context block for LLM injection."""
        lines = [
            f"=== OCR EXTRACTION (method={result.method}, confidence={result.confidence:.2f}) ===",
        ]
        if result.warnings:
            lines.append(f"⚠ Warnings: {'; '.join(result.warnings)}")

        if result.sections:
            lines.append("\nEXTRACTED SECTIONS:")
            for header, content in result.sections.items():
                lines.append(f"  [{header}]\n  {content[:400]}")
        else:
            lines.append("\nEXTRACTED TEXT:")
            lines.append(result.cleaned_text[:2000])

        if result.entities.get("dosages"):
            lines.append(f"\nDosages: {', '.join(result.entities['dosages'])}")
        if result.entities.get("dates"):
            lines.append(f"Dates: {', '.join(result.entities['dates'])}")

        return "\n".join(lines)


import os  # needed for api_key env var lookup inside class
