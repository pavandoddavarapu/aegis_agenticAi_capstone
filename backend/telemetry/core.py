"""
core.py — Async Telemetry Event Bus (Phase 5)

Architecture:
  The TelemetryBus is a singleton async event bus built on asyncio.Queue.
  Design goals:
    1. ZERO blocking — agents call bus.emit() and return immediately.
    2. BATCHING — events are buffered and flushed in configurable batches
       to minimise DB round-trips.
    3. BACKPRESSURE — queue has a max size; overflow events are DROPPED
       not blocked (observability must never degrade orchestration).
    4. GRACEFUL SHUTDOWN — flush() drains the queue on app shutdown.

  Consumer loop (background asyncio task):
    while True:
      batch = collect up to BATCH_SIZE events (timeout: FLUSH_INTERVAL_S)
      await storage.write_batch(batch)

  This is the "fire-and-forget, best-effort" telemetry contract:
    - Every emit() is non-blocking.
    - Storage failures are logged but do NOT propagate to callers.
    - In-process queue is NOT durable (restart = lost buffer).
    - For durability, use TELEMETRY_MODE=redis to persist events to Redis
      before the consumer picks them up.

Performance budget:
  Target overhead per request: < 2ms additional latency.
  Queue max size: 10,000 events (prevents unbounded memory).
"""
from __future__ import annotations
import asyncio
import time
import json
from typing import List, Optional, TYPE_CHECKING

from backend.utils.logger import logger

if TYPE_CHECKING:
    from backend.telemetry.events import AnyEvent

# ── Configuration ─────────────────────────────────────────────────────────────
QUEUE_MAX_SIZE     = 10_000
BATCH_SIZE         = 50
FLUSH_INTERVAL_S   = 2.0     # seconds between forced flushes
WORKER_TIMEOUT_S   = 5.0     # asyncio.wait_for timeout per batch write


class TelemetryBus:
    """
    Singleton async event bus.

    Usage:
        from backend.telemetry.core import telemetry_bus
        telemetry_bus.emit(RetrievalEvent(...))   # sync, non-blocking
        await telemetry_bus.async_emit(event)     # from async context
    """

    def __init__(self):
        self._queue:   asyncio.Queue  = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._storage: Optional[object] = None
        self._task:    Optional[asyncio.Task] = None
        self._running: bool = False
        self._stats = {
            "emitted":  0,
            "dropped":  0,
            "flushed":  0,
            "errors":   0,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, storage=None):
        """Start the background consumer task."""
        from backend.telemetry.storage import TelemetryStorage
        self._storage = storage or TelemetryStorage()
        await self._storage.initialize()
        self._running = True
        self._task    = asyncio.create_task(self._consumer_loop(), name="telemetry_consumer")
        logger.info("[TelemetryBus] Started (queue_max=%d, batch=%d, interval=%.1fs)",
                    QUEUE_MAX_SIZE, BATCH_SIZE, FLUSH_INTERVAL_S)

    async def stop(self):
        """Graceful shutdown — flush remaining events."""
        self._running = False
        await self.flush()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[TelemetryBus] Stopped. Stats: %s", self._stats)

    # ── Emit API ──────────────────────────────────────────────────────────────

    def emit(self, event) -> bool:
        """
        Synchronous non-blocking emit.
        Returns True if queued, False if dropped (queue full).
        Safe to call from sync agent code.
        """
        try:
            self._queue.put_nowait(event)
            self._stats["emitted"] += 1
            return True
        except asyncio.QueueFull:
            self._stats["dropped"] += 1
            logger.warning("[TelemetryBus] Queue full — event dropped: %s",
                           type(event).__name__)
            return False

    async def async_emit(self, event) -> bool:
        """Async emit — waits if queue is full (max 100ms)."""
        try:
            await asyncio.wait_for(self._queue.put(event), timeout=0.1)
            self._stats["emitted"] += 1
            return True
        except (asyncio.TimeoutError, asyncio.QueueFull):
            self._stats["dropped"] += 1
            return False

    # ── Consumer Loop ─────────────────────────────────────────────────────────

    async def _consumer_loop(self):
        """Background task: collect → batch → write."""
        while self._running:
            batch = await self._collect_batch()
            if batch:
                await self._write_batch(batch)

    async def _collect_batch(self) -> list:
        """Collect up to BATCH_SIZE events within FLUSH_INTERVAL_S seconds."""
        batch    = []
        deadline = time.monotonic() + FLUSH_INTERVAL_S

        while len(batch) < BATCH_SIZE:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                batch.append(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                break

        return batch

    async def _write_batch(self, batch: list):
        """Write a batch to storage, catching and logging all errors."""
        if not self._storage:
            return
        try:
            await asyncio.wait_for(
                self._storage.write_batch(batch),
                timeout=WORKER_TIMEOUT_S,
            )
            self._stats["flushed"] += len(batch)
        except asyncio.TimeoutError:
            self._stats["errors"] += len(batch)
            logger.error("[TelemetryBus] Storage write timeout (%d events dropped)", len(batch))
        except Exception as exc:
            self._stats["errors"] += len(batch)
            logger.error("[TelemetryBus] Storage write error: %s", exc)

    async def flush(self):
        """Drain the entire queue to storage immediately."""
        batch = []
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                batch.append(event)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        if batch:
            await self._write_batch(batch)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {**self._stats, "queue_size": self._queue.qsize()}


# ── Module-level singleton ────────────────────────────────────────────────────
telemetry_bus = TelemetryBus()
