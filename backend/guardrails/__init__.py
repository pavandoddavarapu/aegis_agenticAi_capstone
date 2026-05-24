"""
guardrails/ — Aegis Clinical AI Safety Guardrails (Phase 14)

This package provides layered safety guardrails that intercept inputs and
outputs at multiple points in the clinical agentic pipeline:

  INPUT GUARDRAILS (pre-processing):
    - InputGuardrail : query length, injection detection, PII scrubbing,
                       non-medical topic rejection, prompt injection blocking

  OUTPUT GUARDRAILS (post-processing):
    - OutputGuardrail : hallucination markers, unsafe medical advice detection,
                        disclaimer enforcement, self-diagnosis rejection,
                        emergency keyword escalation in final response

  LLM PROMPT GUARDRAILS (during LLM calls):
    - PromptGuardrail : system prompt protection, context length cap,
                        unsafe instruction filtering

  CLINICAL SAFETY GUARDRAILS:
    - ClinicalGuardrail : drug dosage sanity checks, age-medication flags,
                          pediatric/obstetric special handling, contraindication
                          pattern matching in the final response

All guardrails are stateless, deterministic, and never invoke an LLM.
They are designed to be fast (<5ms per call) and composable.

Integration points:
  1. InputGuardrail  → called at top of POST /analyze/ BEFORE run_workflow()
  2. OutputGuardrail → called inside finalize_response() BEFORE returning
  3. PromptGuardrail → called inside reasoning_agent & orchestration_planner
  4. ClinicalGuardrail → called inside finalize_response() alongside OutputGuardrail
"""

from .input_guardrail    import InputGuardrail,    InputGuardrailResult
from .output_guardrail   import OutputGuardrail,   OutputGuardrailResult
from .clinical_guardrail import ClinicalGuardrail, ClinicalGuardrailResult
from .prompt_guardrail   import PromptGuardrail,   PromptGuardrailResult

__all__ = [
    "InputGuardrail",    "InputGuardrailResult",
    "OutputGuardrail",   "OutputGuardrailResult",
    "ClinicalGuardrail", "ClinicalGuardrailResult",
    "PromptGuardrail",   "PromptGuardrailResult",
]
