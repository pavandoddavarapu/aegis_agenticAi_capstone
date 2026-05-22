"""
evidence_evaluator.py — Evidence Quality Evaluation Layer (Phase 12)

Scores EVERY retrieved evidence source for trust, freshness, relevance,
and grounding quality BEFORE it influences reasoning.

Problem solved:
  Currently, a WHO guideline and a blurry OCR scan have equal weight in
  the reasoning prompt. This module introduces principled evidence quality
  scoring that directly affects which sources are used in reasoning and
  how much they contribute to confidence scoring.

Source Trust Taxonomy (evidence-based, peer-reviewed):
  authoritative    → WHO/CDC/AHA/ESC/NICE guidelines: trust≈0.97
  systematic_review → Cochrane/Meta-analyses: trust≈0.93
  high_evidence    → RCTs (PubMed): trust≈0.88
  graph_knowledge  → Neo4j medical graph: trust≈0.88
  moderate_evidence → Prospective cohort: trust≈0.80
  observational    → Retrospective cohort: trust≈0.72
  multimodal_high  → ECG/Radiology (confidence>0.85): trust≈0.90
  multimodal_med   → ECG/Radiology (confidence 0.60-0.85): trust≈0.75
  semantic_high    → Qdrant match (score>0.80): trust≈0.85
  semantic_med     → Qdrant match (score 0.60-0.80): trust≈0.70
  case_memory      → Similar case memory: trust≈0.72
  low_evidence     → Case reports/expert opinion: trust≈0.50
  multimodal_low   → Low-confidence OCR (<0.70): trust≈0.40
  poor             → Blurry/artifact: trust≈0.25

Design:
  - Uses existing research_ranker.py and freshness_engine.py
  - No LLM calls — deterministic, auditable
  - Results stored in state["evidence_scores"] and state["evidence_quality_summary"]
  - ValidationAgent reads evidence_quality_summary.avg_quality as additional weight

Usage:
  from backend.evaluation.evidence_evaluator import evaluate_evidence, EvidenceScore
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.logger import logger


# ═════════════════════════════════════════════════════════════════════════════
# Trust Taxonomy
# ═════════════════════════════════════════════════════════════════════════════

# Source type patterns to detect from document metadata
_GUIDELINE_SOURCES = [
    "who", "world health organization", "cdc", "centers for disease control",
    "nice", "aha", "american heart association", "esc", "european society",
    "acc", "american college of cardiology", "bts", "nice guidelines",
    "acog", "idsa", "ats", "ers", "jnc", "aasld",
]

_META_ANALYSIS_PATTERNS = [
    r"\bmeta.?analysis\b", r"\bsystematic\s+review\b", r"\bcochrane\b",
    r"\bevidence\s+synthesis\b",
]

_RCT_PATTERNS = [
    r"\brandomized\s+(?:controlled\s+)?trial\b", r"\bRCT\b",
    r"\bplacebo.?controlled\b", r"\bdouble.?blind\b",
]

_CASE_REPORT_PATTERNS = [
    r"\bcase\s+report\b", r"\bcase\s+series\b", r"\bN\s*=\s*[1-9]\d?\b",
]

_TIER_TRUST: Dict[str, float] = {
    "authoritative":      0.97,
    "systematic_review":  0.93,
    "high_evidence":      0.88,
    "graph_knowledge":    0.88,
    "multimodal_high":    0.90,
    "moderate_evidence":  0.80,
    "semantic_high":      0.85,
    "observational":      0.72,
    "case_memory":        0.72,
    "semantic_med":       0.70,
    "expert_opinion":     0.60,
    "multimodal_med":     0.75,
    "low_evidence":       0.50,
    "semantic_low":       0.50,
    "multimodal_low":     0.40,
    "poor":               0.25,
}

# Score below which source is excluded from reasoning
MINIMUM_QUALITY_THRESHOLD = 0.30


# ═════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class EvidenceScore:
    """Quality assessment for a single evidence source."""
    source_id:         str
    source_type:       str           # "semantic" | "graph" | "research" | "multimodal" | "case"
    source_reference:  str           # filename, URL, or identifier
    tier:              str           # trust tier label
    trust_score:       float         # 0-1 based on source type
    freshness_score:   float         # 0-1 based on publication date
    relevance_score:   float         # 0-1 based on semantic similarity score
    grounding_score:   float         # 0-1 based on overlap with query terms
    contradiction_flag: bool = False
    overall_quality:   float = 0.0   # composite
    use_in_reasoning:  bool  = True  # False if overall_quality < threshold
    weight_in_composite: float = 1.0 # weight for final confidence aggregation
    metadata:          Dict[str, Any] = field(default_factory=dict)

    def compute_overall(self) -> float:
        """Weighted composite: trust=0.40, freshness=0.20, relevance=0.25, grounding=0.15"""
        self.overall_quality = round(
            0.40 * self.trust_score
            + 0.20 * self.freshness_score
            + 0.25 * self.relevance_score
            + 0.15 * self.grounding_score,
            4,
        )
        self.use_in_reasoning = self.overall_quality >= MINIMUM_QUALITY_THRESHOLD
        return self.overall_quality


@dataclass
class EvidenceQualitySummary:
    """Aggregate quality metrics across all evidence sources."""
    total_sources:       int   = 0
    high_quality_count:  int   = 0    # overall_quality >= 0.75
    medium_quality_count: int  = 0    # 0.50 <= overall_quality < 0.75
    low_quality_count:   int   = 0    # 0.30 <= overall_quality < 0.50
    filtered_count:      int   = 0    # overall_quality < 0.30 (excluded)
    avg_trust:           float = 0.0
    avg_quality:         float = 0.0
    avg_freshness:       float = 0.0
    avg_relevance:       float = 0.0
    has_authoritative:   bool  = False
    has_systematic_review: bool = False
    overall_sufficiency: str  = "unknown"  # strong/adequate/weak/insufficient
    sufficiency_score:   float = 0.0       # 0-1 composite sufficiency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sources":        self.total_sources,
            "high_quality_count":   self.high_quality_count,
            "medium_quality_count": self.medium_quality_count,
            "low_quality_count":    self.low_quality_count,
            "filtered_count":       self.filtered_count,
            "avg_trust":            round(self.avg_trust, 3),
            "avg_quality":          round(self.avg_quality, 3),
            "avg_freshness":        round(self.avg_freshness, 3),
            "avg_relevance":        round(self.avg_relevance, 3),
            "has_authoritative":    self.has_authoritative,
            "has_systematic_review": self.has_systematic_review,
            "overall_sufficiency":  self.overall_sufficiency,
            "sufficiency_score":    round(self.sufficiency_score, 3),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Source Classification
# ═════════════════════════════════════════════════════════════════════════════

def _classify_semantic_doc(doc: Dict[str, Any]) -> Tuple[str, float]:
    """Determine tier + trust for a semantic (Qdrant) document."""
    text   = (doc.get("text", "") + " " + doc.get("source", "")).lower()
    score  = float(doc.get("score", 0.5))

    # Check source name for authoritative signals
    for src in _GUIDELINE_SOURCES:
        if src in text:
            return "authoritative", _TIER_TRUST["authoritative"]

    # Check text content
    for pattern in _META_ANALYSIS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "systematic_review", _TIER_TRUST["systematic_review"]

    for pattern in _RCT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "high_evidence", _TIER_TRUST["high_evidence"]

    for pattern in _CASE_REPORT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "low_evidence", _TIER_TRUST["low_evidence"]

    # Fall back to Qdrant score
    if score >= 0.80:
        return "semantic_high", _TIER_TRUST["semantic_high"]
    elif score >= 0.60:
        return "semantic_med", _TIER_TRUST["semantic_med"]
    else:
        return "semantic_low", _TIER_TRUST["semantic_low"]


def _compute_freshness(doc: Dict[str, Any]) -> float:
    """
    Score freshness based on publication/document year.
    2024-2026: 1.0 | 2020-2023: 0.85 | 2015-2019: 0.70 | <2015: 0.50
    """
    try:
        from backend.research.freshness_engine import FreshnessEngine
        fe = FreshnessEngine()
        year = fe.extract_year(doc.get("text", "") + " " + doc.get("source", ""))
        if year:
            return fe.score_year(year)
    except Exception:
        pass

    # Default: moderate freshness (unknown date)
    return 0.70


def _compute_grounding(doc_text: str, query: str) -> float:
    """Simple term overlap between query keywords and document text."""
    if not doc_text or not query:
        return 0.5

    # Extract meaningful query terms (5+ chars, not stopwords)
    _STOP = {"patient", "history", "presents", "currently", "taking", "recently",
              "developed", "diagnosed", "with", "years", "known", "significant"}
    query_words = [
        w.lower() for w in re.findall(r"\b\w{5,}\b", query)
        if w.lower() not in _STOP
    ][:15]

    if not query_words:
        return 0.5

    doc_lower = doc_text.lower()
    hits = sum(1 for w in query_words if w in doc_lower)
    return round(min(hits / len(query_words), 1.0), 3)


# ═════════════════════════════════════════════════════════════════════════════
# Per-Source Evaluation
# ═════════════════════════════════════════════════════════════════════════════

def _evaluate_semantic_doc(doc: Dict[str, Any], idx: int, query: str) -> EvidenceScore:
    tier, trust = _classify_semantic_doc(doc)
    freshness   = _compute_freshness(doc)
    relevance   = float(doc.get("score", 0.5))
    grounding   = _compute_grounding(doc.get("text", ""), query)

    ev = EvidenceScore(
        source_id        = f"sem_{idx}",
        source_type      = "semantic",
        source_reference = doc.get("source", f"doc_{idx}"),
        tier             = tier,
        trust_score      = trust,
        freshness_score  = freshness,
        relevance_score  = relevance,
        grounding_score  = grounding,
        metadata         = {"doc_index": idx, "raw_score": relevance},
    )
    ev.compute_overall()
    return ev


def _evaluate_graph_context(graph_context: str, query: str) -> Optional[EvidenceScore]:
    if not graph_context or len(graph_context.strip()) < 50:
        return None

    grounding = _compute_grounding(graph_context, query)
    ev = EvidenceScore(
        source_id        = "graph_0",
        source_type      = "graph",
        source_reference = "Neo4j Medical Knowledge Graph",
        tier             = "graph_knowledge",
        trust_score      = _TIER_TRUST["graph_knowledge"],
        freshness_score  = 0.90,   # Graph is maintained/updated
        relevance_score  = 0.85,   # Graph retrieval is already filtered
        grounding_score  = grounding,
        metadata         = {"char_length": len(graph_context)},
    )
    ev.compute_overall()
    return ev


def _evaluate_research_context(research_context: str, query: str) -> Optional[EvidenceScore]:
    if not research_context or len(research_context.strip()) < 50:
        return None

    text_lower = research_context.lower()

    # Detect tier from research context content
    tier = "moderate_evidence"
    trust = _TIER_TRUST["moderate_evidence"]
    for pattern in _META_ANALYSIS_PATTERNS:
        if re.search(pattern, text_lower):
            tier  = "systematic_review"
            trust = _TIER_TRUST["systematic_review"]
            break
    for pattern in _RCT_PATTERNS:
        if re.search(pattern, text_lower):
            tier  = "high_evidence"
            trust = _TIER_TRUST["high_evidence"]
            break

    grounding = _compute_grounding(research_context, query)
    freshness = 0.90  # Live research is recent

    ev = EvidenceScore(
        source_id        = "research_0",
        source_type      = "research",
        source_reference = "PubMed Live Research",
        tier             = tier,
        trust_score      = trust,
        freshness_score  = freshness,
        relevance_score  = 0.80,   # Research agent filters for relevance
        grounding_score  = grounding,
        metadata         = {"char_length": len(research_context)},
    )
    ev.compute_overall()
    return ev


def _evaluate_multimodal(
    visual_context: str,
    image_confidence: float,
    image_modality: str,
    query: str,
) -> Optional[EvidenceScore]:
    if not visual_context or len(visual_context.strip()) < 20:
        return None

    # Classify multimodal tier by confidence
    if image_confidence >= 0.85:
        tier  = "multimodal_high"
        trust = _TIER_TRUST["multimodal_high"]
    elif image_confidence >= 0.60:
        tier  = "multimodal_med"
        trust = _TIER_TRUST["multimodal_med"]
    else:
        tier  = "multimodal_low"
        trust = _TIER_TRUST["multimodal_low"]

    grounding = _compute_grounding(visual_context, query)
    ev = EvidenceScore(
        source_id        = "visual_0",
        source_type      = "multimodal",
        source_reference = f"{image_modality} Analysis",
        tier             = tier,
        trust_score      = trust,
        freshness_score  = 1.0,    # Current patient data — always fresh
        relevance_score  = 0.95,   # Patient-specific — highly relevant
        grounding_score  = grounding,
        metadata         = {"image_confidence": image_confidence, "modality": image_modality},
    )
    ev.compute_overall()
    return ev


def _evaluate_similar_cases(cases_context: str, query: str) -> Optional[EvidenceScore]:
    if not cases_context or len(cases_context.strip()) < 50:
        return None

    grounding = _compute_grounding(cases_context, query)
    ev = EvidenceScore(
        source_id        = "cases_0",
        source_type      = "case",
        source_reference = "Clinical Case Memory",
        tier             = "case_memory",
        trust_score      = _TIER_TRUST["case_memory"],
        freshness_score  = 0.75,
        relevance_score  = 0.80,
        grounding_score  = grounding,
        metadata         = {"char_length": len(cases_context)},
    )
    ev.compute_overall()
    return ev


# ═════════════════════════════════════════════════════════════════════════════
# Summary Computation
# ═════════════════════════════════════════════════════════════════════════════

def _compute_summary(scores: List[EvidenceScore]) -> EvidenceQualitySummary:
    if not scores:
        return EvidenceQualitySummary(
            total_sources=0,
            overall_sufficiency="insufficient",
            sufficiency_score=0.0,
        )

    usable = [s for s in scores if s.use_in_reasoning]
    filtered = len(scores) - len(usable)

    high   = sum(1 for s in usable if s.overall_quality >= 0.75)
    medium = sum(1 for s in usable if 0.50 <= s.overall_quality < 0.75)
    low    = sum(1 for s in usable if s.overall_quality < 0.50)

    avg_trust     = (sum(s.trust_score for s in usable) / len(usable)) if usable else 0.0
    avg_quality   = (sum(s.overall_quality for s in usable) / len(usable)) if usable else 0.0
    avg_freshness = (sum(s.freshness_score for s in usable) / len(usable)) if usable else 0.0
    avg_relevance = (sum(s.relevance_score for s in usable) / len(usable)) if usable else 0.0

    has_auth = any(s.tier == "authoritative" for s in usable)
    has_sr   = any(s.tier in {"systematic_review", "high_evidence"} for s in usable)

    # Overall sufficiency classification
    n_usable = len(usable)
    if n_usable == 0:
        sufficiency = "insufficient"
        suf_score   = 0.0
    elif avg_quality >= 0.80 and n_usable >= 3:
        sufficiency = "strong"
        suf_score   = min(1.0, avg_quality + 0.05)
    elif avg_quality >= 0.65 and n_usable >= 2:
        sufficiency = "adequate"
        suf_score   = avg_quality
    elif avg_quality >= 0.45 and n_usable >= 1:
        sufficiency = "weak"
        suf_score   = avg_quality
    else:
        sufficiency = "insufficient"
        suf_score   = avg_quality

    return EvidenceQualitySummary(
        total_sources        = len(scores),
        high_quality_count   = high,
        medium_quality_count = medium,
        low_quality_count    = low,
        filtered_count       = filtered,
        avg_trust            = round(avg_trust, 4),
        avg_quality          = round(avg_quality, 4),
        avg_freshness        = round(avg_freshness, 4),
        avg_relevance        = round(avg_relevance, 4),
        has_authoritative    = has_auth,
        has_systematic_review = has_sr,
        overall_sufficiency  = sufficiency,
        sufficiency_score    = round(suf_score, 4),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═════════════════════════════════════════════════════════════════════════════

def evaluate_evidence(
    docs:             List[Dict[str, Any]],
    query:            str,
    graph_context:    str     = "",
    research_context: str     = "",
    visual_context:   str     = "",
    image_confidence: float   = 1.0,
    image_modality:   str     = "unknown",
    similar_cases:    str     = "",
) -> Tuple[List[EvidenceScore], EvidenceQualitySummary]:
    """
    Evaluate quality of all evidence sources retrieved for a query.

    Args:
        docs:              Semantic retrieval results (Qdrant docs list).
        query:             Original query (for grounding computation).
        graph_context:     Neo4j graph context string.
        research_context:  Live PubMed research context string.
        visual_context:    ECG/Radiology/OCR analysis string.
        image_confidence:  Confidence from image analysis pipeline.
        image_modality:    Modality type (ecg/radiology/ocr).
        similar_cases:     Similar case memory context.

    Returns:
        Tuple of (List[EvidenceScore], EvidenceQualitySummary)
    """
    all_scores: List[EvidenceScore] = []

    # ── Semantic documents ────────────────────────────────────────────────────
    for i, doc in enumerate(docs):
        try:
            ev = _evaluate_semantic_doc(doc, i, query)
            all_scores.append(ev)
        except Exception as exc:
            logger.warning(f"[EvidenceEvaluator] Failed to score doc {i}: {exc}")

    # ── Graph context ─────────────────────────────────────────────────────────
    if graph_context:
        try:
            ev = _evaluate_graph_context(graph_context, query)
            if ev:
                all_scores.append(ev)
        except Exception as exc:
            logger.warning(f"[EvidenceEvaluator] Failed to score graph context: {exc}")

    # ── Research context ──────────────────────────────────────────────────────
    if research_context:
        try:
            ev = _evaluate_research_context(research_context, query)
            if ev:
                all_scores.append(ev)
        except Exception as exc:
            logger.warning(f"[EvidenceEvaluator] Failed to score research context: {exc}")

    # ── Multimodal context ────────────────────────────────────────────────────
    if visual_context:
        try:
            ev = _evaluate_multimodal(visual_context, image_confidence, image_modality, query)
            if ev:
                all_scores.append(ev)
        except Exception as exc:
            logger.warning(f"[EvidenceEvaluator] Failed to score multimodal context: {exc}")

    # ── Similar cases ─────────────────────────────────────────────────────────
    if similar_cases:
        try:
            ev = _evaluate_similar_cases(similar_cases, query)
            if ev:
                all_scores.append(ev)
        except Exception as exc:
            logger.warning(f"[EvidenceEvaluator] Failed to score similar cases: {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = _compute_summary(all_scores)

    logger.info(
        f"[EvidenceEvaluator] Evaluated {len(all_scores)} sources. "
        f"Sufficiency: {summary.overall_sufficiency} (score={summary.sufficiency_score:.3f}) "
        f"avg_quality={summary.avg_quality:.3f} "
        f"filtered={summary.filtered_count}"
    )

    return all_scores, summary


def evidence_scores_to_dict_list(scores: List[EvidenceScore]) -> List[Dict[str, Any]]:
    """Serialise EvidenceScore list for AgentState storage."""
    return [
        {
            "source_id":        s.source_id,
            "source_type":      s.source_type,
            "source_reference": s.source_reference,
            "tier":             s.tier,
            "trust_score":      s.trust_score,
            "freshness_score":  s.freshness_score,
            "relevance_score":  s.relevance_score,
            "grounding_score":  s.grounding_score,
            "overall_quality":  s.overall_quality,
            "use_in_reasoning": s.use_in_reasoning,
            "contradiction_flag": s.contradiction_flag,
        }
        for s in scores
    ]
