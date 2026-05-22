"""
backend/decision — Orchestration Intelligence Layer (Phase 4.5)

This package is the adaptive decision brain of the Aegis system.
It classifies, plans, routes, and configures every request
before any retrieval or reasoning occurs.

Public surface:
  DecisionPlan         — output of the decision layer
  RiskAssessment       — risk engine output
  WorkflowConfig       — per-workflow orchestration configuration
  make_decision()      — single entry point for the orchestration brain
"""
from backend.decision.schemas import (
    DecisionPlan,
    RiskAssessment,
    WorkflowConfig,
    RiskLevel,
    WorkflowType,
    RetrievalStrategy,
    ReflectionStrategy,
    ValidationStrictness,
    SourcePriority,
)
from backend.decision.decision_layer import make_decision

__all__ = [
    "DecisionPlan", "RiskAssessment", "WorkflowConfig",
    "RiskLevel", "WorkflowType", "RetrievalStrategy",
    "ReflectionStrategy", "ValidationStrictness", "SourcePriority",
    "make_decision",
]
