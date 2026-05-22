"""
research_validator.py — Live Research Validation Engine (Phase 7)

Architecture:
  Provides pre-reasoning validation of fetched live research.
  Rejects low-quality papers, pre-print servers without peer review,
  or papers explicitly retracted.
"""
from typing import List, Dict, Any
import re
from backend.utils.logger import logger

class ResearchValidator:
    
    # Sources or terms that trigger immediate rejection
    BANNED_TERMS = ["retracted", "withdrawn", "erratum"]
    BANNED_SOURCES = ["biorxiv", "medrxiv"] # Pre-prints not peer-reviewed
    
    def validate_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out low quality or retracted papers."""
        valid_papers = []
        for paper in papers:
            if not self._is_valid(paper):
                continue
            valid_papers.append(paper)
            
        if len(papers) != len(valid_papers):
            logger.info(f"[ResearchValidator] Filtered out {len(papers) - len(valid_papers)} invalid papers.")
            
        return valid_papers

    def _is_valid(self, paper: Dict[str, Any]) -> bool:
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        source = paper.get("source", "").lower()
        
        # Check for retraction in title
        for term in self.BANNED_TERMS:
            if re.search(rf"\b{term}\b", title):
                logger.warning(f"[ResearchValidator] Rejecting paper due to term: {term}")
                return False
                
        # Check source
        if source in self.BANNED_SOURCES:
            logger.warning(f"[ResearchValidator] Rejecting paper due to source: {source}")
            return False
            
        # Reject if no abstract (useless for LLM reasoning)
        if len(abstract) < 50:
            logger.warning("[ResearchValidator] Rejecting paper due to missing/short abstract.")
            return False
            
        return True
