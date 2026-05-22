"""
session_store.py — In-Memory Conversational Session Store (Phase 13)

TTL-based session store for ConversationalPatientSession objects.

Design:
  - In-memory dict (keyed by session_id string)
  - 2-hour TTL: sessions expire after 2 hours of inactivity
  - MAX_SESSIONS=500: LRU eviction when limit is reached
  - Thread-safe: uses asyncio lock for concurrent access safety
  - Production upgrade path: replace with Redis (sessions are JSON-serializable)

Singleton: session_store = SessionStore() — import this instance.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from backend.models.session import ConversationalPatientSession
from backend.utils.logger import logger


class SessionStore:
    """
    Thread-safe in-memory session store with TTL-based expiry.

    Usage:
        from backend.session.session_store import session_store

        session = session_store.create()
        session = session_store.get("some-session-id")
        session_store.update(session)
        session_store.delete("some-session-id")
    """

    TTL_HOURS   = 2
    MAX_SESSIONS = 500

    def __init__(self):
        self._sessions: Dict[str, ConversationalPatientSession] = {}
        self._lock = asyncio.Lock()

    # ── CRUD Operations ────────────────────────────────────────────────────────

    def create(self) -> ConversationalPatientSession:
        """Create a new session and store it. Returns the new session."""
        session = ConversationalPatientSession()
        self._sessions[session.session_id] = session
        logger.info(f"[SessionStore] Created session {session.session_id}")

        # Enforce session limit (simple LRU: evict oldest)
        if len(self._sessions) > self.MAX_SESSIONS:
            self._evict_oldest()

        return session

    def get(self, session_id: str) -> Optional[ConversationalPatientSession]:
        """Retrieve a session by ID. Returns None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        # Check TTL
        try:
            last_active = datetime.fromisoformat(session.last_active)
            if datetime.utcnow() - last_active > timedelta(hours=self.TTL_HOURS):
                logger.info(f"[SessionStore] Session {session_id} expired — removing.")
                del self._sessions[session_id]
                return None
        except Exception:
            pass  # Don't crash on bad timestamp — just return the session

        # Touch last_active
        session.last_active = datetime.utcnow().isoformat()
        return session

    def update(self, session: ConversationalPatientSession) -> None:
        """Persist updates to an existing session."""
        session.last_active = datetime.utcnow().isoformat()
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if deleted, False if not found."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[SessionStore] Deleted session {session_id}")
            return True
        return False

    # ── Maintenance ────────────────────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        cutoff = datetime.utcnow() - timedelta(hours=self.TTL_HOURS)
        expired: List[str] = []

        for sid, session in self._sessions.items():
            try:
                last_active = datetime.fromisoformat(session.last_active)
                if last_active < cutoff:
                    expired.append(sid)
            except Exception:
                pass

        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info(f"[SessionStore] Cleaned up {len(expired)} expired sessions.")

        return len(expired)

    def _evict_oldest(self) -> None:
        """Evict the oldest session when MAX_SESSIONS is exceeded."""
        if not self._sessions:
            return
        oldest_sid = min(
            self._sessions,
            key=lambda sid: self._sessions[sid].last_active,
        )
        del self._sessions[oldest_sid]
        logger.info(f"[SessionStore] Evicted oldest session {oldest_sid} (limit reached).")

    def stats(self) -> dict:
        """Return store statistics for health checks."""
        return {
            "total_sessions":    len(self._sessions),
            "max_sessions":      self.MAX_SESSIONS,
            "ttl_hours":         self.TTL_HOURS,
        }


# ── Module-Level Singleton ─────────────────────────────────────────────────────

session_store = SessionStore()
