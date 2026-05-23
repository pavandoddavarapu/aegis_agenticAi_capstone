"""
storage.py — Telemetry Storage Layer (Phase 5)

Architecture:
  Dual-backend storage strategy:
    1. PostgreSQL  — durable long-term event & trace storage
       Tables: telemetry_events, workflow_traces, retrieval_traces,
               agent_spans, evaluation_results
    2. Redis       — hot metrics cache (last 24h aggregates)
       Keys: aegis:metrics:daily, aegis:workflow:{id}, aegis:retrieval:{id}

  Write path:
    TelemetryBus.write_batch(events)
      → partition by event_type
      → PostgreSQL bulk INSERT (executemany for efficiency)
      → Redis HSET for aggregate metrics

  Read path (monitoring endpoints):
    Fast: Redis cache hit (< 1ms)
    Slow: PostgreSQL query (< 50ms for indexed queries)

  Schema (PostgreSQL):
    telemetry_events: raw event log, partitioned by date
    workflow_traces:  per-request workflow summaries
    retrieval_traces: per-request retrieval breakdowns
    agent_spans:      per-agent execution timing

  Retention:
    Raw events:    30 days (then archive to cold storage)
    Aggregates:    90 days
    Workflow traces: 180 days (clinical audit requirement)
"""
from __future__ import annotations
import json
import asyncio
import os
import time
from dataclasses import asdict
from typing import List, Optional, Dict, Any

from backend.utils.logger import logger

# ── Schema SQL ────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS telemetry_events (
    id              BIGSERIAL PRIMARY KEY,
    request_id      UUID NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id      UUID,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_te_request_id  ON telemetry_events(request_id);
CREATE INDEX IF NOT EXISTS idx_te_event_type  ON telemetry_events(event_type);
CREATE INDEX IF NOT EXISTS idx_te_ts          ON telemetry_events(ts DESC);

CREATE TABLE IF NOT EXISTS workflow_traces (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          UUID NOT NULL UNIQUE,
    query_hash          VARCHAR(32),
    query_type          VARCHAR(64),
    selected_workflow   VARCHAR(64),
    risk_level          VARCHAR(32),
    confidence_threshold FLOAT,
    final_confidence    FLOAT,
    total_ms            INT,
    retry_count         INT,
    workflow_path       TEXT,
    escalation_required BOOLEAN DEFAULT FALSE,
    status              VARCHAR(32),
    evidence_count      INT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wt_request_id ON workflow_traces(request_id);
CREATE INDEX IF NOT EXISTS idx_wt_created_at ON workflow_traces(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wt_workflow   ON workflow_traces(selected_workflow);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          UUID NOT NULL,
    strategy            VARCHAR(64),
    dense_candidates    INT,
    sparse_candidates   INT,
    fused_candidates    INT,
    final_docs          INT,
    top_score           FLOAT,
    avg_score           FLOAT,
    avg_trust_score     FLOAT,
    source_diversity    INT,
    total_latency_ms    INT,
    retrieval_success   BOOLEAN,
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rt_request_id ON retrieval_traces(request_id);

CREATE TABLE IF NOT EXISTS agent_spans (
    id           BIGSERIAL PRIMARY KEY,
    request_id   UUID NOT NULL,
    node         VARCHAR(64) NOT NULL,
    duration_ms  INT,
    success      BOOLEAN,
    error_msg    TEXT,
    ts           TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_as_request_id ON agent_spans(request_id);
CREATE INDEX IF NOT EXISTS idx_as_node       ON agent_spans(node);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id                 BIGSERIAL PRIMARY KEY,
    dataset            VARCHAR(128),
    recall_at_5        FLOAT,
    recall_at_10       FLOAT,
    precision_at_5     FLOAT,
    mrr                FLOAT,
    ndcg_at_10         FLOAT,
    grounding_score    FLOAT,
    hallucination_rate FLOAT,
    sample_count       INT,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);
"""


class TelemetryStorage:
    """Dual-backend telemetry storage: PostgreSQL + Redis."""

    def __init__(self):
        self._pg_pool  = None
        self._redis    = None
        self._ready    = False
        from collections import deque
        self._memory_traces = deque(maxlen=100) # Store recent request IDs
        self._memory_events = {} # Map request_id -> list of raw events
        self._memory_workflows = {} # Map request_id -> workflow_trace dict
        self._memory_retrievals = {} # Map request_id -> retrieval_trace dict

    async def initialize(self):
        """Create connection pools and ensure schema exists."""
        try:
            await self._init_postgres()
        except Exception as exc:
            logger.warning(f"[TelemetryStorage] PostgreSQL unavailable: {exc}")
        try:
            await self._init_redis()
        except Exception as exc:
            logger.warning(f"[TelemetryStorage] Redis unavailable: {exc}")
        self._ready = True

    async def _init_postgres(self):
        try:
            import asyncpg
            dsn = os.getenv("DATABASE_URL", "postgresql://aegis:aegis@localhost:5432/aegis_db")
            self._pg_pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
            async with self._pg_pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("[TelemetryStorage] PostgreSQL pool created.")
        except ImportError:
            logger.warning("[TelemetryStorage] asyncpg not installed — PG storage disabled.")

    async def _init_redis(self):
        try:
            import redis.asyncio as aioredis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = aioredis.from_url(url, decode_responses=True)
            await self._redis.ping()
            logger.info("[TelemetryStorage] Redis connected.")
        except Exception as exc:
            logger.warning(f"[TelemetryStorage] Redis init failed: {exc}")

    # ── Batch Write ───────────────────────────────────────────────────────────

    async def write_batch(self, events: list):
        """Partition events and write to appropriate tables."""
        if not events:
            return

        workflow_ends, retrievals, node_ends, raw = [], [], [], []

        for ev in events:
            etype = ev.event_type
            if etype == "workflow_end":
                workflow_ends.append(ev)
            elif etype == "retrieval":
                retrievals.append(ev)
            elif etype == "node_end":
                node_ends.append(ev)
            raw.append(ev)

        tasks = []
        if self._pg_pool:
            tasks += [
                self._insert_raw(raw),
                self._insert_workflow_ends(workflow_ends),
                self._insert_retrievals(retrievals),
                self._insert_node_ends(node_ends),
            ]
        if self._redis:
            tasks.append(self._update_redis_aggregates(events))
            
        # In-memory fallback
        for ev in events:
            rid = str(ev.request_id)
            if rid not in self._memory_events:
                self._memory_events[rid] = []
                self._memory_traces.append(rid)
            self._memory_events[rid].append(asdict(ev))
            
            if ev.event_type == "workflow_end":
                self._memory_workflows[rid] = asdict(ev)
            elif ev.event_type == "retrieval":
                self._memory_retrievals[rid] = asdict(ev)
                
        # cleanup memory
        while len(self._memory_traces) > 100:
            old_rid = self._memory_traces.popleft()
            self._memory_events.pop(old_rid, None)
            self._memory_workflows.pop(old_rid, None)
            self._memory_retrievals.pop(old_rid, None)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _insert_raw(self, events: list):
        if not events or not self._pg_pool:
            return
        try:
            rows = [
                (ev.request_id, ev.event_type, ev.ts, ev.session_id,
                 json.dumps(asdict(ev)))
                for ev in events
            ]
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO telemetry_events(request_id,event_type,ts,session_id,payload) "
                    "VALUES($1,$2,$3::timestamptz,$4::uuid,$5::jsonb) ON CONFLICT DO NOTHING",
                    rows
                )
        except Exception as exc:
            logger.error(f"[TelemetryStorage] raw insert error: {exc}")

    async def _insert_workflow_ends(self, events: list):
        if not events or not self._pg_pool:
            return
        try:
            rows = [
                (ev.request_id, ev.event_type, ev.total_ms, ev.final_confidence,
                 ev.retry_count, ev.workflow_path, ev.escalation_required,
                 ev.status, ev.evidence_count)
                for ev in events
            ]
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO workflow_traces(request_id,query_type,total_ms,"
                    "final_confidence,retry_count,workflow_path,escalation_required,"
                    "status,evidence_count) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) "
                    "ON CONFLICT(request_id) DO NOTHING",
                    rows
                )
        except Exception as exc:
            logger.error(f"[TelemetryStorage] workflow_traces insert: {exc}")

    async def _insert_retrievals(self, events: list):
        if not events or not self._pg_pool:
            return
        try:
            rows = [
                (ev.request_id, ev.strategy, ev.dense_candidates, ev.sparse_candidates,
                 ev.fused_candidates, ev.final_docs, ev.top_score, ev.avg_score,
                 ev.avg_trust_score, ev.source_diversity, ev.total_latency_ms,
                 ev.retrieval_success, ev.failure_reason or None)
                for ev in events
            ]
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO retrieval_traces(request_id,strategy,dense_candidates,"
                    "sparse_candidates,fused_candidates,final_docs,top_score,avg_score,"
                    "avg_trust_score,source_diversity,total_latency_ms,retrieval_success,"
                    "failure_reason) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                    rows
                )
        except Exception as exc:
            logger.error(f"[TelemetryStorage] retrieval_traces insert: {exc}")

    async def _insert_node_ends(self, events: list):
        if not events or not self._pg_pool:
            return
        try:
            rows = [
                (ev.request_id, ev.node, ev.duration_ms, ev.success, ev.error_msg or None, ev.ts)
                for ev in events
            ]
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO agent_spans(request_id,node,duration_ms,success,error_msg,ts)"
                    " VALUES($1,$2,$3,$4,$5,$6::timestamptz)",
                    rows
                )
        except Exception as exc:
            logger.error(f"[TelemetryStorage] agent_spans insert: {exc}")

    async def _update_redis_aggregates(self, events: list):
        if not self._redis:
            return
        try:
            pipe = self._redis.pipeline()
            for ev in events:
                key = f"aegis:telemetry:event:{ev.request_id}"
                pipe.rpush(key, json.dumps(asdict(ev)))
                pipe.expire(key, 86400)  # 24h TTL
            await pipe.execute()
        except Exception as exc:
            logger.debug(f"[TelemetryStorage] Redis aggregate error: {exc}")

    # ── Query API (for monitoring endpoints) ──────────────────────────────────

    async def get_workflow_trace(self, request_id: str) -> Optional[Dict]:
        """Fetch workflow trace by request ID."""
        if self._redis:
            try:
                events_raw = await self._redis.lrange(
                    f"aegis:telemetry:event:{request_id}", 0, -1
                )
                if events_raw:
                    return {"request_id": request_id,
                            "events": [json.loads(e) for e in events_raw]}
            except Exception:
                pass

        if self._pg_pool:
            try:
                async with self._pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM workflow_traces WHERE request_id=$1::uuid",
                        request_id
                    )
                    if row:
                        return dict(row)
            except Exception as exc:
                logger.error(f"[TelemetryStorage] get_workflow_trace: {exc}")
                
        # In-memory fallback
        if str(request_id) in self._memory_events:
            return {"request_id": str(request_id), "events": self._memory_events[str(request_id)]}
            
        return None

    async def get_recent_metrics(self, hours: int = 24) -> Dict:
        """Aggregate metrics for the monitoring dashboard."""
        if not self._pg_pool:
            # Memory fallback
            wfs = list(self._memory_workflows.values())
            if not wfs: return {}
            return {
                "total_requests": len(wfs),
                "avg_latency_ms": sum(w.get("total_ms", 0) or 0 for w in wfs) / len(wfs),
                "avg_confidence": sum(w.get("final_confidence", 0) or 0 for w in wfs) / len(wfs),
                "escalations": sum(1 for w in wfs if w.get("escalation_required")),
                "errors": sum(1 for w in wfs if w.get("status") == "error"),
                "avg_retries": sum(w.get("retry_count", 0) or 0 for w in wfs) / len(wfs)
            }
        try:
            async with self._pg_pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_requests,
                        AVG(total_ms) as avg_latency_ms,
                        AVG(final_confidence) as avg_confidence,
                        SUM(CASE WHEN escalation_required THEN 1 ELSE 0 END) as escalations,
                        SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors,
                        AVG(retry_count) as avg_retries
                    FROM workflow_traces
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                """, hours)
                return dict(stats) if stats else {}
        except Exception as exc:
            logger.error(f"[TelemetryStorage] get_recent_metrics: {exc}")
            return {}

    async def get_retrieval_stats(self, hours: int = 24) -> Dict:
        if not self._pg_pool:
            rets = list(self._memory_retrievals.values())
            if not rets: return {}
            return {
                "avg_retrieval_ms": sum(r.get("total_latency_ms", 0) or 0 for r in rets) / len(rets),
                "avg_docs_returned": sum(r.get("final_docs", 0) or 0 for r in rets) / len(rets),
                "avg_retrieval_score": sum(r.get("avg_score", 0) or 0 for r in rets) / len(rets),
                "avg_trust": sum(r.get("avg_trust_score", 0) or 0 for r in rets) / len(rets),
                "avg_source_diversity": sum(r.get("source_diversity", 0) or 0 for r in rets) / len(rets),
                "failures": sum(1 for r in rets if not r.get("retrieval_success"))
            }
        try:
            async with self._pg_pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT
                        AVG(total_latency_ms)    as avg_retrieval_ms,
                        AVG(final_docs)          as avg_docs_returned,
                        AVG(avg_score)           as avg_retrieval_score,
                        AVG(avg_trust_score)     as avg_trust,
                        AVG(source_diversity)    as avg_source_diversity,
                        SUM(CASE WHEN NOT retrieval_success THEN 1 ELSE 0 END) as failures
                    FROM retrieval_traces
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                """, hours)
                return dict(stats) if stats else {}
        except Exception as exc:
            logger.error(f"[TelemetryStorage] get_retrieval_stats: {exc}")
            return {}

    async def get_agent_latency_breakdown(self, hours: int = 24) -> List[Dict]:
        if not self._pg_pool:
            # Memory fallback
            node_stats = {}
            for evs in self._memory_events.values():
                for ev in evs:
                    if ev.get("event_type") == "node_end":
                        node = ev.get("node", "unknown")
                        if node not in node_stats:
                            node_stats[node] = {"durations": [], "failures": 0}
                        node_stats[node]["durations"].append(ev.get("duration_ms", 0))
                        if not ev.get("success", True):
                            node_stats[node]["failures"] += 1
            res = []
            for node, stats in node_stats.items():
                durs = sorted(stats["durations"])
                if not durs: continue
                res.append({
                    "node": node,
                    "avg_ms": sum(durs) / len(durs),
                    "p95_ms": durs[int(len(durs) * 0.95)],
                    "count": len(durs),
                    "failures": stats["failures"]
                })
            res.sort(key=lambda x: x["avg_ms"], reverse=True)
            return res
            
        try:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT node,
                           AVG(duration_ms) as avg_ms,
                           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_ms,
                           COUNT(*) as count,
                           SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures
                    FROM agent_spans
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                    GROUP BY node ORDER BY avg_ms DESC
                """, hours)
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"[TelemetryStorage] get_agent_latency: {exc}")
            return []
