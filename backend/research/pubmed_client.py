"""
pubmed_client.py — Live PubMed Retrieval Engine (Phase 7)

Architecture:
  Provides an async interface to the NCBI E-utilities API.
  Implements safe, rate-limited retrieval of PubMed abstracts,
  publication dates, and metadata.

  Features:
    - E-utilities search (esearch) and fetch (esummary/efetch)
    - Exponential backoff and retry handling
    - Automatic MeSH term expansion and filtering (e.g., RCTs, Meta-analyses)
    - Time-bounded queries for freshness
"""
import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Any, Optional

import httpx

from backend.utils.logger import logger


class PubMedClient:
    """Async client for PubMed E-utilities with rate limiting and retries."""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    def __init__(self):
        self.api_key = os.getenv("NCBI_API_KEY")
        # 3 req/sec without key, 10 with key. We'll use a semaphore for safety.
        limit = 10 if self.api_key else 3
        self._semaphore = asyncio.Semaphore(limit)
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        await self._client.aclose()

    async def _safe_request(self, endpoint: str, params: Dict[str, Any]) -> httpx.Response:
        """Execute request with exponential backoff and rate limiting."""
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}.fcgi"
        
        for attempt in range(3):
            async with self._semaphore:
                try:
                    response = await self._client.get(url, params=params)
                    response.raise_for_status()
                    # Polite delay for NCBI
                    await asyncio.sleep(0.34 if not self.api_key else 0.1)
                    return response
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        delay = 2 ** attempt
                        logger.warning(f"[PubMedClient] Rate limited. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[PubMedClient] HTTP error: {e}")
                        break
                except httpx.RequestError as e:
                    logger.error(f"[PubMedClient] Request failed: {e}")
                    break
        
        raise Exception(f"Failed to fetch from {endpoint} after 3 attempts.")

    async def search(self, query: str, max_results: int = 10, days_back: int = None, strict_rct: bool = False) -> List[str]:
        """Search PubMed and return a list of PMIDs."""
        # Query enhancement
        enhanced_query = query
        if strict_rct:
            enhanced_query += ' AND ("randomized controlled trial"[Publication Type] OR "meta-analysis"[Publication Type] OR "systematic review"[Publication Type])'
            
        params = {
            "db": "pubmed",
            "term": enhanced_query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "date" # Prioritize recent
        }
        
        if days_back:
            params["reldate"] = days_back
            params["datetype"] = "pdat"

        try:
            logger.info(f"[PubMedClient] Searching: '{enhanced_query}' (limit={max_results})")
            response = await self._safe_request("esearch", params)
            data = response.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            return pmids
        except Exception as e:
            logger.error(f"[PubMedClient] Search error: {e}")
            return []

    async def fetch_summaries(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """Fetch metadata and abstracts for a list of PMIDs using efetch."""
        if not pmids:
            return []
            
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        
        results = []
        try:
            response = await self._safe_request("efetch", params)
            # Parse XML
            root = ET.fromstring(response.content)
            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID", default="")
                title = article.findtext(".//ArticleTitle", default="")
                
                abstract_elem = article.find(".//Abstract")
                abstract = ""
                if abstract_elem is not None:
                    abstract_texts = abstract_elem.findall("AbstractText")
                    abstract = " ".join([elem.text for elem in abstract_texts if elem.text])
                
                pub_date_elem = article.find(".//PubDate")
                year = pub_date_elem.findtext("Year", default=str(datetime.now().year)) if pub_date_elem is not None else str(datetime.now().year)
                
                pub_types = [pt.text for pt in article.findall(".//PublicationType") if pt.text]
                
                results.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                    "year": int(year),
                    "publication_types": pub_types,
                    "source": "PubMed",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                })
            
            logger.info(f"[PubMedClient] Fetched {len(results)} abstracts.")
            return results
        except Exception as e:
            logger.error(f"[PubMedClient] Fetch error: {e}")
            return []
