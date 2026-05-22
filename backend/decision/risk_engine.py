"""
risk_engine.py — Medical Risk Assessment Engine (Phase 4.5)

Architecture:
  The risk engine is a SIGNAL-BASED weighted scorer, NOT a rule chain.
  Every risk dimension is an independent RiskSignal with a weight.
  The composite score is a weighted sum normalised to [0, 1].
  This makes the engine:
    - auditable (every signal is individually logged)
    - configurable (weights can be tuned per deployment)
    - extensible (new signals are added without touching scoring logic)

Risk levels map to orchestration behaviour changes:
  LOW      → standard workflow, base thresholds
  MEDIUM   → slight threshold boost (+0.05)
  HIGH     → significant boost (+0.12), extra reflection allowed
  CRITICAL → max boost (+0.20), mandatory escalation, extra retries

Signal categories:
  1. Clinical emergency signals (chest pain, syncope, respiratory distress)
  2. Medication safety signals (interaction, overdose, contraindication)
  3. Evidence quality signals (low retrieval confidence, contradictions)
  4. Patient vulnerability signals (pediatric, geriatric, pregnancy)
  5. Procedural risk signals (surgery, invasive intervention)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from backend.decision.schemas import (
    RiskLevel, RiskSignal, RiskAssessment,
)
from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Signal Definitions
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class SignalSpec:
    """A compiled signal specification with keyword patterns and weight."""
    name:        str
    weight:      float           # contribution to composite 0–1 score
    patterns:    List[str]       # regex patterns (case-insensitive)
    description: str = ""


# ── Emergency Signals (weight: 0.25–0.40) ─────────────────────────────────────
EMERGENCY_SIGNALS: List[SignalSpec] = [
    SignalSpec("chest_pain",         0.35, [r"\bchest\s+pain\b", r"\bchest\s+tightness\b"],       "Possible ACS"),
    SignalSpec("st_elevation",       0.40, [r"\bst[\s-]?elevation\b", r"\bstemi\b"],               "STEMI pattern"),
    SignalSpec("respiratory_arrest", 0.40, [r"\brespiratory\s+arrest\b", r"\bapn[oe]a\b"],         "Airway emergency"),
    SignalSpec("severe_hypotension", 0.38, [r"\bhypotension\b", r"\bshock\b", r"\bsbp\s*[<≤]\s*90"], "Haemodynamic instability"),
    SignalSpec("altered_consciousness",0.35,[r"\bunresponsive\b", r"\bGCS\s*[<≤]\s*8\b", r"\bcoma\b"], "Neurological emergency"),
    SignalSpec("anaphylaxis",        0.38, [r"\banaphylax\w*\b", r"\bsevere\s+allergic\b"],        "Anaphylaxis"),
    SignalSpec("sepsis",             0.35, [r"\bsepsis\b", r"\bseptic\s+shock\b", r"\bqSOFA\b"],  "Sepsis / SIRS"),
    SignalSpec("stroke",             0.37, [r"\bstroke\b", r"\bcvA\b", r"\bcerebrovascular\b"],   "Stroke"),
    SignalSpec("suicidal",           0.40, [r"\bsuicid\w*\b", r"\bself.harm\b"],                   "Mental health emergency"),
    SignalSpec("overdose",           0.38, [r"\boverdose\b", r"\btoxic\s+ingestion\b"],            "Toxicological emergency"),
]

# ── Medication Safety Signals (weight: 0.15–0.30) ─────────────────────────────
MEDICATION_SIGNALS: List[SignalSpec] = [
    SignalSpec("drug_interaction",   0.25, [r"\binteraction\b", r"\bcontraindicated?\b"],          "Drug interaction"),
    SignalSpec("narrow_therapeutic", 0.30, [r"\bwarfarin\b", r"\blithium\b", r"\bdigoxin\b", r"\bphenytoin\b"], "Narrow TI drug"),
    SignalSpec("anticoagulation",    0.22, [r"\banticoagul\w*\b", r"\bheparin\b", r"\bnoak\b"],   "Anticoagulation risk"),
    SignalSpec("high_dose",          0.20, [r"\bhigh[\s-]?dose\b", r"\bmaximum\s+dose\b"],        "High dosing query"),
    SignalSpec("paediatric_drug",    0.25, [r"\bpaediatric\s+dose\b", r"\bneonatal\s+dose\b"],    "Paediatric dosing"),
    SignalSpec("chemotherapy",       0.28, [r"\bchemotherapy\b", r"\bcytotoxic\b"],               "Chemotherapy safety"),
]

# ── Patient Vulnerability Signals (weight: 0.10–0.20) ─────────────────────────
VULNERABILITY_SIGNALS: List[SignalSpec] = [
    SignalSpec("paediatric",         0.18, [r"\bneonatal\b", r"\binfant\b", r"\bpaediatric\b", r"\bchild\b"], "Paediatric patient"),
    SignalSpec("geriatric",          0.15, [r"\belderly\b", r"\bgeriatric\b", r"\b>?\s*80\s*year\b"], "Geriatric patient"),
    SignalSpec("pregnancy",          0.20, [r"\bpregnant\b", r"\bpregnancy\b", r"\bgestational\b"], "Obstetric"),
    SignalSpec("immunocompromised",  0.15, [r"\bimmunocompromised\b", r"\bHIV\b", r"\btransplant\b"], "Immunosuppression"),
    SignalSpec("renal_impairment",   0.12, [r"\brenal\s+impairment\b", r"\bCKD\s+stage\s+[345]\b"], "Renal dose adjustment"),
]

# ── Procedural / Surgical Signals (weight: 0.12–0.22) ─────────────────────────
PROCEDURAL_SIGNALS: List[SignalSpec] = [
    SignalSpec("surgery",            0.18, [r"\bsurgery\b", r"\bsurgical\b", r"\boperative\b"],   "Surgical procedure"),
    SignalSpec("invasive_procedure", 0.20, [r"\bcatheterisation\b", r"\bintubation\b", r"\bventilation\b"], "Invasive procedure"),
    SignalSpec("anaesthesia",        0.22, [r"\banaesthesia\b", r"\banaesthetic\b"],              "Anaesthesia"),
    SignalSpec("ICU",                0.20, [r"\bICU\b", r"\bintensive\s+care\b", r"\bventilat\w*\b"], "Critical care"),
]

ALL_SIGNAL_GROUPS: List[Tuple[str, List[SignalSpec]]] = [
    ("emergency",      EMERGENCY_SIGNALS),
    ("medication",     MEDICATION_SIGNALS),
    ("vulnerability",  VULNERABILITY_SIGNALS),
    ("procedural",     PROCEDURAL_SIGNALS),
]

# ── Evidence quality signals (evaluated from retrieval state) ──────────────────
# These are evaluated from numeric values, not text patterns.

ESCALATION_SCORE_THRESHOLD = 0.55   # risk score above which escalation is flagged


# ═════════════════════════════════════════════════════════════════════════════
# Scoring Functions
# ═════════════════════════════════════════════════════════════════════════════

def _match_signals(text: str, specs: List[SignalSpec]) -> List[RiskSignal]:
    """Evaluate all signal specs against text. Returns triggered signals."""
    text_lower = text.lower()
    results    = []
    for spec in specs:
        triggered = any(re.search(p, text_lower, re.IGNORECASE) for p in spec.patterns)
        results.append(RiskSignal(
            name        = spec.name,
            weight      = spec.weight,
            triggered   = triggered,
            description = spec.description,
        ))
    return results


def _evidence_quality_signals(
    retrieval_confidence: float,
    contradiction_detected: bool,
    evidence_coverage: float,
) -> List[RiskSignal]:
    """Numeric evidence quality signals."""
    return [
        RiskSignal(
            name      = "low_retrieval_confidence",
            weight    = 0.18,
            triggered = retrieval_confidence < 0.50,
            description = f"Retrieval confidence {retrieval_confidence:.2f} < 0.50",
        ),
        RiskSignal(
            name      = "contradictory_evidence",
            weight    = 0.22,
            triggered = contradiction_detected,
            description = "Conflicting evidence detected in retrieved docs",
        ),
        RiskSignal(
            name      = "sparse_evidence",
            weight    = 0.15,
            triggered = evidence_coverage < 0.40,
            description = f"Evidence coverage {evidence_coverage:.2f} < 0.40",
        ),
    ]


def _compute_composite_score(signals: List[RiskSignal]) -> float:
    """
    Weighted composite risk score.
    Uses a saturating formula so multiple minor signals don't
    dominate a single critical emergency signal:
      score = 1 - Π(1 - w_i)  for all triggered signals
    This is equivalent to "probability any signal fires" under independence.
    """
    active_weights = [s.weight for s in signals if s.triggered]
    if not active_weights:
        return 0.0
    complement = 1.0
    for w in active_weights:
        complement *= (1.0 - w)
    return round(1.0 - complement, 4)


def _score_to_level(score: float) -> RiskLevel:
    if score >= 0.55:
        return RiskLevel.CRITICAL
    elif score >= 0.35:
        return RiskLevel.HIGH
    elif score >= 0.15:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


_CONFIDENCE_BOOST = {
    RiskLevel.LOW:      0.00,
    RiskLevel.MEDIUM:   0.05,
    RiskLevel.HIGH:     0.12,
    RiskLevel.CRITICAL: 0.20,
}

_MAX_RETRIES_OVERRIDE = {
    RiskLevel.LOW:      None,   # use workflow default
    RiskLevel.MEDIUM:   None,
    RiskLevel.HIGH:     3,
    RiskLevel.CRITICAL: 4,
}


# ═════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═════════════════════════════════════════════════════════════════════════════

def assess_risk(
    query:                  str,
    retrieval_confidence:   float = 0.70,
    contradiction_detected: bool  = False,
    evidence_coverage:      float = 0.70,
) -> RiskAssessment:
    """
    Full risk assessment against a medical query.

    Args:
        query:                  The (acronym-expanded) medical query.
        retrieval_confidence:   Composite retrieval score (0–1).
        contradiction_detected: Whether validation found contradictions.
        evidence_coverage:      % of query entities covered by evidence.

    Returns:
        RiskAssessment with level, score, signals, and orchestration adjustments.
    """
    all_signals: List[RiskSignal] = []

    # Text-pattern signals
    for _, specs in ALL_SIGNAL_GROUPS:
        all_signals.extend(_match_signals(query, specs))

    # Evidence quality signals
    all_signals.extend(_evidence_quality_signals(
        retrieval_confidence, contradiction_detected, evidence_coverage
    ))

    score   = _compute_composite_score(all_signals)
    level   = _score_to_level(score)
    factors = [s.description for s in all_signals if s.triggered]

    logger.info(
        f"[RiskEngine] score={score:.3f}, level={level.value}, "
        f"signals_triggered={sum(1 for s in all_signals if s.triggered)}"
    )

    return RiskAssessment(
        level                = level,
        score                = score,
        signals              = all_signals,
        requires_escalation  = score >= ESCALATION_SCORE_THRESHOLD,
        confidence_boost     = _CONFIDENCE_BOOST[level],
        max_retries_override = _MAX_RETRIES_OVERRIDE[level],
        contributing_factors = factors,
    )
