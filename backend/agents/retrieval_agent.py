"""
retrieval_agent.py — Retrieval Agent (Phase 6 — Vector + Graph + Cases)

Upgrades from Phase 4 to:
  1. Hybrid retrieval (Dense + Sparse)
  2. Cross-encoder reranking
  3. GraphRAG retrieval via Neo4j
  4. Episodic case memory retrieval

Reads:  state["query"], state["query_variants"]
Writes: state["retrieved_docs"], state["graph_context"],
        state["similar_cases_context"], state["compressed_context"]
"""
import asyncio
from backend.models.state          import AgentState
from backend.rag.hybrid_retriever  import hybrid_retrieve
from backend.rag.compressor        import compress_context
from backend.graphrag.hybrid_graph_retriever import HybridGraphRetriever
from backend.graphrag.similar_case_engine import SimilarCaseEngine
from backend.graphrag.graph_client import GraphClient
from backend.research.research_agent import ResearchAgent
from backend.utils.logger          import logger


async def retrieval_agent(state: AgentState) -> dict:
    """
    Graph-Aware Retrieval Agent node.

    Pipeline:
      1. Vector search + Reranking + Graph Traversal
      2. Similar Case Memory Fetching (if enabled)
      3. Contextual Compression
    """
    query    = state.get("query", "").strip()
    variants = state.get("query_variants", [])
    
    # Extract decision layer flags (from decision_trace)
    trace = state.get("decision_trace", {})
    use_graph = trace.get("graph_retrieval", False)
    use_cases = trace.get("case_retrieval", False)
    use_research = trace.get("internet_retrieval", False)

    logger.info(
        f"[RetrievalAgent] Retrieving for: '{query[:80]}' "
        f"| graph={use_graph} | cases={use_cases} | live_research={use_research}"
    )

    if not query:
        logger.warning("[RetrievalAgent] Empty query.")
        return {
            "retrieved_docs":     [],
            "graph_context":      "",
            "similar_cases_context": "",
            "compressed_context": "No query provided.",
            "workflow_path":      ["retrieve"],
            "error":              "Empty query passed to retrieval agent.",
        }

    docs = []
    graph_edges = []
    graph_context = ""
    similar_cases_context = ""
    live_research_context = ""

    async def fetch_graph_and_semantic():
        nonlocal docs, graph_context
        if use_graph:
            try:
                retriever = HybridGraphRetriever()
                await retriever.initialize()
                res = await retriever.retrieve(
                    query=query, 
                    query_variants=variants, 
                    top_k=8
                )
                docs = res.get("retrieved_docs", [])
                graph_context = res.get("graph_context", "")
            except Exception as exc:
                logger.exception(f"[RetrievalAgent] Hybrid Graph retrieval failed: {exc}")
        else:
            # Fallback to pure semantic retrieval
            try:
                # Need to run synchronous hybrid_retrieve in a thread
                docs = await asyncio.to_thread(
                    hybrid_retrieve,
                    query=query,
                    query_variants=variants,
                    top_k_final=8,
                )
                logger.info(f"[RetrievalAgent] Semantic hybrid returned {len(docs)} docs.")
            except Exception as exc:
                logger.exception(f"[RetrievalAgent] Hybrid retrieval failed: {exc}")

    async def fetch_similar_cases():
        nonlocal similar_cases_context
        if use_cases:
            try:
                client = GraphClient.get_instance()
                await client.initialize()
                engine = SimilarCaseEngine(client)
                # Assuming query contains some case context; for now, we use Jaccard search via NLP extraction
                # Here we just fetch cases for a detected disease as a fallback
                from backend.graphrag.graph_ingestor import extract_entities
                extracted = extract_entities(query)
                diseases = [e.canonical for e in extracted if e.label == "Disease"]
                cases = []
                if diseases:
                    cases = await engine.get_cases_for_disease(diseases[0], limit=3)
                similar_cases_context = engine.format_case_context(cases)
                if similar_cases_context:
                    logger.info("[RetrievalAgent] Attached episodic case memory.")
            except Exception as exc:
                logger.exception(f"[RetrievalAgent] Case retrieval failed: {exc}")
                similar_cases_context = ""
                
            # Fallback to Real-World PubMed Case Reports if local database has no similar patients
            if not similar_cases_context:
                try:
                    research_agent = ResearchAgent()
                    research_query = sorted(variants, key=len)[0] if variants else query
                    if len(research_query.split()) > 8:
                        stop_words = {"patient", "presents", "history", "with", "currently", "taking", "recently", "developed", "advised", "start", "current", "latest"}
                        words = [w for w in research_query.split() if w.lower() not in stop_words and len(w) > 3]
                        research_query = " ".join(words[:4])
                        
                    case_query = f"{research_query} case report"
                    logger.info(f"[RetrievalAgent] Fetching real-world case reports from PubMed: '{case_query}'")
                    case_res = await research_agent.run_research(case_query, strict_rct=False)
                    if case_res:
                        similar_cases_context = f"=== REAL-WORLD PUBLISHED CASE REPORTS ===\n{case_res}"
                except Exception as e:
                    logger.error(f"[RetrievalAgent] PubMed case report fallback failed: {e}")

    async def fetch_live_research():
        nonlocal live_research_context
        if use_research:
            try:
                research_agent = ResearchAgent()
                # Use the most concise AI-generated query variant
                research_query = sorted(variants, key=len)[0] if variants else query
                
                # Pure dynamic fallback if the AI failed to generate variants
                if len(research_query.split()) > 8:
                    # Remove common stop words dynamically instead of hardcoded lists
                    stop_words = {"patient", "presents", "history", "with", "currently", "taking", "recently", "developed", "advised", "start", "current", "latest"}
                    words = [w for w in research_query.split() if w.lower() not in stop_words and len(w) > 3]
                    research_query = " ".join(words[:4])
                    
                logger.info(f"[RetrievalAgent] Executing dynamic PubMed search with: '{research_query}'")
                live_research_context = await research_agent.run_research(research_query, strict_rct=False)
                if live_research_context:
                    logger.info("[RetrievalAgent] Attached live research context.")
            except Exception as exc:
                logger.exception(f"[RetrievalAgent] Live research failed: {exc}")

    # Run the three sub-retrievals concurrently
    await asyncio.gather(
        fetch_graph_and_semantic(),
        fetch_similar_cases(),
        fetch_live_research()
    )

    # ── Contextual compression ──────────────────────────────────────────────
    try:
        # We only compress the semantic docs, graph/case text goes directly to reasoning
        compressed = await asyncio.to_thread(compress_context, query=query, chunks=docs)
    except Exception as exc:
        logger.warning(f"[RetrievalAgent] Compression failed: {exc}")
        compressed = "\n\n".join(
            f"[Evidence {i+1}] {d.get('text','')[:400]}"
            for i, d in enumerate(docs)
        )

    return {
        "retrieved_docs":        docs,
        "graph_context":         graph_context,
        "similar_cases_context": similar_cases_context,
        "live_research_context": live_research_context,
        "compressed_context":    compressed,
        "workflow_path":         ["retrieve"],
        "error":                 None if (docs or graph_context or similar_cases_context or live_research_context) else "No evidence found.",
    }
