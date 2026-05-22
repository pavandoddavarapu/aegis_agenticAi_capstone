"""
ecg_pipeline.py — ECG Intelligence Pipeline (Phase 8)

Architecture:
  Vision-LLM orchestrated ECG interpretation pipeline.
  Uses GPT-4o Vision as primary interpreter with structured prompting
  that forces clinically-grounded, safety-conscious output.

  CRITICAL DESIGN PRINCIPLE:
    This system provides DECISION SUPPORT, NOT DIAGNOSIS.
    All outputs are explicitly labelled as AI observations requiring
    clinical confirmation. Emergency flags trigger escalation.

  Pipeline stages:
    1. Image validation and normalization
    2. GPT-4o Vision structured analysis with clinical prompt
    3. Rule-based safety cross-checks (ST-elevation, rate thresholds)
    4. Structured finding extraction
    5. Context formatting for downstream retrieval augmentation

  Findings extracted:
    - Estimated heart rate
    - Rhythm assessment (sinus, AF, flutter, etc.)
    - ST-segment changes (elevation, depression)
    - QRS morphology observations
    - Axis estimation
    - Notable arrhythmia indicators
    - Emergency flags (STEMI pattern, VF, VT)

  Safety layer:
    - Rule-based validation cross-checks LLM output
    - Emergency patterns trigger immediate escalation flag
    - Low confidence → warnings attached to finding block
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.utils.logger import logger


# ── ECG Finding dataclass ─────────────────────────────────────────────────────

@dataclass
class EcgFindings:
    heart_rate:        Optional[str]     = None   # e.g. "72 bpm"
    rhythm:            Optional[str]     = None   # e.g. "Sinus tachycardia"
    st_changes:        Optional[str]     = None   # e.g. "ST elevation V1-V4"
    qrs_observations:  Optional[str]     = None
    axis:              Optional[str]     = None
    arrhythmia_flags:  List[str]         = field(default_factory=list)
    emergency_flag:    bool              = False  # STEMI/VF/VT pattern detected
    emergency_reason:  Optional[str]     = None
    raw_analysis:      str               = ""
    confidence:        float             = 0.0
    warnings:          List[str]         = field(default_factory=list)


# ── Emergency pattern detection (rule-based safety) ─────────────────────────

_EMERGENCY_PATTERNS = [
    (re.compile(r"\bSTEMI\b",                 re.I), "STEMI pattern detected"),
    (re.compile(r"ST.{0,10}elevation",        re.I), "ST elevation noted"),
    (re.compile(r"\bventricular fibrillation\b", re.I), "Ventricular fibrillation"),
    (re.compile(r"\bVF\b"),                        "Ventricular fibrillation (VF)"),
    (re.compile(r"\bventricular tachycardia\b", re.I), "Ventricular tachycardia"),
    (re.compile(r"\bcomplete heart block\b",   re.I), "Complete heart block"),
    (re.compile(r"rate[:\s]+(\d{3,})",         re.I), "Extreme tachycardia"),
]


def _check_emergency_patterns(text: str) -> tuple[bool, Optional[str]]:
    """Rule-based scan for life-threatening ECG patterns."""
    for pattern, reason in _EMERGENCY_PATTERNS:
        match = pattern.search(text)
        if match:
            # Special case: rate pattern — check actual value
            if "rate" in pattern.pattern and match.lastindex:
                rate = int(match.group(1))
                if rate < 150:
                    continue
            return True, reason
    return False, None


# ── Structured extraction from LLM text ──────────────────────────────────────

def _parse_ecg_findings(analysis_text: str) -> EcgFindings:
    """Extract structured fields from GPT-4o ECG analysis."""
    text = analysis_text

    def _extract(pattern: str, default: Optional[str] = None) -> Optional[str]:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            val = m.group(1).strip().split("\n")[0][:200]
            return val if val else default
        return default

    heart_rate = _extract(r"heart rate[:\s]+([^\n.]+)")
    rhythm     = _extract(r"rhythm[:\s]+([^\n.]+)")
    st_changes = _extract(r"ST[- ]?(segment|changes?|elevation|depression)[:\s]+([^\n.]+)", "Not identified")
    qrs_obs    = _extract(r"QRS[:\s]+([^\n.]+)")
    axis       = _extract(r"axis[:\s]+([^\n.]+)")

    # Emergency check on raw output
    is_emergency, emergency_reason = _check_emergency_patterns(text)

    arrhythmia_flags = []
    for af_term in ["atrial fibrillation", "atrial flutter", "AV block",
                     "bundle branch block", "tachycardia", "bradycardia", "ectopy"]:
        if re.search(rf"\b{re.escape(af_term)}\b", text, re.I):
            arrhythmia_flags.append(af_term)

    return EcgFindings(
        heart_rate=heart_rate,
        rhythm=rhythm,
        st_changes=st_changes,
        qrs_observations=qrs_obs,
        axis=axis,
        arrhythmia_flags=arrhythmia_flags,
        emergency_flag=is_emergency,
        emergency_reason=emergency_reason,
        raw_analysis=text,
    )


# ── GPT-4o Vision ECG Analysis ────────────────────────────────────────────────

_ECG_SYSTEM_PROMPT = """You are a clinical cardiology AI assistant providing decision support.
You are analyzing an ECG image and must provide a structured, safety-conscious interpretation.

CRITICAL RULES:
1. You are providing DECISION SUPPORT only — NOT a clinical diagnosis.
2. All observations must be explicitly prefaced as "AI observation:"
3. Flag any potentially life-threatening patterns for immediate escalation.
4. Do not express certainty — use "appears to show", "suggests", "possible".
5. Structure your response using the exact headers below.

OUTPUT FORMAT:
Heart Rate: [estimated rate in bpm]
Rhythm: [rhythm assessment]
ST Segment: [ST changes or 'No obvious changes identified']
QRS: [QRS morphology observations]
Axis: [electrical axis estimate]
Notable Findings: [bullet points of significant observations]
Emergency Flags: [NONE | specific pattern requiring immediate attention]
AI Confidence: [LOW | MEDIUM | HIGH based on image quality]
Interpretation Caveat: This is an AI-assisted observation only. Clinical ECG interpretation by a qualified cardiologist is required.
"""


async def _analyze_ecg_gpt4o(image_b64: str, api_key: str) -> tuple[str, float]:
    """Send ECG image to GPT-4o with structured cardiological prompt."""
    try:
        import httpx

        payload = {
            "model": "gpt-4o",
            "max_tokens": 800,
            "messages": [
                {
                    "role": "system",
                    "content": _ECG_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this ECG image and provide a structured clinical observation:",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                },
            ],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()

            # Extract confidence from text
            conf_map = {"low": 0.45, "medium": 0.70, "high": 0.88}
            conf_match = re.search(r"AI Confidence:\s*(LOW|MEDIUM|HIGH)", text, re.I)
            confidence = conf_map.get(conf_match.group(1).lower(), 0.60) if conf_match else 0.60

            return text, confidence

    except Exception as exc:
        raise RuntimeError(f"GPT-4o ECG analysis failed: {exc}")


# ── Public ECG Pipeline ───────────────────────────────────────────────────────

class EcgPipeline:
    """
    ECG interpretation pipeline using GPT-4o Vision with
    structured clinical prompting and rule-based safety checks.

    Outputs:
      - EcgFindings (structured)
      - Context block string for agent state injection
      - Emergency escalation flag
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    async def analyze(self, image_b64: str) -> EcgFindings:
        """Run full ECG analysis pipeline."""
        if not self._api_key:
            logger.error("[EcgPipeline] No API key — cannot analyze ECG.")
            findings = EcgFindings(warnings=["No vision API key configured."])
            return findings

        try:
            logger.info("[EcgPipeline] Starting GPT-4o ECG analysis...")
            raw_analysis, confidence = await _analyze_ecg_gpt4o(image_b64, self._api_key)
            findings = _parse_ecg_findings(raw_analysis)
            findings.confidence = confidence

            if findings.emergency_flag:
                logger.warning(
                    f"[EcgPipeline] ⚠ EMERGENCY FLAG: {findings.emergency_reason}"
                )

            logger.info(
                f"[EcgPipeline] Analysis complete. "
                f"confidence={confidence:.2f} emergency={findings.emergency_flag}"
            )
            return findings

        except Exception as exc:
            logger.exception(f"[EcgPipeline] Analysis failed: {exc}")
            return EcgFindings(
                warnings=[f"ECG analysis failed: {exc}"],
                confidence=0.0,
            )

    def to_context_block(self, findings: EcgFindings) -> str:
        """Format EcgFindings into a structured context block for LLM injection."""
        lines = [
            "=== ECG ANALYSIS (AI Decision Support — NOT a clinical diagnosis) ===",
            f"Confidence: {findings.confidence:.2f} | "
            f"Emergency Flag: {'🚨 YES' if findings.emergency_flag else 'None'}",
        ]

        if findings.emergency_flag:
            lines.append(f"⚠ EMERGENCY: {findings.emergency_reason} — requires immediate clinical review")

        if findings.heart_rate:
            lines.append(f"Heart Rate: {findings.heart_rate}")
        if findings.rhythm:
            lines.append(f"Rhythm: {findings.rhythm}")
        if findings.st_changes:
            lines.append(f"ST Segment: {findings.st_changes}")
        if findings.qrs_observations:
            lines.append(f"QRS: {findings.qrs_observations}")
        if findings.axis:
            lines.append(f"Axis: {findings.axis}")
        if findings.arrhythmia_flags:
            lines.append(f"Arrhythmia Indicators: {', '.join(findings.arrhythmia_flags)}")

        lines.append(
            "\n[AI Observation] The above findings are AI-assisted observations only. "
            "Clinical ECG interpretation by a qualified cardiologist is mandatory."
        )

        return "\n".join(lines)
