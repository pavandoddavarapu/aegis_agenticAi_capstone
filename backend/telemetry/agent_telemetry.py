"""
agent_telemetry.py — Per-Agent Instrumentation (Phase 5)

Architecture:
  Two instrumentation mechanisms:

  1. @instrument_agent decorator (for LangGraph node functions)
     Wraps the node function with:
       - Entry/exit telemetry via OrchestrationTrace
       - Exception capture → ErrorEvent
       - Zero-overhead when telemetry_bus has no listeners

  2. AgentTimer context manager (for sub-operations within agents)
     Measures sub-operation latency (dense retrieval, BM25, reranker, etc.)
     and records them as sub-span dicts in the node span payload.

  Usage in agent functions:
      @instrument_agent("retrieve")
      def retrieval_agent(state: AgentState) -> dict:
          ...

      # Sub-operation timing:
      with AgentTimer("dense_search") as t:
          results = qdrant_search(...)
      t.duration_ms  # available after context exit

  Design constraint:
    The decorator must NOT change the function signature.
    LangGraph calls node functions with exactly one argument: state dict.
"""
from __future__ import annotations
import functools
import time
import inspect
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, Optional

from backend.telemetry.core   import telemetry_bus
from backend.telemetry.events import ErrorEvent
from backend.utils.logger     import logger


# ── Sub-operation timer ───────────────────────────────────────────────────────

@dataclass
class AgentTimer:
    """
    Context manager for measuring sub-operation latency.

    Usage:
        with AgentTimer("bm25_search") as t:
            results = bm25.search(query)
        print(t.duration_ms)
    """
    name:        str
    duration_ms: int  = field(default=0, init=False)
    _start:      float= field(default=0.0, init=False, repr=False)

    def __enter__(self) -> "AgentTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.duration_ms = int((time.perf_counter() - self._start) * 1000)


# ── Node instrumentation decorator ───────────────────────────────────────────

def instrument_agent(node_name: str):
    """
    Decorator that instruments a LangGraph node function with telemetry.
    Supports both synchronous and asynchronous node functions.

    Reads the active OrchestrationTrace from state["_trace"] if present.
    Falls back gracefully if no trace is attached.

    Args:
        node_name: The LangGraph node name (e.g. "retrieve", "reason").
    """
    def decorator(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(state: Dict) -> Dict:
                trace = state.get("_trace")

                # Enter telemetry
                if trace:
                    try:
                        trace.enter_node(node_name)
                    except Exception:
                        pass

                # Execute node
                success   = True
                error_msg = ""
                result    = {}
                try:
                    result = await fn(state)
                except Exception as exc:
                    success   = False
                    error_msg = str(exc)
                    logger.exception(f"[{node_name}] Unhandled exception: {exc}")
                    telemetry_bus.emit(ErrorEvent(
                        request_id = state.get("_request_id", "unknown"),
                        node       = node_name,
                        error_type = type(exc).__name__,
                        error_msg  = error_msg,
                        recoverable= False,
                    ))
                    result = {"error": error_msg, "workflow_path": [node_name]}

                # Exit telemetry
                if trace:
                    try:
                        trace.exit_node(node_name, success=success, error_msg=error_msg)
                    except Exception:
                        pass

                    # Capture validation score evolution
                    if node_name == "validate" and "validation_score" in result:
                        try:
                            trace.record_confidence(node_name, result["validation_score"])
                        except Exception:
                            pass

                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(state: Dict) -> Dict:
                trace = state.get("_trace")

                # Enter telemetry
                if trace:
                    try:
                        trace.enter_node(node_name)
                    except Exception:
                        pass

                # Execute node
                success   = True
                error_msg = ""
                result    = {}
                try:
                    result = fn(state)
                except Exception as exc:
                    success   = False
                    error_msg = str(exc)
                    logger.exception(f"[{node_name}] Unhandled exception: {exc}")
                    telemetry_bus.emit(ErrorEvent(
                        request_id = state.get("_request_id", "unknown"),
                        node       = node_name,
                        error_type = type(exc).__name__,
                        error_msg  = error_msg,
                        recoverable= False,
                    ))
                    result = {"error": error_msg, "workflow_path": [node_name]}

                # Exit telemetry
                if trace:
                    try:
                        trace.exit_node(node_name, success=success, error_msg=error_msg)
                    except Exception:
                        pass

                    # Capture validation score evolution
                    if node_name == "validate" and "validation_score" in result:
                        try:
                            trace.record_confidence(node_name, result["validation_score"])
                        except Exception:
                            pass

                return result
            return sync_wrapper
    return decorator


# ── Retrieval sub-telemetry helper ────────────────────────────────────────────

def build_retrieval_event_data(
    request_id:         str,
    strategy:           str,
    dense_results:      list,
    sparse_results:     list,
    fused_results:      list,
    final_docs:         list,
    dense_ms:           int,
    sparse_ms:          int,
    rerank_ms:          int,
    compress_ms:        int,
) -> dict:
    """
    Compute all retrieval telemetry fields from raw retrieval outputs.
    Returns a dict suitable for constructing a RetrievalEvent.
    """
    scores      = [d.get("rerank_score") or d.get("score", 0) for d in final_docs]
    trusts      = [float(d.get("trust_score", 0.6)) for d in final_docs]
    sources     = {d.get("source", "unknown") for d in final_docs}

    return {
        "request_id":       request_id,
        "strategy":         strategy,
        "dense_candidates": len(dense_results),
        "sparse_candidates":len(sparse_results),
        "fused_candidates": len(fused_results),
        "final_docs":       len(final_docs),
        "top_score":        round(max(scores, default=0.0), 4),
        "avg_score":        round(sum(scores) / max(len(scores), 1), 4),
        "avg_trust_score":  round(sum(trusts) / max(len(trusts), 1), 4),
        "source_diversity": len(sources),
        "dense_latency_ms": dense_ms,
        "sparse_latency_ms":sparse_ms,
        "rerank_latency_ms":rerank_ms,
        "compress_latency_ms": compress_ms,
        "total_latency_ms": dense_ms + sparse_ms + rerank_ms + compress_ms,
        "retrieval_success":len(final_docs) > 0,
        "failure_reason":   "" if final_docs else "no_documents_retrieved",
    }
