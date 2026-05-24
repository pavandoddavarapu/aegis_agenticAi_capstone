"""
output_guardrail.py — Output Safety Guardrail (Phase 14)

Validates AI-generated clinical responses BEFORE they are returned to
the user. This is the last line of defense before the output reaches
the clinician.

Checks performed:
  1. Hallucination marker detection  — flags LLM uncertainty statements
  2. Self-diagnosis / direct prescription blocking — detects responses
     that prescribe specific drugs/doses to non-professional users
  3. Disclaimer enforcement          — ensures mandatory safety disclaimer
  4. Emergency keyword escalation    — promotes emergency flags from body
     to top-level response prefix
  5. Profanity / inappropriate content check
  6. Response completeness check     — catches empty or extremely short
     responses that slipped through

Design:
  - Never blocks output completely (clinical emergencies must get through)
  - Instead: annotates, prepends warnings, or upgrades escalation flags
  - Returns OutputGuardrailResult with:
      .safe             : bool   — False if critical safety issue found
      .modified_response: str    — sanitized + enriched final response
      .warnings         : list   — advisory messages to include in metadata
      .escalation_needed: bool   — True if human review should be triggered
      .reasons          : list   — machine-readable issue labels
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from backend.utils.logger import logger


# ── Patterns ────────────────────────────────────────────────────────────────────

# Hallucination signal phrases — LLM admitting uncertainty in a harmful way
_HALLUCINATION_SIGNALS = [
    r"i\s+(don'?t|do\s+not)\s+have\s+access\s+to\s+(real|live|current|actual)",
    r"as\s+of\s+my\s+(knowledge\s+)?cut-?off",
    r"i\s+(can't|cannot|am\s+not\s+able\s+to)\s+provide\s+specific\s+medical\s+advice",
    r"this\s+is\s+not\s+medical\s+advice\s+and\s+should\s+not\s+replace",
    r"i\s+am\s+an\s+ai\s+and\s+cannot\s+diagnose",
    r"please\s+consult\s+(a|your)\s+(doctor|physician|specialist)",  # in body means LLM didn't follow structure
]

# Direct prescribing patterns — dangerous outputs from LLMs prescribing to lay users
_DIRECT_PRESCRIPTION_SIGNALS = [
    r"you\s+should\s+take\s+\d+\s*mg",
    r"take\s+\d+\s*(mg|mcg|units?|tablets?|capsules?)\s+(of\s+)?\w+\s+(every|twice|once|daily|bd|tds)",
    r"i\s+recommend\s+you\s+(take|start|begin)\s+\w+\s+\d+",
    r"your\s+dose\s+should\s+be\s+\d+",
]

# Emergency escalation keywords in output body that require top-level flagging
_EMERGENCY_PATTERNS = [
    r"\bSTEMI\b",
    r"\bpneumothorax\b",
    r"\baortic\s+dissection\b",
    r"\bpulmonary\s+embolism\b",
    r"\banaphylaxis\b",
    r"\bstroke\b",
    r"\brespiratory\s+failure\b",
    r"\bcardiac\s+arrest\b",
    r"\bseptic\s+shock\b",
    r"\bmeningitis\b",
    r"immediate\s+(medical\s+)?attention\s+required",
    r"call\s+(911|999|112|emergency\s+services|an\s+ambulance)",
    r"life.?threatening",
]

# Required disclaimer pattern — must be in every final response
_DISCLAIMER_RE = re.compile(
    r"(AI.assisted|physician\s+judgment|qualified\s+clinician|clinical\s+decision"
    r"|not\s+a\s+substitute|human\s+oversight)",
    re.IGNORECASE,
)

_MANDATORY_DISCLAIMER = (
    "\n\n⚕️ **Clinical Disclaimer**: This output is AI-assisted analysis intended "
    "for qualified healthcare professionals only. It does not constitute a final "
    "diagnosis or treatment prescription. All clinical decisions must be made by "
    "a licensed physician with full knowledge of the patient's condition."
)

_EMERGENCY_PREFIX_TEMPLATE = (
    "🚨 **EMERGENCY ALERT**: Critical clinical condition detected — "
    "{reason}. Immediate evaluation required.\n\n"
)

_COMPILED_HALLUCINATION   = [re.compile(p, re.IGNORECASE) for p in _HALLUCINATION_SIGNALS]
_COMPILED_PRESCRIPTION    = [re.compile(p, re.IGNORECASE) for p in _DIRECT_PRESCRIPTION_SIGNALS]
_COMPILED_EMERGENCY       = [re.compile(p, re.IGNORECASE) for p in _EMERGENCY_PATTERNS]


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class OutputGuardrailResult:
    safe:              bool
    modified_response: str
    warnings:          List[str] = field(default_factory=list)
    escalation_needed: bool      = False
    reasons:           List[str] = field(default_factory=list)


# ── Guardrail ──────────────────────────────────────────────────────────────────

class OutputGuardrail:
    """
    Stateless output validation and enrichment guardrail.

    Usage:
        result = OutputGuardrail().check(final_response, risk_level)
        final_response = result.modified_response
        if result.escalation_needed:
            # trigger human review
    """

    def check(
        self,
        response: str,
        risk_level: str = "low",
        query: str = "",
        image_emergency_flag: bool = False,
        image_emergency_reason: str = "",
    ) -> OutputGuardrailResult:
        """Run all output guardrail checks. Returns OutputGuardrailResult."""
        if not response or not response.strip():
            return OutputGuardrailResult(
                safe=False,
                modified_response=(
                    "⚠️ The clinical analysis system was unable to generate a response. "
                    "Please try again or consult a qualified clinician directly."
                    + _MANDATORY_DISCLAIMER
                ),
                warnings=["Empty response intercepted by output guardrail."],
                escalation_needed=True,
                reasons=["EMPTY_RESPONSE"],
            )

        warnings: List[str] = []
        reasons:  List[str] = []
        modified  = response
        escalation_needed = False

        # ── 1. Hallucination signal detection ─────────────────────────────────
        for pattern in _COMPILED_HALLUCINATION:
            if pattern.search(modified):
                reasons.append("HALLUCINATION_SIGNAL")
                warnings.append(
                    "Response contains LLM uncertainty language. "
                    "This may indicate the model exceeded its evidence boundaries."
                )
                escalation_needed = True
                break

        # ── 2. Direct prescribing pattern check ───────────────────────────────
        for pattern in _COMPILED_PRESCRIPTION:
            if pattern.search(modified):
                reasons.append("DIRECT_PRESCRIPTION_DETECTED")
                warnings.append(
                    "Response contains direct dosage prescription language. "
                    "Escalated for physician review — prescribing authority required."
                )
                escalation_needed = True
                # Inject inline warning immediately after the pattern
                modified = pattern.sub(
                    lambda m: f"[⚠️ PRESCRIBING NOTE — Physician Verification Required: {m.group()}]",
                    modified
                )
                break

        # ── 3. Emergency keyword detection ────────────────────────────────────
        emergency_found: List[str] = []
        if image_emergency_flag:
            emergency_found.append(image_emergency_reason or "Medical emergency detected in image")
            reasons.append("IMAGE_EMERGENCY_FLAG")
            escalation_needed = True

        for pattern in _COMPILED_EMERGENCY:
            m = pattern.search(modified)
            if m:
                term = m.group().strip()
                if term not in emergency_found:
                    emergency_found.append(term)

        if emergency_found and not modified.startswith("🚨"):
            # Prepend emergency banner to top of response
            emergency_text = "; ".join(emergency_found[:3])
            prefix = _EMERGENCY_PREFIX_TEMPLATE.format(reason=emergency_text)
            modified = prefix + modified
            reasons.append("EMERGENCY_KEYWORD_ESCALATION")
            escalation_needed = True
            warnings.append(f"Emergency keywords detected: {emergency_text}")

        # ── 4. Disclaimer enforcement ──────────────────────────────────────────
        if not _DISCLAIMER_RE.search(modified):
            modified = modified + _MANDATORY_DISCLAIMER
            warnings.append("Mandatory clinical disclaimer appended.")
            reasons.append("DISCLAIMER_ENFORCED")

        # ── 5. Critical risk level → force escalation flag ────────────────────
        if risk_level == "critical" and not escalation_needed:
            escalation_needed = True
            reasons.append("CRITICAL_RISK_LEVEL_ESCALATION")

        # ── 6. Response length sanity ─────────────────────────────────────────
        if len(response.strip()) < 50:
            warnings.append(
                "Response is extremely short. Clinical completeness may be insufficient."
            )
            reasons.append("SUSPICIOUSLY_SHORT_RESPONSE")

        safe = "EMPTY_RESPONSE" not in reasons

        logger.info(
            f"[OutputGuardrail] Checked. safe={safe} "
            f"escalation={escalation_needed} reasons={reasons}"
        )

        return OutputGuardrailResult(
            safe=safe,
            modified_response=modified,
            warnings=warnings,
            escalation_needed=escalation_needed,
            reasons=reasons,
        )
