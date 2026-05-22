"""
research_ranker.py — Evidence Ranking Engine (Phase 7)

Architecture:
  Scores and ranks live research papers based on:
  - Publication type (RCTs > Meta-analyses > Observational)
  - Freshness (Temporal scoring)
  - Source authority

  Ensures high-quality evidence is prioritized.
"""
from typing import List, Dict, Any
from backend.research.freshness_engine import FreshnessEngine
from backend.utils.logger import logger

class ResearchRanker:
    
    # Hierarchy of evidence weights
    EVIDENCE_WEIGHTS = {
        "Guideline": 1.0,
        "Practice Guideline": 1.0,
        "Meta-Analysis": 0.95,
        "Systematic Review": 0.90,
        "Randomized Controlled Trial": 0.85,
        "Clinical Trial": 0.80,
        "Observational Study": 0.60,
        "Case Reports": 0.30,
        "Review": 0.50
    }
    
    def __init__(self):
        self.freshness_engine = FreshnessEngine()
        
    def score_paper(self, paper: Dict[str, Any], temporal_intent: bool) -> float:
        """Calculate a composite quality score for a paper."""
        # 1. Evidence Quality Score
        pub_types = paper.get("publication_types", [])
        evidence_score = 0.4  # base score
        for ptype in pub_types:
            if ptype in self.EVIDENCE_WEIGHTS:
                evidence_score = max(evidence_score, self.EVIDENCE_WEIGHTS[ptype])
                
        # 2. Freshness Score
        freshness = self.freshness_engine.apply_temporal_penalty(paper, temporal_intent)
        
        # 3. Composite (Weighted)
        # 60% Evidence Quality, 40% Freshness (shifts if temporal intent)
        if temporal_intent:
            composite = (evidence_score * 0.4) + (freshness * 0.6)
        else:
            composite = (evidence_score * 0.7) + (freshness * 0.3)
            
        return round(composite, 3)
        
    def rank_papers(self, query: str, papers: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """Rank a list of papers and return the top_k."""
        temporal_intent = self.freshness_engine.requires_fresh_evidence(query)
        
        for paper in papers:
            paper["research_score"] = self.score_paper(paper, temporal_intent)
            
        ranked = sorted(papers, key=lambda x: x["research_score"], reverse=True)
        
        logger.info(f"[ResearchRanker] Ranked {len(papers)} papers. Temporal intent: {temporal_intent}")
        return ranked[:top_k]
