"""
graph_client.py — Async Neo4j Connection Pool (Phase 6)

Architecture:
  Singleton async driver using neo4j.AsyncGraphDatabase.driver().
  Connection pool is initialized once at app startup via initialize()
  and shared across all graph modules.

  Design constraints:
    - All queries run in async sessions (non-blocking I/O)
    - Sessions are acquired per-query and immediately released
    - The driver maintains an internal connection pool (configured via
      max_connection_pool_size)
    - Schema (constraints + indexes) is applied once on startup

  Usage:
      client = GraphClient.get_instance()
      await client.initialize()
      records = await client.run_query(CYPHER, {"param": value})
      await client.close()

  Fallback:
    If Neo4j is unreachable, all methods return empty results (not errors).
    This ensures the rest of the orchestration pipeline is unaffected when
    the graph backend is unavailable.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from backend.graphrag.schema import SCHEMA_CYPHER
from backend.utils.logger import logger

_INSTANCE: Optional["GraphClient"] = None


class GraphClient:
    """
    Singleton async Neo4j client.
    Thread-safe: all methods are coroutines.
    """

    def __init__(self):
        self._driver  = None
        self._ready   = False

    # ── Singleton access ──────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "GraphClient":
        global _INSTANCE
        if _INSTANCE is None:
            _INSTANCE = cls()
        return _INSTANCE

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """
        Connect to Neo4j and apply schema DDL.
        Returns True on success, False on failure (graceful fallback).
        """
        if self._ready:
            return True

        uri      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
        user     = os.getenv("NEO4J_USER",     "neo4j")
        password = os.getenv("NEO4J_PASSWORD",  "password")

        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                uri, auth=(user, password),
                max_connection_pool_size=20,
                connection_timeout=5.0,
            )
            await self._driver.verify_connectivity()
            await self._apply_schema()
            self._ready = True
            logger.info(f"[GraphClient] Connected to Neo4j: {uri}")
            return True
        except ImportError:
            logger.warning("[GraphClient] neo4j package not installed — graph disabled.")
        except Exception as exc:
            logger.warning(f"[GraphClient] Neo4j unavailable: {exc} — graph disabled.")
        return False

    async def close(self):
        """Gracefully close the connection pool."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            self._ready  = False
            logger.info("[GraphClient] Connection pool closed.")

    async def _apply_schema(self):
        """Run all schema DDL statements (idempotent IF NOT EXISTS guards)."""
        if not self._driver:
            return
        async with self._driver.session() as session:
            for cypher in SCHEMA_CYPHER:
                try:
                    await session.run(cypher)
                except Exception as exc:
                    # Schema DDL errors are non-fatal (e.g. already exists)
                    logger.debug(f"[GraphClient] Schema DDL: {exc}")
        logger.info("[GraphClient] Schema applied.")

    # ── Query API ─────────────────────────────────────────────────────────────

    async def run_query(
        self,
        cypher:     str,
        params:     Optional[Dict[str, Any]] = None,
        database:   str = None,
        timeout_s:  float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return a list of record dicts.

        Returns [] on any error (graph errors never propagate to callers).
        All queries are read-only by default — use run_write() for mutations.
        """
        if not self._ready:
            return []
        try:
            import asyncio
            async with self._driver.session(database=database) if database else self._driver.session() as session:
                result = await asyncio.wait_for(
                    session.run(cypher, params or {}),
                    timeout=timeout_s,
                )
                return [dict(record) async for record in result]
        except Exception as exc:
            logger.error(f"[GraphClient] Query error: {exc}\nCypher: {cypher[:200]}")
            return []

    async def run_write(
        self,
        cypher:  str,
        params:  Optional[Dict[str, Any]] = None,
        database:str = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a write transaction (MERGE / CREATE / SET).
        Returns [] on error.
        """
        if not self._ready:
            return []
        try:
            async with self._driver.session(database=database) if database else self._driver.session() as session:
                result = await session.run(cypher, params or {})
                return [dict(record) async for record in result]
        except Exception as exc:
            logger.error(f"[GraphClient] Write error: {exc}")
            return []

    @property
    def is_ready(self) -> bool:
        return self._ready
