"""
graph_validator.py — Relationship Safety Validation (Phase 6)

Architecture:
  Provides a final safety check on LLM reasoning against the hard
  constraints stored in the Neo4j graph.
  If the reasoning agent suggests a drug that the graph explicitly
  marks as CONTRAINDICATED_WITH the patient's condition, this
  layer flags a critical validation failure.
"""
import asyncio
from typing import List, Tuple

from backend.graphrag.graph_client import GraphClient
from backend.graphrag import cypher_templates as CQL
from backend.graphrag.graph_ingestor import extract_entities
from backend.utils.logger import logger

class GraphValidator:
    def __init__(self, client: GraphClient):
        self._client = client

    async def validate_reasoning(self, reasoning_text: str, patient_conditions: List[str] = None) -> Tuple[bool, List[str]]:
        """
        Verify that drugs mentioned in the reasoning output do not have
        graph-level contraindications with the patient's known conditions.
        
        Returns: (is_safe: bool, violations: List[str])
        """
        if not patient_conditions:
            # If we don't know the condition, extract it from the reasoning text itself
            extracted = extract_entities(reasoning_text)
            patient_conditions = [e.canonical for e in extracted if e.label == "Disease"]
            
        # Extract drugs proposed by the LLM
        extracted_drugs = [e.canonical for e in extract_entities(reasoning_text) if e.label == "Drug"]
        
        if not patient_conditions or not extracted_drugs:
            return True, []
            
        violations = []
        # Check every proposed drug against every patient condition
        for drug in extracted_drugs:
            for condition in patient_conditions:
                params = {"disease_name": condition, "min_weight": 0.8, "limit": 1}
                res = await self._client.run_query(CQL.DRUG_CONTRAINDICATIONS_FOR_DISEASE, params)
                for record in res:
                    if record.get("drug", "") == drug:
                        reason = record.get("reason", "Unknown mechanism")
                        violations.append(f"CRITICAL CONTRAINDICATION: {drug} is contraindicated in {condition} ({reason})")
                        
        if violations:
            logger.warning(f"[GraphValidator] Discovered {len(violations)} relationship violations!")
            return False, violations
            
        return True, []
