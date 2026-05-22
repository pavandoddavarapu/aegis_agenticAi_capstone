"""
router.py — Live Monitoring API (Phase 5)

Endpoints:
  GET /monitoring/health          — telemetry bus health + stats
  GET /monitoring/metrics         — aggregate workflow + retrieval metrics (24h)
  GET /monitoring/workflow/{id}   — full workflow trace by request_id
  GET /monitoring/timeline/{id}   — execution timeline for a request
  GET /monitoring/agent-latency   — per-node P50/P95 latency breakdown
  GET /monitoring/retrieval-stats — retrieval quality aggregates
  GET /monitoring/failure-analysis— failure pattern report
  GET /monitoring/grounding-summary — recent grounding/hallucination stats
  POST /monitoring/evaluate       — trigger offline evaluation run

All endpoints are async and read from the TelemetryStorage dual backend.
Cold paths (PostgreSQL) use indexed queries targeting < 50ms.
Hot paths (recent metrics) use Redis cache.
"""
from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.telemetry.storage         import TelemetryStorage
from backend.telemetry.core            import telemetry_bus
from backend.evaluation.failure_analytics import analyze_failures
from backend.utils.logger              import logger

router     = APIRouter(prefix="/monitoring", tags=["Observability"])
_storage   = TelemetryStorage()    # lazy-initialised singleton


async def _get_storage() -> TelemetryStorage:
    """Return initialized storage singleton."""
    global _storage
    if not _storage._ready:
        await _storage.initialize()
    return _storage


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def monitoring_health():
    """Telemetry bus health and queue statistics."""
    return {
        "status":          "ok",
        "telemetry_bus":   telemetry_bus.get_stats(),
        "storage_backends": {
            "postgres": "connected" if (await _get_storage())._pg_pool else "unavailable",
            "redis":    "connected" if (await _get_storage())._redis   else "unavailable",
        },
    }


# ─── Aggregate Metrics ────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics(hours: int = Query(default=24, ge=1, le=168)):
    """
    Aggregate workflow and retrieval metrics over the last N hours.
    Returns dashboard-ready KPIs.
    """
    storage = await _get_storage()
    wf      = await storage.get_recent_metrics(hours)
    ret     = await storage.get_retrieval_stats(hours)
    bus     = telemetry_bus.get_stats()

    return {
        "window_hours":    hours,
        "workflow": {
            "total_requests":      wf.get("total_requests", 0),
            "avg_latency_ms":      round(wf.get("avg_latency_ms") or 0, 1),
            "avg_confidence":      round(wf.get("avg_confidence") or 0, 3),
            "escalation_count":    wf.get("escalations", 0),
            "error_count":         wf.get("errors", 0),
            "avg_retries":         round(wf.get("avg_retries") or 0, 2),
        },
        "retrieval": {
            "avg_latency_ms":      round(ret.get("avg_retrieval_ms") or 0, 1),
            "avg_docs_returned":   round(ret.get("avg_docs_returned") or 0, 1),
            "avg_retrieval_score": round(ret.get("avg_retrieval_score") or 0, 3),
            "avg_trust_score":     round(ret.get("avg_trust") or 0, 3),
            "avg_source_diversity":round(ret.get("avg_source_diversity") or 0, 1),
            "retrieval_failures":  ret.get("failures", 0),
        },
        "telemetry_bus": bus,
    }


# ─── Workflow Trace ───────────────────────────────────────────────────────────

@router.get("/workflow/{request_id}")
async def get_workflow_trace(request_id: str):
    """
    Full workflow trace for a specific request_id.
    Returns node spans, routing decisions, confidence history, DAG edges.
    """
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id format (must be UUID)")

    storage = await _get_storage()
    trace   = await storage.get_workflow_trace(request_id)

    if not trace:
        raise HTTPException(status_code=404, detail=f"No trace found for request_id={request_id}")

    return trace


# ─── Timeline ─────────────────────────────────────────────────────────────────

@router.get("/timeline/{request_id}")
async def get_timeline(request_id: str):
    """
    Execution timeline for a request — ordered node spans with durations.
    Highlights bottlenecks (nodes exceeding 500ms).
    """
    storage = await _get_storage()
    trace   = await storage.get_workflow_trace(request_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    events  = trace.get("events", [])
    spans   = {}
    timeline= []

    for ev in events:
        etype = ev.get("event_type")
        node  = ev.get("node", "")
        if etype == "node_start":
            spans[node] = ev.get("ts", "")
        elif etype == "node_end" and node in spans:
            timeline.append({
                "node":        node,
                "duration_ms": ev.get("duration_ms", 0),
                "success":     ev.get("success", True),
                "start_ts":    spans.pop(node),
            })

    timeline.sort(key=lambda x: x.get("start_ts", ""))
    total_ms  = sum(s["duration_ms"] for s in timeline)
    bottlenecks = [s for s in timeline if s["duration_ms"] >= 500]

    return {
        "request_id":   request_id,
        "timeline":     timeline,
        "total_ms":     total_ms,
        "bottlenecks":  bottlenecks,
        "node_count":   len(timeline),
    }


# ─── Agent Latency Breakdown ──────────────────────────────────────────────────

@router.get("/agent-latency")
async def get_agent_latency(hours: int = Query(default=24, ge=1, le=168)):
    """
    Per-node P50/P95 latency breakdown.
    Identifies consistent latency hotspots across all requests.
    """
    storage = await _get_storage()
    rows    = await storage.get_agent_latency_breakdown(hours)
    return {
        "window_hours": hours,
        "nodes":        rows,
        "bottleneck":   rows[0]["node"] if rows else None,
    }


# ─── Retrieval Stats ─────────────────────────────────────────────────────────

@router.get("/retrieval-stats")
async def get_retrieval_stats(hours: int = Query(default=24, ge=1, le=168)):
    """Retrieval quality aggregates: scores, latency, diversity, failures."""
    storage = await _get_storage()
    stats   = await storage.get_retrieval_stats(hours)
    return {"window_hours": hours, **stats}


# ─── Failure Analysis ────────────────────────────────────────────────────────

@router.get("/failure-analysis")
async def get_failure_analysis(hours: int = Query(default=24, ge=1, le=168)):
    """
    Run failure pattern detection across recent workflow telemetry.
    Returns all detected systemic weaknesses with recommendations.
    """
    storage = await _get_storage()
    report  = await analyze_failures(storage, hours)
    return report.to_dict()


# ─── Evaluation Summary ──────────────────────────────────────────────────────

@router.get("/evaluation/summary")
async def get_evaluation_summary():
    """Most recent offline evaluation results from evaluation_results table."""
    storage = await _get_storage()
    if not storage._pg_pool:
        return {"error": "PostgreSQL unavailable"}
    try:
        async with storage._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM evaluation_results ORDER BY created_at DESC LIMIT 10"
            )
            return {"results": [dict(r) for r in rows]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
