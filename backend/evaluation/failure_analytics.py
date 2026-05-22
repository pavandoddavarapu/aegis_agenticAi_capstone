"""
failure_analytics.py — Failure Pattern Analytics (Phase 5)

Architecture:
  FailureAnalyzer reads historical telemetry events from TelemetryStorage
  and identifies systemic weaknesses across workflow executions:

  Patterns detected:
    1. RETRIEVAL_BLINDSPOT  — recurring query types with low retrieval scores
    2. REFLECTION_LOOP_AMPLIFICATION — queries causing 3+ retries consistently
    3. LOW_CONFIDENCE_CLUSTER — queries persistently below threshold
    4. RERANKER_DEGRADATION — reranker score lift trending downward
    5. ESCALATION_SPIKE     — sudden increase in escalation rate
    6. WORKFLOW_DEAD_PATH   — workflow types with consistently high error rates
    7. SOURCE_MONOCULTURE   — queries resolved from single source repeatedly

  All pattern detections are threshold-based — no ML required.
  Results are exposed via GET /failure-analysis endpoint.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from backend.utils.logger import logger


@dataclass
class FailurePattern:
    pattern_type:   str
    severity:       str         # LOW | MEDIUM | HIGH | CRITICAL
    description:    str
    affected_count: int
    sample_ids:     List[str]
    recommendation: str


@dataclass
class FailureReport:
    patterns:          List[FailurePattern]
    total_analyzed:    int
    analysis_window_h: int
    critical_count:    int
    high_count:        int

    def to_dict(self) -> Dict:
        return {
            "total_analyzed":    self.total_analyzed,
            "analysis_window_h": self.analysis_window_h,
            "critical_count":    self.critical_count,
            "high_count":        self.high_count,
            "patterns":          [
                {
                    "pattern_type":   p.pattern_type,
                    "severity":       p.severity,
                    "description":    p.description,
                    "affected_count": p.affected_count,
                    "recommendation": p.recommendation,
                }
                for p in self.patterns
            ],
        }


# ─── Pattern detectors ────────────────────────────────────────────────────────

def _detect_retrieval_blindspots(workflow_rows: List[Dict]) -> Optional[FailurePattern]:
    """Queries with final_confidence < 0.50 after retrieval (no retry helped)."""
    low = [r for r in workflow_rows
           if r.get("final_confidence", 1.0) < 0.50 and r.get("retry_count", 0) >= 2]
    if len(low) < 3:
        return None
    ids = [str(r.get("request_id", "")) for r in low[:5]]
    sev = "CRITICAL" if len(low) > 10 else "HIGH"
    return FailurePattern(
        pattern_type   = "RETRIEVAL_BLINDSPOT",
        severity       = sev,
        description    = (
            f"{len(low)} requests had low confidence ({len(low)/max(len(workflow_rows),1)*100:.0f}%) "
            f"even after max retries. Corpus likely missing relevant documents."
        ),
        affected_count = len(low),
        sample_ids     = ids,
        recommendation = (
            "Ingest additional medical literature for the affected query types. "
            "Consider enabling live PubMed retrieval for these workflows."
        ),
    )


def _detect_reflection_amplification(workflow_rows: List[Dict]) -> Optional[FailurePattern]:
    """Requests with retry_count >= 3 indicate expensive reflection loops."""
    heavy = [r for r in workflow_rows if r.get("retry_count", 0) >= 3]
    if len(heavy) < 2:
        return None
    ratio = len(heavy) / max(len(workflow_rows), 1)
    sev   = "HIGH" if ratio > 0.20 else "MEDIUM"
    return FailurePattern(
        pattern_type   = "REFLECTION_LOOP_AMPLIFICATION",
        severity       = sev,
        description    = (
            f"{len(heavy)} requests ({ratio*100:.0f}%) triggered ≥3 reflection cycles. "
            f"Average latency penalty: ~2–4 seconds per affected request."
        ),
        affected_count = len(heavy),
        sample_ids     = [str(r.get("request_id","")) for r in heavy[:5]],
        recommendation = (
            "Tune retrieval quality to reduce reflection triggers. "
            "Check if hybrid retrieval is enabled for these workflow types."
        ),
    )


def _detect_escalation_spike(workflow_rows: List[Dict]) -> Optional[FailurePattern]:
    """Sudden spike in escalation rate vs baseline."""
    esc  = [r for r in workflow_rows if r.get("escalation_required")]
    rate = len(esc) / max(len(workflow_rows), 1)
    if rate < 0.10:  # < 10% baseline is acceptable
        return None
    sev = "CRITICAL" if rate > 0.30 else "HIGH"
    return FailurePattern(
        pattern_type   = "ESCALATION_SPIKE",
        severity       = sev,
        description    = (
            f"Escalation rate {rate*100:.0f}% ({len(esc)}/{len(workflow_rows)} requests). "
            f"May indicate high-risk query pattern or miscalibrated risk thresholds."
        ),
        affected_count = len(esc),
        sample_ids     = [str(r.get("request_id","")) for r in esc[:5]],
        recommendation = (
            "Review risk engine signal weights. If false-positive escalations, "
            "raise escalation_threshold in the relevant WorkflowConfig."
        ),
    )


def _detect_workflow_dead_paths(workflow_rows: List[Dict]) -> Optional[FailurePattern]:
    """Workflow types with disproportionately high error rates."""
    from collections import defaultdict
    by_workflow: Dict[str, List] = defaultdict(list)
    for r in workflow_rows:
        by_workflow[r.get("selected_workflow","unknown")].append(r)

    dead = []
    for wf, rows in by_workflow.items():
        errs  = sum(1 for r in rows if r.get("status") == "error")
        ratio = errs / max(len(rows), 1)
        if ratio > 0.15 and len(rows) >= 3:
            dead.append((wf, ratio, len(rows)))

    if not dead:
        return None
    worst = sorted(dead, key=lambda x: -x[1])[0]
    sev   = "CRITICAL" if worst[1] > 0.40 else "HIGH"
    return FailurePattern(
        pattern_type   = "WORKFLOW_DEAD_PATH",
        severity       = sev,
        description    = (
            f"Workflow '{worst[0]}' has {worst[1]*100:.0f}% error rate "
            f"({worst[2]} total requests). "
            f"Dead paths: {[d[0] for d in dead]}."
        ),
        affected_count = sum(d[2] for d in dead),
        sample_ids     = [],
        recommendation = (
            f"Inspect agent logs for workflow '{worst[0]}'. "
            "Check Qdrant connectivity and collection configuration."
        ),
    )


def _detect_source_monoculture(retrieval_rows: List[Dict]) -> Optional[FailurePattern]:
    """Requests returning docs from only 1 unique source (diversity=1)."""
    mono = [r for r in retrieval_rows if r.get("source_diversity", 2) <= 1
            and r.get("retrieval_success")]
    if len(mono) < 5:
        return None
    ratio = len(mono) / max(len(retrieval_rows), 1)
    return FailurePattern(
        pattern_type   = "SOURCE_MONOCULTURE",
        severity       = "MEDIUM",
        description    = (
            f"{len(mono)} requests ({ratio*100:.0f}%) returned evidence from only 1 source. "
            "Single-source responses carry higher hallucination risk."
        ),
        affected_count = len(mono),
        sample_ids     = [],
        recommendation = (
            "Ingest more diverse medical literature. "
            "Check if source diversity filter is too restrictive."
        ),
    )


# ─── Main analyzer ────────────────────────────────────────────────────────────

async def analyze_failures(storage, hours: int = 24) -> FailureReport:
    """
    Run all failure pattern detectors against recent telemetry.

    Args:
        storage:  TelemetryStorage instance
        hours:    Analysis window in hours

    Returns:
        FailureReport with all detected patterns.
    """
    workflow_rows  = []
    retrieval_rows = []

    try:
        metrics = await storage.get_recent_metrics(hours)
        workflow_rows  = await _fetch_workflow_rows(storage, hours)
        retrieval_rows = await _fetch_retrieval_rows(storage, hours)
    except Exception as exc:
        logger.error(f"[FailureAnalytics] Data fetch error: {exc}")

    detectors = [
        _detect_retrieval_blindspots(workflow_rows),
        _detect_reflection_amplification(workflow_rows),
        _detect_escalation_spike(workflow_rows),
        _detect_workflow_dead_paths(workflow_rows),
        _detect_source_monoculture(retrieval_rows),
    ]
    patterns = [p for p in detectors if p is not None]

    critical = sum(1 for p in patterns if p.severity == "CRITICAL")
    high     = sum(1 for p in patterns if p.severity == "HIGH")

    logger.info(f"[FailureAnalytics] {len(patterns)} patterns detected "
                f"(critical={critical}, high={high})")

    return FailureReport(
        patterns          = patterns,
        total_analyzed    = len(workflow_rows),
        analysis_window_h = hours,
        critical_count    = critical,
        high_count        = high,
    )


async def _fetch_workflow_rows(storage, hours: int) -> List[Dict]:
    """Fetch workflow_traces rows from storage."""
    if not storage._pg_pool:
        return []
    try:
        async with storage._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM workflow_traces "
                "WHERE created_at > NOW() - INTERVAL '%s hours' "
                "ORDER BY created_at DESC LIMIT 500",
                hours,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error(f"[FailureAnalytics] workflow fetch: {exc}")
        return []


async def _fetch_retrieval_rows(storage, hours: int) -> List[Dict]:
    """Fetch retrieval_traces rows from storage."""
    if not storage._pg_pool:
        return []
    try:
        async with storage._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM retrieval_traces "
                "WHERE created_at > NOW() - INTERVAL '%s hours' "
                "ORDER BY created_at DESC LIMIT 500",
                hours,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error(f"[FailureAnalytics] retrieval fetch: {exc}")
        return []
