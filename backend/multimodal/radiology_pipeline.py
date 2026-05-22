"""
radiology_pipeline.py — Radiology Image Intelligence Pipeline (Phase 8)

Architecture:
  Vision-LLM orchestrated radiology finding extraction.
  Supports: Chest X-ray, CT, MRI, Ultrasound screenshots.

  CRITICAL DESIGN PRINCIPLE:
    This system provides DECISION SUPPORT for radiological observations.
    It does NOT replace radiologist review. All outputs are clearly
    labelled as AI-assisted observations.

  Pipeline stages:
    1. Image normalization and quality check
    2. Modality sub-classification (CXR / CT / MRI / US)
    3. GPT-4o Vision structured observation extraction
    4. Finding normalization and safety-check
    5. Context block generation for downstream retrieval

  Observations extracted per modality:
    Chest X-Ray:
      - Lung fields (opacification, consolidation, effusion)
      - Cardiac silhouette (cardiomegaly, pericardial effusion)
      - Mediastinal findings
      - Pneumothorax indicators
      - Bone/rib observations
    CT/MRI:
      - Region of interest
      - Density/signal abnormalities
      - Mass or lesion observations
      - Vascular findings
    Ultrasound:
      - Organ size and echogenicity
      - Free fluid indicators
      - Vascular flow observations

  Downstream integration:
    Extracted findings → query generation → hybrid retrieval
    Example: "possible pulmonary edema" → PubMed + graph retrieval
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.utils.logger import logger


# ── Radiology Finding dataclass ───────────────────────────────────────────────

@dataclass
class RadiologyFindings:
    modality_hint:    str              = "unknown"  # cxr / ct / mri / us
    region:           Optional[str]   = None        # anatomical region
    findings:         List[str]        = field(default_factory=list)
    abnormalities:    List[str]        = field(default_factory=list)
    impression:       Optional[str]   = None
    emergency_flag:   bool             = False
    emergency_reason: Optional[str]   = None
    raw_analysis:     str              = ""
    confidence:       float            = 0.0
    warnings:         List[str]        = field(default_factory=list)


# ── Modality sub-classifier ───────────────────────────────────────────────────

_MODALITY_SIGNALS = {
    "cxr":  ["chest", "x-ray", "xray", "cxr", "pa view", "ap view"],
    "ct":   ["ct", "computed tomography", "axial", "hounsfield"],
    "mri":  ["mri", "t1", "t2", "flair", "diffusion", "magnetic"],
    "us":   ["ultrasound", "sono", "echo", "doppler", "fetal"],
}

def _guess_radiology_modality(filename: str, analysis_text: str = "") -> str:
    combined = (filename + " " + analysis_text).lower()
    for modality, signals in _MODALITY_SIGNALS.items():
        if any(sig in combined for sig in signals):
            return modality
    return "unknown"


# ── Emergency pattern detection ───────────────────────────────────────────────

_RADIOLOGY_EMERGENCY = [
    (re.compile(r"pneumothorax",       re.I), "Pneumothorax detected"),
    (re.compile(r"tension pneumo",     re.I), "Tension pneumothorax"),
    (re.compile(r"aortic dissection",  re.I), "Aortic dissection"),
    (re.compile(r"massive effusion",   re.I), "Massive pleural effusion"),
    (re.compile(r"pulmonary embolism", re.I), "Pulmonary embolism pattern"),
    (re.compile(r"herniation",         re.I), "Brain herniation pattern"),
]

def _check_radiology_emergency(text: str) -> tuple[bool, Optional[str]]:
    for pattern, reason in _RADIOLOGY_EMERGENCY:
        if pattern.search(text):
            return True, reason
    return False, None


# ── GPT-4o Vision radiology prompt ───────────────────────────────────────────

_RADIOLOGY_SYSTEM_PROMPT = """You are a clinical radiology AI assistant providing decision support.
You are analyzing a medical imaging screenshot.

CRITICAL RULES:
1. You provide DECISION SUPPORT only — NOT a radiological diagnosis.
2. Prefix all observations with "AI observation:"
3. Immediately flag life-threatening findings for escalation.
4. Use hedged language: "appears to show", "may suggest", "cannot exclude".
5. Do not infer clinical diagnoses — describe imaging observations only.

OUTPUT FORMAT:
Imaging Modality: [chest x-ray / CT / MRI / ultrasound / other]
Region: [anatomical region]
Findings:
  - [observation 1]
  - [observation 2]
Potential Abnormalities:
  - [abnormality 1 or NONE]
Impression: [brief one-sentence summary of most significant finding]
Emergency Flags: [NONE | specific pattern requiring urgent clinical review]
Image Quality: [POOR / ADEQUATE / GOOD]
AI Confidence: [LOW / MEDIUM / HIGH]
Interpretation Caveat: This is an AI-assisted observation only. Formal radiological review is required.
"""

async def _analyze_radiology_gpt4o(image_b64: str, api_key: str) -> tuple[str, float]:
    """Send radiology image to GPT-4o Vision for structured finding extraction."""
    try:
        import httpx
        payload = {
            "model": "gpt-4o",
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": _RADIOLOGY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": "Analyze this medical image and provide structured observations:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
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
            conf_map = {"low": 0.40, "medium": 0.68, "high": 0.85}
            m = re.search(r"AI Confidence:\s*(LOW|MEDIUM|HIGH)", text, re.I)
            confidence = conf_map.get(m.group(1).lower(), 0.60) if m else 0.60
            return text, confidence
    except Exception as exc:
        raise RuntimeError(f"GPT-4o radiology analysis failed: {exc}")


def _parse_radiology_findings(text: str, filename: str = "") -> RadiologyFindings:
    """Parse structured output from GPT-4o into RadiologyFindings."""
    modality_hint = _guess_radiology_modality(filename, text)

    def _extract(pattern: str) -> Optional[str]:
        m = re.search(pattern, text, re.I | re.S)
        return m.group(1).strip().split("\n")[0][:300] if m else None

    region     = _extract(r"Region:\s*([^\n]+)")
    impression = _extract(r"Impression:\s*([^\n]+)")

    # Extract bullet-pointed findings
    findings_section  = re.search(r"Findings:(.*?)(?:Potential Abnormalities:|$)", text, re.I | re.S)
    findings = []
    if findings_section:
        for line in findings_section.group(1).split("\n"):
            line = line.strip(" -•·")
            if line and len(line) > 5:
                findings.append(line[:200])

    abnorm_section = re.search(r"Potential Abnormalities:(.*?)(?:Impression:|$)", text, re.I | re.S)
    abnormalities = []
    if abnorm_section:
        for line in abnorm_section.group(1).split("\n"):
            line = line.strip(" -•·")
            if line and len(line) > 5 and "none" not in line.lower():
                abnormalities.append(line[:200])

    is_emergency, emergency_reason = _check_radiology_emergency(text)

    return RadiologyFindings(
        modality_hint=modality_hint,
        region=region,
        findings=findings,
        abnormalities=abnormalities,
        impression=impression,
        emergency_flag=is_emergency,
        emergency_reason=emergency_reason,
        raw_analysis=text,
    )


# ── Public Radiology Pipeline ─────────────────────────────────────────────────

class RadiologyPipeline:
    """
    Radiology image analysis pipeline using GPT-4o Vision with
    structured clinical observation prompting.

    Outputs:
      - RadiologyFindings (structured)
      - Query strings for downstream retrieval augmentation
      - Emergency escalation flag
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    async def analyze(self, image_b64: str, filename: str = "image") -> RadiologyFindings:
        """Run full radiology analysis pipeline."""
        if not self._api_key:
            logger.error("[RadiologyPipeline] No API key.")
            return RadiologyFindings(warnings=["No vision API key configured."])

        try:
            logger.info(f"[RadiologyPipeline] Analyzing {filename}...")
            raw_analysis, confidence = await _analyze_radiology_gpt4o(image_b64, self._api_key)
            findings = _parse_radiology_findings(raw_analysis, filename)
            findings.confidence = confidence
            findings.raw_analysis = raw_analysis

            if findings.emergency_flag:
                logger.warning(f"[RadiologyPipeline] ⚠ EMERGENCY: {findings.emergency_reason}")

            logger.info(
                f"[RadiologyPipeline] Done. modality={findings.modality_hint} "
                f"confidence={confidence:.2f} abnormalities={len(findings.abnormalities)}"
            )
            return findings

        except Exception as exc:
            logger.exception(f"[RadiologyPipeline] Failed: {exc}")
            return RadiologyFindings(
                warnings=[f"Radiology analysis failed: {exc}"],
                confidence=0.0,
            )

    def generate_retrieval_query(self, findings: RadiologyFindings) -> str:
        """Generate a retrieval query from extracted findings for downstream RAG."""
        parts = []
        if findings.impression:
            parts.append(findings.impression)
        if findings.abnormalities:
            parts.extend(findings.abnormalities[:2])
        if findings.region:
            parts.append(f"in {findings.region}")
        query = " ".join(parts)
        return query[:400] if query else "radiology findings clinical significance"

    def to_context_block(self, findings: RadiologyFindings) -> str:
        """Format RadiologyFindings into context block for LLM injection."""
        lines = [
            f"=== RADIOLOGY ANALYSIS — {findings.modality_hint.upper()} "
            f"(AI Decision Support — NOT a radiological report) ===",
            f"Confidence: {findings.confidence:.2f} | "
            f"Emergency Flag: {'🚨 YES' if findings.emergency_flag else 'None'}",
        ]
        if findings.emergency_flag:
            lines.append(f"⚠ EMERGENCY: {findings.emergency_reason}")
        if findings.region:
            lines.append(f"Region: {findings.region}")
        if findings.impression:
            lines.append(f"Impression: {findings.impression}")
        if findings.findings:
            lines.append("Findings:")
            for f in findings.findings[:5]:
                lines.append(f"  - {f}")
        if findings.abnormalities:
            lines.append("Potential Abnormalities:")
            for a in findings.abnormalities[:3]:
                lines.append(f"  - {a}")
        lines.append(
            "\n[AI Observation] The above are AI-assisted imaging observations only. "
            "Formal radiological review by a qualified radiologist is mandatory."
        )
        return "\n".join(lines)
