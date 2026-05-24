"""
prompt_guardrail.py — LLM Prompt Safety Guardrail (Phase 14)

Validates LLM prompts BEFORE they are sent to the language model.
Prevents system prompt leakage attempts, context flooding, and
unsafe instruction injection that could manipulate the clinical LLM.

Checks performed:
  1. System prompt protection  — prevents user content from overriding system instructions
  2. Context length cap        — ensures token budget is not exceeded before LLM call
  3. Role injection detection  — blocks attempts to inject new role/system messages
  4. Instruction override      — blocks attempts to change model behavior inline
  5. Output format tampering   — detects attempts to change expected JSON/medical format

Design:
  - Stateless, synchronous, <1ms per call
  - Returns PromptGuardrailResult with:
      .safe              : bool  — False if prompt should not be sent to LLM
      .sanitized_messages: list  — cleaned message list
      .block_reason      : str   — reason if blocked
      .warnings          : list  — non-blocking notes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

from backend.utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

MAX_PROMPT_CHARS     = 32_000   # ~8k tokens at 4 chars/token
MAX_USER_MSG_CHARS   =  8_000   # max individual user message

# Patterns in user content that attempt to override the system prompt
_ROLE_INJECTION_PATTERNS = [
    r"<\|?system\|?>",                         # token-style system injection
    r"\[SYSTEM\]",
    r"<system>.*?</system>",
    r"<<SYS>>.*?<</SYS>>",
    r"\[INST\].*?\[/INST\]",
    r"###\s+system:",
    r"---\s*system\s*---",
]

_OVERRIDE_PATTERNS = [
    r"new\s+instructions?[:.]",
    r"override\s+(previous|system|all)\s+instructions?",
    r"your\s+new\s+(role|task|purpose|goal)\s+is",
    r"from\s+now\s+on\s+you\s+(must|will|should|are)",
    r"ignore\s+(all\s+)?(previous|prior|system)\s+prompt",
    r"forget\s+(your|all|the)\s+(instructions?|rules?|guidelines?)",
]

_FORMAT_TAMPER_PATTERNS = [
    r"do\s+not\s+use\s+(JSON|markdown|structured|numbered)",
    r"respond\s+(only\s+)?in\s+(plain\s+text|free\s+form|unstructured)",
    r"skip\s+(the\s+)?(disclaimer|warning|caveat|summary|citation)",
    r"don'?t\s+(add|include)\s+(any\s+)?(disclaimer|citation|evidence|warning)",
]

_COMPILED_ROLE     = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _ROLE_INJECTION_PATTERNS]
_COMPILED_OVERRIDE = [re.compile(p, re.IGNORECASE) for p in _OVERRIDE_PATTERNS]
_COMPILED_FORMAT   = [re.compile(p, re.IGNORECASE) for p in _FORMAT_TAMPER_PATTERNS]


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class PromptGuardrailResult:
    safe:               bool
    sanitized_messages: List[Dict[str, Any]]
    block_reason:       str       = ""
    warnings:           List[str] = field(default_factory=list)


# ── Guardrail ──────────────────────────────────────────────────────────────────

class PromptGuardrail:
    """
    LLM Prompt safety guardrail.

    Usage (in reasoning_agent, orchestration_planner, etc.):

        result = PromptGuardrail().check(messages)
        if not result.safe:
            raise ValueError(result.block_reason)
        response = llm.call(result.sanitized_messages)
    """

    def check(self, messages: List[Dict[str, Any]]) -> PromptGuardrailResult:
        """Validate and sanitize a list of LLM chat messages."""

        warnings: List[str] = []
        sanitized: List[Dict[str, Any]] = []

        # ── 1. Total context length check ─────────────────────────────────────
        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars > MAX_PROMPT_CHARS:
            # Truncate the longest non-system message
            return PromptGuardrailResult(
                safe=False,
                sanitized_messages=messages,
                block_reason=(
                    f"Prompt context exceeds maximum allowed length "
                    f"({total_chars} chars > {MAX_PROMPT_CHARS} chars). "
                    "Reduce evidence context or use context compression."
                ),
            )

        for msg in messages:
            role    = msg.get("role", "user")
            content = msg.get("content", "")

            # ── 2. Protect system messages — do not alter them ─────────────────
            if role == "system":
                sanitized.append(msg)
                continue

            # ── 3. Individual message length cap ───────────────────────────────
            if len(content) > MAX_USER_MSG_CHARS:
                content = content[:MAX_USER_MSG_CHARS] + "\n\n[Content truncated by safety guardrail]"
                warnings.append(f"Message from role='{role}' truncated to {MAX_USER_MSG_CHARS} chars.")

            # ── 4. Role injection detection ────────────────────────────────────
            for pattern in _COMPILED_ROLE:
                if pattern.search(content):
                    logger.warning(f"[PromptGuardrail] Role injection detected in {role} message.")
                    return PromptGuardrailResult(
                        safe=False,
                        sanitized_messages=messages,
                        block_reason=(
                            "Prompt contains system-role injection tokens. "
                            "The LLM call has been blocked to protect clinical integrity."
                        ),
                    )

            # ── 5. Override instruction detection ─────────────────────────────
            for pattern in _COMPILED_OVERRIDE:
                if pattern.search(content):
                    logger.warning(f"[PromptGuardrail] Override attempt in {role} message.")
                    return PromptGuardrailResult(
                        safe=False,
                        sanitized_messages=messages,
                        block_reason=(
                            "Prompt contains instructions attempting to override system behavior. "
                            "The LLM call has been blocked."
                        ),
                    )

            # ── 6. Output format tampering ────────────────────────────────────
            for pattern in _COMPILED_FORMAT:
                if pattern.search(content):
                    warnings.append(
                        "Prompt contains request to alter expected output format. "
                        "Standard clinical output format will be enforced."
                    )
                    # Sanitize: remove the tampering instruction
                    content = pattern.sub("", content)
                    break

            sanitized.append({**msg, "content": content})

        logger.info(
            f"[PromptGuardrail] Passed. messages={len(sanitized)} "
            f"total_chars={total_chars} warnings={len(warnings)}"
        )

        return PromptGuardrailResult(
            safe=True,
            sanitized_messages=sanitized,
            warnings=warnings,
        )
