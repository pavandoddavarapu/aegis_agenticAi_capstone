"""
wikipedia_client.py — Wikipedia Medical API Client (Phase 13)

Architecture:
  Retrieves medical articles and summaries from Wikipedia using the official MediaWiki API.
"""
from typing import List, Dict, Any
import httpx
from backend.utils.logger import logger

class WikipediaClient:
    """Client for Wikipedia/MediaWiki API."""
    
    BASE_URL = "https://en.wikipedia.org/w/api.php"
    
    def __init__(self):
        headers = {
            "User-Agent": "AegisClinicalAI/13.0.0 (https://aegis-clinical.ai; contact@aegis-clinical.ai) httpx/0.24",
            "Accept": "application/json"
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=10.0)

    async def close(self):
        await self._client.aclose()

    async def search_articles(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search Wikipedia for articles matching the query and return page summaries.
        """
        # Step 1: Search for matching page titles
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "utf8": 1,
            "srlimit": max_results
        }
        
        try:
            logger.info(f"[WikipediaClient] Searching Wikipedia for: '{query}'")
            response = await self._client.get(self.BASE_URL, params=search_params)
            response.raise_for_status()
            search_data = response.json()
            
            search_results = search_data.get("query", {}).get("search", [])
            if not search_results:
                logger.info(f"[WikipediaClient] No articles found for: '{query}'")
                return []
                
            page_titles = [item["title"] for item in search_results]
            
            # Step 2: Fetch summaries for all found page titles in one request
            fetch_params = {
                "action": "query",
                "format": "json",
                "titles": "|".join(page_titles),
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exlimit": "max"
            }
            
            logger.info(f"[WikipediaClient] Fetching content for titles: {page_titles}")
            fetch_response = await self._client.get(self.BASE_URL, params=fetch_params)
            fetch_response.raise_for_status()
            fetch_data = fetch_response.json()
            
            pages = fetch_data.get("query", {}).get("pages", {})
            results = []
            
            for page_id, page_info in pages.items():
                title = page_info.get("title", "")
                extract = page_info.get("extract", "").strip()
                page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                
                if extract and len(extract) > 50:
                    results.append({
                        "pmid": f"WIKI_{page_id}", # unique ID format for compatibility
                        "title": title,
                        "abstract": extract,
                        "publication_types": ["Review"], # map to Review for scoring weights
                        "source": "Wikipedia Medicine",
                        "url": page_url
                    })
            
            logger.info(f"[WikipediaClient] Found {len(results)} valid articles.")
            return results
            
        except Exception as e:
            logger.error(f"[WikipediaClient] Search failed: {e}")
            return []
