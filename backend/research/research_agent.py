"""
research_agent.py — Research Intelligence Coordinator (Phase 7)

Architecture:
  Acts as the facade for the live research subsystem.
  Orchestrates PubMed retrieval, validation, ranking, and context injection.
"""
import asyncio
from typing import Dict, Any

from backend.research.pubmed_client import PubMedClient
from backend.research.clinical_trials_client import ClinicalTrialsClient
from backend.research.semantic_scholar_client import SemanticScholarClient
from backend.research.research_validator import ResearchValidator
from backend.research.research_ranker import ResearchRanker
from backend.research.temporary_context_manager import TemporaryContextManager
from backend.utils.retries import graceful_fallback
from backend.utils.logger import logger

class ResearchAgent:
    """Coordinator for live internet medical research."""
    
    def __init__(self):
        self.pubmed = PubMedClient()
        self.clinical_trials = ClinicalTrialsClient()
        self.semantic_scholar = SemanticScholarClient()
        self.validator = ResearchValidator()
        self.ranker = ResearchRanker()
        self.context_manager = TemporaryContextManager()
        
    @graceful_fallback("")
    async def run_research(self, query: str, strict_rct: bool = False) -> str:
        """
        Execute the full research pipeline:
        Search -> Fetch -> Validate -> Rank -> Format
        """
        # Re-initialize to ensure fresh HTTP sessions if the agent is reused
        self.pubmed = PubMedClient()
        self.clinical_trials = ClinicalTrialsClient()
        self.semantic_scholar = SemanticScholarClient()
        
        logger.info(f"[ResearchAgent] Starting live research for: '{query}'")
        
        try:
            # 1. Search PubMed and ClinicalTrials.gov in parallel
            logger.info("[ResearchAgent] Dispatching PubMed search and ClinicalTrials.gov search concurrently.")
            pubmed_task = self.pubmed.search(query, max_results=10, strict_rct=strict_rct)
            trials_task = self.clinical_trials.search_trials(query, max_results=5)
            
            pmids, trials = await asyncio.gather(pubmed_task, trials_task)
            
            # 2. Fetch PubMed Abstracts and their citation metrics
            papers = []
            if pmids:
                papers = await self.pubmed.fetch_summaries(pmids)
                
                # Fetch Semantic Scholar metrics for PubMed papers in parallel
                if papers:
                    logger.info(f"[ResearchAgent] Fetching citation metrics from Semantic Scholar for {len(papers)} papers.")
                    metric_tasks = [
                        self.semantic_scholar.fetch_citation_metrics(p.get("pmid", ""))
                        for p in papers
                    ]
                    metrics = await asyncio.gather(*metric_tasks)
                    
                    # Attach metrics back to the papers
                    for paper, metric in zip(papers, metrics):
                        paper["citation_count"] = metric.get("citationCount", 0)
                        paper["influential_citation_count"] = metric.get("influentialCitationCount", 0)
                        # Fallback to Semantic Scholar TLDR if paper abstract is missing or too short
                        if metric.get("tldr") and len(paper.get("abstract", "")) < 50:
                            paper["abstract"] = metric["tldr"]
            
            # Combine literature papers and clinical trials
            all_documents = papers + trials
            if not all_documents:
                logger.warning("[ResearchAgent] No PMIDs or clinical trials found.")
                return ""
                
            # 3. Validate (Remove retracted/poor quality)
            valid_docs = self.validator.validate_papers(all_documents)
            
            # 4. Rank (Apply freshness + evidence hierarchy)
            ranked_docs = self.ranker.rank_papers(query, valid_docs, top_k=5)
            
            # 5. Format Context
            context = self.context_manager.format_research_context(ranked_docs)
            
            logger.info(f"[ResearchAgent] Successfully formatted {len(ranked_docs)} documents for context.")
            return context
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Live research pipeline failed: {e}")
            return ""
        finally:
            await asyncio.gather(
                self.pubmed.close(),
                self.clinical_trials.close(),
                self.semantic_scholar.close(),
                return_exceptions=True
            )

