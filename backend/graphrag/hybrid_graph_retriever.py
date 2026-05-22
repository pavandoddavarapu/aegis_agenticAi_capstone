"""
hybrid_graph_retriever.py — Semantic + Relational Retrieval (Phase 6)

Architecture:
  Unifies Qdrant (dense + sparse vector search) with Neo4j (graph traversal).

  Given a query (e.g. "STEMI with hypotension"), it:
   1. Uses traditional RRF vector retrieval to find evidence chunks.
   2. Uses the QueryAgent's `query_plan` (entities) to fetch Neo4j graphs.
   3. Looks up Disease Profiles if a core disease is detected.
   4. Looks up Contraindications if drugs are mentioned.
   5. Compiles the `compressed_context` into two sections:
      - [SEMANTIC EVIDENCE] (from PDFs)
      - [RELATIONAL GRAPH KNOWLEDGE] (from Neo4j)

  This provides the Reasoning Agent with both deep literature (chunks)
  and explicit structured constraints (graph).
"""
import asyncio
from typing import Dict, List, Any

from backend.rag.hybrid_retriever import hybrid_retrieve
from backend.graphrag.graph_client import GraphClient
from backend.graphrag.graph_retriever import GraphRetriever
from backend.graphrag.graph_ingestor import extract_entities
from backend.utils.logger import logger

class HybridGraphRetriever:
    """Combines Qdrant semantic search with Neo4j relational graph search."""
    
    def __init__(self):
        self.graph_client = GraphClient.get_instance()
        self.graph_retriever = GraphRetriever(self.graph_client)
    
    async def initialize(self):
        await self.graph_client.initialize()

    async def retrieve(
        self,
        query: str,
        entities: List[str] = None,
        top_k: int = 5,
        fetch_interactions: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform concurrent Vector + Graph retrieval.
        Returns a dictionary with both semantic docs and structured graph data.
        """
        # 1. Fire semantic retrieval (hybrid RRF + reranking)
        semantic_task = asyncio.to_thread(
            hybrid_retrieve,
            query=query,
            query_variants=kwargs.get("query_variants", []),
            top_k_final=top_k
        )
        
        # 2. Fire graph retrieval
        # If no explicit entities provided, run fast regex extraction
        if not entities:
            extracted = extract_entities(query)
            entities = [e.canonical for e in extracted]
            
        graph_tasks = []
        for ent in entities:
            graph_tasks.append(self.graph_retriever.get_entity_neighborhood(ent, depth=1, limit=5))
            
            # If interaction checks are needed, run contraindication checks
            if fetch_interactions:
                graph_tasks.append(self.graph_retriever.get_drug_interactions(ent))
                graph_tasks.append(self.graph_retriever.get_disease_contraindications(ent))

        # Wait for all I/O
        results = await asyncio.gather(semantic_task, *graph_tasks, return_exceptions=True)
        
        # Parse results
        semantic_res = results[0]
        if isinstance(semantic_res, Exception):
            logger.error(f"[HybridRetriever] Semantic search failed: {semantic_res}")
            docs = []
        else:
            docs = semantic_res
            
        # Parse graph edges
        all_edges = []
        for g_res in results[1:]:
            if isinstance(g_res, list):
                all_edges.extend(g_res)
                
        # Deduplicate edges based on source-target
        unique_edges = {}
        for edge in all_edges:
            src = edge.get("source", edge.get("drug", ""))
            tgt = edge.get("target", edge.get("interacts_with", ""))
            rel = edge.get("rel_type", edge.get("interaction_type", "RELATED"))
            key = f"{src}-{rel}-{tgt}"
            if key not in unique_edges:
                unique_edges[key] = edge
                
        graph_context_str = self.graph_retriever.format_graph_context(list(unique_edges.values()))
        
        logger.info(
            f"[HybridRetriever] Query '{query[:30]}...' returned "
            f"{len(docs)} chunks and {len(unique_edges)} graph edges."
        )
        
        return {
            "retrieved_docs": docs,
            "graph_edges": list(unique_edges.values()),
            "graph_context": graph_context_str
        }

    def format_combined_context(self, hybrid_result: Dict[str, Any]) -> str:
        """Combine semantic docs and graph edges into a single prompt string."""
        docs = hybrid_result.get("retrieved_docs", [])
        graph_ctx = hybrid_result.get("graph_context", "")
        
        blocks = []
        if graph_ctx:
            blocks.append("=== RELATIONAL GRAPH KNOWLEDGE ===\n" + graph_ctx)
            
        if docs:
            docs_str = "\n\n".join([f"Source: {d['source']}\n{d['text']}" for d in docs])
            blocks.append("=== SEMANTIC EVIDENCE CHUNKS ===\n" + docs_str)
            
        return "\n\n".join(blocks)
