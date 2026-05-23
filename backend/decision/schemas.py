"""
schemas.py — Shared Type System for the Decision & Workflow Layer (Phase 4.5)

All enums, dataclasses, and type aliases used across the decision package
are defined here to avoid circular imports and provide a single source of truth.

Design principles:
  - Enums for all categorical values (not string constants).
  - Frozen dataclasses for immutable config objects.
  - Mutable dataclass only for DecisionPlan (mutated during risk adjustment).
  - Every field has a docstring-level comment explaining its orchestration role.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


# ═════════════════════════════════════════════════════════════════════════════
# Enumerated Types
# ═════════════════════════════════════════════════════════════════════════════

class WorkflowType(str, Enum):
    """
    Recognized orchestration workflow archetypes.
    Each maps to a WorkflowConfig in the registry.
    The string value is used in decision traces and API responses.
    """
    CLINICAL        = "clinical"        # General patient/clinical queries
    RESEARCH        = "research"        # Scientific / literature queries
    EMERGENCY       = "emergency"       # Time-critical / life-threatening
    MEDICATION      = "medication"      # Drug interactions, dosing, safety
    SIMILAR_CASE    = "similar_case"    # Episodic case-matching queries
    LITERATURE      = "literature"      # Systematic review / meta-analysis
    MULTIMODAL      = "multimodal"      # Image/DICOM combined queries
    DIAGNOSIS       = "diagnosis"       # Differential diagnosis support
    TREATMENT       = "treatment"       # Treatment protocol planning
    TEMPORAL        = "temporal"        # Time-sensitive / recent evidence


class RiskLevel(str, Enum):
    """
    Risk classification driving orchestration strictness.
    Higher risk = stricter validation, lower hallucination tolerance,
    more reflection cycles, mandatory escalation review.
    """
    LOW      = "low"       # Informational queries; low clinical impact
    MEDIUM   = "medium"    # Outpatient clinical; moderate impact
    HIGH     = "high"      # Inpatient / procedural; high impact
    CRITICAL = "critical"  # Emergency / life-threatening; zero tolerance


class RetrievalStrategy(str, Enum):
    """
    Named retrieval strategies. Each translates to a specific
    combination of dense, sparse, graph, and internet retrieval calls.
    """
    DENSE_ONLY          = "dense_only"
    SPARSE_ONLY         = "sparse_only"
    HYBRID              = "hybrid"              # Dense + BM25 + RRF
    HYBRID_BROAD        = "hybrid_broad"        # Hybrid + relaxed filters
    HYBRID_STRICT       = "hybrid_strict"       # Hybrid + trust_score >= 0.8
    GUIDELINE_PRIORITY  = "guideline_priority"  # Trusted guidelines first
    CASE_SIMILARITY     = "case_similarity"     # Patient case matching
    INTERNET_AUGMENTED  = "internet_augmented"  # Hybrid + PubMed live
    GRAPH_AUGMENTED     = "graph_augmented"     # Hybrid + Neo4j traversal


class ReflectionStrategy(str, Enum):
    """
    Controls how aggressively the Reflection Agent pursues better evidence.
    """
    MINIMAL     = "minimal"     # 1 retry max; accept partial evidence
    MODERATE    = "moderate"    # 2 retries; standard query expansion
    AGGRESSIVE  = "aggressive"  # 3 retries; HyDE + ontology + live search
    EMERGENCY   = "emergency"   # 1 retry but immediate escalation on fail


class ValidationStrictness(str, Enum):
    """
    Controls the composite validation score threshold and
    which checks are enforced by the Validation Agent.
    """
    RELAXED  = "relaxed"   # 0.55 composite — research/exploratory
    STANDARD = "standard"  # 0.70 composite — general clinical
    STRICT   = "strict"    # 0.82 composite — medication/procedural
    CRITICAL = "critical"  # 0.95 composite — emergency / drug safety


class SourcePriority(str, Enum):
    """
    Named source priority policies controlling trust-score weighting
    and which document types are surfaced first during reranking.
    """
    BROAD_ACADEMIC    = "broad_academic"    # All peer-reviewed, any date
    GUIDELINE_FIRST   = "guideline_first"   # WHO/NIH/NICE guidelines first
    TRIAL_EVIDENCE    = "trial_evidence"    # RCTs and clinical trials first
    LOCAL_RAG         = "local_rag"         # Only local curated corpus
    RECENCY_WEIGHTED  = "recency_weighted"  # Recent publications prioritised
    TRUSTED_ONLY      = "trusted_only"      # trust_score >= 0.85 only


# ═════════════════════════════════════════════════════════════════════════════
# Core Data Objects
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class WorkflowConfig:
    """
    Immutable orchestration template for a workflow archetype.

    Frozen so registry instances are never mutated at runtime.
    Risk engine may produce an adjusted copy via dataclasses.replace().
    """
    workflow_type:          WorkflowType
    retrieval_strategy:     RetrievalStrategy
    validation_strictness:  ValidationStrictness
    reflection_strategy:    ReflectionStrategy
    source_priority:        SourcePriority
    confidence_threshold:   float          # base — adjusted by risk engine
    max_retries:            int            # base — can be overridden
    context_budget_tokens:  int            # token allocation for compressor
    internet_retrieval:     bool           # whether live PubMed is enabled
    case_retrieval:         bool           # whether similar-case is enabled
    graph_retrieval:        bool           # whether Neo4j is enabled
    escalation_threshold:   float          # risk score above which to flag
    emergency_override:     bool           # short-circuit on CRITICAL risk
    description:            str = ""       # human-readable for audit logs


@dataclass
class RiskSignal:
    """A single contributing factor to the risk assessment."""
    name:        str
    weight:      float   # contribution to composite risk score
    triggered:   bool
    description: str = ""


@dataclass
class RiskAssessment:
    """
    Output of the Risk Engine.
    Drives confidence threshold adjustment and reflection aggressiveness.
    """
    level:                  RiskLevel
    score:                  float           # 0.0 – 1.0
    signals:                List[RiskSignal]
    requires_escalation:    bool
    confidence_boost:       float           # added to base threshold
    max_retries_override:   Optional[int]   # None = use workflow default
    contributing_factors:   List[str]       # human-readable for trace


@dataclass
class QueryClassification:
    """
    Multi-label query classification result.
    Supports composite query types (e.g., emergency + medication).
    """
    primary_type:       WorkflowType
    secondary_types:    List[WorkflowType]
    intent_confidence:  float              # 0.0 – 1.0 classifier confidence
    labels:             List[str]          # raw string labels for trace
    classification_method: str             # "signal" | "llm" | "fallback"


@dataclass
class DecisionPlan:
    """
    The complete orchestration plan produced by the Decision Layer.

    This is the central artifact that all downstream nodes consume
    to configure their behaviour. It is stored in AgentState and
    serialised into the API decision_trace.
    """
    # ── Classification ─────────────────────────────────────────────────────
    classification:         QueryClassification

    # ── Risk ───────────────────────────────────────────────────────────────
    risk:                   RiskAssessment

    # ── Selected orchestration ─────────────────────────────────────────────
    workflow:               WorkflowConfig
    retrieval_strategy:     RetrievalStrategy
    confidence_threshold:   float          # final (base + risk boost)
    reflection_strategy:    ReflectionStrategy
    validation_strictness:  ValidationStrictness
    source_priority:        SourcePriority
    max_retries:            int
    context_budget_tokens:  int

    # ── Escalation ─────────────────────────────────────────────────────────
    escalation_required:    bool
    escalation_reason:      str

    # ── Full audit trace ───────────────────────────────────────────────────
    decision_trace:         Dict[str, Any] = field(default_factory=dict)

    def to_trace_dict(self) -> Dict[str, Any]:
        """Serialise to JSON-safe dict for API response and logging."""
        return {
            "query_type":           self.classification.primary_type.value,
            "secondary_types":      [t.value for t in self.classification.secondary_types],
            "intent_confidence":    round(self.classification.intent_confidence, 3),
            "classification_method": self.classification.classification_method,
            "risk_level":           self.risk.level.value,
            "risk_score":           round(self.risk.score, 3),
            "risk_factors":         self.risk.contributing_factors,
            "requires_escalation":  self.escalation_required,
            "escalation_reason":    self.escalation_reason,
            "selected_workflow":    self.workflow.workflow_type.value,
            "retrieval_strategy":   self.retrieval_strategy.value,
            "confidence_threshold": round(self.confidence_threshold, 3),
            "validation_policy":    self.validation_strictness.value,
            "reflection_strategy":  self.reflection_strategy.value,
            "source_priority":      self.source_priority.value,
            "max_retries":          self.max_retries,
            "context_budget_tokens": self.context_budget_tokens,
            "internet_retrieval":   self.workflow.internet_retrieval,
            "case_retrieval":       self.workflow.case_retrieval,
        }



# -- WORKFLOW REGISTRY ---------------------------------------------------------
WORKFLOW_REGISTRY = {
    WorkflowType.CLINICAL: WorkflowConfig(
        workflow_type=WorkflowType.CLINICAL,
        retrieval_strategy=RetrievalStrategy.HYBRID,
        validation_strictness=ValidationStrictness.STANDARD,
        reflection_strategy=ReflectionStrategy.MODERATE,
        source_priority=SourcePriority.GUIDELINE_FIRST,
        confidence_threshold=0.72,
        max_retries=2,
        context_budget_tokens=3500,
        internet_retrieval=True,
        case_retrieval=True,
        graph_retrieval=True,
        escalation_threshold=0.5,
        emergency_override=False,
    ),
    WorkflowType.RESEARCH: WorkflowConfig(
        workflow_type=WorkflowType.RESEARCH,
        retrieval_strategy=RetrievalStrategy.INTERNET_AUGMENTED,
        validation_strictness=ValidationStrictness.RELAXED,
        reflection_strategy=ReflectionStrategy.MODERATE,
        source_priority=SourcePriority.RECENCY_WEIGHTED,
        confidence_threshold=0.6,
        max_retries=2,
        context_budget_tokens=4000,
        internet_retrieval=True,
        case_retrieval=False,
        graph_retrieval=True,
        escalation_threshold=0.7,
        emergency_override=False,
    ),
    WorkflowType.EMERGENCY: WorkflowConfig(
        workflow_type=WorkflowType.EMERGENCY,
        retrieval_strategy=RetrievalStrategy.HYBRID_STRICT,
        validation_strictness=ValidationStrictness.CRITICAL,
        reflection_strategy=ReflectionStrategy.EMERGENCY,
        source_priority=SourcePriority.GUIDELINE_FIRST,
        confidence_threshold=0.85,
        max_retries=1,
        context_budget_tokens=3000,
        internet_retrieval=False,
        case_retrieval=False,
        graph_retrieval=True,
        escalation_threshold=0.1,
        emergency_override=True,
    ),
    WorkflowType.MEDICATION: WorkflowConfig(
        workflow_type=WorkflowType.MEDICATION,
        retrieval_strategy=RetrievalStrategy.HYBRID_STRICT,
        validation_strictness=ValidationStrictness.STRICT,
        reflection_strategy=ReflectionStrategy.AGGRESSIVE,
        source_priority=SourcePriority.GUIDELINE_FIRST,
        confidence_threshold=0.8,
        max_retries=3,
        context_budget_tokens=3500,
        internet_retrieval=False,
        case_retrieval=False,
        graph_retrieval=True,
        escalation_threshold=0.4,
        emergency_override=False,
    ),
    WorkflowType.SIMILAR_CASE: WorkflowConfig(
        workflow_type=WorkflowType.SIMILAR_CASE,
        retrieval_strategy=RetrievalStrategy.CASE_SIMILARITY,
        validation_strictness=ValidationStrictness.STANDARD,
        reflection_strategy=ReflectionStrategy.MODERATE,
        source_priority=SourcePriority.LOCAL_RAG,
        confidence_threshold=0.68,
        max_retries=2,
        context_budget_tokens=3500,
        internet_retrieval=True,
        case_retrieval=True,
        graph_retrieval=True,
        escalation_threshold=0.55,
        emergency_override=False,
    ),
    WorkflowType.LITERATURE: WorkflowConfig(
        workflow_type=WorkflowType.LITERATURE,
        retrieval_strategy=RetrievalStrategy.INTERNET_AUGMENTED,
        validation_strictness=ValidationStrictness.RELAXED,
        reflection_strategy=ReflectionStrategy.AGGRESSIVE,
        source_priority=SourcePriority.RECENCY_WEIGHTED,
        confidence_threshold=0.65,
        max_retries=3,
        context_budget_tokens=4000,
        internet_retrieval=True,
        case_retrieval=False,
        graph_retrieval=True,
        escalation_threshold=0.6,
        emergency_override=False,
    ),
    WorkflowType.MULTIMODAL: WorkflowConfig(
        workflow_type=WorkflowType.MULTIMODAL,
        retrieval_strategy=RetrievalStrategy.HYBRID,
        validation_strictness=ValidationStrictness.STRICT,
        reflection_strategy=ReflectionStrategy.AGGRESSIVE,
        source_priority=SourcePriority.GUIDELINE_FIRST,
        confidence_threshold=0.72,
        max_retries=3,
        context_budget_tokens=4000,
        internet_retrieval=True,
        case_retrieval=True,
        graph_retrieval=True,
        escalation_threshold=0.35,
        emergency_override=True,
    ),
}
