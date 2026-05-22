"""
graph_retriever.py — Knowledge Graph Retrieval Engine (Phase 6)

Architecture:
  Provides relational retrieval methods that augment vector search.
  - Neighborhood Traversal (what is connected to X?)
  - Interaction Traversal (what interacts with X?)
  - Shortest Path (how are X and Y related?)
  - Profile Retrieval (full 360 view of a disease)
"""
from __future__ import annotations

from typing import Dict, List, Any

from backend.graphrag.graph_client  import GraphClient
from backend.graphrag               import cypher_templates as CQL
from backend.utils.logger           import logger


class GraphRetriever:
    """
    High-level API for semantic graph retrieval.
    All methods are safe and return empty lists/dicts if the graph is unavailable.
    """

    def __init__(self, client: GraphClient):
        self._client = client

    async def get_entity_neighborhood(
        self,
        entity_name: str,
        depth:       int   = 1,
        min_weight:  float = 0.70,
        limit:       int   = 20,
    ) -> List[Dict[str, Any]]:
        """
        Traverse the graph around a specific entity.
        Returns relationships (source, target, rel_type, weight).
        """
        query = CQL.ENTITY_NEIGHBORHOOD if depth > 1 else CQL.ENTITY_NEIGHBORHOOD_SIMPLE
        params = {
            "name":       entity_name.lower(),
            "depth":      depth,
            "min_weight": min_weight,
            "limit":      limit,
        }
        results = await self._client.run_query(query, params)
        logger.info(f"[GraphRetriever] Neighborhood for '{entity_name}' yielded {len(results)} edges.")
        return results

    async def get_drug_interactions(
        self,
        drug_name:  str,
        min_weight: float = 0.75,
        limit:      int   = 15,
    ) -> List[Dict[str, Any]]:
        """Find INTERACTS_WITH or CONTRAINDICATED_WITH for a drug."""
        params = {
            "drug_name":  drug_name.lower(),
            "min_weight": min_weight,
            "limit":      limit,
        }
        return await self._client.run_query(CQL.DRUG_INTERACTIONS, params)

    async def get_disease_contraindications(
        self,
        disease_name: str,
        min_weight:   float = 0.80,
    ) -> List[Dict[str, Any]]:
        """Find drugs contraindicated with a specific disease."""
        params = {
            "disease_name": disease_name.lower(),
            "min_weight":   min_weight,
            "limit":        10,
        }
        return await self._client.run_query(CQL.DRUG_CONTRAINDICATIONS_FOR_DISEASE, params)

    async def get_disease_profile(
        self,
        disease_name: str,
        min_weight:   float = 0.75,
    ) -> Optional[Dict[str, Any]]:
        """
        Return a comprehensive 360° profile of a disease:
        symptoms, treatments, risk factors, and related lab results.
        """
        params = {
            "disease_name": disease_name.lower(),
            "min_weight":   min_weight,
        }
        results = await self._client.run_query(CQL.DISEASE_FULL_PROFILE, params)
        if not results:
            return None
        logger.info(f"[GraphRetriever] Disease profile generated for '{disease_name}'.")
        return results[0]

    async def find_shortest_path(
        self,
        concept_a: str,
        concept_b: str,
        max_depth: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Find how two medical concepts are related."""
        params = {
            "start":     concept_a.lower(),
            "end":       concept_b.lower(),
            "max_depth": max_depth,
        }
        results = await self._client.run_query(CQL.SHORTEST_PATH_BETWEEN, params)
        if not results:
            return None
        logger.info(f"[GraphRetriever] Shortest path found between {concept_a} and {concept_b}.")
        return results[0]

    def format_graph_context(self, relationships: List[Dict[str, Any]]) -> str:
        """Format relationships into a string block for the Reasoning Agent."""
        if not relationships:
            return ""
        lines = []
        for r in relationships:
            src = r.get("source", "")
            tgt = r.get("target", r.get("interacts_with", r.get("drug", "")))
            rel = r.get("rel_type", r.get("interaction_type", "RELATED_TO"))
            weight = r.get("weight", r.get("severity", 0.0))
            if src and tgt:
                lines.append(f"- {src} [{rel}] {tgt} (confidence: {weight:.2f})")
        return "\n".join(lines)
