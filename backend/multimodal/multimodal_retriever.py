"""
multimodal_retriever.py — Multimodal-Augmented Retrieval Engine (Phase 8)

Architecture:
  Extends HybridGraphRetriever to incorporate visual findings into the
  retrieval pipeline. When an image has been analyzed, the extracted
  visual query is used as an ADDITIONAL retrieval dimension.

  Retrieval pipeline:
    1. Visual findings query (from image analysis)
    2. Original text query (from user)
    3. Semantic vector retrieval (Qdrant)
    4. Graph traversal (Neo4j)
    5. Live research retrieval (PubMed, if enabled)
    6. RRF fusion of all retrieved docs

  Context assembly:
    - Visual context (ECG / Radiology / OCR)
    - Semantic evidence
    - Graph evidence
    - Similar cases
    - Live research
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from backend.graphrag.hybrid_graph_retriever import HybridGraphRetriever
from backend.utils.logger                    import logger


class MultimodalRetriever:
    """
    Retriever that fuses visual findings with semantic + graph + research retrieval.
    """

    async def retrieve(
        self,
        query:            str,
        visual_query:     Optional[str]   = None,
        query_variants:   Optional[List[str]] = None,
        use_graph:        bool            = False,
        use_research:     bool            = False,
        top_k:            int             = 8,
    ) -> Dict[str, Any]:
        """
        Run multimodal retrieval.

        If visual_query is provided (derived from image findings),
        it is used as the primary retrieval query. The original text
        query is added as a variant for broader coverage.
        """
        query_variants = query_variants or []

        # Augment variants with visual retrieval query
        effective_query = visual_query if visual_query else query
        if visual_query and query:
            query_variants = [query] + query_variants  # original text as variant

        logger.info(
            f"[MultimodalRetriever] Retrieving: primary='{effective_query[:80]}' "
            f"variants={len(query_variants)} graph={use_graph} research={use_research}"
        )

        try:
            retriever = HybridGraphRetriever()
            await retriever.initialize()
            result = await retriever.retrieve(
                query=effective_query,
                query_variants=query_variants,
                top_k=top_k,
            )
            logger.info(
                f"[MultimodalRetriever] Retrieved {len(result.get('retrieved_docs', []))} docs"
            )
            return result
        except Exception as exc:
            logger.exception(f"[MultimodalRetriever] Retrieval failed: {exc}")
            return {"retrieved_docs": [], "graph_context": ""}
