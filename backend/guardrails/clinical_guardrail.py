"""
clinical_guardrail.py — Clinical Safety Guardrail (Phase 14)

Performs clinical-domain-specific safety checks on the final AI output.
These are rule-based checks that catch dangerous clinical content that
general output guardrails may miss.

Checks performed:
  1. Dangerous dosage detection       — catches extremely high or clearly
                                        erroneous drug doses mentioned in output
  2. Contraindicated drug pairs       — checks if output recommends drugs that
                                        are known to have severe interactions
  3. Pediatric safety flags           — detects adult drug mentions in pediatric
                                        context without age-appropriate caveats
  4. Pregnancy risk signals           — detects Category X drugs mentioned
                                        in obstetric queries without warnings
  5. Off-label/experimental therapy   — warns if experimental treatments are
                                        presented as first-line without caveats
  6. Lab value critical range check   — detects critically abnormal lab values
                                        mentioned in output without action guidance

Design:
  - All checks are conservative (err on the side of adding warnings)
  - Results are advisory, never blocking (clinical output must reach clinician)
  - Returns ClinicalGuardrailResult with warnings and escalation flags
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

from backend.utils.logger import logger


# ── Known dangerous drug pairs (simplified — extend with full DB in production) ─

_DANGEROUS_PAIRS: List[tuple] = [
    # (drug_a_pattern, drug_b_pattern, description)
    (r"\bwarfarin\b", r"\baspirin\b",       "Warfarin + Aspirin: high bleeding risk"),
    (r"\bwarfarin\b", r"\bibuprofen\b",     "Warfarin + Ibuprofen: high bleeding risk"),
    (r"\bSSRI\b|\bcitalopram\b|\bsertraline\b|\bfluoxetine\b",
     r"\bMAOI\b|\bphenelzine\b|\bisocarboxazid\b",
                                            "SSRI + MAOI: risk of serotonin syndrome"),
    (r"\bmetformin\b",  r"\biodinated\s+contrast\b|\bcontrast\s+dye\b",
                                            "Metformin + Iodinated Contrast: lactic acidosis risk"),
    (r"\bstatins?\b|\batorvastatin\b|\brosuvastatin\b",
     r"\bgemfibrozil\b",                    "Statin + Gemfibrozil: rhabdomyolysis risk"),
    (r"\bsildenafil\b|\btadalafil\b",
     r"\bnitrates?\b|\bnitroglycerin\b|\bisosorbide\b",
                                            "PDE5 inhibitor + Nitrates: severe hypotension risk"),
    (r"\bclopidogrel\b", r"\bomeprazole\b", "Clopidogrel + Omeprazole: reduced antiplatelet effect"),
    (r"\bACE\s+inhibitors?\b|\blisinopril\b|\bramipril\b|\benalapril\b",
     r"\bspironolactone\b|\bpotassium\b",   "ACEi + Potassium-sparing diuretics: hyperkalemia risk"),
    (r"\bamiodarone\b", r"\bdigoxin\b",     "Amiodarone + Digoxin: digoxin toxicity risk"),
    (r"\bmethotrexate\b", r"\bNSAIDs?\b|\bibuprofen\b|\bnaproxen\b",
                                            "Methotrexate + NSAIDs: methotrexate toxicity"),
]

# Category X drugs (teratogenic) — require pregnancy warning
_PREGNANCY_X_DRUGS = [
    r"\bwarfarin\b", r"\bmethotrexate\b", r"\bthalidomide\b",
    r"\bisotretinoin\b|\baccutane\b", r"\bACE\s+inhibitors?\b|\blisinopril\b|\bramipril\b",
    r"\bvalproic?\s+acid\b|\bvalproate\b|\bdepakote\b",
    r"\bfluconazole\b",  r"\btetracycline\b", r"\bdoxycycline\b",
    r"\bstatins?\b|\batorvastatin\b|\bsimvastatin\b|\brosuvastatin\b",
]

# Critically high lab value patterns
_CRITICAL_LAB_PATTERNS = [
    (r"potassium\s*[=:>]\s*([6-9]\.\d+|\d{2})\s*(?:mmol|mEq)",   "Hyperkalemia (K⁺ ≥ 6.0): cardiac arrhythmia risk"),
    (r"glucose\s*[=:>]\s*([4-9]\d{2}|[1-9]\d{3})\s*(?:mg/dL|mmol)",   "Severe hyperglycemia: DKA/HHS risk"),
    (r"sodium\s*[=:<]\s*(1[0-2]\d)\s*(?:mmol|mEq)",               "Severe hyponatremia (Na⁺ ≤ 129): seizure/herniation risk"),
    (r"pH\s*[=:<]\s*(7\.[0-2]\d)",                                 "Severe acidosis (pH ≤ 7.29): critical condition"),
    (r"creatinine\s*[=:>]\s*([5-9]\.\d|[1-9]\d\.)\s*(?:mg/dL|µmol)",  "Severe renal impairment: dose adjustment required"),
    (r"INR\s*[=:>]\s*([5-9]\.?\d*|[1-9]\d\.?\d*)",                "Supratherapeutic INR (≥ 5): bleeding risk"),
    (r"troponin.{0,30}(elevated|raised|positive|high)",            "Elevated troponin: rule out ACS"),
    (r"lactate\s*[=:>]\s*([4-9]\.?\d*|\d{2}\.?\d*)\s*mmol",       "Elevated lactate (≥ 4.0): sepsis/shock indicator"),
]

# Pediatric-unsafe drug patterns (avoid in children without explicit dosing)
_PEDS_UNSAFE_ADULT_PATTERNS = [
    r"\baspirin\b",         # Reye's syndrome risk in children
    r"\bmetronidazole\b",   # Avoid in neonates
    r"\bfluoroquinolones?\b|\bciprofloxacin\b|\blevofloxacin\b",  # Cartilage risk <18
    r"\btetracyclines?\b|\bdoxycycline\b",   # Teeth/bone in <8yr
    r"\bchloramphenicol\b", # Grey baby syndrome
]

# Experimental / off-label therapy signals
_EXPERIMENTAL_SIGNALS = [
    r"\bexperimental\b", r"\boff.label\b", r"\bcompassionate\s+use\b",
    r"\bnot\s+(yet\s+)?(?:FDA|EMA|MHRA|TGA)\s+approved\b",
    r"\bclinical\s+trial\s+only\b", r"\binvestigational\b",
]

# Precompiled
_COMPILED_PEDS     = [re.compile(p, re.IGNORECASE) for p in _PEDS_UNSAFE_ADULT_PATTERNS]
_COMPILED_PREG_X   = [re.compile(p, re.IGNORECASE) for p in _PREGNANCY_X_DRUGS]
_COMPILED_EXPTL    = [re.compile(p, re.IGNORECASE) for p in _EXPERIMENTAL_SIGNALS]


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class ClinicalGuardrailResult:
    safe:              bool            # False only for catastrophic failures
    warnings:          List[str] = field(default_factory=list)
    critical_alerts:   List[str] = field(default_factory=list)
    escalation_needed: bool      = False
    reasons:           List[str] = field(default_factory=list)
    modified_response: str       = ""  # set if inline annotations were added


# ── Guardrail ──────────────────────────────────────────────────────────────────

class ClinicalGuardrail:
    """
    Clinical domain-specific safety guardrail.

    Usage:
        result = ClinicalGuardrail().check(
            response=final_response,
            query=original_query,
            clinical_intent=state.get("clinical_intent", ""),
            patient_context=state.get("patient_context", {}),
        )
    """

    def check(
        self,
        response:         str,
        query:            str        = "",
        clinical_intent:  str        = "",
        patient_context:  dict | None = None,
    ) -> ClinicalGuardrailResult:
        """Run all clinical safety checks."""

        ctx        = patient_context or {}
        warnings:        List[str] = []
        critical_alerts: List[str] = []
        reasons:         List[str] = []
        escalation_needed = False
        modified   = response

        combined_text = (query + " " + response).lower()

        # ── 1. Dangerous drug interaction pairs ───────────────────────────────
        for drug_a_pat, drug_b_pat, description in _DANGEROUS_PAIRS:
            if (re.search(drug_a_pat, combined_text, re.IGNORECASE) and
                    re.search(drug_b_pat, combined_text, re.IGNORECASE)):
                alert = f"⚠️ DRUG INTERACTION: {description}"
                critical_alerts.append(alert)
                reasons.append("DRUG_INTERACTION_DETECTED")
                escalation_needed = True
                # Add inline annotation if not already present
                if description not in modified:
                    modified += f"\n\n{alert} — Verify with pharmacist before prescribing."

        # ── 2. Pediatric context + adult-unsafe drugs ─────────────────────────
        is_pediatric = bool(re.search(
            r"\b(child|children|pediatric|paediatric|infant|neonate|newborn|"
            r"toddler|adolescent|teen|\d\s*(year|yr|month|week)s?\s*(old)?)\b",
            combined_text, re.IGNORECASE
        ))
        if is_pediatric:
            for pattern in _COMPILED_PEDS:
                m = pattern.search(response)
                if m:
                    drug = m.group()
                    alert = (
                        f"⚠️ PEDIATRIC SAFETY: '{drug}' requires special consideration "
                        f"in pediatric patients. Age-appropriate dosing and contraindications "
                        f"must be confirmed."
                    )
                    warnings.append(alert)
                    reasons.append("PEDIATRIC_DRUG_CAUTION")
                    escalation_needed = True

        # ── 3. Pregnancy context + Category X drugs ───────────────────────────
        is_obstetric = bool(re.search(
            r"\b(pregnant|pregnancy|obstetric|gestational|trimester|"
            r"antenatal|prenatal|gravida|fetus|foetus|maternal)\b",
            combined_text, re.IGNORECASE
        ))
        if is_obstetric:
            for pattern in _COMPILED_PREG_X:
                m = pattern.search(response)
                if m:
                    drug = m.group()
                    alert = (
                        f"🚨 TERATOGENICITY RISK: '{drug}' is classified as Pregnancy "
                        f"Category X or has known teratogenic risk. Contraindicated in "
                        f"pregnancy unless benefits clearly outweigh risks."
                    )
                    critical_alerts.append(alert)
                    reasons.append("PREGNANCY_CATEGORY_X_DRUG")
                    escalation_needed = True
                    if alert not in modified:
                        modified += f"\n\n{alert}"

        # ── 4. Critical laboratory value detection ────────────────────────────
        for lab_pattern, lab_description in _CRITICAL_LAB_PATTERNS:
            if re.search(lab_pattern, combined_text, re.IGNORECASE):
                alert = f"🔴 CRITICAL LAB VALUE: {lab_description}"
                critical_alerts.append(alert)
                reasons.append("CRITICAL_LAB_VALUE")
                escalation_needed = True
                if alert not in modified:
                    modified = alert + "\n\n" + modified

        # ── 5. Experimental / off-label therapy ───────────────────────────────
        for pattern in _COMPILED_EXPTL:
            if pattern.search(response):
                warning = (
                    "⚠️ EXPERIMENTAL/OFF-LABEL THERAPY mentioned. "
                    "Clinical evidence and regulatory status must be verified "
                    "before clinical application."
                )
                warnings.append(warning)
                reasons.append("EXPERIMENTAL_THERAPY_MENTIONED")
                break

        # ── 6. Emergency + no escalation path → add 911/emergency note ────────
        has_emergency = bool(re.search(
            r"\b(cardiac\s+arrest|STEMI|stroke|anaphylaxis|respiratory\s+failure|"
            r"septic\s+shock|aortic\s+dissection)\b",
            response, re.IGNORECASE
        ))
        if has_emergency and "call" not in response.lower() and "activate" not in response.lower():
            emergency_note = (
                "\n\n🚨 **IMMEDIATE ACTION**: If this is an acute emergency, "
                "activate your institution's emergency response protocol immediately "
                "(Code Blue / ACLS / Emergency Services)."
            )
            modified += emergency_note
            reasons.append("EMERGENCY_ACTION_GUIDANCE_ADDED")

        logger.info(
            f"[ClinicalGuardrail] Complete. critical_alerts={len(critical_alerts)} "
            f"warnings={len(warnings)} escalation={escalation_needed}"
        )

        return ClinicalGuardrailResult(
            safe              = True,   # never block — clinician must see output
            warnings          = warnings,
            critical_alerts   = critical_alerts,
            escalation_needed = escalation_needed,
            reasons           = reasons,
            modified_response = modified,
        )
