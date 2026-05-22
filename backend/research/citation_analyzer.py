"""
citation_analyzer.py — Citation Analysis Engine (Phase 7)

Architecture:
  Analyzes citation counts and impact factors to weigh evidence quality.
"""
from typing import Dict, Any

class CitationAnalyzer:
    """Computes impact scores based on citation graphs."""
    
    def calculate_impact_score(self, citation_count: int, years_since_publication: int) -> float:
        """
        Calculate an impact score.
        A paper with 10 citations in 1 year is highly impactful.
        A paper with 10 citations in 10 years is less so.
        """
        if years_since_publication <= 0:
            years_since_publication = 1
            
        citations_per_year = citation_count / years_since_publication
        
        if citations_per_year > 50:
            return 1.0
        elif citations_per_year > 10:
            return 0.8
        elif citations_per_year > 2:
            return 0.6
        return 0.4
