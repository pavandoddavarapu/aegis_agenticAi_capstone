"""
similar_case_engine.py — Episodic Clinical Memory Engine (Phase 6)

Architecture:
  Retrieves historical patient cases structurally similar to the current
  query context based on Jaccard similarity of graph relationships
  (symptom overlap, treatment pathways).
"""
from typing import Dict, List, Any

from backend.graphrag.graph_client import GraphClient
from backend.graphrag import cypher_templates as CQL
from backend.utils.logger import logger

class SimilarCaseEngine:
    def __init__(self, client: GraphClient):
        self._client = client

    async def get_similar_cases(
        self,
        anchor_case_id: str,
        min_similarity: float = 0.5,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Fetch cases with high symptom overlap (Jaccard index via Cypher).
        """
        params = {
            "case_id": anchor_case_id,
            "min_similarity": min_similarity,
            "limit": limit
        }
        results = await self._client.run_query(CQL.SIMILAR_CASES_BY_SYMPTOM_OVERLAP, params)
        logger.info(f"[SimilarCaseEngine] Found {len(results)} similar cases for {anchor_case_id}.")
        return results

    async def get_cases_for_disease(
        self,
        disease_name: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetch general historical cases diagnosed with a specific disease."""
        params = {
            "disease_name": disease_name.lower(),
            "limit": limit
        }
        return await self._client.run_query(CQL.ALL_CASES_FOR_DISEASE, params)

    def format_case_context(self, cases: List[Dict[str, Any]]) -> str:
        """Format historical cases for LLM context injection."""
        if not cases:
            return ""
        
        lines = ["=== SIMILAR HISTORICAL CASES ==="]
        for c in cases:
            sim = c.get("similarity_score", 0)
            summary = c.get("summary", "")
            outcome = c.get("outcome", "Unknown")
            lines.append(f"[Similarity: {sim:.2f}] {summary} -> Outcome: {outcome}")
            
        return "\n".join(lines)
