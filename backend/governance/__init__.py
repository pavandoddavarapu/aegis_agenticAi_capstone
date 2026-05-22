"""
backend/governance — Phase 9: HITL + Governance Layer

Lightweight, production-style human oversight infrastructure.

Components:
  escalation_engine.py  — Determines WHEN human review is required
  review_engine.py      — Manages the review lifecycle (approve/reject/override)
  audit_logger.py       — Persists all review actions to PostgreSQL

Philosophy:
  - Human decision ALWAYS wins over AI output
  - All escalations and overrides are immutably logged
  - Critical-risk outputs are BLOCKED until reviewed
  - Simple configurable rules — not a complex workflow engine
"""
from backend.governance.escalation_engine import EscalationEngine, EscalationDecision
from backend.governance.review_engine     import ReviewEngine, ReviewStatus, ReviewAction
from backend.governance.audit_logger      import AuditLogger

__all__ = [
    "EscalationEngine", "EscalationDecision",
    "ReviewEngine", "ReviewStatus", "ReviewAction",
    "AuditLogger",
]
