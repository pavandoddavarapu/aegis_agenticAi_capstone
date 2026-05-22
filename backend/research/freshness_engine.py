"""
freshness_engine.py — Temporal Research Intelligence (Phase 7)

Architecture:
  Analyzes queries for temporal intent (e.g., "latest", "2026")
  and calculates freshness scores for retrieved papers.
  Down-ranks outdated protocols.
"""
import re
from datetime import datetime
from typing import Dict, Any

class FreshnessEngine:
    
    # Keywords indicating a desire for recent information
    TEMPORAL_KEYWORDS = [
        "latest", "recent", "new", "current", "update", "updated", 
        "2023", "2024", "2025", "2026", "2027"
    ]
    
    def __init__(self):
        self.current_year = datetime.now().year
        
    def requires_fresh_evidence(self, query: str) -> bool:
        """Detect if the query explicitly asks for recent information."""
        query_lower = query.lower()
        for keyword in self.TEMPORAL_KEYWORDS:
            if re.search(rf"\b{keyword}\b", query_lower):
                return True
        return False
        
    def calculate_freshness_score(self, year_published: int) -> float:
        """
        Calculate a freshness score [0.0 - 1.0] based on publication year.
        Uses an exponential decay function.
        """
        if not year_published:
            return 0.5
            
        age_in_years = max(0, self.current_year - year_published)
        
        # Immediate decay:
        # Age 0 -> 1.0
        # Age 1 -> 0.95
        # Age 3 -> 0.80
        # Age 5 -> 0.60
        # Age 10 -> 0.20
        # Age >20 -> 0.05
        
        if age_in_years == 0:
            return 1.0
        elif age_in_years <= 2:
            return 0.9
        elif age_in_years <= 5:
            return 0.75
        elif age_in_years <= 10:
            return 0.4
        else:
            return 0.1
            
    def apply_temporal_penalty(self, paper: Dict[str, Any], temporal_intent: bool) -> float:
        """
        Calculates the temporal multiplier for a paper.
        If the query has temporal intent, old papers are heavily penalized.
        """
        year = paper.get("year", self.current_year - 5)
        freshness = self.calculate_freshness_score(year)
        
        if temporal_intent:
            # Heavily penalize older papers if the user asked for "latest"
            if freshness < 0.7:
                return freshness * 0.5
            return freshness
        else:
            # Mild penalty for old papers otherwise
            return freshness * 0.8 + 0.2
