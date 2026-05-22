"""backend/evaluation — Phase 5 + Phase 12 Evaluation Package"""
from backend.evaluation.metrics         import (
    recall_at_k, precision_at_k, mean_reciprocal_rank, ndcg_at_k,
    reranker_lift, grounding_score, unsupported_claim_rate,
    evidence_coverage, contradiction_rate, compute_evaluation_summary,
    reflection_success_rate, escalation_precision, workflow_success_rate,
)
from backend.evaluation.grounding_engine import compute_grounding, GroundingReport
from backend.evaluation.failure_analytics import analyze_failures, FailureReport

# Phase 12: Evidence quality + contradiction evaluation
from backend.evaluation.evidence_evaluator import (
    evaluate_evidence, EvidenceScore, EvidenceQualitySummary,
    evidence_scores_to_dict_list,
)
from backend.evaluation.contradiction_analyzer import (
    analyze_contradictions, ContradictionReport, ContradictionPair,
)

__all__ = [
    # Phase 5
    "recall_at_k","precision_at_k","mean_reciprocal_rank","ndcg_at_k",
    "reranker_lift","grounding_score","unsupported_claim_rate",
    "evidence_coverage","contradiction_rate","compute_evaluation_summary",
    "reflection_success_rate","escalation_precision","workflow_success_rate",
    "compute_grounding","GroundingReport",
    "analyze_failures","FailureReport",
    # Phase 12
    "evaluate_evidence","EvidenceScore","EvidenceQualitySummary",
    "evidence_scores_to_dict_list",
    "analyze_contradictions","ContradictionReport","ContradictionPair",
]
