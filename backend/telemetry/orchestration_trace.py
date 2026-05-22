"""
orchestration_trace.py — Execution DAG Tracer (Phase 5)

Architecture:
  OrchestrationTrace is the per-request execution context.
  It is created in run_workflow() and passed through the graph via
  a thread-local (sync) or contextvars.ContextVar (async).

  Each agent node calls:
    trace.enter_node(name)     → records NodeStartEvent, starts timer
    trace.exit_node(name, ok)  → records NodeEndEvent, duration
    trace.record_routing(decision, reason)
    trace.record_confidence(score)

  At workflow end:
    trace.finalise() → emits WorkflowEndEvent + RetrievalEvent summary

  The trace captures:
    - Ordered node execution list
    - Per-node duration (wall-clock, perf_counter)
    - Confidence evolution across retry cycles
    - Routing decisions at each conditional edge
    - Full DAG as adjacency list (for replay visualisation)

  Overhead target: < 0.5ms per node entry/exit.
"""
from __future__ import annotations
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.telemetry.core   import telemetry_bus
from backend.telemetry.events import (
    WorkflowStartEvent, WorkflowEndEvent,
    NodeStartEvent, NodeEndEvent,
    EscalationEvent,
)
from backend.utils.logger import logger


@dataclass
class NodeSpan:
    """Single node execution record."""
    node:        str
    start_ms:    float      # perf_counter() * 1000
    end_ms:      float = 0.0
    success:     bool  = True
    error_msg:   str   = ""

    @property
    def duration_ms(self) -> int:
        return int(self.end_ms - self.start_ms)


@dataclass
class RoutingDecision:
    at_node:    str
    decision:   str     # ROUTE_REFLECT | ROUTE_END
    reason:     str
    score:      float


class OrchestrationTrace:
    """
    Per-request execution tracer.

    Lifecycle:
        trace = OrchestrationTrace(request_id, query, initial_state)
        trace.start()
        # ... workflow runs, nodes call enter/exit ...
        result = trace.finalise(final_state)
    """

    def __init__(self, request_id: str, query: str, plan_dict: Dict):
        self.request_id     = request_id
        self.query_hash     = hashlib.sha256(query.encode()).hexdigest()[:12]
        self.plan           = plan_dict
        self._spans:        List[NodeSpan]       = []
        self._active:       Dict[str, NodeSpan]  = {}   # node → open span
        self._routing:      List[RoutingDecision]= []
        self._confidence_history: List[Tuple[str, float]] = []
        self._dag_edges:    List[Tuple[str, str]]= []   # (from_node, to_node)
        self._wall_start:   float = 0.0
        self._prev_node:    Optional[str] = None

    def start(self):
        """Emit WorkflowStartEvent and start wall clock."""
        self._wall_start = time.perf_counter()
        telemetry_bus.emit(WorkflowStartEvent(
            request_id           = self.request_id,
            query_hash           = self.query_hash,
            query_type           = self.plan.get("query_type", ""),
            selected_workflow    = self.plan.get("selected_workflow", ""),
            risk_level           = self.plan.get("risk_level", ""),
            confidence_threshold = self.plan.get("confidence_threshold", 0.0),
        ))
        logger.debug("[OTrace] Workflow started: %s", self.request_id)

    def enter_node(self, node: str):
        """Record node entry. Call at the start of each agent node."""
        span = NodeSpan(node=node, start_ms=time.perf_counter() * 1000)
        self._active[node] = span
        if self._prev_node and (self._prev_node, node) not in self._dag_edges:
            self._dag_edges.append((self._prev_node, node))
        telemetry_bus.emit(NodeStartEvent(
            request_id=self.request_id, node=node
        ))

    def exit_node(self, node: str, success: bool = True, error_msg: str = ""):
        """Record node exit and emit NodeEndEvent."""
        span = self._active.pop(node, None)
        if span is None:
            span = NodeSpan(node=node, start_ms=time.perf_counter() * 1000)
        span.end_ms    = time.perf_counter() * 1000
        span.success   = success
        span.error_msg = error_msg
        self._spans.append(span)
        self._prev_node = node

        telemetry_bus.emit(NodeEndEvent(
            request_id = self.request_id,
            node       = node,
            duration_ms= span.duration_ms,
            success    = success,
            error_msg  = error_msg,
        ))

    def record_routing(self, decision: str, reason: str, score: float = 0.0):
        """Record a supervisor routing decision."""
        self._routing.append(RoutingDecision(
            at_node  = self._prev_node or "unknown",
            decision = decision,
            reason   = reason,
            score    = score,
        ))

    def record_confidence(self, node: str, score: float):
        """Track confidence evolution across the workflow."""
        self._confidence_history.append((node, round(score, 4)))

    def record_escalation(self, reason: str, risk_level: str, risk_score: float):
        telemetry_bus.emit(EscalationEvent(
            request_id = self.request_id,
            risk_level = risk_level,
            risk_score = risk_score,
            reason     = reason,
            workflow   = self.plan.get("selected_workflow", ""),
        ))

    def finalise(self, final_state: Dict) -> Dict:
        """
        Emit WorkflowEndEvent and return the full trace summary dict.
        Called once at the very end of run_workflow().
        """
        total_ms = int((time.perf_counter() - self._wall_start) * 1000)

        path = "|".join(final_state.get("workflow_path", []))
        telemetry_bus.emit(WorkflowEndEvent(
            request_id           = self.request_id,
            total_ms             = total_ms,
            final_confidence     = final_state.get("validation_score", 0.0),
            retry_count          = final_state.get("retry_count", 0),
            workflow_path        = path,
            escalation_required  = final_state.get("escalation_required", False),
            status               = "error" if final_state.get("error") else "success",
            evidence_count       = len(final_state.get("retrieved_docs", [])),
        ))

        return self.to_summary(total_ms, final_state)

    def to_summary(self, total_ms: int, final_state: Dict) -> Dict:
        """Serialise the full trace to a JSON-safe dict for API responses."""
        return {
            "request_id":          self.request_id,
            "total_ms":            total_ms,
            "dag_edges":           self._dag_edges,
            "node_spans":          [
                {
                    "node":        s.node,
                    "duration_ms": s.duration_ms,
                    "success":     s.success,
                    "error_msg":   s.error_msg,
                }
                for s in self._spans
            ],
            "confidence_history":  self._confidence_history,
            "routing_decisions":   [
                {
                    "at_node":  r.at_node,
                    "decision": r.decision,
                    "reason":   r.reason,
                    "score":    r.score,
                }
                for r in self._routing
            ],
            "retry_count":         final_state.get("retry_count", 0),
            "escalation_required": final_state.get("escalation_required", False),
            "final_confidence":    final_state.get("validation_score", 0.0),
            "status":              "error" if final_state.get("error") else "success",
        }

    # ── Timeline extraction ───────────────────────────────────────────────────

    def get_timeline(self) -> List[Dict]:
        """Return spans sorted by start time — for the timeline endpoint."""
        return sorted(
            [
                {
                    "node":        s.node,
                    "start_ms":    round(s.start_ms, 1),
                    "end_ms":      round(s.end_ms, 1),
                    "duration_ms": s.duration_ms,
                    "success":     s.success,
                }
                for s in self._spans
            ],
            key=lambda x: x["start_ms"],
        )

    def get_bottlenecks(self, threshold_ms: int = 500) -> List[Dict]:
        """Return spans exceeding threshold_ms — latency hotspot detection."""
        return [
            s for s in self.get_timeline()
            if s["duration_ms"] >= threshold_ms
        ]
