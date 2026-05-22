"""
research_agent.py — Research Intelligence Coordinator (Phase 7)

Architecture:
  Acts as the facade for the live research subsystem.
  Orchestrates PubMed retrieval, validation, ranking, and context injection.
"""
import asyncio
from typing import Dict, Any

from backend.research.pubmed_client import PubMedClient
from backend.research.research_validator import ResearchValidator
from backend.research.research_ranker import ResearchRanker
from backend.research.temporary_context_manager import TemporaryContextManager
from backend.utils.retries import graceful_fallback
from backend.utils.logger import logger

class ResearchAgent:
    """Coordinator for live internet medical research."""
    
    def __init__(self):
        self.pubmed = PubMedClient()
        self.validator = ResearchValidator()
        self.ranker = ResearchRanker()
        self.context_manager = TemporaryContextManager()
        
    @graceful_fallback("")
    async def run_research(self, query: str, strict_rct: bool = False) -> str:
        """
        Execute the full research pipeline:
        Search -> Fetch -> Validate -> Rank -> Format
        """
        logger.info(f"[ResearchAgent] Starting live research for: '{query}'")
        
        try:
            # 1. Search (Fetch PMIDs)
            pmids = await self.pubmed.search(query, max_results=15, strict_rct=strict_rct)
            if not pmids:
                logger.warning("[ResearchAgent] No PMIDs found.")
                return ""
                
            # 2. Fetch Abstracts
            papers = await self.pubmed.fetch_summaries(pmids)
            
            # 3. Validate (Remove retracted/poor quality)
            valid_papers = self.validator.validate_papers(papers)
            
            # 4. Rank (Apply freshness + evidence hierarchy)
            ranked_papers = self.ranker.rank_papers(query, valid_papers, top_k=4)
            
            # 5. Format Context
            context = self.context_manager.format_research_context(ranked_papers)
            
            logger.info(f"[ResearchAgent] Successfully formatted {len(ranked_papers)} papers for context.")
            return context
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Live research pipeline failed: {e}")
            return ""
        finally:
            await self.pubmed.close()
