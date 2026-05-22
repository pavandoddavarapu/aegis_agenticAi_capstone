"""
information_sufficiency_engine.py — Clinical Information Sufficiency Analyzer (Phase 12)

Determines whether enough clinical context exists to execute safely.
Uses signal-based detection (regex + keyword, NO LLM) for speed and determinism.

Design:
  - Signal-based only (no LLM) — deterministic, fast, no hallucination risk
  - Domain-aware: different requirements for cardiac vs metabolic vs medication queries
  - Emergency bypass: CRITICAL risk cases always can_proceed=True
  - Non-blocking: missing information produces warnings, not hard failures

Usage:
  from backend.decision.information_sufficiency_engine import (
      check_sufficiency, SufficiencyReport
  )
  report = check_sufficiency(query, clinical_intent)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.decision.execution_plan import (
    ClarificationQuestion, ClinicalIntent,
    QuestionCategory, QuestionPriority,
)
from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Signal Definitions — what counts as "present" in a clinical query
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class PresenceSignal:
    """Detects whether a clinical element is present in the query text."""
    name:        str
    category:    str
    patterns:    List[str]   # regex patterns (case-insensitive)
    description: str = ""


# Demographics
DEMOGRAPHICS_SIGNALS = [
    PresenceSignal(
        "age", "demographics",
        [r"\b\d{1,3}[\s-]?year[\s-]?old\b", r"\bage\s*[:=]?\s*\d{1,3}\b",
         r"\b\d{1,3}\s*(?:yo|yrs?|years?)\b"],
        "Patient age"
    ),
    PresenceSignal(
        "gender", "demographics",
        [r"\b(?:male|female|man|woman|boy|girl|gentleman|lady)\b",
         r"\b(?:M|F)\s*(?:,|\.|/|\d)"],
        "Patient gender"
    ),
]

# Chief Complaint / Symptoms
COMPLAINT_SIGNALS = [
    PresenceSignal(
        "chief_complaint", "chief_complaint",
        [
            r"\bpresenting\s+with\b", r"\bcomplaining\s+of\b", r"\bc/o\b",
            r"\bsuffering\s+from\b", r"\bexperiencing\b",
            # Natural language: "with chest pain", "with shortness of breath"
            r"\bwith\s+(?:chest|back|abdominal|head|throat|neck|leg|arm|severe|acute|sudden)\b",
            # Direct symptom words — these alone indicate a chief complaint
            r"\b(?:chest\s+pain|chest\s+tightness|chest\s+pressure|angina)\b",
            r"\b(?:shortness\s+of\s+breath|dyspnea|breathlessness|sob)\b",
            r"\b(?:palpitation|syncope|dizziness|lightheadedness|vertigo)\b",
            r"\b(?:diaphoresis|sweating|nausea|vomiting|headache|confusion)\b",
            r"\b(?:weakness|paralysis|slurred\s+speech|seizure|convulsion)\b",
            r"\b(?:swelling|edema|jaundice|haematuria|haemoptysis|haematemesis)\b",
            # Old-style patterns
            r"\bhas\b.{0,30}\b(?:pain|ache|fever|dyspnea|cough|weakness|swelling)\b",
        ],
        "Chief complaint / presenting symptom"
    ),
    PresenceSignal(
        "symptom_duration", "symptoms",
        [r"\b(?:for\s+(?:the\s+)?(?:past\s+)?\d+\s*(?:hours?|days?|weeks?|months?))\b",
         r"\bsince\s+(?:yesterday|last\s+\w+|\d+\s*(?:hours?|days?))\b",
         r"\b(?:onset|started|began)\s+\w*\s*(?:\d+\s*(?:hours?|days?)|\btoday\b|\byesterday\b)\b",
         r"\b(?:acute|sudden|chronic|progressive|gradual)\b"],
        "Symptom duration / onset"
    ),
]


# Vitals
VITALS_SIGNALS = [
    PresenceSignal(
        "blood_pressure", "vitals",
        [r"\bBP\s*[:=]?\s*\d{2,3}/\d{2,3}\b",
         r"\b(?:blood\s+pressure|systolic|diastolic)\s*[:=]?\s*\d{2,3}\b",
         r"\b\d{2,3}/\d{2,3}\s*(?:mmHg|mm\s*Hg)\b"],
        "Blood pressure"
    ),
    PresenceSignal(
        "heart_rate", "vitals",
        [r"\bHR\s*[:=]?\s*\d{2,3}\b",
         r"\b(?:heart\s+rate|pulse)\s*[:=]?\s*\d{2,3}\b",
         r"\b\d{2,3}\s*(?:bpm|beats?/min)\b"],
        "Heart rate"
    ),
    PresenceSignal(
        "oxygen_saturation", "vitals",
        [r"\bO2\s*(?:sat|saturation)?\s*[:=]?\s*\d{2,3}%?\b",
         r"\bSpO2\s*[:=]?\s*\d{2,3}\b",
         r"\boxygen\s+saturation\s*[:=]?\s*\d{2,3}\b"],
        "Oxygen saturation"
    ),
    PresenceSignal(
        "temperature", "vitals",
        [r"\btemp(?:erature)?\s*[:=]?\s*\d{2,3}(?:\.\d)?\s*(?:°?[CF])?\b",
         r"\bT\s*[:=]?\s*\d{2,3}(?:\.\d)?\b"],
        "Temperature"
    ),
]

# Medications
MEDICATION_SIGNALS = [
    PresenceSignal(
        "medications", "medications",
        [r"\b(?:on|taking|prescribed|currently\s+(?:on|taking))\s+\w+(?:mg|mcg|units?)?\b",
         r"\bmedications?\s*[:=]",
         r"\b(?:metformin|warfarin|aspirin|atorvastatin|lisinopril|metoprolol|amlodipine|heparin|insulin|furosemide|omeprazole|pantoprazole)\b",
         r"\bno\s+(?:medications?|meds?|drugs?)\b",
         r"\bNKDA\b", r"\bnot\s+on\s+any\s+medications?\b"],
        "Current medications"
    ),
    PresenceSignal(
        "allergies", "allergies",
        [r"\ballerg(?:ic|ies?|y)\s+to\b",
         r"\bNKDA\b", r"\bno\s+(?:known\s+)?drug\s+allergies?\b",
         r"\ballergies?\s*[:=]"],
        "Drug allergies"
    ),
]

# Past Medical History
HISTORY_SIGNALS = [
    PresenceSignal(
        "past_history", "history",
        [r"\bhistory\s+of\b", r"\bPMH\b", r"\bknown\s+(?:case\s+of\s+)?\w+\b",
         r"\bback(?:ground|ground)\s+of\b",
         r"\b(?:diabetic|hypertensive|asthmatic|epileptic)\b",
         r"\bno\s+(?:significant\s+)?(?:medical\s+)?history\b",
         r"\bprevious(?:ly)?\b.{0,30}\b(?:surgery|procedure|hospitalization|admission)\b"],
        "Past medical history"
    ),
]

# Imaging / ECG
IMAGING_SIGNALS = [
    PresenceSignal(
        "ecg_data", "imaging",
        [r"\bECG\b", r"\bEKG\b", r"\b(?:ST[\s-]elevation|ST[\s-]depression)\b",
         r"\bQRS\b", r"\bsinus\s+(?:rhythm|tachycardia|bradycardia)\b",
         r"\batrial\s+fibrillation\b", r"\bT[\s-]wave\b", r"\bLBBB\b", r"\bRBBB\b"],
        "ECG / EKG data"
    ),
    PresenceSignal(
        "radiology", "imaging",
        [r"\b(?:X-ray|CXR|CT\s+scan|MRI|ultrasound|echo(?:cardiogram)?)\b",
         r"\bimaging\s+shows?\b", r"\bradiology\s+report\b"],
        "Radiology / imaging results"
    ),
]

# Lab Values
LAB_SIGNALS = [
    PresenceSignal(
        "cardiac_biomarkers", "labs",
        [r"\btroponin\b", r"\bCPK\b", r"\bCK[\s-]MB\b", r"\bBNP\b", r"\bNT[\s-]proBNP\b"],
        "Cardiac biomarkers (troponin, BNP)"
    ),
    PresenceSignal(
        "basic_labs", "labs",
        [r"\bHb\b", r"\bhaemoglobin\b", r"\bWBC\b", r"\bplatelet\b",
         r"\bcreatinine\b", r"\bGFR\b", r"\bsodium\b", r"\bpotassium\b",
         r"\bglucose\b", r"\bHbA1c\b", r"\bCBC\b", r"\bBMP\b", r"\bCMP\b"],
        "Basic laboratory values"
    ),
]

ALL_SIGNAL_GROUPS: Dict[str, List[PresenceSignal]] = {
    "demographics": DEMOGRAPHICS_SIGNALS,
    "complaint":    COMPLAINT_SIGNALS,
    "vitals":       VITALS_SIGNALS,
    "medications":  MEDICATION_SIGNALS,
    "history":      HISTORY_SIGNALS,
    "imaging":      IMAGING_SIGNALS,
    "labs":         LAB_SIGNALS,
}


# ═════════════════════════════════════════════════════════════════════════════
# Intent-Based Requirements
# ═════════════════════════════════════════════════════════════════════════════

# Per clinical intent: which elements are CRITICAL (must-have) vs IMPORTANT
INTENT_REQUIREMENTS: Dict[ClinicalIntent, Dict[str, List[str]]] = {
    ClinicalIntent.EMERGENCY_TRIAGE: {
        "critical":  ["age", "chief_complaint", "vitals_any"],
        "important": ["blood_pressure", "heart_rate", "oxygen_saturation", "symptom_duration"],
        "optional":  ["medications", "past_history"],
    },
    ClinicalIntent.DIAGNOSTIC_WORKUP: {
        "critical":  ["age", "chief_complaint", "symptom_duration"],
        "important": ["past_history", "medications", "vitals_any"],
        "optional":  ["allergies", "labs"],
    },
    ClinicalIntent.TREATMENT_PLANNING: {
        "critical":  ["age", "chief_complaint", "past_history"],
        "important": ["medications", "allergies"],
        "optional":  ["vitals_any", "labs"],
    },
    ClinicalIntent.MEDICATION_REVIEW: {
        "critical":  ["age", "medications"],
        "important": ["allergies", "past_history"],
        "optional":  ["vitals_any", "gender"],
    },
    ClinicalIntent.RESEARCH_LOOKUP: {
        "critical":  ["chief_complaint"],
        "important": [],
        "optional":  ["age", "past_history"],
    },
    ClinicalIntent.LITERATURE_SYNTHESIS: {
        "critical":  ["chief_complaint"],
        "important": [],
        "optional":  [],
    },
    ClinicalIntent.SIMILAR_CASE_SEARCH: {
        "critical":  ["age", "chief_complaint"],
        "important": ["past_history", "symptom_duration"],
        "optional":  ["vitals_any", "medications"],
    },
    ClinicalIntent.RISK_STRATIFICATION: {
        "critical":  ["age", "chief_complaint"],
        "important": ["vitals_any", "past_history"],
        "optional":  ["labs", "medications"],
    },
    ClinicalIntent.MONITORING_FOLLOW_UP: {
        "critical":  ["chief_complaint"],
        "important": ["past_history", "medications"],
        "optional":  ["vitals_any", "labs"],
    },
    ClinicalIntent.UNKNOWN: {
        "critical":  ["age", "chief_complaint"],
        "important": ["past_history"],
        "optional":  ["vitals_any", "medications"],
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Question Templates
# ═════════════════════════════════════════════════════════════════════════════

QUESTION_TEMPLATES: Dict[str, ClarificationQuestion] = {
    "age": ClarificationQuestion(
        question_text="What is the patient's age?",
        category=QuestionCategory.DEMOGRAPHICS,
        priority=QuestionPriority.CRITICAL,
        expected_format="numeric",
        hint="e.g., 65 years old",
    ),
    "gender": ClarificationQuestion(
        question_text="What is the patient's biological sex?",
        category=QuestionCategory.DEMOGRAPHICS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="choice",
        choices=["Male", "Female", "Not specified"],
    ),
    "chief_complaint": ClarificationQuestion(
        question_text="What is the patient's chief complaint or primary presenting symptom?",
        category=QuestionCategory.CHIEF_COMPLAINT,
        priority=QuestionPriority.CRITICAL,
        expected_format="freetext",
        hint="e.g., chest pain, shortness of breath, confusion",
    ),
    "symptom_duration": ClarificationQuestion(
        question_text="How long has the patient been experiencing these symptoms?",
        category=QuestionCategory.SYMPTOMS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="freetext",
        hint="e.g., 2 hours, 3 days, sudden onset 30 minutes ago",
    ),
    "vitals_any": ClarificationQuestion(
        question_text="What are the patient's current vital signs? (BP, HR, SpO2, Temp, RR)",
        category=QuestionCategory.VITALS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="freetext",
        hint="e.g., BP 160/100, HR 95, SpO2 94%, Temp 37.2°C, RR 18",
    ),
    "blood_pressure": ClarificationQuestion(
        question_text="What is the patient's blood pressure?",
        category=QuestionCategory.VITALS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="numeric",
        hint="e.g., 160/100 mmHg",
    ),
    "heart_rate": ClarificationQuestion(
        question_text="What is the patient's heart rate?",
        category=QuestionCategory.VITALS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="numeric",
        hint="e.g., 95 bpm",
    ),
    "oxygen_saturation": ClarificationQuestion(
        question_text="What is the patient's oxygen saturation (SpO2)?",
        category=QuestionCategory.VITALS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="numeric",
        hint="e.g., 94%",
    ),
    "medications": ClarificationQuestion(
        question_text="What medications is the patient currently taking? (or 'none')",
        category=QuestionCategory.MEDICATIONS,
        priority=QuestionPriority.IMPORTANT,
        expected_format="freetext",
        default_if_skipped="Not specified",
        hint="Include dose if known, e.g., Metformin 500mg BD, Amlodipine 5mg OD",
    ),
    "allergies": ClarificationQuestion(
        question_text="Does the patient have any known drug allergies? (or 'NKDA' for none)",
        category=QuestionCategory.ALLERGIES,
        priority=QuestionPriority.IMPORTANT,
        expected_format="freetext",
        default_if_skipped="Not specified",
        hint="e.g., Penicillin allergy, NKDA",
    ),
    "past_history": ClarificationQuestion(
        question_text="What is the patient's significant past medical history?",
        category=QuestionCategory.HISTORY,
        priority=QuestionPriority.IMPORTANT,
        expected_format="freetext",
        default_if_skipped="No significant past history provided",
        hint="e.g., Hypertension, Type 2 Diabetes, previous MI",
    ),
    "cardiac_biomarkers": ClarificationQuestion(
        question_text="Are cardiac biomarkers (troponin, BNP) available? If so, what are the values?",
        category=QuestionCategory.LABS,
        priority=QuestionPriority.CRITICAL,
        expected_format="freetext",
        default_if_skipped="Not available",
        hint="e.g., Troponin I: 2.4 ng/mL (elevated), BNP: 450 pg/mL",
    ),
    "basic_labs": ClarificationQuestion(
        question_text="Are any laboratory results available (CBC, BMP, HbA1c, etc.)?",
        category=QuestionCategory.LABS,
        priority=QuestionPriority.OPTIONAL,
        expected_format="freetext",
        default_if_skipped="Not available",
    ),
    "ecg_data": ClarificationQuestion(
        question_text="Is an ECG available? If so, what are the key findings?",
        category=QuestionCategory.IMAGING,
        priority=QuestionPriority.CRITICAL,
        expected_format="freetext",
        default_if_skipped="ECG not available",
        hint="e.g., Sinus tachycardia, ST elevation in V1-V4, LBBB",
    ),
}


# ═════════════════════════════════════════════════════════════════════════════
# Sufficiency Report
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class SufficiencyReport:
    """Output of the InformationSufficiencyEngine."""
    is_sufficient:           bool
    sufficiency_score:       float           # 0.0 – 1.0
    missing_critical:        List[str]       # blocks safe execution
    missing_important:       List[str]       # helpful but not blocking
    missing_optional:        List[str]       # nice to have
    clarification_questions: List[ClarificationQuestion] = field(default_factory=list)
    can_proceed:             bool = True     # True unless missing_critical present
    proceed_with_caveat:     str  = ""       # warning to attach to output
    completeness_by_domain:  Dict[str, float] = field(default_factory=dict)
    detected_elements:       Dict[str, bool]  = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# Core Detection Logic
# ═════════════════════════════════════════════════════════════════════════════

def _detect_element(text: str, signals: List[PresenceSignal]) -> Dict[str, bool]:
    """Returns {signal_name: True/False} for each signal in the group."""
    text_lower = text.lower()
    results = {}
    for sig in signals:
        triggered = any(re.search(p, text_lower, re.IGNORECASE) for p in sig.patterns)
        results[sig.name] = triggered
    return results


def _detect_vitals_any(detected: Dict[str, bool]) -> bool:
    """True if ANY vital sign is present."""
    return any([
        detected.get("blood_pressure", False),
        detected.get("heart_rate", False),
        detected.get("oxygen_saturation", False),
        detected.get("temperature", False),
    ])


def _compute_domain_score(detected: Dict[str, bool], domain_signals: List[str]) -> float:
    """Score a domain: fraction of signals detected."""
    if not domain_signals:
        return 1.0
    hits = sum(1 for s in domain_signals if detected.get(s, False))
    return round(hits / len(domain_signals), 3)


# ═════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═════════════════════════════════════════════════════════════════════════════

def check_sufficiency(
    query:           str,
    clinical_intent: ClinicalIntent,
    emergency_override: bool = False,
) -> SufficiencyReport:
    """
    Analyze whether the query contains sufficient clinical context.

    Args:
        query:              The clinical query / patient case text.
        clinical_intent:    What the clinician is trying to do.
        emergency_override: If True (CRITICAL risk), always return can_proceed=True.

    Returns:
        SufficiencyReport with missing elements and clarification questions.
    """
    if emergency_override:
        logger.info("[SufficiencyEngine] Emergency override — skipping sufficiency check.")
        return SufficiencyReport(
            is_sufficient=True,
            sufficiency_score=1.0,
            missing_critical=[],
            missing_important=[],
            missing_optional=[],
            can_proceed=True,
            proceed_with_caveat="Emergency case — sufficiency check bypassed.",
        )

    logger.info(
        f"[SufficiencyEngine] Checking sufficiency for intent={clinical_intent.value} "
        f"query='{query[:60]}...'"
    )

    # ── Detect all elements ───────────────────────────────────────────────────
    all_detected: Dict[str, bool] = {}
    for _group_name, signals in ALL_SIGNAL_GROUPS.items():
        all_detected.update(_detect_element(query, signals))

    # Synthetic: vitals_any = any vital detected
    all_detected["vitals_any"] = _detect_vitals_any(all_detected)

    # ── Look up intent requirements ───────────────────────────────────────────
    intent_key = clinical_intent
    if intent_key not in INTENT_REQUIREMENTS:
        intent_key = ClinicalIntent.UNKNOWN
    requirements = INTENT_REQUIREMENTS[intent_key]

    critical_needed  = requirements.get("critical", [])
    important_needed = requirements.get("important", [])
    optional_needed  = requirements.get("optional", [])

    # ── Identify missing elements ─────────────────────────────────────────────
    missing_critical  = [e for e in critical_needed  if not all_detected.get(e, False)]
    missing_important = [e for e in important_needed if not all_detected.get(e, False)]
    missing_optional  = [e for e in optional_needed  if not all_detected.get(e, False)]

    # ── Compute scores ────────────────────────────────────────────────────────
    # Weight: critical=0.6, important=0.3, optional=0.1
    critical_score  = _compute_domain_score(all_detected, critical_needed) if critical_needed else 1.0
    important_score = _compute_domain_score(all_detected, important_needed) if important_needed else 1.0
    optional_score  = _compute_domain_score(all_detected, optional_needed) if optional_needed else 1.0

    sufficiency_score = round(
        0.60 * critical_score + 0.30 * important_score + 0.10 * optional_score, 3
    )

    # Per-domain completeness
    completeness_by_domain = {
        "demographics": _compute_domain_score(all_detected, ["age", "gender"]),
        "complaint":    _compute_domain_score(all_detected, ["chief_complaint", "symptom_duration"]),
        "vitals":       _compute_domain_score(all_detected, ["blood_pressure", "heart_rate", "oxygen_saturation"]),
        "medications":  _compute_domain_score(all_detected, ["medications", "allergies"]),
        "history":      _compute_domain_score(all_detected, ["past_history"]),
        "labs":         _compute_domain_score(all_detected, ["cardiac_biomarkers", "basic_labs"]),
        "imaging":      _compute_domain_score(all_detected, ["ecg_data", "radiology"]),
    }

    # ── Determine can_proceed ─────────────────────────────────────────────────
    # Can proceed unless critical elements missing
    can_proceed = len(missing_critical) == 0

    # Caveat message if proceeding without full context
    caveat_parts = []
    if missing_critical:
        caveat_parts.append(f"Missing critical context: {', '.join(missing_critical)}")
    if missing_important:
        caveat_parts.append(f"Missing important context: {', '.join(missing_important)}")
    proceed_with_caveat = " | ".join(caveat_parts) if caveat_parts else ""

    # ── Generate clarification questions ─────────────────────────────────────
    questions: List[ClarificationQuestion] = []
    missing_all = missing_critical + missing_important + missing_optional
    
    if missing_all:
        try:
            import os, json
            from openai import OpenAI
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
            base_url = "https://api.groq.com/openai/v1" if os.getenv("GROQ_API_KEY") else None
            model = "llama-3.1-8b-instant" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            prompt = f"""You are a clinical AI orchestrator.
The clinician provided this patient query: "{query}"

The following clinical elements are missing or insufficiently specified: {', '.join(missing_all)}

Generate 1 to 3 dynamic, non-redundant clarification questions to ask the clinician.
Combine related questions (e.g., ask for 'vital signs (BP, HR, SpO2, Temp)' instead of 4 separate questions).
Return ONLY a valid JSON object with a single key "questions" containing an array of objects.
Each object must match this schema:
{{
  "question_text": "...",
  "category": "vitals" | "demographics" | "history" | "medications" | "imaging" | "labs" | "symptoms" | "chief_complaint",
  "priority": "critical" | "important" | "optional",
  "expected_format": "freetext",
  "hint": "e.g., ..."
}}"""
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if content:
                data = json.loads(content)
                for q_data in data.get("questions", [])[:5]:
                    from backend.decision.execution_plan import QuestionCategory, QuestionPriority
                    import uuid
                    # Try to map strings to enums safely, fallback to free text if unknown
                    try:
                        cat = QuestionCategory(q_data.get("category", "symptoms"))
                    except ValueError:
                        cat = QuestionCategory.SYMPTOMS
                    try:
                        pri = QuestionPriority(q_data.get("priority", "important"))
                    except ValueError:
                        pri = QuestionPriority.IMPORTANT
                        
                    q = ClarificationQuestion(
                        question_id=f"q_{uuid.uuid4().hex[:8]}",
                        question_text=q_data.get("question_text", "Could you provide more details?"),
                        category=cat,
                        priority=pri,
                        expected_format=q_data.get("expected_format", "freetext"),
                        hint=q_data.get("hint", "")
                    )
                    questions.append(q)
            logger.info(f"[SufficiencyEngine] Dynamically generated {len(questions)} questions.")
        except Exception as e:
            logger.warning(f"[SufficiencyEngine] Dynamic question generation failed: {e}. Falling back to static.")
            # Fallback to static mapping
            MAX_QUESTIONS = 5
            for element in missing_all:
                if len(questions) >= MAX_QUESTIONS:
                    break
                if element in QUESTION_TEMPLATES:
                    import copy
                    q = copy.deepcopy(QUESTION_TEMPLATES[element])
                    questions.append(q)

    is_sufficient = (
        len(missing_critical) == 0
        and sufficiency_score >= 0.50
    )

    logger.info(
        f"[SufficiencyEngine] score={sufficiency_score:.3f} "
        f"sufficient={is_sufficient} can_proceed={can_proceed} "
        f"missing_critical={missing_critical} "
        f"missing_important={missing_important}"
    )

    return SufficiencyReport(
        is_sufficient=is_sufficient,
        sufficiency_score=sufficiency_score,
        missing_critical=missing_critical,
        missing_important=missing_important,
        missing_optional=missing_optional,
        clarification_questions=questions,
        can_proceed=can_proceed,
        proceed_with_caveat=proceed_with_caveat,
        completeness_by_domain=completeness_by_domain,
        detected_elements=all_detected,
    )
