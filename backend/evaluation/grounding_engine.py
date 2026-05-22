"""
grounding_engine.py — Grounding & Hallucination Analytics (Phase 5)

Per-claim grounding analysis:
  1. Claim extraction     — split reasoning into atomic sentences
  2. Entity extraction    — pull medical terms from each claim
  3. Evidence alignment   — Jaccard keyword overlap to find best chunk
  4. Support classification — SUPPORTED | PARTIAL | UNSUPPORTED
  5. Hallucination scoring — unsupported / total claims
  6. Gap detection        — query topics not in any evidence
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from backend.utils.logger import logger

SUPPORT_SUPPORTED   = "supported"
SUPPORT_PARTIAL     = "partial"
SUPPORT_UNSUPPORTED = "unsupported"

_STOPWORDS = {
    "patient","clinical","medical","provide","evidence","suggest","based",
    "which","these","their","should","would","could","study","found","shown",
}

@dataclass
class ClaimAnalysis:
    claim:            str
    support_status:   str
    best_evidence_idx:Optional[int]
    overlap_score:    float
    medical_entities: List[str]
    ungrounded_terms: List[str]

@dataclass
class GroundingReport:
    total_claims:       int
    supported_claims:   int
    partial_claims:     int
    unsupported_claims: int
    grounding_score:    float
    hallucination_score:float
    citation_density:   float
    evidence_gaps:      List[str]
    claim_analyses:     List[ClaimAnalysis]
    risk_level:         str

    def to_dict(self) -> Dict:
        return {
            "total_claims":        self.total_claims,
            "supported_claims":    self.supported_claims,
            "unsupported_claims":  self.unsupported_claims,
            "grounding_score":     round(self.grounding_score, 3),
            "hallucination_score": round(self.hallucination_score, 3),
            "citation_density":    round(self.citation_density, 3),
            "evidence_gaps":       self.evidence_gaps,
            "risk_level":          self.risk_level,
        }

def _extract_claims(reasoning: str) -> List[str]:
    claims = []
    for line in reasoning.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("**"):
            continue
        for s in re.split(r"(?<=[.!?])\s+", line):
            if len(s.strip()) > 20:
                claims.append(s.strip())
    return claims

def _extract_terms(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z]{6,}", text)
            if w.lower() not in _STOPWORDS]

def _overlap(claim: str, evidence: str) -> float:
    def tok(t):
        return {w.lower() for w in re.findall(r"[A-Za-z]{5,}", t)}
    c, e = tok(claim), tok(evidence)
    if not c or not e:
        return 0.0
    return len(c & e) / len(c | e)

def _best_evidence(claim: str, docs: List[Dict]) -> Tuple[Optional[int], float]:
    best_idx, best = None, 0.0
    for i, doc in enumerate(docs):
        sc = _overlap(claim, doc.get("text", ""))
        if sc > best:
            best, best_idx = sc, i
    return best_idx, best

def _classify(overlap: float, has_cite: bool, ungrounded: List[str]) -> str:
    ur = len(ungrounded) / max(len(ungrounded) + 1, 1)
    if (has_cite or overlap >= 0.25) and ur < 0.50:
        return SUPPORT_SUPPORTED
    if overlap >= 0.10 or has_cite:
        return SUPPORT_PARTIAL
    return SUPPORT_UNSUPPORTED

def _risk(score: float) -> str:
    if score >= 0.50: return "CRITICAL"
    if score >= 0.30: return "HIGH"
    if score >= 0.15: return "MEDIUM"
    return "LOW"

def _gaps(query: str, docs: List[Dict]) -> List[str]:
    terms = {w.lower() for w in re.findall(r"[A-Za-z]{6,}", query)
             if w.lower() not in _STOPWORDS}
    doc_text = " ".join(d.get("text", "") for d in docs).lower()
    return [t for t in terms if t not in doc_text]

def compute_grounding(query: str, reasoning: str, docs: List[Dict]) -> GroundingReport:
    """Full grounding analysis. Returns GroundingReport."""
    if not reasoning or not docs:
        return GroundingReport(0,0,0,0,0.0,1.0,0.0,_gaps(query,docs),[],  "CRITICAL")

    claims = _extract_claims(reasoning)
    analyses, supported, partial, unsupported, cited = [], 0, 0, 0, 0

    for claim in claims:
        entities   = _extract_terms(claim)
        doc_all    = " ".join(d.get("text","") for d in docs).lower()
        ungrounded = [e for e in entities if e not in doc_all]
        best_idx, ov = _best_evidence(claim, docs)
        has_cite     = bool(re.search(r"\[evidence\s*\d+\]", claim, re.I))
        if has_cite: cited += 1
        status = _classify(ov, has_cite, ungrounded)
        if status == SUPPORT_SUPPORTED:   supported  += 1
        elif status == SUPPORT_PARTIAL:   partial    += 1
        else:                             unsupported += 1
        analyses.append(ClaimAnalysis(claim[:200], status, best_idx,
                                      round(ov,3), entities[:8], ungrounded[:5]))

    total = max(len(claims), 1)
    h_score = round(unsupported / total, 4)
    logger.info(f"[GroundingEngine] claims={total} unsupported={unsupported} "
                f"hallucination={h_score:.3f} risk={_risk(h_score)}")
    return GroundingReport(
        total_claims=total, supported_claims=supported, partial_claims=partial,
        unsupported_claims=unsupported, grounding_score=round(supported/total,4),
        hallucination_score=h_score, citation_density=round(cited/total,4),
        evidence_gaps=_gaps(query, docs), claim_analyses=analyses,
        risk_level=_risk(h_score),
    )
