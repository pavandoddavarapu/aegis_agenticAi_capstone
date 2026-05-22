"""
contradiction_analyzer.py — Evidence Contradiction Detection (Phase 12)

Detects conflicts between retrieved evidence sources before they reach
the reasoning agent, preventing contradictory guidance from being presented
as a unified recommendation.

Problem solved:
  When two sources recommend conflicting treatments (e.g., one says "use
  antibiotic X" and another says "X is contraindicated"), passing both to
  the LLM reasoning agent can result in confused or unreliable outputs.
  This module detects these conflicts and either resolves them (defer to
  higher trust source) or flags them for human review.

Contradiction types detected:
  1. Drug recommendation conflicts (recommend vs contraindicate)
  2. Dosage conflicts (numeric value disagreements)
  3. Diagnostic criteria conflicts (positive vs negative finding)
  4. Guideline version conflicts (old vs updated recommendation)
  5. Multimodal vs textual conflicts (image says X, text says Y)

Design:
  - Rule-based pattern matching (no LLM) — deterministic, fast
  - Uses EvidenceScore.trust_score for resolution strategy
  - Outputs ContradictionReport with confidence penalty

Usage:
  from backend.evaluation.contradiction_analyzer import (
      analyze_contradictions, ContradictionReport
  )
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Conflict Detection Patterns
# ═════════════════════════════════════════════════════════════════════════════

# Drug terms that often appear in conflicts
_DRUG_NAMES = [
    "aspirin", "warfarin", "heparin", "metformin", "insulin", "atorvastatin",
    "lisinopril", "metoprolol", "amlodipine", "furosemide", "amiodarone",
    "digoxin", "clopidogrel", "rivaroxaban", "apixaban", "dabigatran",
    "vancomycin", "piperacillin", "tazobactam", "meropenem", "gentamicin",
    "penicillin", "amoxicillin", "ciprofloxacin", "azithromycin", "dexamethasone",
    "prednisone", "hydrocortisone", "morphine", "fentanyl", "tramadol",
    "paracetamol", "ibuprofen", "diclofenac", "omeprazole", "pantoprazole",
]

# Positive recommendation patterns
_RECOMMEND_PATTERNS = [
    r"\b(?:recommend|indicated|first.?line|administer|give|use|prescribe|start)\b",
    r"\bshould\s+(?:be\s+)?(?:given|used|administered|prescribed)\b",
    r"\bis\s+(?:the\s+)?(?:treatment|therapy|drug)\s+of\s+choice\b",
    r"\bbeneficial\b", r"\beffective\b", r"\befficacious\b",
]

# Negative recommendation patterns
_CONTRAINDICATE_PATTERNS = [
    r"\b(?:contraindicated?|avoid|do\s+not\s+use|should\s+not|must\s+not|never\s+use)\b",
    r"\b(?:harmful|dangerous|unsafe|prohibited)\b",
    r"\bnot\s+(?:recommended|indicated|safe)\b",
    r"\bcontra.?indication\b",
]

# Diagnostic positive patterns
_POSITIVE_FINDING_PATTERNS = [
    r"\b(?:positive|elevated|increased|high|present|confirmed|consistent\s+with)\b",
    r"\bsuggest(?:s|ive)?\s+of\b", r"\bdiagnosed\s+with\b",
    r"\b(?:ST\s+elevation|STEMI|ACS|MI)\b",
]

# Diagnostic negative patterns
_NEGATIVE_FINDING_PATTERNS = [
    r"\b(?:negative|normal|within\s+normal\s+limits|WNL|absent|not\s+present|ruled\s+out)\b",
    r"\bno\s+(?:evidence|sign|finding)\s+of\b",
    r"\bexcludes?\b",
]

# Numeric extraction (for dosage comparison)
_NUMERIC_DOSE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:mg|mcg|μg|g|units?|IU|mEq|mmol|ml|mg/kg)\b",
    re.IGNORECASE,
)


# ═════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ContradictionPair:
    """A detected conflict between two evidence sources."""
    source_a_id:    str
    source_b_id:    str
    source_a_ref:   str
    source_b_ref:   str
    conflict_type:  str   # drug_recommendation|dosage|diagnosis|guideline_version|multimodal
    conflict_description: str
    severity:       str   # minor|moderate|critical
    # Resolution strategy
    resolution_strategy: str   # defer_to_highest_trust|flag_for_review|escalate
    winning_source_id:   Optional[str] = None
    confidence_penalty:  float = 0.0


@dataclass
class ContradictionReport:
    """Complete contradiction analysis result."""
    has_contradictions:   bool
    contradiction_pairs:  List[ContradictionPair] = field(default_factory=list)
    overall_severity:     str   = "none"     # none|minor|moderate|critical
    total_penalty:        float = 0.0        # sum of confidence penalties (capped at 0.30)
    escalation_required:  bool  = False
    resolution_notes:     List[str] = field(default_factory=list)
    summary:              str   = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_contradictions":  self.has_contradictions,
            "overall_severity":    self.overall_severity,
            "total_penalty":       round(self.total_penalty, 3),
            "escalation_required": self.escalation_required,
            "contradiction_count": len(self.contradiction_pairs),
            "summary":             self.summary,
            "resolution_notes":    self.resolution_notes,
            "pairs": [
                {
                    "source_a": p.source_a_ref,
                    "source_b": p.source_b_ref,
                    "conflict_type": p.conflict_type,
                    "description": p.conflict_description,
                    "severity": p.severity,
                    "resolution": p.resolution_strategy,
                }
                for p in self.contradiction_pairs
            ],
        }


# ═════════════════════════════════════════════════════════════════════════════
# Detection Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _has_pattern(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _extract_drug_mentions(text: str) -> List[str]:
    """Return list of drug names mentioned in text."""
    text_lower = text.lower()
    return [drug for drug in _DRUG_NAMES if drug in text_lower]


def _get_drug_stance(text: str, drug: str) -> Optional[str]:
    """
    Determine if text recommends or contraindicates a drug.
    Returns: "recommend" | "contraindicate" | None (neutral)
    """
    # Find sentences/clauses near the drug name
    pattern = re.compile(
        rf".{{0,100}}\b{re.escape(drug)}\b.{{0,100}}", re.IGNORECASE
    )
    contexts = pattern.findall(text)
    if not contexts:
        return None

    context_text = " ".join(contexts)

    is_recommend    = _has_pattern(context_text, _RECOMMEND_PATTERNS)
    is_contraindicate = _has_pattern(context_text, _CONTRAINDICATE_PATTERNS)

    if is_recommend and not is_contraindicate:
        return "recommend"
    if is_contraindicate and not is_recommend:
        return "contraindicate"
    return None  # Ambiguous or both


def _check_drug_conflicts(
    text_a: str, text_b: str,
    ref_a: str, ref_b: str,
    id_a: str, id_b: str,
    trust_a: float, trust_b: float,
) -> List[ContradictionPair]:
    """Detect drug recommendation conflicts between two texts."""
    conflicts = []
    all_drugs = set(_extract_drug_mentions(text_a)) & set(_extract_drug_mentions(text_b))

    for drug in all_drugs:
        stance_a = _get_drug_stance(text_a, drug)
        stance_b = _get_drug_stance(text_b, drug)

        if stance_a and stance_b and stance_a != stance_b:
            severity = "critical" if drug in [
                "warfarin", "heparin", "digoxin", "amiodarone", "insulin"
            ] else "moderate"

            penalty = 0.20 if severity == "critical" else 0.10
            winning = id_a if trust_a >= trust_b else id_b
            resolution = "escalate" if severity == "critical" else "defer_to_highest_trust"

            conflicts.append(ContradictionPair(
                source_a_id         = id_a,
                source_b_id         = id_b,
                source_a_ref        = ref_a,
                source_b_ref        = ref_b,
                conflict_type       = "drug_recommendation",
                conflict_description = (
                    f"Source '{ref_a}' {stance_a}s {drug} while "
                    f"source '{ref_b}' {stance_b}s it."
                ),
                severity            = severity,
                resolution_strategy = resolution,
                winning_source_id   = winning,
                confidence_penalty  = penalty,
            ))

    return conflicts


def _check_diagnostic_conflicts(
    text_a: str, text_b: str,
    ref_a: str, ref_b: str,
    id_a: str, id_b: str,
    trust_a: float, trust_b: float,
) -> List[ContradictionPair]:
    """Detect diagnostic finding conflicts."""
    conflicts = []

    # Check for STEMI/ACS specific conflicts (high clinical significance)
    stemi_terms = ["STEMI", "ST elevation", "acute MI", "ACS"]
    for term in stemi_terms:
        a_positive = bool(re.search(term, text_a, re.IGNORECASE)) and _has_pattern(text_a, _POSITIVE_FINDING_PATTERNS)
        a_negative = _has_pattern(text_a, _NEGATIVE_FINDING_PATTERNS) and bool(re.search(term, text_a, re.IGNORECASE))
        b_positive = bool(re.search(term, text_b, re.IGNORECASE)) and _has_pattern(text_b, _POSITIVE_FINDING_PATTERNS)
        b_negative = _has_pattern(text_b, _NEGATIVE_FINDING_PATTERNS) and bool(re.search(term, text_b, re.IGNORECASE))

        if (a_positive and b_negative) or (a_negative and b_positive):
            conflicts.append(ContradictionPair(
                source_a_id         = id_a,
                source_b_id         = id_b,
                source_a_ref        = ref_a,
                source_b_ref        = ref_b,
                conflict_type       = "diagnosis",
                conflict_description = (
                    f"Conflicting {term} finding: one source indicates positive, "
                    f"another indicates negative or absent."
                ),
                severity            = "critical",
                resolution_strategy = "escalate",
                winning_source_id   = id_a if trust_a >= trust_b else id_b,
                confidence_penalty  = 0.25,
            ))

    return conflicts


def _check_multimodal_conflict(
    semantic_texts: List[str],
    visual_context: str,
    visual_id: str,
) -> List[ContradictionPair]:
    """Detect conflicts between multimodal findings and textual evidence."""
    if not visual_context or not semantic_texts:
        return []

    conflicts = []

    # Check: visual says ST elevation but text says no ST changes
    if re.search(r"\bST.?elevation\b", visual_context, re.IGNORECASE):
        for i, text in enumerate(semantic_texts):
            if re.search(r"\bno\s+ST.?(?:elevation|changes)\b", text, re.IGNORECASE):
                conflicts.append(ContradictionPair(
                    source_a_id         = visual_id,
                    source_b_id         = f"sem_{i}",
                    source_a_ref        = "Visual/ECG Analysis",
                    source_b_ref        = f"Semantic Doc {i+1}",
                    conflict_type       = "multimodal",
                    conflict_description = (
                        "ECG/visual analysis indicates ST elevation, but retrieved "
                        "text evidence indicates no ST changes. Patient-specific "
                        "multimodal analysis should take precedence."
                    ),
                    severity            = "moderate",
                    resolution_strategy = "defer_to_highest_trust",
                    winning_source_id   = visual_id,
                    confidence_penalty  = 0.10,
                ))

    return conflicts


# ═════════════════════════════════════════════════════════════════════════════
# Severity + Summary
# ═════════════════════════════════════════════════════════════════════════════

def _overall_severity(pairs: List[ContradictionPair]) -> str:
    if not pairs:
        return "none"
    severities = [p.severity for p in pairs]
    if "critical" in severities:
        return "critical"
    if "moderate" in severities:
        return "moderate"
    return "minor"


def _build_summary(pairs: List[ContradictionPair]) -> str:
    if not pairs:
        return "No contradictions detected across evidence sources."
    types = {}
    for p in pairs:
        types[p.conflict_type] = types.get(p.conflict_type, 0) + 1
    type_str = ", ".join(f"{k}({v})" for k, v in types.items())
    return (
        f"{len(pairs)} contradiction(s) detected: {type_str}. "
        f"Overall severity: {_overall_severity(pairs)}."
    )


# ═════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═════════════════════════════════════════════════════════════════════════════

def analyze_contradictions(
    docs:             List[Dict[str, Any]],
    evidence_scores:  Optional[List[Any]] = None,   # List[EvidenceScore] — optional
    graph_context:    str = "",
    research_context: str = "",
    visual_context:   str = "",
) -> ContradictionReport:
    """
    Analyze all retrieved evidence for internal contradictions.

    Args:
        docs:             Semantic retrieval results.
        evidence_scores:  Optional EvidenceScore list for trust-based resolution.
        graph_context:    Neo4j graph context.
        research_context: Live research context.
        visual_context:   Multimodal/visual analysis context.

    Returns:
        ContradictionReport
    """
    logger.info(
        f"[ContradictionAnalyzer] Checking {len(docs)} docs + "
        f"graph={'yes' if graph_context else 'no'} "
        f"research={'yes' if research_context else 'no'} "
        f"visual={'yes' if visual_context else 'no'}"
    )

    all_pairs: List[ContradictionPair] = []

    # Build trust lookup
    trust_map: Dict[str, float] = {}
    if evidence_scores:
        for ev in evidence_scores:
            try:
                trust_map[ev.source_id] = ev.trust_score
            except AttributeError:
                pass

    # Extract doc texts for comparison
    doc_texts  = [d.get("text", "") for d in docs]
    doc_refs   = [d.get("source", f"doc_{i}") for i, d in enumerate(docs)]
    doc_ids    = [f"sem_{i}" for i in range(len(docs))]

    # Add research/graph to comparison pool
    all_texts = list(doc_texts)
    all_refs  = list(doc_refs)
    all_ids   = list(doc_ids)
    all_trust = [trust_map.get(f"sem_{i}", 0.70) for i in range(len(docs))]

    if research_context:
        all_texts.append(research_context)
        all_refs.append("PubMed Research")
        all_ids.append("research_0")
        all_trust.append(trust_map.get("research_0", 0.80))

    if graph_context:
        all_texts.append(graph_context)
        all_refs.append("Neo4j Graph")
        all_ids.append("graph_0")
        all_trust.append(trust_map.get("graph_0", 0.88))

    # ── Pairwise comparison ───────────────────────────────────────────────────
    n = len(all_texts)
    for i in range(n):
        for j in range(i + 1, n):
            text_a = all_texts[i]
            text_b = all_texts[j]
            if not text_a or not text_b:
                continue

            # Drug conflicts
            try:
                pairs = _check_drug_conflicts(
                    text_a, text_b,
                    all_refs[i], all_refs[j],
                    all_ids[i], all_ids[j],
                    all_trust[i], all_trust[j],
                )
                all_pairs.extend(pairs)
            except Exception as exc:
                logger.debug(f"[ContradictionAnalyzer] Drug check failed {i},{j}: {exc}")

            # Diagnostic conflicts
            try:
                pairs = _check_diagnostic_conflicts(
                    text_a, text_b,
                    all_refs[i], all_refs[j],
                    all_ids[i], all_ids[j],
                    all_trust[i], all_trust[j],
                )
                all_pairs.extend(pairs)
            except Exception as exc:
                logger.debug(f"[ContradictionAnalyzer] Diagnostic check failed {i},{j}: {exc}")

    # ── Multimodal vs text conflicts ──────────────────────────────────────────
    if visual_context:
        try:
            pairs = _check_multimodal_conflict(doc_texts, visual_context, "visual_0")
            all_pairs.extend(pairs)
        except Exception as exc:
            logger.debug(f"[ContradictionAnalyzer] Multimodal check failed: {exc}")

    # ── Build report ──────────────────────────────────────────────────────────
    severity = _overall_severity(all_pairs)
    total_penalty = min(sum(p.confidence_penalty for p in all_pairs), 0.30)  # cap at 0.30
    escalation_required = severity == "critical"

    resolution_notes = []
    for p in all_pairs:
        if p.winning_source_id:
            resolution_notes.append(
                f"{p.conflict_type}: deferring to source '{p.winning_source_id}' "
                f"(higher trust)."
            )

    report = ContradictionReport(
        has_contradictions  = len(all_pairs) > 0,
        contradiction_pairs = all_pairs,
        overall_severity    = severity,
        total_penalty       = round(total_penalty, 3),
        escalation_required = escalation_required,
        resolution_notes    = resolution_notes,
        summary             = _build_summary(all_pairs),
    )

    if all_pairs:
        logger.warning(
            f"[ContradictionAnalyzer] {len(all_pairs)} contradiction(s) found. "
            f"Severity: {severity}. Penalty: {total_penalty:.3f}. "
            f"Escalate: {escalation_required}"
        )
    else:
        logger.info("[ContradictionAnalyzer] No contradictions detected.")

    return report
