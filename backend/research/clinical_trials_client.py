"""
clinical_trials_client.py — ClinicalTrials.gov API Client (Phase 7)

Architecture:
  Retrieves active and completed clinical trials for emerging medical protocols.
"""
from typing import List, Dict, Any
import asyncio
import httpx
from backend.utils.logger import logger

class ClinicalTrialsClient:
    """Client for ClinicalTrials.gov API v2."""
    
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
    
    def __init__(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=10.0)
        self._semaphore = asyncio.Semaphore(5)

    async def close(self):
        await self._client.aclose()

    async def search_trials(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch clinical trials matching a query using the ClinicalTrials.gov V2 API.
        """
        params = {
            "query.term": query,
            "pageSize": max_results,
        }
        
        for attempt in range(3):
            async with self._semaphore:
                try:
                    logger.info(f"[ClinicalTrialsClient] Querying V2 API for: '{query}' (attempt {attempt+1})")
                    response = await self._client.get(self.BASE_URL, params=params)
                    
                    if response.status_code == 429:
                        delay = 2 ** attempt
                        logger.warning(f"[ClinicalTrialsClient] Rate limited. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                        
                    if response.status_code == 404:
                        return []
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    studies = data.get("studies", [])
                    results = []
                    for study in studies:
                        protocol = study.get("protocolSection", {})
                        ident = protocol.get("identificationModule", {})
                        status_mod = protocol.get("statusModule", {})
                        desc_mod = protocol.get("descriptionModule", {})
                        cond_mod = protocol.get("conditionsModule", {})
                        
                        nct_id = ident.get("nctId", "")
                        title = ident.get("briefTitle") or ident.get("officialTitle") or "Unknown Trial"
                        status = status_mod.get("overallStatus", "UNKNOWN")
                        summary = desc_mod.get("briefSummary", "")
                        conditions = cond_mod.get("conditions", [])
                        
                        results.append({
                            "pmid": f"NCT_{nct_id}", # custom mock-pmid structure for validator compatibility
                            "title": title,
                            "abstract": summary, # map brief summary to abstract
                            "status": status,
                            "conditions": conditions,
                            "publication_types": ["Clinical Trial"],
                            "source": "ClinicalTrials.gov",
                            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""
                        })
                    logger.info(f"[ClinicalTrialsClient] Found {len(results)} trials.")
                    return results
                except Exception as e:
                    logger.error(f"[ClinicalTrialsClient] Request failed on attempt {attempt+1}: {e}")
                    if attempt == 2:
                        return []
                    await asyncio.sleep(1)
        return []

