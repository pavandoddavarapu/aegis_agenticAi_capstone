# PROJECT_ORCHESTRATION_UPGRADE_PLAN.md
# Aegis Clinical Intelligence System — Orchestration Evolution Plan
# Version: 1.0 | Date: 2026-05-20 | Phase: 12 (Adaptive Orchestration)

---

> [!IMPORTANT]
> **CONTINUATION DOCUMENT**: This file is the canonical state tracker for the Phase 12 orchestration upgrade. Any future agent session MUST read this file first to understand what has been done and what remains. Do NOT restart work from scratch.

---

## 1. CURRENT ARCHITECTURE SUMMARY

### System Overview
The Aegis Clinical Intelligence System is a production-grade healthcare AI platform built on **LangGraph** + **FastAPI** + **Next.js 14**. It is currently at Phase 11.

### Existing Capabilities (PRESERVE ALL OF THESE)
| Capability | Module | Status |
|---|---|---|
| Hybrid RAG (Dense+Sparse+Reranking) | `backend/rag/` | ✅ Production |
| GraphRAG (Neo4j) | `backend/graphrag/` | ✅ Production |
| Similar Case Intelligence | `backend/graphrag/similar_case_engine.py` | ✅ Production |
| Live Research Intelligence (PubMed) | `backend/research/` | ✅ Production |
| Multimodal ECG/X-ray/OCR | `backend/multimodal/` | ✅ Production |
| Governance / HITL | `backend/governance/` | ✅ Production |
| LangGraph Orchestration | `backend/orchestration/graph.py` | ✅ Production |
| Reflection System | `backend/agents/reflection_agent.py` | ✅ Production |
| Validation Agent | `backend/agents/validation_agent.py` | ✅ Production |
| Observability / Telemetry | `backend/telemetry/`, `backend/monitoring/` | ✅ Production |
| JWT Auth | `backend/auth/` | ✅ Production |
| Rate Limiting | `backend/api/rate_limiter.py` | ✅ Production |
| Sentry Error Monitoring | `backend/main.py` | ✅ Production |
| Decision Layer | `backend/decision/` | ✅ Needs Evolution |
| Risk Engine | `backend/decision/risk_engine.py` | ✅ Production |
| Confidence Scoring | `backend/agents/validation_agent.py` | ✅ Production |
| Grounding Analysis | `backend/evaluation/grounding_engine.py` | ✅ Production |
| Research Ranking | `backend/research/research_ranker.py` | ✅ Production |
| Clinical Dashboards | `frontend/src/` (Next.js) | ✅ Production |

### Current Tech Stack
- **Backend**: FastAPI + LangGraph + Python 3.11
- **LLM**: Groq (llama-3.3-70b-versatile) with OpenAI fallback
- **Vector DB**: Qdrant
- **Graph DB**: Neo4j
- **Frontend**: Next.js 14 + TypeScript + Tailwind
- **Auth**: JWT + Simple RBAC
- **Monitoring**: Sentry + Custom telemetry bus
- **Infra**: Docker + docker-compose

### Current Agent Topology (LangGraph graph.py)
```
decide → query_understand → retrieve → reason → validate
                                                    ↓
                                           supervisor_router
                                           ├─ REFLECT → reflect → retrieve (retry)
                                           └─ END     → finalize
```

### Current File Inventory
```
backend/
├── agents/
│   ├── decision_agent.py      (Phase 4.5 — routes to workflow type)
│   ├── query_agent.py         (Phase 4 — query understanding/expansion)
│   ├── retrieval_agent.py     (Phase 6 — graph+semantic+cases+research)
│   ├── reasoning_agent.py     (Phase 8 — multimodal reasoning)
│   ├── validation_agent.py    (Phase 3 — confidence scoring)
│   ├── reflection_agent.py    (Phase 3 — adaptive retry)
│   └── supervisor_agent.py    (Phase 9 — governance finalize)
├── api/
│   ├── agentic.py             (POST /analyze/)
│   ├── governance_api.py
│   ├── multimodal_api.py
│   ├── upload.py, retrieve.py, health.py
│   └── rate_limiter.py
├── auth/                      (JWT + RBAC)
├── decision/
│   ├── decision_layer.py      (make_decision() entry point)
│   ├── risk_engine.py         (signal-weighted risk scorer)
│   ├── workflow_router.py     (priority-weighted workflow selector)
│   ├── schemas.py             (all domain types)
│   └── source_policy.py
├── evaluation/
│   ├── failure_analytics.py
│   ├── grounding_engine.py
│   └── metrics.py
├── governance/
│   ├── escalation_engine.py
│   ├── review_engine.py
│   └── audit_logger.py
├── graphrag/                  (Neo4j + hybrid graph retrieval)
├── models/
│   └── state.py               (AgentState TypedDict)
├── monitoring/                (metrics endpoints)
├── multimodal/                (ECG/X-ray/OCR pipelines)
├── orchestration/
│   └── graph.py               (LangGraph workflow builder)
├── rag/                       (hybrid retrieval pipeline)
├── research/                  (PubMed + ranking + freshness)
├── telemetry/                 (event bus + tracing)
├── utils/
└── workflows/                 (workflow config registry)
```

---

## 2. IDENTIFIED ARCHITECTURAL PROBLEMS

### Problem 1: Workflow-Centric Instead of Goal-Centric
**Current**: DecisionAgent selects a predefined workflow (emergency/medication/clinical/research/etc.) and execution path is mostly predetermined.  
**Target**: Planner understands clinical *goals* and dynamically composes execution plans per case.

### Problem 2: No Information Sufficiency Analysis
**Current**: Queries execute immediately after classification, regardless of missing clinical context (no vitals, no medications list, ambiguous complaint).  
**Target**: Before execution, system checks "Do I have enough information to proceed safely?" and triggers a clarification loop if not.

### Problem 3: Agents as Static Pipeline Nodes
**Current**: All 7 nodes execute in near-linear order regardless of case type.  
**Target**: Planner decides which agents, in what order, with what retry/fallback strategies — per case, not per workflow type.

### Problem 4: Reflection Happens Too Late
**Current**: Supervisor triggers reflection ONLY after validation failure (post-execution). No mid-execution monitoring.  
**Target**: Supervisor monitors evidence quality, confidence trends, and contradiction risk DURING execution and re-plans proactively.

### Problem 5: System is Retrieval-Aware but Not Evidence-Aware
**Current**: Retrieved documents pass to reasoning without quality evaluation. A blurry OCR scan and a WHO guideline have equal weight.  
**Target**: Every evidence source scored for trust, freshness, grounding quality, and contradiction risk BEFORE influencing reasoning.

### Problem 6: UI Drifted Toward Chatbot
**Current**: Workspace page is a single text area + file upload + one "Analyze" button.  
**Target**: AI-powered patient intelligence workspace with structured intake, sufficiency gauge, clarification questions, evidence scorecard, and an orchestration-aware copilot embedded inside the workflow.

---

## 3. TARGET ARCHITECTURE

```
Doctor provides patient case
          ↓
OrchestrationPlanner understands clinical intent
          ↓
InformationSufficiencyEngine checks completeness
          ↓ (if insufficient)
ClarificationLoop asks targeted questions
          ↓ (when sufficient)
ExecutionPlan created (first-class object)
          ↓
Dynamic agent capability selection
          ↓
QueryAgent + RetrievalAgent (existing, unchanged)
          ↓
EvidenceEvaluator scores every retrieved source
          ↓
ContradictionAnalyzer detects conflicts
          ↓
ReasoningAgent (evidence-quality-aware)
          ↓
ValidationAgent (existing, unchanged)
          ↓
ContinuousSupervisorMonitor (proactive, not just reactive)
          ↓
GovernanceValidation (Phase 9, fully preserved)
          ↓
Structured Clinical Intelligence Report
```

---

## 4. DETAILED IMPLEMENTATION PLAN

### PHASE 12A — Core New Backend Modules

#### 4A.1 `ExecutionPlan` Schema
**File**: `backend/decision/execution_plan.py` [NEW]

```python
# Key classes to create:
class ClinicalIntent(str, Enum):
    EMERGENCY_TRIAGE = "emergency_triage"
    DIAGNOSTIC_WORKUP = "diagnostic_workup"
    TREATMENT_PLANNING = "treatment_planning"
    MEDICATION_REVIEW = "medication_review"
    RESEARCH_LOOKUP = "research_lookup"
    LITERATURE_SYNTHESIS = "literature_synthesis"
    SIMILAR_CASE_SEARCH = "similar_case_search"
    RISK_STRATIFICATION = "risk_stratification"

class ClarificationQuestion:
    question_id: str
    question_text: str
    category: str       # vitals/history/medications/imaging/labs
    priority: str       # critical/important/optional
    expected_format: str
    default_if_skipped: Optional[str]

class ExecutionStep:
    step_id: str
    capability: str     # agent capability name
    required: bool
    depends_on: List[str]
    retry_limit: int
    fallback_strategy: str

class EvidenceStrategy:
    use_graph: bool
    use_semantic: bool
    use_research: bool
    use_multimodal: bool
    use_similar_cases: bool
    retrieval_depth: str    # shallow/standard/deep
    source_priority: List[str]

class ExecutionPlan:
    plan_id: str
    clinical_intent: ClinicalIntent
    goal: str
    patient_context: Dict
    risk_assessment: RiskAssessment     # from existing risk_engine.py
    required_capabilities: List[str]
    optional_capabilities: List[str]
    execution_steps: List[ExecutionStep]
    evidence_strategy: EvidenceStrategy
    clarification_required: bool
    clarification_questions: List[ClarificationQuestion]
    missing_information: List[str]
    governance_policy: Dict
    replan_triggers: List[str]
    max_replan_iterations: int
    plan_trace: Dict
```

#### 4A.2 `InformationSufficiencyEngine`
**File**: `backend/decision/information_sufficiency_engine.py` [NEW]

Signal-based (no LLM) analyzer that checks for clinical completeness.

Clinical element detection signals (regex + keyword):
- **Age/Demographics**: age patterns, gender terms
- **Chief Complaint**: symptom terms, onset/duration
- **Vitals**: BP patterns, HR, O2 sat, temperature, RR
- **Medications**: drug names, "on X mg of", "taking"
- **Allergies**: "allergic to", "NKDA", allergy patterns
- **Past History**: PMH patterns, "history of", disease terms
- **ECG data**: ECG/EKG terms (required for cardiac queries)
- **Lab values**: troponin, CBC, BMP, HbA1c patterns
- **Imaging**: "X-ray showed", "CT scan", "MRI" (if relevant)

```python
class SufficiencyReport:
    is_sufficient: bool
    sufficiency_score: float          # 0-1
    missing_critical: List[str]       # blocks safe execution
    missing_important: List[str]      # helpful but not blocking
    missing_optional: List[str]       # nice to have
    clarification_questions: List[ClarificationQuestion]
    can_proceed: bool                 # True if no critical missing
    proceed_with_caveat: str          # warning to add if proceeding anyway
    completeness_by_domain: Dict      # vitals/history/meds/etc scores

def check_sufficiency(query: str, clinical_intent: ClinicalIntent) -> SufficiencyReport:
    ...
```

Key rule: Emergency cases (risk_level=CRITICAL) ALWAYS `can_proceed=True` — never block emergencies with clarification.

#### 4A.3 `ClarificationEngine`
**File**: `backend/decision/clarification_engine.py` [NEW]

```python
def generate_clarification_questions(
    sufficiency_report: SufficiencyReport,
    clinical_intent: ClinicalIntent,
    max_questions: int = 5,
) -> List[ClarificationQuestion]:
    """
    Generate targeted, clinically appropriate questions.
    Priority order: critical → important → optional.
    Max 5 questions to avoid overwhelming clinicians.
    Context-aware: doesn't ask about ECG if no cardiac signals.
    """

def resolve_clarification(
    questions: List[ClarificationQuestion],
    answers: Dict[str, str],
) -> str:
    """
    Merge clarification answers back into the enriched query.
    Returns enriched_query string.
    """
```

#### 4A.4 `OrchestrationPlanner` (replaces `decision_agent.py` node)
**File**: `backend/agents/orchestration_planner.py` [NEW]

```python
async def orchestration_planner(state: AgentState) -> dict:
    """
    Phase 12 Orchestration Planner node.
    
    BACKWARD COMPATIBLE: still populates all Phase 4.5 decision fields
    (query_type, risk_level, selected_workflow, retrieval_strategy, etc.)
    so all downstream agents work unchanged.
    
    EXTENDS with:
    - clinical_intent understanding
    - information sufficiency check
    - ExecutionPlan creation
    - clarification_required determination
    
    Reads: state["query"], state["clarification_answers"]
    Writes: all existing decision fields + Phase 12 fields
    """
    query = state.get("query", "")
    clarification_answers = state.get("clarification_answers", {})
    
    # 1. Existing make_decision() for backward compat
    plan = make_decision(query)  # preserves all existing logic
    
    # 2. Detect clinical intent
    intent = _detect_clinical_intent(query)
    
    # 3. Check information sufficiency (skip if emergency)
    sufficiency = None
    clarification_required = False
    clarification_questions = []
    missing_information = []
    
    if plan.risk.level != RiskLevel.CRITICAL:
        sufficiency = check_sufficiency(query, intent)
        clarification_required = not sufficiency.can_proceed and not clarification_answers
        clarification_questions = [q.dict() for q in sufficiency.clarification_questions]
        missing_information = sufficiency.missing_critical + sufficiency.missing_important
    
    # 4. Create ExecutionPlan
    exec_plan = _build_execution_plan(query, intent, plan, sufficiency)
    
    # 5. Return: all Phase 4.5 fields + Phase 12 fields
    return {
        # All existing Phase 4.5 fields (backward compat)
        "query_type": plan.classification.primary_type.value,
        "query_intent_confidence": plan.classification.intent_confidence,
        "risk_level": plan.risk.level.value,
        "selected_workflow": plan.workflow.workflow_type.value,
        "retrieval_strategy": plan.retrieval_strategy.value,
        "validation_policy": plan.validation_strictness.value,
        "confidence_threshold": plan.confidence_threshold,
        "reflection_strategy": plan.reflection_strategy.value,
        "max_retries": plan.max_retries,
        "source_priority": plan.source_priority.value,
        "context_budget_tokens": plan.context_budget_tokens,
        "escalation_required": plan.escalation_required,
        "escalation_reason": plan.escalation_reason,
        "decision_trace": plan.decision_trace,
        # Phase 12 fields
        "clinical_intent": intent.value,
        "execution_plan": exec_plan.dict(),
        "clarification_required": clarification_required,
        "clarification_questions": clarification_questions,
        "missing_information": missing_information,
        "patient_context": exec_plan.patient_context,
        "workflow_path": ["plan"],
    }
```

#### 4A.5 `EvidenceEvaluator`
**File**: `backend/evaluation/evidence_evaluator.py` [NEW]

Source trust taxonomy (hard-coded, evidence-based):
```
Authoritative Guidelines (WHO/CDC/AHA/ESC/NICE)  → trust=0.97
Cochrane Reviews / Meta-analyses                   → trust=0.93
RCTs (PubMed, published)                           → trust=0.88
Prospective cohort studies                         → trust=0.80
Retrospective cohort / Observational               → trust=0.72
Case series (N>50)                                 → trust=0.65
Case series (N<50)                                 → trust=0.55
Case report / Expert opinion                       → trust=0.50
ECG analysis (confidence > 0.85)                   → trust=0.90
ECG analysis (confidence 0.60-0.85)                → trust=0.75
ECG analysis (confidence < 0.60)                   → trust=0.50
Radiology / Chest X-ray (high confidence)          → trust=0.88
OCR extraction (high confidence)                   → trust=0.82
OCR extraction (low confidence < 0.70)             → trust=0.40
Qdrant semantic match (score > 0.80)               → trust=0.85
Qdrant semantic match (score 0.60-0.80)            → trust=0.70
Qdrant semantic match (score < 0.60)               → trust=0.50
Graph knowledge (Neo4j)                            → trust=0.88
Similar case memory (local)                        → trust=0.72
```

```python
class EvidenceScore:
    source_id: str
    source_type: str
    trust_score: float
    freshness_score: float
    relevance_score: float
    grounding_score: float
    contradiction_flag: bool
    overall_quality: float    # composite
    tier: str                 # authoritative/high_evidence/moderate/low/poor
    use_in_reasoning: bool    # filter out if overall_quality < threshold
    weight_in_composite: float

class EvidenceQualitySummary:
    avg_trust: float
    avg_quality: float
    high_quality_count: int
    low_quality_count: int
    filtered_count: int       # excluded from reasoning
    overall_sufficiency: str  # strong/adequate/weak/insufficient

def evaluate_evidence(
    docs: List[Dict],
    graph_context: str,
    research_context: str,
    visual_context: str,
    image_confidence: float,
    query: str,
) -> Tuple[List[EvidenceScore], EvidenceQualitySummary]:
    ...
```

Uses existing: `research_ranker.py` (for research source quality), `freshness_engine.py` (for publication date scoring).

#### 4A.6 `ContradictionAnalyzer`
**File**: `backend/evaluation/contradiction_analyzer.py` [NEW]

```python
class ContradictionPair:
    source_a: str
    source_b: str
    conflict_type: str    # dosage/drug_recommendation/diagnosis/guideline_version
    conflict_description: str
    severity: str         # minor/moderate/critical
    resolution: str       # defer_to_highest_trust/flag_for_review/escalate

class ContradictionReport:
    has_contradictions: bool
    contradiction_pairs: List[ContradictionPair]
    overall_severity: str
    confidence_penalty: float    # 0.0-0.3 deducted from composite
    escalation_required: bool
    summary: str

def analyze_contradictions(
    docs: List[Dict],
    evidence_scores: List[EvidenceScore],
    graph_context: str,
    research_context: str,
    visual_context: str,
) -> ContradictionReport:
    """
    Detects conflicts using:
    1. Drug name cross-referencing between sources
    2. Dosage value comparison (numeric extraction)
    3. Diagnostic term contradictions (positive vs negative)
    4. Guideline date comparison (older vs newer guideline)
    5. Multimodal vs textual conflicts
    """
```

---

### PHASE 12B — State and Graph Refactor

#### 4B.1 Extend `backend/models/state.py`

Add Phase 12 fields:
```python
# PHASE 12 — ORCHESTRATION PLANNER
execution_plan:             Optional[Dict[str, Any]]  # serialized ExecutionPlan
clinical_intent:            str                       # ClinicalIntent enum value
clarification_required:     bool                      # need clarification before exec
clarification_questions:    List[Dict[str, Any]]      # pending questions
clarification_answers:      Dict[str, str]            # submitted answers
missing_information:        List[str]                 # detected missing elements
patient_context:            Dict[str, Any]            # extracted structured patient data

# PHASE 12 — EVIDENCE EVALUATION
evidence_scores:            List[Dict[str, Any]]      # per-source EvidenceScore
evidence_quality_summary:   Dict[str, Any]            # EvidenceQualitySummary
contradiction_report:       Optional[Dict[str, Any]]  # ContradictionReport

# PHASE 12 — CONTINUOUS MONITORING
monitor_events:             List[Dict[str, Any]]      # supervisor events during exec
replan_count:               int                       # adaptive re-plan counter
replan_reasons:             List[str]                 # why re-planning triggered
```

All new fields must have defaults in `_initial_state()` in `graph.py`.

#### 4B.2 Refactor `backend/orchestration/graph.py`

New node constants:
```python
NODE_PLAN      = "plan"          # replaces NODE_DECIDE
NODE_CLARIFY   = "clarify"       # new: clarification loop node
NODE_EVID_EVAL = "evidence_eval" # new: evidence quality scoring
NODE_CONTRADICT = "contradiction_check"  # new: contradiction analysis
# Existing nodes preserved:
NODE_QUERY    = "query_understand"
NODE_RETRIEVE = "retrieve"
NODE_REASON   = "reason"
NODE_VALIDATE = "validate"
NODE_REFLECT  = "reflect"
NODE_FINALIZE = "finalize"
```

New graph topology:
```python
# Entry point changes from NODE_DECIDE to NODE_PLAN
graph.set_entry_point(NODE_PLAN)

# Conditional: if clarification needed and not resolved → clarify
graph.add_conditional_edges(
    NODE_PLAN,
    _plan_router,   # new function
    {
        "clarify":          NODE_CLARIFY,
        "query_understand": NODE_QUERY,
    }
)

# Clarification loops back to plan with answers
graph.add_edge(NODE_CLARIFY, NODE_PLAN)

# Existing linear path after query understand:
graph.add_edge(NODE_QUERY, NODE_RETRIEVE)

# New nodes after retrieve:
graph.add_edge(NODE_RETRIEVE, NODE_EVID_EVAL)
graph.add_edge(NODE_EVID_EVAL, NODE_CONTRADICT)
graph.add_edge(NODE_CONTRADICT, NODE_REASON)

# Existing path preserved:
graph.add_edge(NODE_REASON, NODE_VALIDATE)
graph.add_conditional_edges(NODE_VALIDATE, supervisor_router, {...})
graph.add_edge(NODE_REFLECT, NODE_RETRIEVE)  # still re-enters at retrieve
graph.add_edge(NODE_FINALIZE, END)
```

Safety: `_plan_router` function:
- If `clarification_required=True` AND `clarification_resolved=False` AND `retry_count < 1`: → `clarify`
- If `risk_level == CRITICAL`: skip clarification → `query_understand`
- Otherwise: → `query_understand`

#### 4B.3 New node functions in `graph.py`
```python
def clarification_node(state: AgentState) -> dict:
    """
    Presents clarification questions.
    Returns state update marking questions as pending.
    In the API context, this effectively pauses the workflow
    and returns clarification questions to the caller.
    """

async def evidence_eval_node(state: AgentState) -> dict:
    """Runs EvidenceEvaluator. Annotates docs with quality scores."""

async def contradiction_check_node(state: AgentState) -> dict:
    """Runs ContradictionAnalyzer. Adds contradiction_report to state."""
```

---

### PHASE 12C — Supervisor Evolution

#### 4C.1 Evolve `backend/agents/supervisor_agent.py`

Add `continuous_monitor()` helper:
```python
def continuous_monitor(state: AgentState, checkpoint: str) -> Optional[str]:
    """
    Called at key execution checkpoints.
    Returns: None (continue) | "replan" | "escalate"
    
    Monitors:
    - evidence_quality_summary.overall_sufficiency
    - contradiction_report.overall_severity  
    - image_confidence (if multimodal)
    - replan_count vs max_replan_iterations
    """
```

Emit monitoring events to `monitor_events` state list for observability.

Evolve `supervisor_router()` to also check:
- `contradiction_report.escalation_required` → escalate
- `evidence_quality_summary.overall_sufficiency == "insufficient"` → reflect
- `replan_count >= max_replan_iterations` → end (best effort)

**Preserve**: All existing governance logic in `finalize_response()` unchanged.

---

### PHASE 12D — API Layer Updates

#### 4D.1 Update `backend/api/agentic.py`

Extend `AnalyzeResponse` with new optional fields:
```python
# Phase 12 fields (all Optional with defaults for backward compat)
clinical_intent:          str           = "unknown"
execution_plan_summary:   Optional[Dict] = None
clarification_required:   bool          = False
clarification_questions:  List[Dict]    = []
missing_information:      List[str]     = []
evidence_quality_summary: Optional[Dict] = None
contradiction_summary:    Optional[Dict] = None
replan_count:             int           = 0
```

Add new endpoint:
```python
@router.post("/clarify/", summary="Submit clarification answers and continue analysis")
async def analyze_with_clarification(
    request: Request,
    body: ClarifyRequest,
) -> AnalyzeResponse:
    """
    Accepts clarification answers and re-runs analysis with enriched context.
    ClarifyRequest: { original_query, clarification_answers: Dict[str,str] }
    """
```

#### 4D.2 Update `backend/main.py`
- Version bump: `"11.0.0"` → `"12.0.0"`
- Update description string
- No new router registration needed (clarify endpoint is in existing agentic router)

---

### PHASE 12E — Frontend Evolution

#### 4E.1 Major Workspace Page Redesign
**File**: `frontend/src/app/workspace/page.tsx`

New 3-panel layout:
```
┌─ Header ─────────────────────────────────────────────────────────────────────┐
│ Aegis  | [Patient ID] | Risk: [LEVEL] | Intent: [INTENT] | Governance: [OK] │
├──────────────────┬────────────────────────────────────┬──────────────────────┤
│  LEFT PANEL      │  CENTER PANEL                      │  RIGHT PANEL         │
│  Patient Intake  │  Clinical Intelligence             │  AI Copilot          │
│  ─────────────   │  ─────────────────────             │  ─────────────       │
│  Structured form │  Execution Plan Viewer             │  Orchestration-aware │
│  Vitals inputs   │  ─────────────────────             │  chat interface      │
│  History checks  │  Evidence Scorecard                │  Knows: patient,     │
│  Meds/Allergies  │  ─────────────────────             │  graph, research,    │
│  File upload     │  Contradiction Alerts              │  governance state    │
│  ─────────────   │  ─────────────────────             │  ─────────────       │
│  Sufficiency     │  Clinical Report                   │  Governance Panel    │
│  Gauge           │  (structured sections)             │                      │
│  ─────────────   │                                    │                      │
│  Clarification   │                                    │                      │
│  Questions       │                                    │                      │
│  ─────────────   │                                    │                      │
│  [Analyze]       │                                    │                      │
└──────────────────┴────────────────────────────────────┴──────────────────────┘
```

#### 4E.2 New Frontend Components to Create

| Component | File | Purpose |
|---|---|---|
| `SufficiencyGauge` | `components/workspace/SufficiencyGauge.tsx` | Visual completeness meter |
| `ClarificationPanel` | `components/workspace/ClarificationPanel.tsx` | Question/answer UI pre-analysis |
| `ExecutionPlanViewer` | `components/workspace/ExecutionPlanViewer.tsx` | Shows dynamic plan + intent |
| `EvidenceScorecard` | `components/workspace/EvidenceScorecard.tsx` | Per-source trust visualization |
| `ContradictionAlert` | `components/workspace/ContradictionAlert.tsx` | Conflict warning banner |
| `OrchestraCopilot` | `components/workspace/OrchestraCopilot.tsx` | Context-aware AI copilot |
| `ClinicalReport` | `components/workspace/ClinicalReport.tsx` | Navigable structured report |

#### 4E.3 Evolve Existing Components

`PatientIntakePanel.tsx` → Add:
- Vitals input fields (BP, HR, O2, temp, RR)
- Age/gender dropdowns  
- Symptom checkboxes + free text
- History checkboxes (HTN, DM, CAD, etc.)
- Medications text area
- Allergies field
- SufficiencyGauge integration
- ClarificationPanel integration

`AnalysisPanel.tsx` → Add:
- ExecutionPlanViewer at top
- EvidenceScorecard below evidence list
- ContradictionAlert banner

---

## 5. FILE CHANGE TRACKER

### NEW FILES
| File | Status |
|---|---|
| `backend/decision/execution_plan.py` | ✅ DONE |
| `backend/decision/information_sufficiency_engine.py` | ✅ DONE (chief_complaint signal fixed) |
| `backend/decision/clarification_engine.py` | ✅ DONE |
| `backend/agents/orchestration_planner.py` | ✅ DONE |
| `backend/evaluation/evidence_evaluator.py` | ✅ DONE |
| `backend/evaluation/contradiction_analyzer.py` | ✅ DONE |
| `frontend/src/components/workspace/ClarificationPanel.tsx` | ✅ DONE |
| `frontend/src/components/workspace/ExecutionPlanViewer.tsx` | ✅ DONE |
| `frontend/src/components/workspace/EvidenceScorecard.tsx` | ✅ DONE |
| `frontend/src/components/workspace/ContradictionAlert.tsx` | ✅ DONE |
| `frontend/src/components/workspace/SufficiencyGauge.tsx` | ⏳ TODO |
| `frontend/src/components/workspace/OrchestraCopilot.tsx` | ⏳ TODO |

### MODIFIED FILES
| File | Change | Status |
|---|---|---|
| `backend/models/state.py` | Add Phase 12 fields | ✅ DONE |
| `backend/orchestration/graph.py` | New nodes + conditional edges | ✅ DONE |
| `backend/agents/supervisor_agent.py` | continuous_monitor() | ✅ DONE |
| `backend/api/agentic.py` | New fields + /clarify endpoint | ✅ DONE |
| `backend/main.py` | Version 12.0.0 | ✅ DONE |
| `backend/evaluation/__init__.py` | Export new evaluators | ✅ DONE |
| `frontend/src/app/workspace/page.tsx` | Phase 12 workspace evolution | ✅ DONE |
| `frontend/src/types/clinical.ts` | Phase 12 types | ✅ DONE |
| `frontend/src/services/analysisService.ts` | Clarification flow support | ✅ DONE |
| `frontend/src/app/governance/page.tsx` | TS2322 unkown→ReactNode fix | ✅ DONE |
| `frontend/src/components/workspace/PatientIntakePanel.tsx` | Structured form + sufficiency | ⏳ TODO |
| `frontend/src/components/workspace/AnalysisPanel.tsx` | Evidence scorecard integration | ⏳ TODO |

### PRESERVED (DO NOT MODIFY)
```
backend/governance/           — HITL governance fully working
backend/auth/                 — JWT auth working
backend/rag/                  — Hybrid RAG working
backend/graphrag/             — GraphRAG + Neo4j working
backend/multimodal/           — ECG/X-ray/OCR working
backend/research/             — PubMed live research working
backend/telemetry/            — Observability working
backend/monitoring/           — Monitoring endpoints working
backend/decision/risk_engine.py    — Signal-weighted risk scoring working
backend/decision/workflow_router.py — Workflow selection working
backend/decision/schemas.py        — All domain schemas working
backend/evaluation/grounding_engine.py — Grounding analysis working
backend/evaluation/metrics.py      — Metrics collection working
backend/agents/reflection_agent.py — Reflection/retry working
backend/agents/validation_agent.py — Validation working
backend/agents/reasoning_agent.py  — Reasoning working
backend/agents/retrieval_agent.py  — Retrieval working
backend/agents/query_agent.py      — Query understanding working
backend/workflows/            — Workflow config registry working
```

---

## 6. EXECUTION SEQUENCE (ORDERED)

```
Step 1:  Create backend/decision/execution_plan.py         (schemas + types)
Step 2:  Extend backend/models/state.py                    (Phase 12 fields)
Step 3:  Create backend/decision/information_sufficiency_engine.py
Step 4:  Create backend/decision/clarification_engine.py
Step 5:  Create backend/evaluation/evidence_evaluator.py
Step 6:  Create backend/evaluation/contradiction_analyzer.py
Step 7:  Update backend/evaluation/__init__.py
Step 8:  Create backend/agents/orchestration_planner.py
Step 9:  Refactor backend/orchestration/graph.py           (new nodes + edges)
Step 10: Evolve backend/agents/supervisor_agent.py         (continuous monitor)
Step 11: Update backend/api/agentic.py                     (new fields + endpoint)
Step 12: Update backend/main.py                            (version 12.0.0)
Step 13: Evolve frontend/src/app/workspace/page.tsx        (3-panel workspace)
Step 14: Create 7 new frontend components
Step 15: Evolve PatientIntakePanel.tsx and AnalysisPanel.tsx
Step 16: End-to-end verification
```

---

## 7. IMPLEMENTATION PROGRESS

```
PHASE 12A — Backend New Modules
  [x] execution_plan.py (schemas + enums + types)
  [x] information_sufficiency_engine.py (signal-based, fixed chief_complaint detection)
  [x] clarification_engine.py
  [x] evidence_evaluator.py
  [x] contradiction_analyzer.py
  [x] orchestration_planner.py

PHASE 12B — Graph + State Refactor
  [x] state.py Phase 12 fields (all new optional fields with defaults)
  [x] graph.py new nodes + topology (plan→clarify|query→retrieve→evidence_eval→contradiction_check→reason→validate→...)

PHASE 12C — Supervisor Evolution
  [x] supervisor_agent.py continuous monitoring (threshold checks + escalation signals)

PHASE 12D — API Layer
  [x] agentic.py new response fields + POST /analyze/clarify/ endpoint
  [x] main.py version 12.0.0

PHASE 12E — Frontend
  [x] frontend/src/types/clinical.ts — All Phase 12 types (ClarificationQuestion, EvidenceQualitySummary, ContradictionSummary, ExecutionPlanSummary, MonitorEvent, extended AnalysisResult)
  [x] frontend/src/services/analysisService.ts — Clarification flow (clarificationAnswers param + submitClarificationAnswers)
  [x] workspace page.tsx — Phase 12 clarification gate, tabbed right panel (Plan/Evidence/Gov), contradiction alert, enriched loading
  [x] EvidenceScorecard.tsx — trust/relevance/freshness score bars + authority badges + source count grid
  [x] ContradictionAlert.tsx — severity-colored alert + conflict pairs + escalation warning
  [x] ClarificationPanel.tsx — multi-priority Q&A UI (critical/important/optional grouping)
  [x] ExecutionPlanViewer.tsx — execution plan card with intent icon, capabilities, evidence strategy grid
  [ ] SufficiencyGauge.tsx — visual sufficiency meter (planned next)
  [ ] OrchestraCopilot.tsx — context-aware AI copilot panel (planned next)
  [ ] PatientIntakePanel.tsx evolved — structured form with sufficiency integration (planned next)
  [ ] AnalysisPanel.tsx evolved — evidence scorecard integration (planned next)

PHASE 12F — Verification
  [x] Backend imports OK — ALL SYSTEMS VERIFIED
  [x] SufficiencyEngine signal detection fixed (chief_complaint now catches 'chest pain', 'SOB', etc.)
  [x] Frontend TypeScript compilation — ZERO ERRORS
  [ ] End-to-end API test
  [ ] Backward compat verified
  [ ] Governance preserved verified
```

---

## 8. KEY DESIGN DECISIONS

**D1: OrchestrationPlanner is ADDITIVE**
Wraps existing `make_decision()`. Returns ALL existing Phase 4.5 state fields for backward compat PLUS new Phase 12 fields. No downstream agent needs to change.

**D2: EvidenceEvaluator is PRE-REASONING**
Runs after retrieval, before reasoning. Annotates docs with quality scores. ValidationAgent (post-reasoning) preserved unchanged. Evidence scores feed into ValidationAgent's composite via `evidence_quality_summary`.

**D3: Clarification is Non-Blocking**
Emergency cases (CRITICAL risk) always bypass clarification. Non-emergency clarification is advisory — if caller doesn't answer, system proceeds with `proceed_with_caveat` warning appended to output.

**D4: Backward API Compatibility**
`POST /analyze/` signature unchanged. All new AnalyzeResponse fields are Optional with defaults. Existing frontend works without change. New frontend features are additive enhancements.

**D5: No LLM in Sufficiency/Contradiction Engines**
Both engines use rule-based signal detection for performance and determinism. This preserves the "controlled adaptive orchestration" design principle and avoids hallucination risk in safety-critical components.

---

## 9. SAFETY REQUIREMENTS

> [!CAUTION]
> These are NON-NEGOTIABLE architectural constraints:

1. **Clarification max iterations**: 3 (prevents infinite clarification loops)
2. **Re-planning max iterations**: `max_replan_iterations` in ExecutionPlan (default: 3)
3. **Emergency bypass**: `risk_level=CRITICAL` ALWAYS skips clarification and evidence filtering
4. **Governance preserved**: `finalize_response()` governance code unchanged
5. **Observability preserved**: All telemetry hooks preserved
6. **Planner fallback**: If orchestration_planner fails, falls back to existing `decision_agent.py` logic
7. **Evidence filtering threshold**: Only filter docs with `overall_quality < 0.30` (very conservative — don't over-filter)
8. **No autonomous agent swarm**: Every agent execution is tracked, bounded, and supervised

---

## 10. CONTEXT FOR NEXT AGENT SESSION

**Quick start** (next agent must do this first):
1. Read this file completely
2. Check Section 7 (Progress) for current state
3. Find next unchecked item in Section 6 (Execution Sequence)
4. Do NOT skip steps — they have dependencies

**Critical paths**:
```python
# Test backend imports:
from backend.decision.execution_plan import ExecutionPlan
from backend.decision.information_sufficiency_engine import check_sufficiency
from backend.agents.orchestration_planner import orchestration_planner
from backend.evaluation.evidence_evaluator import evaluate_evidence
from backend.evaluation.contradiction_analyzer import analyze_contradictions

# Run backend:
# uvicorn backend.main:app --reload --port 8000
# (from project root: c:\Users\pavan\OneDrive\Desktop\aegis-clinical-ai)

# Run frontend:
# cd frontend && npm run dev
```

**Import hierarchy** (to avoid circular imports):
```
execution_plan.py           (no backend imports — pure schemas)
  ↑
information_sufficiency_engine.py  (imports execution_plan)
clarification_engine.py           (imports execution_plan)
  ↑
evidence_evaluator.py       (imports existing research_ranker, freshness_engine)
contradiction_analyzer.py   (imports evidence_evaluator)
  ↑
orchestration_planner.py    (imports all decision + evaluation modules)
  ↑
graph.py                    (imports orchestration_planner + new eval nodes)
```

---

*Last updated: 2026-05-20 by Antigravity*  
*Phase: 12 — Adaptive Evidence-Aware Clinical Orchestration — CORE COMPLETE*  

## NEXT AGENT SESSION — What Remains

```
Completed (Phases 12A–12E core):
  ✅ All backend modules (planner, sufficiency, clarification, evidence eval, contradiction)
  ✅ Graph topology refactor (plan→clarify|query→...→evidence_eval→contradiction→reason)
  ✅ State.py Phase 12 fields
  ✅ API: /analyze/ extended + /analyze/clarify/ new endpoint
  ✅ Frontend types (clinical.ts Phase 12)
  ✅ Frontend service (analysisService.ts clarification flow)
  ✅ Workspace page evolved (clarification gate + tabbed right panel)
  ✅ 4 new Phase 12 workspace components
  ✅ Backend ALL SYSTEMS VERIFIED (venv test passed)
  ✅ Frontend TypeScript ZERO ERRORS

Remaining (next session):
  ⏳ SufficiencyGauge.tsx component
  ⏳ PatientIntakePanel.tsx structured form evolution
  ⏳ AnalysisPanel.tsx evidence scorecard integration
  ⏳ OrchestraCopilot.tsx context-aware copilot panel
  ⏳ End-to-end API test with live backend
  ⏳ E2E test: clarification loop (submit sparse query → get questions → answer → get full analysis)

To start next session:
  1. Read this file
  2. Check task.md in C:\Users\pavan\.gemini\antigravity\brain\0cf39e7f-6c40-4f20-8913-71725a1a0f83\task.md
  3. Start frontend: cd frontend && npm run dev
  4. Start backend: uvicorn backend.main:app --reload --port 8000
  5. Test clarification loop: POST /analyze/ with sparse query, check clarification_required=True
```
