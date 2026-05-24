"""
semantic_scholar_client.py — Semantic Scholar API Client (Phase 7)

Architecture:
  Fetches citation metrics and influential citation counts to weigh paper impact.
"""
from typing import Dict, Any
import asyncio
import httpx
from backend.utils.logger import logger

class SemanticScholarClient:
    """Client for Semantic Scholar API."""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper"
    
    def __init__(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=5.0)
        self._semaphore = asyncio.Semaphore(5) # run requests in parallel with concurrency limit

    async def close(self):
        await self._client.aclose()
        
    async def fetch_citation_metrics(self, pmid: str) -> Dict[str, Any]:
        """
        Fetch citation counts and TLDR for a given PubMed ID.
        """
        if not pmid or pmid.startswith("NCT_"): # Skip non-pubmed ids
            return {"citationCount": 0, "influentialCitationCount": 0}
            
        url = f"{self.BASE_URL}/PMID:{pmid}"
        params = {
            "fields": "citationCount,influentialCitationCount,tldr"
        }
        
        for attempt in range(3):
            async with self._semaphore:
                try:
                    # Polite sleep to keep rate limits clean
                    await asyncio.sleep(0.1)
                    response = await self._client.get(url, params=params)
                    
                    if response.status_code == 429:
                        # Fail fast on rate limits to protect retrieval response times
                        logger.warning(f"[SemanticScholarClient] Rate limited (429) for PMID {pmid}. Failing fast to maintain sub-second latency.")
                        return {"citationCount": 0, "influentialCitationCount": 0}
                        
                    if response.status_code == 404:
                        return {"citationCount": 0, "influentialCitationCount": 0}
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    return {
                        "citationCount": data.get("citationCount", 0),
                        "influentialCitationCount": data.get("influentialCitationCount", 0),
                        "tldr": data.get("tldr", {}).get("text", "") if data.get("tldr") else ""
                    }
                except Exception as e:
                    logger.debug(f"[SemanticScholarClient] Attempt {attempt+1} failed for PMID {pmid}: {e}")
                    if attempt == 2:
                        return {"citationCount": 0, "influentialCitationCount": 0}
                    await asyncio.sleep(0.5)
        return {"citationCount": 0, "influentialCitationCount": 0}

