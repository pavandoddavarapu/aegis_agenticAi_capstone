"""
events.py — Telemetry Event Schema (Phase 5)

All telemetry events are immutable frozen dataclasses.
This gives us:
  - Type safety (no dict key typos)
  - Serialisation via dataclasses.asdict()
  - Hashability for deduplication
  - Clear schema documentation

Event hierarchy:
  BaseEvent                     — common fields (request_id, ts, session_id)
    WorkflowStartEvent
    WorkflowEndEvent
    NodeStartEvent
    NodeEndEvent
    RetrievalEvent              — deep retrieval breakdown
    RerankerEvent               — per-chunk score deltas
    CompressionEvent            — token discard ratio
    ValidationEvent
    ReflectionEvent
    EscalationEvent
    ErrorEvent
    EvaluationEvent             — offline evaluation metrics

Storage contract:
  All events serialise via dataclasses.asdict() to JSON-safe dicts.
  Timestamps are UTC ISO-8601 strings.
  duration_ms is always measured wall-clock via time.perf_counter().
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import datetime


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _new_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BaseEvent:
    request_id:  str
    event_type:  str
    ts:          str = field(default_factory=_now)
    session_id:  str = field(default_factory=_new_id)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class WorkflowStartEvent(BaseEvent):
    event_type:       str = "workflow_start"
    query_hash:       str = ""         # SHA256[:12] of query (privacy-safe)
    query_type:       str = ""
    selected_workflow:str = ""
    risk_level:       str = ""
    confidence_threshold: float = 0.0


@dataclass(frozen=True)
class WorkflowEndEvent(BaseEvent):
    event_type:         str   = "workflow_end"
    total_ms:           int   = 0
    final_confidence:   float = 0.0
    retry_count:        int   = 0
    workflow_path:      str   = ""     # pipe-joined node names
    escalation_required:bool  = False
    status:             str   = "success"   # success|partial|error
    evidence_count:     int   = 0


@dataclass(frozen=True)
class NodeStartEvent(BaseEvent):
    event_type: str = "node_start"
    node:       str = ""


@dataclass(frozen=True)
class NodeEndEvent(BaseEvent):
    event_type:  str   = "node_end"
    node:        str   = ""
    duration_ms: int   = 0
    success:     bool  = True
    error_msg:   str   = ""


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RetrievalEvent(BaseEvent):
    event_type:           str   = "retrieval"
    strategy:             str   = ""      # hybrid|dense_only|guideline_priority
    dense_candidates:     int   = 0
    sparse_candidates:    int   = 0
    fused_candidates:     int   = 0
    final_docs:           int   = 0
    top_score:            float = 0.0
    avg_score:            float = 0.0
    avg_trust_score:      float = 0.0
    source_diversity:     int   = 0       # unique sources
    dense_latency_ms:     int   = 0
    sparse_latency_ms:    int   = 0
    rerank_latency_ms:    int   = 0
    compress_latency_ms:  int   = 0
    total_latency_ms:     int   = 0
    retrieval_success:    bool  = True
    failure_reason:       str   = ""


@dataclass(frozen=True)
class RerankerEvent(BaseEvent):
    event_type:       str   = "reranker"
    input_count:      int   = 0
    output_count:     int   = 0
    avg_score_before: float = 0.0    # avg RRF score before rerank
    avg_score_after:  float = 0.0    # avg rerank_score after
    score_lift:       float = 0.0    # avg_score_after - avg_score_before
    top1_section:     str   = ""     # section of top-1 chunk after rerank
    duration_ms:      int   = 0


@dataclass(frozen=True)
class CompressionEvent(BaseEvent):
    event_type:        str   = "compression"
    input_chunks:      int   = 0
    output_chunks:     int   = 0
    input_tokens:      int   = 0
    output_tokens:     int   = 0
    discard_ratio:     float = 0.0   # (input - output) / input
    dedup_removed:     int   = 0
    duration_ms:       int   = 0


@dataclass(frozen=True)
class ValidationEvent(BaseEvent):
    event_type:         str   = "validation"
    composite_score:    float = 0.0
    evidence_coverage:  float = 0.0
    grounding_score:    float = 0.0
    source_diversity:   float = 0.0
    temporal_coverage:  float = 0.0
    contradiction_flag: bool  = False
    passed:             bool  = False
    failure_reasons:    str   = ""    # pipe-joined
    duration_ms:        int   = 0


@dataclass(frozen=True)
class ReflectionEvent(BaseEvent):
    event_type:        str   = "reflection"
    retry_number:      int   = 0
    strategy:          str   = ""     # minimal|moderate|aggressive|emergency
    trigger_reason:    str   = ""     # which validation sub-score failed
    score_before:      float = 0.0
    score_after:       float = 0.0
    query_expanded:    bool  = False
    live_search_used:  bool  = False
    duration_ms:       int   = 0
    improved:          bool  = False


@dataclass(frozen=True)
class EscalationEvent(BaseEvent):
    event_type:    str   = "escalation"
    risk_level:    str   = ""
    risk_score:    float = 0.0
    reason:        str   = ""
    workflow:      str   = ""
    auto_resolved: bool  = False     # True if resolved without human


@dataclass(frozen=True)
class ErrorEvent(BaseEvent):
    event_type:  str = "error"
    node:        str = ""
    error_type:  str = ""
    error_msg:   str = ""
    recoverable: bool = True


@dataclass(frozen=True)
class EvaluationEvent(BaseEvent):
    event_type:        str   = "evaluation"
    dataset:           str   = ""
    recall_at_5:       float = 0.0
    recall_at_10:      float = 0.0
    precision_at_5:    float = 0.0
    mrr:               float = 0.0
    ndcg_at_10:        float = 0.0
    grounding_score:   float = 0.0
    hallucination_rate:float = 0.0
    sample_count:      int   = 0


# Union type for type checkers
AnyEvent = (
    WorkflowStartEvent | WorkflowEndEvent |
    NodeStartEvent | NodeEndEvent |
    RetrievalEvent | RerankerEvent | CompressionEvent |
    ValidationEvent | ReflectionEvent |
    EscalationEvent | ErrorEvent | EvaluationEvent
)
