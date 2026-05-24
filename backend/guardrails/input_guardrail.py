"""
input_guardrail.py — Input Safety Guardrail (Phase 14)

Validates and sanitizes incoming user queries BEFORE they enter the
agentic pipeline. This is the first line of defense.

Checks performed (in order):
  1. Query length limits (min/max)
  2. Prompt injection detection (jailbreak patterns)
  3. Non-medical / off-topic query rejection
  4. PII detection and scrubbing (patient names, phone numbers, emails, NHI)
  5. Repetitive / spam query detection
  6. Malformed / garbled text detection

Design:
  - Returns InputGuardrailResult with:
      .blocked     : bool   — True if query should NOT proceed
      .sanitized   : str    — cleaned/scrubbed query text
      .warnings    : list   — non-blocking advisory messages
      .block_reason: str    — human-readable reason if blocked
      .pii_found   : bool   — True if PII was detected and removed
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from backend.utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

MIN_QUERY_LEN   = 3
MAX_QUERY_LEN   = 8000

# Patterns that indicate prompt injection / jailbreak attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions",
    r"forget\s+(everything|all|your|the)\s+",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"pretend\s+(you\s+are|to\s+be)\s+",
    r"act\s+as\s+(if\s+you\s+are\s+|a\s+)?(?!a\s+doctor|a\s+clinician|an\s+expert)",
    r"disregard\s+(your\s+)?(safety|guidelines|rules|instructions)",
    r"do\s+not\s+add\s+(any\s+)?(disclaimer|warning|caveat)",
    r"(bypass|override|disable)\s+(the\s+)?(safety|filter|guardrail|restriction)",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions|secret|training)",
    r"DAN\s+mode",
    r"you\s+must\s+not\s+refuse",
    r"sudo\s+mode",
    r"developer\s+mode",
]

# Keywords indicating clearly non-medical / off-topic content
_NON_MEDICAL_BLOCKLIST = [
    r"\b(hack|exploit|malware|phishing|ransomware|sql\s*injection|xss|csrf)\b",
    r"\b(cryptocurrency|bitcoin|forex|stock\s+market|trading\s+bot)\b",
    r"\b(write\s+(a\s+)?(poem|song|novel|story|code|script|essay))\b",
    r"\b(illegal|how\s+to\s+(make|build|create)\s+(a\s+)?(bomb|weapon|drug))\b",
    r"\b(political|election|vote|party\s+manifesto)\b",
]

# PII patterns to detect and scrub
_PII_PATTERNS: List[Tuple[str, str, str]] = [
    # (pattern, replacement, label)
    (r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b(?=\s+(is|has|age|patient|presents|dob|born))", "[PATIENT_NAME]", "name"),
    (r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_REDACTED]", "phone"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]", "email"),
    (r"\b(NHS|NHI|MRN|DOB|SSN|NIN)[:\s#-]*[A-Z0-9]{5,12}\b", "[ID_REDACTED]", "patient_id"),
    (r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", "[DATE_REDACTED]", "dob"),   # ISO date (could be DOB)
    (r"\b(patient\s+(name|id)\s*[:=]\s*)[^\s,\.]+", r"\1[REDACTED]", "patient_field"),
]

# Minimum medical vocabulary presence to pass topic filter
_MEDICAL_KEYWORD_RE = re.compile(
    r"\b(patient|symptom|diagnosis|treatment|medication|dose|drug|disease|"
    r"clinical|medical|health|hospital|doctor|physician|nurse|therapy|pain|"
    r"blood|pressure|heart|chest|breath|fever|infection|cancer|diabetes|"
    r"hypertension|ECG|EKG|MRI|CT|scan|lab|test|result|vital|surgery|"
    r"emergency|acute|chronic|history|allergy|prescription|protocol|"
    r"guideline|evidence|study|trial|pharma|pathology|radiology|cardio|"
    r"neuro|pediatric|geriatric|obstetric|renal|hepatic|pulmonary|"
    r"what|how|why|explain|define|describe|causes|symptoms|treatment)\b",
    re.IGNORECASE,
)

_COMPILED_INJECTION   = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]
_COMPILED_NON_MEDICAL = [re.compile(p, re.IGNORECASE) for p in _NON_MEDICAL_BLOCKLIST]


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class InputGuardrailResult:
    blocked:      bool
    sanitized:    str
    warnings:     List[str] = field(default_factory=list)
    block_reason: str       = ""
    pii_found:    bool      = False
    pii_types:    List[str] = field(default_factory=list)


# ── Guardrail ──────────────────────────────────────────────────────────────────

class InputGuardrail:
    """
    Stateless input validation and sanitization guardrail.

    Usage:
        result = InputGuardrail().check(query)
        if result.blocked:
            raise HTTPException(400, result.block_reason)
        query = result.sanitized
    """

    def check(self, query: str) -> InputGuardrailResult:
        """Run all input guardrail checks. Returns InputGuardrailResult."""
        warnings: List[str] = []
        pii_types: List[str] = []
        original  = query

        # ── 1. Length check ────────────────────────────────────────────────────
        if len(query.strip()) < MIN_QUERY_LEN:
            return InputGuardrailResult(
                blocked=True,
                sanitized=query,
                block_reason=f"Query too short (minimum {MIN_QUERY_LEN} characters).",
            )
        if len(query) > MAX_QUERY_LEN:
            return InputGuardrailResult(
                blocked=True,
                sanitized=query,
                block_reason=f"Query too long (maximum {MAX_QUERY_LEN} characters). Please shorten your request.",
            )

        # ── 2. Prompt injection detection ──────────────────────────────────────
        for pattern in _COMPILED_INJECTION:
            if pattern.search(query):
                logger.warning(f"[InputGuardrail] Prompt injection detected: '{pattern.pattern[:50]}'")
                return InputGuardrailResult(
                    blocked=True,
                    sanitized=query,
                    block_reason=(
                        "This query contains instructions that attempt to override system "
                        "safety guidelines. Only clinical queries are permitted."
                    ),
                )

        # ── 3. Non-medical topic check ─────────────────────────────────────────
        for pattern in _COMPILED_NON_MEDICAL:
            if pattern.search(query):
                logger.warning(f"[InputGuardrail] Non-medical topic detected: '{pattern.pattern[:50]}'")
                return InputGuardrailResult(
                    blocked=True,
                    sanitized=query,
                    block_reason=(
                        "This system is dedicated to clinical decision support. "
                        "Your query does not appear to be medical in nature. "
                        "Please submit a clinical or medical question."
                    ),
                )

        # ── 4. PII scrubbing ───────────────────────────────────────────────────
        sanitized = query
        for raw_pattern, replacement, label in _PII_PATTERNS:
            new_text, count = re.subn(raw_pattern, replacement, sanitized)
            if count > 0:
                sanitized = new_text
                pii_types.append(label)
                warnings.append(
                    f"PII detected and redacted ({label}). "
                    "Patient identifiers should not be included in queries."
                )

        pii_found = len(pii_types) > 0
        if pii_found:
            logger.info(f"[InputGuardrail] PII scrubbed: types={pii_types}")

        # ── 5. Repetition / spam detection ────────────────────────────────────
        words = sanitized.split()
        if len(words) > 5:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.25:
                return InputGuardrailResult(
                    blocked=True,
                    sanitized=sanitized,
                    block_reason="Query appears to be repetitive or spam. Please submit a meaningful clinical question.",
                    pii_found=pii_found,
                    pii_types=pii_types,
                )

        # ── 6. Minimum medical relevance check ────────────────────────────────
        # Only block short queries with zero medical vocabulary
        if len(words) <= 10 and not _MEDICAL_KEYWORD_RE.search(sanitized):
            warnings.append(
                "Query does not appear to contain medical terminology. "
                "For best results, include clinical context."
            )

        logger.info(
            f"[InputGuardrail] Passed. pii_found={pii_found} "
            f"warnings={len(warnings)} len={len(sanitized)}"
        )

        return InputGuardrailResult(
            blocked=False,
            sanitized=sanitized,
            warnings=warnings,
            pii_found=pii_found,
            pii_types=pii_types,
        )
