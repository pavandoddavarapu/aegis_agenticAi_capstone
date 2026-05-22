"""
temporary_context_manager.py — Live Research Injection (Phase 7)

Architecture:
  Manages temporary caching of live research evidence without permanently
  polluting the local vector database (Qdrant).
  
  Provides methods to format live research into contextual blocks
  that are injected into the agent state and discarded post-request.
"""
from typing import List, Dict, Any
from backend.utils.logger import logger

class TemporaryContextManager:
    
    def __init__(self):
        # In-memory session cache mapping query -> context block
        # In production, this would be Redis with TTL
        self._session_cache = {}
        
    def format_research_context(self, papers: List[Dict[str, Any]]) -> str:
        """Format ranked papers into a structured context block for LLM."""
        if not papers:
            return ""
            
        lines = ["=== LIVE RESEARCH EVIDENCE (TEMPORARY CONTEXT) ==="]
        for idx, paper in enumerate(papers, 1):
            title = paper.get("title", "Unknown Title")
            year = paper.get("year", "Unknown Year")
            source = paper.get("source", "Unknown Source")
            score = paper.get("research_score", 0.0)
            url = paper.get("url", "")
            abstract = paper.get("abstract", "")[:800] # Cap length
            
            pub_types = ", ".join(paper.get("publication_types", []))
            
            lines.append(f"[Research {idx}] {title}")
            lines.append(f"Source: {source} | Year: {year} | Types: {pub_types} | Quality Score: {score:.2f}")
            lines.append(f"URL: {url}")
            lines.append(f"Abstract: {abstract}\n")
            
        return "\n".join(lines)
