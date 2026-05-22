"""
audit_logger.py — Governance Audit Logger (Phase 9)

Persists all governance events — escalations, reviews, approvals,
rejections, overrides — to PostgreSQL for regulatory auditability.

Design:
  - Append-only log table (rows are NEVER updated/deleted)
  - All events have: request_id, event_type, actor, timestamp, payload
  - Async writes via asyncpg connection pool
  - Graceful degradation: if DB unavailable, events are logged to
    the application logger so they are at minimum captured in log files

Schema (auto-created on first write):

  CREATE TABLE IF NOT EXISTS governance_audit_log (
      id            BIGSERIAL PRIMARY KEY,
      request_id    TEXT        NOT NULL,
      event_type    TEXT        NOT NULL,  -- ESCALATED | APPROVED | REJECTED | OVERRIDE | RETRY_REQUESTED
      actor         TEXT        NOT NULL,  -- "system" | clinician_id
      severity      TEXT,
      query_preview TEXT,                  -- first 200 chars of query (never full query — PHI risk)
      workflow_type TEXT,
      confidence    FLOAT,
      notes         TEXT,                  -- clinician notes on review
      payload       JSONB,                 -- full serialisable event data
      created_at    TIMESTAMPTZ DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS idx_audit_request_id ON governance_audit_log(request_id);
  CREATE INDEX IF NOT EXISTS idx_audit_event_type ON governance_audit_log(event_type);
  CREATE INDEX IF NOT EXISTS idx_audit_created_at ON governance_audit_log(created_at DESC);
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.utils.logger import logger


# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS governance_audit_log (
    id            BIGSERIAL PRIMARY KEY,
    request_id    TEXT        NOT NULL,
    event_type    TEXT        NOT NULL,
    actor         TEXT        NOT NULL DEFAULT 'system',
    severity      TEXT,
    query_preview TEXT,
    workflow_type TEXT,
    confidence    FLOAT,
    notes         TEXT,
    payload       JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_request_id ON governance_audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON governance_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON governance_audit_log(created_at DESC);
"""

_INSERT_SQL = """
INSERT INTO governance_audit_log
    (request_id, event_type, actor, severity, query_preview,
     workflow_type, confidence, notes, payload)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
"""


# ── Event type constants ──────────────────────────────────────────────────────

class AuditEvent:
    ESCALATED         = "ESCALATED"
    APPROVED          = "APPROVED"
    REJECTED          = "REJECTED"
    OVERRIDE          = "OVERRIDE"
    RETRY_REQUESTED   = "RETRY_REQUESTED"
    AUTO_CLEARED      = "AUTO_CLEARED"    # Passed all checks, no review needed


# ── AuditLogger ───────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Async PostgreSQL-backed governance audit logger.

    Usage:
        logger = AuditLogger()
        await logger.initialize()          # creates table if needed
        await logger.log(request_id="...", event_type=AuditEvent.ESCALATED, ...)
    """

    def __init__(self):
        self._db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL", "")
        self._pool   = None
        self._ready  = False

    async def initialize(self):
        """Create the audit table if it doesn't exist."""
        if self._ready:
            return
        if not self._db_url:
            logger.warning("[AuditLogger] No DATABASE_URL — falling back to app logger only.")
            return
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._db_url, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(_CREATE_TABLE_SQL)
            self._ready = True
            logger.info("[AuditLogger] PostgreSQL audit table ready.")
        except Exception as exc:
            logger.warning(f"[AuditLogger] DB init failed — fallback mode: {exc}")

    async def log(
        self,
        request_id:    str,
        event_type:    str,
        actor:         str            = "system",
        severity:      Optional[str]  = None,
        query_preview: Optional[str]  = None,
        workflow_type: Optional[str]  = None,
        confidence:    Optional[float] = None,
        notes:         Optional[str]  = None,
        payload:       Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append an audit event. Fails silently (logs to stderr) if DB unavailable."""
        event = {
            "request_id":    request_id,
            "event_type":    event_type,
            "actor":         actor,
            "severity":      severity,
            "query_preview": (query_preview or "")[:200],  # cap — PHI protection
            "workflow_type": workflow_type,
            "confidence":    confidence,
            "notes":         notes,
            "created_at":    datetime.now(timezone.utc).isoformat(),
        }

        # Always log to application logger (backup)
        logger.info(f"[AuditLog] {event_type} | request={request_id} actor={actor} severity={severity}")

        if not self._ready or not self._pool:
            return  # Fallback: app logger only

        try:
            payload_json = json.dumps(payload or event)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    _INSERT_SQL,
                    request_id,
                    event_type,
                    actor,
                    severity,
                    event["query_preview"],
                    workflow_type,
                    confidence,
                    notes,
                    payload_json,
                )
        except Exception as exc:
            logger.error(f"[AuditLogger] Write failed: {exc}")

    async def get_pending_reviews(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Fetch requests that were escalated but not yet approved/rejected."""
        if not self._ready or not self._pool:
            return []
        try:
            sql = """
            SELECT DISTINCT ON (request_id) request_id, severity, query_preview,
                   workflow_type, confidence, created_at
            FROM governance_audit_log
            WHERE event_type = 'ESCALATED'
              AND request_id NOT IN (
                SELECT request_id FROM governance_audit_log
                WHERE event_type IN ('APPROVED','REJECTED','OVERRIDE')
              )
            ORDER BY request_id, created_at DESC
            LIMIT $1
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit)
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"[AuditLogger] get_pending_reviews failed: {exc}")
            return []

    async def get_audit_history(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """Query audit log with optional event_type filter."""
        if not self._ready or not self._pool:
            return []
        try:
            if event_type:
                sql = """
                SELECT id, request_id, event_type, actor, severity,
                       query_preview, workflow_type, confidence, notes, created_at
                FROM governance_audit_log
                WHERE event_type = $1
                ORDER BY created_at DESC LIMIT $2
                """
                args = [event_type, limit]
            else:
                sql = """
                SELECT id, request_id, event_type, actor, severity,
                       query_preview, workflow_type, confidence, notes, created_at
                FROM governance_audit_log
                ORDER BY created_at DESC LIMIT $1
                """
                args = [limit]

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *args)
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"[AuditLogger] get_audit_history failed: {exc}")
            return []

    async def close(self):
        if self._pool:
            await self._pool.close()
