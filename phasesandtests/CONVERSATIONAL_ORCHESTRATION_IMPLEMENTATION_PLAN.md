# CONVERSATIONAL_ORCHESTRATION_IMPLEMENTATION_PLAN.md
# Aegis Clinical Intelligence System — Conversational Orchestration Migration Blueprint
# Version: 13.0 | Date: 2026-05-21 | Authored by: Antigravity (Principal AI Orchestration Architect)

---

> [!IMPORTANT]
> **MANDATORY FIRST READ**: Any future Claude/agent session continuing this work MUST read this document completely before touching any code. This is the single source of truth for what has been built, what problems exist, and what must be done. Do NOT restart architecture from scratch. Evolve intelligently.

---

## TABLE OF CONTENTS

1. [Current Architecture Summary](#1-current-architecture-summary)
2. [Existing Agent Topology & Orchestration Flow](#2-existing-agent-topology--orchestration-flow)
3. [Current Agents and Workflows](#3-current-agents-and-workflows)
4. [Current Frontend Structure](#4-current-frontend-structure)
5. [Problems in Current Architecture](#5-problems-in-current-architecture)
6. [Migration Strategy](#6-migration-strategy)
7. [Files to Modify](#7-files-to-modify)
8. [Files to Delete](#8-files-to-delete)
9. [Orchestration Redesign Plan](#9-orchestration-redesign-plan)
10. [Conversational Workflow Design](#10-conversational-workflow-design)
11. [Patient State Management Plan](#11-patient-state-management-plan)
12. [Dynamic Planning Architecture](#12-dynamic-planning-architecture)
13. [Evidence Evaluation Architecture](#13-evidence-evaluation-architecture)
14. [Clarification Loop Design](#14-clarification-loop-design)
15. [Implementation Phases](#15-implementation-phases)
16. [Pending Tasks Checklist](#16-pending-tasks-checklist)
17. [Risks and Refactor Notes](#17-risks-and-refactor-notes)

---

## 1. CURRENT ARCHITECTURE SUMMARY

### 1.1 System Overview

The Aegis Clinical Intelligence System is a production-grade healthcare AI platform built on **LangGraph + FastAPI + Next.js 14**. It is currently at **Phase 12** — Adaptive Evidence-Aware Clinical Orchestration.

The system is NOT a chatbot. It is a sophisticated multi-agent system that performs:
- Hybrid RAG retrieval (dense + sparse + reranking via Qdrant + BM25)
- GraphRAG knowledge reasoning (Neo4j)
- Live research retrieval (PubMed via `pubmed_client.py`)
- Multimodal analysis (ECG / X-ray / OCR via `backend/multimodal/`)
- Similar case intelligence (`similar_case_engine.py`)
- Evidence evaluation and contradiction detection (`backend/evaluation/`)
- HITL Governance with escalation and review (`backend/governance/`)
- Continuous supervisor monitoring
- Full observability and telemetry (`backend/telemetry/`, `backend/monitoring/`)
- JWT auth + Rate limiting

### 1.2 Existing Capabilities — ALL MUST BE PRESERVED

| Capability | Module | Phase | Status |
|---|---|---|---|
| Hybrid RAG (Dense+Sparse+Reranking) | `backend/rag/` | 6 | ✅ Production |
| GraphRAG (Neo4j) | `backend/graphrag/` | 7 | ✅ Production |
| Similar Case Intelligence | `backend/graphrag/similar_case_engine.py` | 7 | ✅ Production |
| Live Research Intelligence (PubMed) | `backend/research/` | 6 | ✅ Production |
| Multimodal ECG/X-ray/OCR | `backend/multimodal/` | 8 | ✅ Production |
| Governance / HITL | `backend/governance/` | 9 | ✅ Production |
| LangGraph Orchestration | `backend/orchestration/graph.py` | 12 | ✅ Production |
| Reflection System | `backend/agents/reflection_agent.py` | 3 | ✅ Production |
| Validation Agent | `backend/agents/validation_agent.py` | 3 | ✅ Production |
| Observability / Telemetry | `backend/telemetry/`, `backend/monitoring/` | 5 | ✅ Production |
| JWT Auth | `backend/auth/` | 11 | ✅ Production |
| Rate Limiting | `backend/api/rate_limiter.py` | 11 | ✅ Production |
| Sentry Error Monitoring | `backend/main.py` | 11 | ✅ Production |
| Decision Layer | `backend/decision/` | 4.5 | ✅ Production |
| Risk Engine | `backend/decision/risk_engine.py` | 4.5 | ✅ Production |
| OrchestrationPlanner | `backend/agents/orchestration_planner.py` | 12 | ✅ Production |
| Information Sufficiency Engine | `backend/decision/information_sufficiency_engine.py` | 12 | ✅ Production |
| Clarification Engine | `backend/decision/clarification_engine.py` | 12 | ✅ Production |
| Evidence Evaluator | `backend/evaluation/evidence_evaluator.py` | 12 | ✅ Production |
| Contradiction Analyzer | `backend/evaluation/contradiction_analyzer.py` | 12 | ✅ Production |
| Execution Plan Schema | `backend/decision/execution_plan.py` | 12 | ✅ Production |
| Continuous Supervisor Monitoring | `backend/agents/supervisor_agent.py` | 12 | ✅ Production |
| Grounding Analysis | `backend/evaluation/grounding_engine.py` | 9 | ✅ Production |

### 1.3 Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + LangGraph + Python 3.11 |
| LLM | Groq (llama-3.3-70b-versatile) + OpenAI fallback |
| Vector DB | Qdrant |
| Graph DB | Neo4j |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| State Management | Zustand |
| Auth | JWT + Simple RBAC |
| Monitoring | Sentry + Custom telemetry bus |
| Infra | Docker + docker-compose |

---

## 2. EXISTING AGENT TOPOLOGY & ORCHESTRATION FLOW

### 2.1 Current Phase 12 LangGraph Graph Topology

```
INPUT (query + clarification_answers)
    │
    ▼
[ plan ] — OrchestrationPlanner
    │
    ├─ clarification_required=True AND not emergency → [ clarify ] → END
    │                                                     (API returns questions)
    │
    └─ proceed → [ query_understand ] — QueryAgent
                        │
                        ▼
                 [ retrieve ] — RetrievalAgent
                 (graph + semantic + research + multimodal + similar_cases)
                        │
                        ▼
                 [ evidence_eval ] — EvidenceEvaluatorNode [Phase 12]
                        │
                        ▼
                 [ contradiction_check ] — ContradictionAnalyzerNode [Phase 12]
                        │
                        ▼
                 [ reason ] — ReasoningAgent
                        │
                        ▼
                 [ validate ] — ValidationAgent
                        │
                        ▼ supervisor_router()
                        ├─ score < threshold AND retries left → [ reflect ] → [ retrieve ] (retry)
                        └─ score OK OR retries exhausted → [ finalize ] → END
                                        │
                                        ▼
                                HITL Governance Check
                                (EscalationEngine + ReviewEngine + AuditLogger)
```

### 2.2 API Entry Points

| Endpoint | Purpose |
|---|---|
| `POST /analyze/` | Primary analysis — runs full Phase 12 workflow |
| `POST /analyze/clarify/` | Submit clarification answers — re-runs with enriched context |
| `POST /analyze/copilot/` | **MISSING** — copilot chat endpoint (currently fails with 404) |
| `POST /upload/` | Upload ECG/X-ray/PDF for multimodal analysis |
| `GET /health/*` | Service health checks |
| `GET /monitoring/*` | Observability metrics |
| `GET /governance/*` | HITL review management |

### 2.3 Data Flow Through State

```
AgentState (TypedDict):
  query                    → Input
  [Phase 4.5 Decision]     → query_type, risk_level, selected_workflow, 
                              retrieval_strategy, confidence_threshold...
  [Phase 12 Planner]       → clinical_intent, execution_plan, 
                              clarification_required, clarification_questions,
                              missing_information, patient_context
  [Phase 4 Query]          → query_variants, query_plan
  [Retrieval]              → retrieved_docs, compressed_context, 
                              graph_context, similar_cases_context,
                              live_research_context
  [Phase 8 Multimodal]     → visual_context, image_modality, image_confidence
  [Phase 12 Evidence]      → evidence_scores, evidence_quality_summary,
                              contradiction_report
  [Reasoning]              → reasoning_output
  [Validation]             → validation_score, validation_feedback
  [Reflection]             → retry_count, reflection_notes
  [Phase 12 Monitor]       → monitor_events, replan_count, replan_reasons
  [Phase 9 Governance]     → review_required, review_id, review_status
  [Output]                 → final_response, error, workflow_path
```

---

## 3. CURRENT AGENTS AND WORKFLOWS

### 3.1 Backend Agents (`backend/agents/`)

| Agent File | Phase | Role | Status |
|---|---|---|---|
| `orchestration_planner.py` | 12 | Entry node: intent detection, sufficiency check, plan building | ✅ Implemented |
| `decision_agent.py` | 4.5 | Legacy: simple classifier/router (superseded by planner) | ⚠️ Obsolete — delete later |
| `query_agent.py` | 4 | Query understanding, expansion, HyDE | ✅ Production |
| `retrieval_agent.py` | 6 | Hybrid retrieval — graph+semantic+research+multimodal | ✅ Production |
| `reasoning_agent.py` | 8 | Multimodal-aware clinical reasoning via Groq | ✅ Production |
| `validation_agent.py` | 3 | Confidence scoring + grounding check | ✅ Production |
| `reflection_agent.py` | 3 | Adaptive retry with reflection notes | ✅ Production |
| `supervisor_agent.py` | 9/12 | Governance finalizer + continuous monitor | ✅ Production |

### 3.2 Decision Layer (`backend/decision/`)

| File | Purpose | Status |
|---|---|---|
| `decision_layer.py` | `make_decision()` — core classification + risk scoring | ✅ Used by planner |
| `risk_engine.py` | Signal-weighted risk assessment | ✅ Production |
| `workflow_router.py` | Workflow type selection | ✅ Production |
| `schemas.py` | Core enums: WorkflowType, RiskLevel, etc. | ✅ Production |
| `source_policy.py` | Source priority rules | ✅ Production |
| `execution_plan.py` | ExecutionPlan, ClinicalIntent, EvidenceStrategy schemas | ✅ Phase 12 |
| `information_sufficiency_engine.py` | Signal-based clinical completeness checker | ✅ Phase 12 |
| `clarification_engine.py` | Clarification question generation and resolution | ✅ Phase 12 |

### 3.3 Evaluation Layer (`backend/evaluation/`)

| File | Purpose | Status |
|---|---|---|
| `evidence_evaluator.py` | Per-source trust/freshness/relevance scoring | ✅ Phase 12 |
| `contradiction_analyzer.py` | Cross-source conflict detection | ✅ Phase 12 |
| `grounding_engine.py` | Response grounding verification | ✅ Production |
| `failure_analytics.py` | Failure pattern analysis | ✅ Production |
| `metrics.py` | Evaluation metrics | ✅ Production |

### 3.4 Workflow Templates (`backend/workflows/`)

Static workflow configuration files:
- `clinical.py`, `emergency.py`, `literature.py`, `medication.py`
- `multimodal.py`, `research.py`, `similar_case.py`
- These define workflow config parameters — NOT routing logic
- Status: **Mostly vestigial** — routing is now handled by `orchestration_planner.py`
- Action: Review for removal or consolidation in Phase 13

---

## 4. CURRENT FRONTEND STRUCTURE

### 4.1 App Routes (`frontend/src/app/`)

| Route | File | Purpose | Status |
|---|---|---|---|
| `/` | `page.tsx` | Redirects → `/workspace` | ✅ |
| `/workspace` | `workspace/page.tsx` | Main clinical workspace | ✅ Phase 12 evolved |
| `/governance` | `governance/` | HITL review dashboard | ✅ Phase 9 |
| `/dashboard` | `dashboard/` | Monitoring dashboard | ✅ Phase 5 |

### 4.2 Workspace Components (`frontend/src/components/workspace/`)

| Component | Size | Purpose | Status |
|---|---|---|---|
| `PatientIntakePanel.tsx` | 15.8KB | Structured intake: vitals, symptoms, history, meds | ✅ Phase 12 evolved |
| `AnalysisPanel.tsx` | 17.6KB | Main report: sections, evidence, workflow trace | ✅ Phase 12 evolved |
| `GovernancePanel.tsx` | 12.9KB | HITL review status and governance info | ✅ Phase 9 |
| `FileUploadZone.tsx` | 7.5KB | Drag/drop ECG, X-ray, PDF upload | ✅ Production |
| `OrchestraCopilot.tsx` | 11.0KB | Context-aware AI copilot panel (chat) | ✅ Implemented (API 404) |
| `ClarificationPanel.tsx` | 7.8KB | Clarification Q&A UI | ✅ Phase 12 |
| `ExecutionPlanViewer.tsx` | 7.0KB | Execution plan card with intent, capabilities | ✅ Phase 12 |
| `EvidenceScorecard.tsx` | 6.2KB | Trust/freshness/quality visualization | ✅ Phase 12 |
| `ContradictionAlert.tsx` | 3.4KB | Contradiction warning banner | ✅ Phase 12 |
| `SufficiencyGauge.tsx` | 4.6KB | Visual information completeness meter | ✅ Phase 12 |

### 4.3 Supporting Frontend Files

| File | Purpose | Status |
|---|---|---|
| `src/types/clinical.ts` | All TypeScript types (Phase 1–12) | ✅ Complete |
| `src/services/analysisService.ts` | API bridge: query builder + analysis calls | ✅ Phase 12 |
| `src/stores/workspaceStore.ts` | Zustand global state | ✅ Phase 12 |

### 4.4 Current Workspace Layout

```
┌─ Header ───────────────────────────────────────────────────────────────┐
│ Aegis Logo | Status Badge | + New Case | Governance Link               │
├──────────────────────┬─────────────────────────────────────────────────┤
│  LEFT PANEL          │  CENTER + RIGHT PANEL (shown post-analysis)      │
│  (always visible)    │                                                   │
│  PatientIntakePanel  │  CENTER: Report OR Clarification OR Loading      │
│  + SufficiencyGauge  │                                                   │
│  + FileUploadZone    │  RIGHT: Tabbed panel                              │
│                      │    [Plan] ExecutionPlanViewer + MissingInfo       │
│  [Analyze button]    │    [Evidence] Scorecard + Sources                 │
│                      │    [Governance] GovernancePanel                   │
│                      │    [Copilot] OrchestraCopilot (chat panel)        │
└──────────────────────┴─────────────────────────────────────────────────┘
```

**Problem**: The workspace layout puts the conversation SECONDARY to the form-driven intake. The "Copilot" is relegated to a small tab in the right panel. The primary UX is still a form → button → report model.

---

## 5. PROBLEMS IN CURRENT ARCHITECTURE

### Problem 1: Form-First, Not Conversation-First [CRITICAL]

**Current**: Doctor must fill out a structured form (PatientIntakePanel) then click "Analyze Patient Case" button. The copilot is an afterthought — a tab in the right panel that appears AFTER analysis.

**Target**: Doctor types a message. The system listens, understands, extracts structure automatically, and continues the conversation. The form is gone. The chat IS the interface.

### Problem 2: Missing Copilot Backend Endpoint [BLOCKING BUG]

**Current**: `OrchestraCopilot.tsx` calls `POST /analyze/copilot/` which **does not exist** in `backend/main.py` or any router. Every copilot question returns a 404. The frontend degrades to offline fallback answers.

**Target**: `POST /analyze/copilot/` endpoint implemented with Groq LLM that has access to the full patient context, conversation history, and orchestration state.

### Problem 3: Stateless Sessions [CRITICAL]

**Current**: Every "Analyze" button click is a completely fresh invocation. There is no persistent conversation state. If the doctor asks a follow-up question ("Why was the confidence LOW?"), the copilot has no real-time access to the graph findings or execution trace — it uses client-side fallbacks.

**Target**: Persistent conversational patient session. Every message continues the same session. Doctor can ask follow-up questions that reference prior findings.

### Problem 4: No Conversational Orchestration — Chat Doesn't Trigger Agents [CRITICAL]

**Current**: The OrchestraCopilot chat is cosmetically attached to the workspace but does NOT trigger the orchestration pipeline. It calls a missing endpoint, and otherwise relies on pattern-matching fallbacks.

**Target**: Every doctor message in the chat CAN trigger the full orchestration pipeline if needed. The planner decides whether a new analysis run is needed or if the query can be answered from existing patient state.

### Problem 5: Workspace UI Model is Wrong

**Current**: 
```
LEFT: Big structured form (intake) 
CENTER: Report panel (appears after analysis)
RIGHT: Tabbed panels (plan, evidence, governance, copilot)
```

This is a **workflow-execution form** model. Doctors have to understand the layout, fill fields, click buttons, then navigate tabs.

**Target**:
```
LEFT: Patient context sidebar (dynamically populated from conversation)
CENTER: Conversational chat workspace (primary interface)
RIGHT: Dynamic intelligence panels (evidence, orchestration, governance)
```

### Problem 6: The OrchestraCopilot Context is Shallow

**Current**: The copilot buildContext() function only captures basic strings like "clinical intent: X" and "summary: first 300 chars". It has no access to:
- Full execution plan
- Evidence scores per source
- Contradiction details
- Graph reasoning findings
- Multimodal analysis findings
- Governance escalation state

**Target**: Copilot has FULL access to the entire AgentState from the most recent orchestration run, plus conversation history.

### Problem 7: Decision Agent is Vestigial

**Current**: `decision_agent.py` still exists and is registered in `agents/__init__.py` but is NOT used in `graph.py` anymore (replaced by `orchestration_planner.py`).

**Target**: `decision_agent.py` should be deleted. Its registration in `__init__.py` cleaned up.

### Problem 8: Static Workflow Templates Are Mostly Vestigial

**Current**: `backend/workflows/` contains 7 static workflow config files. These were useful when workflow routing was explicit. Now that `orchestration_planner.py` dynamically plans execution, these static templates add confusion without benefit.

**Target**: Review and consolidate. The `workflows/` module can be simplified to a single constants file or removed entirely.

### Problem 9: Patient State Is Not Accumulated Across the Conversation

**Current**: `patient_context` in `AgentState` is extracted fresh from each query using regex. There is no accumulation of findings across conversation turns. If the doctor says "And what about his ECG?" in message 2, the system doesn't remember "his" refers to the patient described in message 1.

**Target**: Persistent `PatientSessionState` that accumulates vitals, findings, uploads, graph results, and prior reasoning across all conversation turns.

### Problem 10: No Streaming Feedback During Orchestration

**Current**: Doctor clicks "Analyze" → UI shows a generic spinning animation → Result appears all at once after 10–30 seconds. There is no real-time feedback about what the system is doing (planning, retrieving, evaluating evidence, etc.).

**Target**: WebSocket or SSE streaming that pushes orchestration stage updates to the UI in real-time ("🧠 Planning execution strategy...", "🔍 Retrieving from GraphRAG...", etc.).

---

## 6. MIGRATION STRATEGY

### Core Principle: Evolve, Don't Restart

The backend infrastructure is excellent. The goal is to:
1. Add a **conversational session layer** on top of existing orchestration
2. Replace the **form-first frontend** with a **chat-first frontend**
3. Fix the **missing copilot endpoint** (the biggest immediate blocker)
4. Add **session persistence** for multi-turn conversations
5. Preserve ALL existing agents, GraphRAG, governance, observability

### Migration Order (Critical Path)

```
PHASE 13A — Fix Critical Backend Gaps (Week 1)
  1. Implement POST /analyze/copilot/ endpoint
  2. Add ConversationalPatientSession model
  3. Add session store (in-memory, keyed by session_id)
  4. Update POST /analyze/ to accept session_id
  5. Add POST /session/new and GET /session/{id} endpoints

PHASE 13B — Conversational Planner Enhancement (Week 1-2)
  6. Extend OrchestrationPlanner to be conversation-turn-aware
  7. Add ConversationalPlanningEngine — decides if new analysis needed
  8. Update AgentState with session_id and conversation_history
  9. Update run_workflow() to accept and return session context

PHASE 13C — Frontend Transformation (Week 2-3)
  10. Redesign workspace/page.tsx to chat-first layout
  11. Create ConversationalChatPanel.tsx (primary interface)
  12. Create PatientContextSidebar.tsx (dynamic sidebar)
  13. Create LiveOrchestrationPanel.tsx (right panel)
  14. Update workspaceStore.ts for conversation + session state
  15. Update analysisService.ts for session-aware API calls

PHASE 13D — Streaming and Real-time Updates (Week 3)
  16. Add SSE streaming to /analyze/ endpoint
  17. Add orchestration stage events pushed via SSE
  18. Frontend subscribes to SSE and shows live progress

PHASE 13E — Cleanup and Polish (Week 4)
  19. Delete decision_agent.py
  20. Consolidate or remove workflows/ templates
  21. End-to-end conversation flow testing
  22. Governance and observability validation
```

---

## 7. FILES TO MODIFY

### 7.1 Backend Files to Modify

| File | Change | Priority |
|---|---|---|
| `backend/api/agentic.py` | Add `/copilot/` endpoint, session_id support, SSE streaming | 🔴 CRITICAL |
| `backend/main.py` | Version → 13.0.0, register session router | 🟡 HIGH |
| `backend/orchestration/graph.py` | Accept session_id, integrate session context into initial_state | 🟡 HIGH |
| `backend/agents/orchestration_planner.py` | Add conversation_history awareness, skip re-plan if copilot Q only | 🟡 HIGH |
| `backend/models/state.py` | Add session_id, conversation_history, copilot_context fields | 🟡 HIGH |
| `backend/agents/supervisor_agent.py` | Pass session context to finalize_response | 🟠 MEDIUM |

### 7.2 Frontend Files to Modify

| File | Change | Priority |
|---|---|---|
| `frontend/src/app/workspace/page.tsx` | Complete redesign: chat-first 3-panel layout | 🔴 CRITICAL |
| `frontend/src/stores/workspaceStore.ts` | Add session state, messages, conversationHistory | 🔴 CRITICAL |
| `frontend/src/services/analysisService.ts` | Add session APIs, copilot endpoint, SSE streaming | 🔴 CRITICAL |
| `frontend/src/types/clinical.ts` | Add Session, ConversationMessage, CopilotRequest types | 🟡 HIGH |
| `frontend/src/components/workspace/OrchestraCopilot.tsx` | Full rebuild: session-aware, triggers real orchestration | 🔴 CRITICAL |
| `frontend/src/app/layout.tsx` | Update page title and meta | 🟠 MEDIUM |
| `frontend/src/app/globals.css` | Add chat-specific styles and animations | 🟠 MEDIUM |

### 7.3 New Backend Files to Create

| File | Purpose | Priority |
|---|---|---|
| `backend/api/session_api.py` | Session management: create/get/delete sessions | 🔴 CRITICAL |
| `backend/models/session.py` | ConversationalPatientSession, ConversationMessage models | 🔴 CRITICAL |
| `backend/session/session_store.py` | In-memory session store (TTL-based) | 🔴 CRITICAL |
| `backend/api/copilot_api.py` | Copilot endpoint with full context-aware LLM | 🔴 CRITICAL |
| `backend/agents/conversational_planner.py` | Extension of orchestration_planner for multi-turn | 🟡 HIGH |

### 7.4 New Frontend Files to Create

| File | Purpose | Priority |
|---|---|---|
| `frontend/src/components/workspace/ConversationalChatPanel.tsx` | Primary chat interface with orchestration awareness | 🔴 CRITICAL |
| `frontend/src/components/workspace/PatientContextSidebar.tsx` | Dynamic sidebar: accumulated patient context | 🟡 HIGH |
| `frontend/src/components/workspace/LiveOrchestrationPanel.tsx` | Real-time orchestration stage viewer | 🟡 HIGH |
| `frontend/src/components/workspace/InlineFileUpload.tsx` | Drag/drop inline in chat | 🟡 HIGH |
| `frontend/src/components/workspace/MessageBubble.tsx` | Rich message bubble with evidence refs | 🟠 MEDIUM |
| `frontend/src/components/workspace/OrchestrationStageBar.tsx` | Live stage progress bar | 🟠 MEDIUM |

---

## 8. FILES TO DELETE

| File | Reason | When |
|---|---|---|
| `backend/agents/decision_agent.py` | Superseded by `orchestration_planner.py`. No longer registered in graph. | Phase 13E cleanup |
| `backend/workflows/clinical.py` | Static config vestigial — planner handles dynamically | Phase 13E cleanup |
| `backend/workflows/emergency.py` | Same reason | Phase 13E cleanup |
| `backend/workflows/literature.py` | Same reason | Phase 13E cleanup |
| `backend/workflows/medication.py` | Same reason | Phase 13E cleanup |
| `backend/workflows/multimodal.py` | Same reason | Phase 13E cleanup |
| `backend/workflows/research.py` | Same reason | Phase 13E cleanup |
| `backend/workflows/similar_case.py` | Same reason | Phase 13E cleanup |

> [!WARNING]
> Before deleting `backend/workflows/`, verify no file in `backend/agents/` or `backend/orchestration/graph.py` imports from `workflows/`. Run: `grep -r "from backend.workflows" backend/` to confirm no live imports.

> [!NOTE]
> The `backend/workflows/__init__.py` should also be deleted with the module. The workflow configuration logic should either be consolidated into `decision/schemas.py` or removed entirely if the dynamic planner makes them unnecessary.

---

## 9. ORCHESTRATION REDESIGN PLAN

### 9.1 NEW Conversation-Turn Routing

When a doctor sends a message, the backend must classify the message into one of:

```python
class MessageIntent(str, Enum):
    NEW_PATIENT_CASE   = "new_patient_case"      # Full orchestration run needed
    FOLLOW_UP_QUESTION = "follow_up_question"     # Can answer from existing state
    UPLOAD_AND_ANALYZE = "upload_and_analyze"     # New file uploaded, needs analysis
    CLARIFICATION      = "clarification"          # Doctor providing requested info
    GENERAL_QUESTION   = "general_question"       # Pure copilot Q&A
    REQUEST_RESEARCH   = "request_research"       # Doctor wants live research
    REQUEST_SIMILAR    = "request_similar_cases"  # Doctor wants similar cases
```

**Decision tree**:
```
Doctor message arrives
        │
        ▼
ConversationalPlanningEngine.classify_message()
        │
        ├─ NEW_PATIENT_CASE      → full run_workflow() with new patient context
        ├─ FOLLOW_UP_QUESTION    → POST /analyze/copilot/ with existing state
        ├─ UPLOAD_AND_ANALYZE    → upload file → targeted retrieval only
        ├─ CLARIFICATION         → POST /analyze/clarify/ with answers
        ├─ GENERAL_QUESTION      → POST /analyze/copilot/ (pure LLM)
        ├─ REQUEST_RESEARCH      → targeted retrieval_agent (research only)
        └─ REQUEST_SIMILAR       → targeted retrieval_agent (similar_cases only)
```

### 9.2 Session-Aware Orchestration State

The `run_workflow()` function should be extended to accept a `session_id` parameter:

```python
async def run_workflow(
    query: str,
    session_id: str | None = None,           # NEW: session continuity
    clarification_answers: dict | None = None,
    conversation_history: list | None = None,  # NEW: multi-turn context
) -> AgentState:
```

The `_initial_state()` function should pull accumulated patient context from the session store rather than starting blank.

### 9.3 Planner Enhancement for Conversational Turns

The `orchestration_planner.py` must be extended with:

```python
def _is_follow_up_question(
    query: str,
    conversation_history: list,
    session: ConversationalPatientSession | None,
) -> bool:
    """
    Returns True if this is a follow-up question that can be answered
    from existing session state without a full orchestration run.
    Examples: "Why was confidence low?", "What does the ECG show?",
              "Explain the contradiction", "What's the evidence quality?"
    """

def _merge_session_context_into_query(
    query: str,
    session: ConversationalPatientSession,
) -> str:
    """
    Enriches the query with accumulated patient context from the session.
    So "What's the best treatment for his condition?" becomes
    "For the 65yo male with STEMI described earlier, what is the
    best treatment for his condition?"
    """
```

---

## 10. CONVERSATIONAL WORKFLOW DESIGN

### 10.1 The Interaction Model

```
Doctor: "65yo male with crushing chest pain, BP 160/100, HR 95..."
                    ↓
    [MessageIntent: NEW_PATIENT_CASE]
                    ↓
    Full orchestration pipeline runs
    (plan → query → retrieve → evidence_eval → contradiction → reason → validate → finalize)
                    ↓
    Streaming updates pushed to UI
    ("🧠 Planning...", "🔍 Retrieving from PubMed...", etc.)
                    ↓
    Clinical Intelligence Report rendered in chat
    Patient context accumulated in session

Doctor: "Why was the confidence only MEDIUM?"
                    ↓
    [MessageIntent: FOLLOW_UP_QUESTION]
                    ↓
    POST /analyze/copilot/ with:
      - session patient context
      - evidence_quality_summary from last run
      - contradiction_report from last run
      - validation_feedback from last run
                    ↓
    Copilot answer in chat (no full re-run)

Doctor: "Can you pull the latest guidelines on dual antiplatelet therapy?"
                    ↓
    [MessageIntent: REQUEST_RESEARCH]
                    ↓
    Targeted research retrieval only (PubMed + GraphRAG)
                    ↓
    Research summary added to chat

Doctor: [uploads ECG image]
                    ↓
    [MessageIntent: UPLOAD_AND_ANALYZE]
                    ↓
    File uploaded → multimodal analysis
                    ↓
    ECG findings added to patient context
    Copilot: "I've analyzed the ECG. ST elevation in leads V2-V4 consistent with anterior STEMI..."
```

### 10.2 Message Types in the Chat UI

The chat should support these message types:

| Type | Description |
|---|---|
| `user_text` | Doctor's text message |
| `user_upload` | Doctor uploaded a file |
| `system_report` | Full clinical intelligence report (collapsible) |
| `system_copilot` | Copilot's conversational response |
| `system_clarification` | System requesting clarification |
| `system_research` | Research findings snippet |
| `system_stage_update` | Live orchestration stage notification |
| `system_escalation` | Governance escalation notification |

### 10.3 Chat Context Window Management

The copilot endpoint must manage context carefully:
- Include last 6 conversation turns (3 user + 3 assistant)
- Always include current patient context summary
- Always include last analysis key findings
- Truncate evidence blocks to 500 chars each
- Include governance state (escalation, review status)

### 10.4 Smart Prompt Suggestions

The UI should dynamically generate suggestions based on what's happening:

```typescript
// After analysis complete:
["Why was confidence MEDIUM?", "Explain the ECG findings", "Any drug interactions?"]

// After clarification returned:
["Patient has no known allergies", "Medications: Metformin, Aspirin", "ECG being uploaded"]

// After contradiction detected:
["Explain the contradiction", "Which guideline is more current?", "Should I escalate?"]

// After research retrieved:
["What's the evidence quality?", "Compare these studies", "Show similar cases"]
```

---

## 11. PATIENT STATE MANAGEMENT PLAN

### 11.1 ConversationalPatientSession Model

```python
# backend/models/session.py (NEW FILE)

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class ConversationMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str                        # "user" | "assistant" | "system"
    content: str                     # text content
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: str = "text"      # "text" | "report" | "research" | "clarification"
    metadata: Dict[str, Any] = {}  # extra data (evidence refs, confidence, etc.)

class AccumulatedPatientContext(BaseModel):
    """Patient context that accumulates across conversation turns."""
    age: Optional[str] = None
    gender: Optional[str] = None
    chief_complaint: Optional[str] = None
    vitals: Dict[str, str] = {}
    symptoms: List[str] = []
    history: List[str] = []
    medications: List[str] = []
    allergies: List[str] = []
    uploaded_files: List[str] = []    # file types uploaded
    ecg_findings: Optional[str] = None
    imaging_findings: Optional[str] = None
    lab_values: Dict[str, str] = {}
    extracted_conditions: List[str] = []

class AnalysisSnapshot(BaseModel):
    """Snapshot of key findings from an analysis run."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    clinical_intent: str = "unknown"
    risk_level: str = "unknown"
    confidence_score: float = 0.0
    confidence_label: str = "LOW"
    evidence_sufficiency: str = "unknown"
    has_contradictions: bool = False
    contradiction_summary: Optional[str] = None
    escalation_required: bool = False
    missing_information: List[str] = []
    key_findings: str = ""           # first 500 chars of final_response
    evidence_quality_summary: Dict[str, Any] = {}
    execution_plan: Dict[str, Any] = {}
    monitor_events: List[Dict[str, Any]] = []

class ConversationalPatientSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    
    # Conversation history
    messages: List[ConversationMessage] = []
    
    # Accumulated patient understanding
    patient_context: AccumulatedPatientContext = Field(
        default_factory=AccumulatedPatientContext
    )
    
    # Last analysis snapshot (for copilot context)
    last_analysis: Optional[AnalysisSnapshot] = None
    
    # Full AgentState from last analysis run (for deep copilot queries)
    last_agent_state: Dict[str, Any] = {}
    
    # Session metadata
    turn_count: int = 0
    analysis_count: int = 0
    clarification_pending: bool = False
    pending_query: Optional[str] = None
```

### 11.2 Session Store

```python
# backend/session/session_store.py (NEW FILE)

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
from backend.models.session import ConversationalPatientSession

class SessionStore:
    """
    In-memory session store with TTL-based expiry.
    
    In production, replace with Redis for horizontal scaling.
    For development: 2-hour TTL, max 1000 sessions.
    """
    
    TTL_HOURS = 2
    MAX_SESSIONS = 1000
    
    def __init__(self):
        self._sessions: Dict[str, ConversationalPatientSession] = {}
    
    def create(self) -> ConversationalPatientSession:
        session = ConversationalPatientSession()
        self._sessions[session.session_id] = session
        return session
    
    def get(self, session_id: str) -> Optional[ConversationalPatientSession]:
        session = self._sessions.get(session_id)
        if session:
            session.last_active = datetime.utcnow()
        return session
    
    def update(self, session: ConversationalPatientSession):
        session.last_active = datetime.utcnow()
        self._sessions[session.session_id] = session
    
    def delete(self, session_id: str):
        self._sessions.pop(session_id, None)
    
    def cleanup_expired(self):
        cutoff = datetime.utcnow() - timedelta(hours=self.TTL_HOURS)
        expired = [sid for sid, s in self._sessions.items() 
                   if s.last_active < cutoff]
        for sid in expired:
            del self._sessions[sid]

# Singleton
session_store = SessionStore()
```

### 11.3 Patient Context Accumulation Strategy

When a new analysis completes, the session's `patient_context` must be MERGED (not replaced):

```python
def update_session_from_analysis(
    session: ConversationalPatientSession,
    agent_state: dict,
    query: str,
) -> ConversationalPatientSession:
    """
    Merge new findings into persistent session patient context.
    Uses max() for numeric confidence values (keep best reading).
    Uses union for lists (accumulate findings).
    Uses latest for string fields (most recent is most relevant).
    """
    pc = session.patient_context
    new_ctx = agent_state.get("patient_context", {})
    
    # Merge patient demographics (keep first non-null value)
    pc.age     = pc.age    or new_ctx.get("age")
    pc.gender  = pc.gender or new_ctx.get("gender")
    
    # Accumulate medications and conditions (union)
    # ... merge logic ...
    
    # Store last analysis snapshot
    session.last_analysis = AnalysisSnapshot(
        clinical_intent      = agent_state.get("clinical_intent", "unknown"),
        risk_level           = agent_state.get("risk_level", "unknown"),
        confidence_score     = agent_state.get("validation_score", 0.0),
        confidence_label     = "HIGH" if agent_state.get("validation_score", 0) >= 0.80 else "MEDIUM",
        evidence_sufficiency = (agent_state.get("evidence_quality_summary") or {}).get("overall_sufficiency", "unknown"),
        has_contradictions   = (agent_state.get("contradiction_report") or {}).get("has_contradictions", False),
        escalation_required  = agent_state.get("escalation_required", False),
        missing_information  = agent_state.get("missing_information", []),
        key_findings         = (agent_state.get("final_response") or "")[:500],
        evidence_quality_summary = agent_state.get("evidence_quality_summary") or {},
        execution_plan       = agent_state.get("execution_plan") or {},
        monitor_events       = agent_state.get("monitor_events", []),
    )
    
    session.last_agent_state = agent_state
    session.turn_count += 1
    session.analysis_count += 1
    
    return session
```

---

## 12. DYNAMIC PLANNING ARCHITECTURE

### 12.1 Conversational Planner Decision Logic

The extended planner must handle multi-turn conversations:

```
Turn 1: "65yo male, chest pain, STEMI suspected"
  → Intent: NEW_PATIENT_CASE
  → Full orchestration run
  → session.patient_context.chief_complaint = "chest pain / STEMI"
  → session.last_analysis populated

Turn 2: "What's his troponin threshold for reperfusion?"
  → Intent: FOLLOW_UP_QUESTION
  → Query resolved against session.patient_context (knows "his" = the patient)
  → Only copilot LLM call needed (no full re-run)
  → Copilot uses session.last_analysis + evidence from last run

Turn 3: [uploads ECG image]
  → Intent: UPLOAD_AND_ANALYZE
  → Multimodal analysis only
  → ECG findings merged into session.patient_context.ecg_findings
  → Copilot: "ECG shows anterior STEMI — this is consistent with the clinical presentation"

Turn 4: "Can you pull any 2024 trials on primary PCI timing?"
  → Intent: REQUEST_RESEARCH  
  → Targeted PubMed retrieval for "primary PCI timing STEMI 2024"
  → Research snippet added to chat, appended to session evidence

Turn 5: "Given all this, what's the management plan?"
  → Intent: NEW_PATIENT_CASE (full context available now)
  → Full orchestration run with ENRICHED query:
    "65yo male, anterior STEMI, ECG [findings from turn 3],
     troponin [from turn 2], medications [accumulated], 
     latest PCI evidence [from turn 4]. Management plan?"
```

### 12.2 Dynamic Execution Plan Builder (Conversational Mode)

When orchestration runs in conversational mode, the `ExecutionPlan` must be sensitive to what's already known:

```python
def _build_conversational_execution_plan(
    query: str,
    session: ConversationalPatientSession | None,
    clinical_intent: ClinicalIntent,
    decision_plan: DecisionPlan,
) -> ExecutionPlan:
    """
    Builds ExecutionPlan that skips redundant retrievals based on session state.
    
    Examples:
    - If session.patient_context.ecg_findings is already populated:
      → evidence_strategy.use_multimodal = False (already have ECG analysis)
    - If session.last_analysis.evidence_quality_summary.overall_sufficiency == "strong":
      → retrieval_depth = RetrievalDepth.SHALLOW (we already have good evidence)
    - If session.analysis_count > 0 and intent == FOLLOW_UP_QUESTION:
      → skip full retrieval, use session evidence
    """
```

---

## 13. EVIDENCE EVALUATION ARCHITECTURE

### 13.1 Current State (Phase 12) — Already Implemented

The evidence evaluation pipeline is complete and working:

```
retrieve → evidence_eval_node → contradiction_check_node → reason
```

- `evidence_evaluator.py`: Scores each source on trust, freshness, relevance, grounding
- `contradiction_analyzer.py`: Cross-source conflict detection
- Both are integrated into `graph.py` as pipeline nodes

### 13.2 Evidence Persistence in Session

Currently evidence findings are lost between turns. They should be accumulated:

```python
class SessionEvidence(BaseModel):
    """Accumulated evidence across conversation turns."""
    retrieved_guidelines: List[Dict] = []      # high-trust sources (trust > 0.85)
    research_findings: List[Dict] = []         # PubMed results
    graph_findings: str = ""                   # Neo4j accumulated facts
    similar_cases: str = ""                    # similar case matches
    multimodal_findings: str = ""              # ECG/Xray/OCR findings
    evidence_quality_history: List[str] = []  # ["strong", "adequate", ...]
```

### 13.3 Evidence Ranking for Copilot Context

When building copilot context, prioritize evidence in this order:
1. Authoritative guidelines (trust > 0.90) — ALWAYS include
2. Systematic reviews / RCTs (trust > 0.85) — include if relevant
3. Graph knowledge facts — always include
4. Multimodal findings (ECG/imaging) — always include if present
5. Similar cases — include if confidence < 0.80
6. Research findings (PubMed) — summarize only

The total copilot context for evidence should be capped at 2000 tokens.

---

## 14. CLARIFICATION LOOP DESIGN

### 14.1 Current Clarification Flow (Phase 12)

```
POST /analyze/ → clarification_required=True
  → status: "clarification_required"
  → clarification_questions: [{question_id, question_text, ...}]

Doctor answers → POST /analyze/clarify/
  → Full re-run with clarification_answers
  → status: "success"
```

**Problem**: This is a TWO-STEP HTTP flow. In the conversational model, the clarification should happen WITHIN the chat, not via a separate endpoint.

### 14.2 Conversational Clarification Flow

```
Doctor: "Patient has chest pain"
Aegis: "To give you the most accurate analysis, could you tell me:
  1. How long has the chest pain been present?
  2. Is there any radiation to the arm or jaw?
  3. Any known cardiac history?
  [SKIP and proceed anyway] [Submit answers]"

Doctor: [types answers directly in chat or clicks submit]
Aegis: [runs full analysis with enriched context]
```

Implementation: The `clarification_required` check in the planner stays. But instead of returning the questions as a blocking gate, the copilot endpoint PRESENTS them as a conversation message. The doctor's NEXT message is the answer.

### 14.3 Clarification Resolution in Conversational Mode

```python
def _is_clarification_response(
    message: str,
    session: ConversationalPatientSession,
) -> bool:
    """
    Returns True if this message looks like an answer to pending clarification.
    Checks: session.clarification_pending == True AND message contains clinical data.
    """

def _resolve_clarification_from_chat(
    message: str,
    pending_questions: list[ClarificationQuestion],
) -> dict:
    """
    Maps the doctor's conversational answer to structured clarification_answers dict.
    Uses NLP to extract answers for each pending question from free-form text.
    """
```

---

## 15. IMPLEMENTATION PHASES

### Phase 13A — Fix Critical Blockers (IMMEDIATE PRIORITY)

**Goal**: Make the copilot actually work. Fix the 404 error.

#### 13A STATUS: ✅ COMPLETE (2026-05-21)

Files created/modified:
- ✅ `backend/api/copilot_api.py` — NEW: Groq-powered copilot endpoint with session context enrichment
- ✅ `backend/api/session_api.py` — NEW: Session management REST API
- ✅ `backend/models/session.py` — NEW: ConversationalPatientSession, AccumulatedPatientContext, AnalysisSnapshot
- ✅ `backend/session/session_store.py` — NEW: In-memory TTL session store
- ✅ `backend/session/__init__.py` — NEW: Session module init
- ✅ `backend/api/agentic.py` — UPDATED: session_id support in /analyze/ and /analyze/clarify/
- ✅ `backend/main.py` — UPDATED: copilot_router + session_router registered, v13.0.0
- ✅ `frontend/src/types/clinical.ts` — UPDATED: Session, ConversationMessage, CopilotRequest/Response types
- ✅ `frontend/src/services/analysisService.ts` — UPDATED: askCopilot(), createSession(), getSessionSummary(), deleteSession()
- ✅ `frontend/src/stores/workspaceStore.ts` — UPDATED: sessionId, messages, patientContext, rightTab
- ✅ `frontend/src/components/workspace/OrchestraCopilot.tsx` — FIXED: now calls askCopilot() (no more 404)

Verification:
- ✅ Python compile check: ALL 5 new backend modules compile clean
- ✅ agentic.py + main.py compile clean
- ✅ TypeScript compile: ZERO ERRORS

```python
# backend/api/copilot_api.py (NEW FILE)

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from backend.utils.logger import logger
from backend.api.rate_limiter import limiter

router = APIRouter(prefix="/analyze", tags=["copilot"])

class CopilotRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    clinical_context: str = Field(default="")
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    session_id: Optional[str] = None          # Phase 13: session support

class CopilotResponse(BaseModel):
    answer: str
    sources_used: List[str] = []
    confidence: str = "medium"
    session_id: Optional[str] = None

@router.post("/copilot/", response_model=CopilotResponse)
@limiter.limit("60/minute")
async def copilot_chat(request: Request, body: CopilotRequest) -> CopilotResponse:
    """
    Context-aware clinical copilot chat endpoint.
    
    Accepts:
    - question: The doctor's question
    - clinical_context: Current patient context + analysis summary
    - conversation_history: Last N turns of conversation
    - session_id: Optional session ID for persistent state
    
    Returns: Contextual answer grounded in current patient state.
    """
```

#### 13A.2 Register copilot router in `backend/main.py`

```python
from backend.api.copilot_api import router as copilot_router
app.include_router(copilot_router)
```

#### 13A.3 Groq-powered copilot implementation

The copilot endpoint should call Groq with a carefully crafted system prompt:

```python
COPILOT_SYSTEM_PROMPT = """
You are Aegis Copilot, a clinical intelligence assistant integrated into the 
Aegis Clinical AI System. You assist physicians by answering questions about 
specific patient cases, clinical evidence, and orchestration findings.

You have access to:
- Current patient context (demographics, vitals, symptoms, history)
- Analysis findings (confidence, clinical intent, risk level)
- Evidence quality summary (trust scores, source types)
- Contradiction findings (if any conflicts detected)
- Missing information gaps

Guidelines:
1. Always ground your answers in the provided patient context and evidence.
2. Be concise. Physicians are busy. Max 200 words unless detail is critical.
3. If you're uncertain, say so explicitly. Never hallucinate clinical facts.
4. Reference evidence quality when making recommendations.
5. Always recommend physician judgment for final clinical decisions.
6. If the question requires a new full analysis, say so.
"""
```

### Phase 13B — Session Infrastructure

**Goal**: Add persistent conversation state.

#### 13B.1 Create Session Models and Store

Create:
- `backend/models/session.py` — Session data models
- `backend/session/session_store.py` — In-memory session store
- `backend/api/session_api.py` — Session management endpoints

#### 13B.2 Update Analysis API for Session Support

```python
# Extended AnalyzeRequest
class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=8000)
    clarification_answers: Optional[Dict[str, str]] = None
    session_id: Optional[str] = None    # NEW: session continuity
    
# Extended AnalyzeResponse
class AnalyzeResponse(BaseModel):
    # ... existing fields ...
    session_id: Optional[str] = None    # NEW: session ID for next turn
```

### Phase 13C — Frontend Transformation

**Goal**: Transform workspace from form-first to chat-first.

#### 13C.1 New Workspace Layout

```
┌─ Header ─────────────────────────────────────────────────────────────────────┐
│  Æ Aegis Clinical Intelligence  |  Patient: [ID] [New] | [Governance] [Docs] │
├────────────────────┬────────────────────────────────────┬─────────────────────┤
│  LEFT SIDEBAR      │  CENTER: CHAT WORKSPACE            │  RIGHT: INTELLIGENCE │
│  (300px)           │  (flex-1)                          │  (340px)            │
│                    │                                    │                     │
│  Patient Context   │  ┌ Message from Aegis ─────────── │  ┌ Orchestration ─  │
│  ─────────────     │  │ 🧬 Clinical Analysis Complete   │  │ Clinical Intent   │
│  Age: 65M          │  │ Risk: HIGH | Confidence: MEDIUM │  │ Evidence Quality  │
│  Chief: STEMI      │  │ [View Full Report]              │  │ Contradictions    │
│  Risk: HIGH        │  └─────────────────────────────── │  │ Governance Status │
│                    │                                    │  └───────────────── │
│  Evidence Summary  │  ┌ Doctor ──────────────────────  │                     │
│  ─────────────     │  │ Why was confidence only MEDIUM? │  ┌ Evidence Panel ─ │
│  ✅ 8 high-quality │  └─────────────────────────────── │  │ EvidenceScorecard │
│  ⚠️ 2 filtered    │                                    │  │ Sources (ranked)  │
│                    │  ┌ Aegis ───────────────────────  │  │ Contradiction     │
│  Files Uploaded    │  │ Confidence was MEDIUM because:  │  │ Alert (if any)    │
│  ─────────────     │  │ • ECG quality: 0.72 confidence  │  └───────────────── │
│  📊 ECG_001.png    │  │ • 2 evidence sources filtered   │                     │
│  📋 Discharge.pdf  │  │ • Troponin values missing       │  ┌ Similar Cases ─  │
│                    │  └─────────────────────────────── │  │ 3 similar patients│
│  [+ Upload File]   │                                    │  │ from case memory  │
│                    │  ┌─────────────────────────────── │  └───────────────── │
│  Session History   │  │ Type a message or drag a file   │                     │
│  ─────────────     │  │ [📎] [🎤]         [Send ↵]     │  ┌ Governance ────  │
│  Turn 1: STEMI     │  └─────────────────────────────── │  │ HITL Status       │
│  Turn 3: ECG       │                                    │  │ Escalation State  │
│                    │                                    │  └───────────────── │
└────────────────────┴────────────────────────────────────┴─────────────────────┘
```

#### 13C.2 Core Interaction Flows for the Chat

**Flow A — New Case via Chat**:
```
Doctor types: "65yo male, crushing chest pain, BP 160/100..."
    ↓ UI: Shows typing animation
    ↓ Service: detectMessageIntent() → NEW_PATIENT_CASE
    ↓ Service: POST /session/new → session_id
    ↓ Service: POST /analyze/ { query, session_id }
    ↓ UI: Shows live orchestration stages (SSE stream)
    ↓ UI: Renders <MessageBubble type="report"> with results
    ↓ UI: Updates PatientContextSidebar from response
    ↓ UI: Shows smart prompt suggestions
```

**Flow B — Follow-up Question**:
```
Doctor types: "Why was confidence MEDIUM?"
    ↓ UI: Shows typing animation
    ↓ Service: detectMessageIntent() → FOLLOW_UP_QUESTION
    ↓ Service: POST /analyze/copilot/ { question, clinical_context, session_id }
    ↓ UI: Renders <MessageBubble type="copilot"> with answer
```

**Flow C — File Upload in Chat**:
```
Doctor drags ECG onto chat
    ↓ UI: Shows file preview in chat input
    ↓ Service: POST /upload/ { file }
    ↓ UI: Shows "ECG uploaded" chip in chat
    ↓ Service: POST /analyze/ { query: "Analyze the uploaded ECG in context", session_id }
    ↓ UI: Renders ECG findings as message
```

#### 13C.3 Updated WorkspaceStore

```typescript
interface WorkspaceStore {
  // Session management
  sessionId: string | null;
  setSessionId: (id: string) => void;
  clearSession: () => void;
  
  // Conversation messages
  messages: ConversationMessage[];
  addMessage: (msg: ConversationMessage) => void;
  clearMessages: () => void;
  
  // Patient context (dynamically populated)
  patientContext: PatientContextSummary | null;
  setPatientContext: (ctx: PatientContextSummary) => void;
  
  // Last analysis result
  lastResult: AnalysisResult | null;
  setLastResult: (result: AnalysisResult) => void;
  
  // UI state
  isOrchestrating: boolean;
  orchestrationStage: string;
  setOrchestrating: (v: boolean, stage?: string) => void;
  
  // File uploads
  files: UploadedFile[];
  addFile: (f: UploadedFile) => void;
  removeFile: (id: string) => void;
  
  // Right panel tabs
  rightTab: "orchestration" | "evidence" | "cases" | "governance";
  setRightTab: (tab: string) => void;
}
```

### Phase 13D — Streaming Orchestration Updates

**Goal**: Show real-time progress during analysis.

#### 13D.1 SSE Endpoint Design

```python
# backend/api/agentic.py — new SSE endpoint

from fastapi.responses import StreamingResponse
import json, asyncio

@router.post("/analyze/stream/")
async def analyze_stream(request: Request, body: AnalyzeRequest):
    """
    SSE-streaming version of /analyze/.
    Pushes stage updates during execution.
    """
    async def event_generator():
        # Stage 1
        yield f"data: {json.dumps({'stage': 'planning', 'message': '🧠 Understanding clinical intent...'})}\n\n"
        
        # Run workflow with stage callbacks
        result = await run_workflow(
            query=body.query,
            session_id=body.session_id,
            stage_callback=lambda stage: asyncio.create_task(
                queue.put(stage)
            )
        )
        
        # Final result
        yield f"data: {json.dumps({'stage': 'complete', 'result': result})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

#### 13D.2 Frontend SSE Consumption

```typescript
// services/analysisService.ts

export async function runAnalysisWithStreaming(
  query: string,
  sessionId: string | null,
  onStageUpdate: (stage: string, message: string) => void,
  onComplete: (result: AnalysisResult) => void,
) {
  const response = await fetch(`${API_BASE}/analyze/stream/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const lines = decoder.decode(value).split("\n\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const event = JSON.parse(line.slice(6));
        if (event.stage === "complete") {
          onComplete(event.result);
        } else {
          onStageUpdate(event.stage, event.message);
        }
      }
    }
  }
}
```

### Phase 13E — Cleanup

**Goal**: Remove dead code. Validate everything works end-to-end.

#### 13E.1 Delete Decision Agent

```bash
# Verify no live imports first:
grep -r "decision_agent" backend/
# Expected: only __init__.py (the registration) — safe to remove both
del backend/agents/decision_agent.py
```

Update `backend/agents/__init__.py` to remove `decision_agent` reference.

#### 13E.2 Consolidate Workflow Templates

```bash
# Verify no live imports:
grep -r "from backend.workflows" backend/
grep -r "import workflows" backend/
# If clean, delete the entire module:
del backend/workflows/
```

The workflow configuration values (escalation thresholds, etc.) should be migrated to `backend/decision/schemas.py` constants if any are still needed.

---

## 16. PENDING TASKS CHECKLIST

### Phase 13A — Critical Fixes (DO FIRST)

- [ ] Create `backend/api/copilot_api.py` with Groq-powered `/analyze/copilot/` endpoint
- [ ] Register `copilot_router` in `backend/main.py`
- [ ] Test: `POST /analyze/copilot/` with question + clinical_context → verify real answer
- [ ] Verify OrchestraCopilot.tsx works end-to-end (currently 404)

### Phase 13B — Session Infrastructure

- [ ] Create `backend/models/session.py` with Session models
- [ ] Create `backend/session/__init__.py`
- [ ] Create `backend/session/session_store.py` with in-memory TTL store
- [ ] Create `backend/api/session_api.py` with create/get/delete endpoints
- [ ] Register `session_router` in `backend/main.py`
- [ ] Update `AnalyzeRequest` to accept `session_id: Optional[str]`
- [ ] Update `AnalyzeResponse` to return `session_id: Optional[str]`
- [ ] Update `run_workflow()` in `graph.py` to accept and use session context
- [ ] Update `_initial_state()` to pull accumulated patient context from session
- [ ] Update `_build_response()` in `agentic.py` to call `update_session_from_analysis()`

### Phase 13C — Frontend Transformation

- [ ] Design and implement new 3-panel chat-first workspace layout in `workspace/page.tsx`
- [ ] Create `ConversationalChatPanel.tsx` — primary chat interface
- [ ] Create `PatientContextSidebar.tsx` — dynamic left sidebar
- [ ] Create `LiveOrchestrationPanel.tsx` — right panel with tabbed intelligence views
- [ ] Create `InlineFileUpload.tsx` — drag/drop inline in chat input
- [ ] Create `MessageBubble.tsx` — rich message types (report, copilot, clarification, research)
- [ ] Create `OrchestrationStageBar.tsx` — live stage progress
- [ ] Update `workspaceStore.ts` for session + conversation state
- [ ] Update `analysisService.ts` for session-aware API calls
- [ ] Update `clinical.ts` types with Session, ConversationMessage types
- [ ] Implement `detectMessageIntent()` client-side classification
- [ ] Wire dynamic smart prompt suggestions based on session state

### Phase 13D — Streaming

- [ ] Add SSE streaming to `/analyze/stream/` endpoint in `agentic.py`
- [ ] Add stage callback mechanism to `run_workflow()` in `graph.py`
- [ ] Add stage emissions in each graph node (plan, retrieve, evidence_eval, etc.)
- [ ] Frontend SSE consumer in `analysisService.ts`
- [ ] Frontend live stage progress rendering in chat UI

### Phase 13E — Cleanup

- [ ] Verify `decision_agent.py` has no live callers
- [ ] Delete `backend/agents/decision_agent.py`
- [ ] Remove `decision_agent` from `backend/agents/__init__.py`
- [ ] Verify `backend/workflows/` has no live callers
- [ ] Delete `backend/workflows/` directory
- [ ] End-to-end test: Full conversation flow (new case → follow-up → upload ECG → research request)
- [ ] End-to-end test: Governance still enforced
- [ ] End-to-end test: Clarification loop in chat mode
- [ ] End-to-end test: Session persistence across 5+ turns
- [ ] Verify TypeScript: `cd frontend && npx tsc --noEmit`
- [ ] Version bump: `main.py` → 13.0.0

---

## 17. RISKS AND REFACTOR NOTES

### Risk 1: Session Memory Leak

**Risk**: The in-memory session store will grow unbounded if cleanup is not run.

**Mitigation**: 
- Add TTL-based cleanup (2-hour sessions)
- Add background cleanup task on FastAPI startup
- Add MAX_SESSIONS limit with LRU eviction
- In production: migrate to Redis

### Risk 2: Context Window Overflow in Copilot

**Risk**: If session accumulates many turns, the copilot's context may exceed Groq's token limit.

**Mitigation**:
- Hard limit: last 6 messages only in conversation_history
- Evidence block: truncate each to 500 chars
- Patient context: serialize to compact string (~500 tokens max)
- Total copilot context budget: 3000 tokens

### Risk 3: SSE Connection Drops

**Risk**: Long-running analysis (15–30 seconds) may cause SSE timeout or connection drop.

**Mitigation**:
- Send heartbeat events every 5 seconds
- Frontend reconnects if connection drops
- Fallback to polling `/session/{id}/status` if SSE fails

### Risk 4: Breaking Governance

**Risk**: Session-aware orchestration could inadvertently bypass governance checks.

**Mitigation**:
- `finalize_response()` in `supervisor_agent.py` is NEVER bypassed
- Copilot endpoint has its own disclaimer logic (never presents analysis as final)
- Session-aware runs still go through full LangGraph pipeline
- Audit logging preserved for all runs

### Risk 5: Frontend Performance with Growing Chat

**Risk**: Long conversation with many messages and embedded reports will slow down React rendering.

**Mitigation**:
- Virtualize the message list (react-window or similar)
- Collapse report messages by default (show header, expand on click)
- Paginate session history (load last 20 messages initially)

### Risk 6: The OrchestraCopilot Build vs. New ConversationalChatPanel

**Risk**: The existing `OrchestraCopilot.tsx` component was built as a panel tab. The new `ConversationalChatPanel.tsx` will be the primary interface. There is overlap.

**Decision**: 
- `OrchestraCopilot.tsx` becomes the IMPLEMENTATION of the copilot logic (the API call layer)
- `ConversationalChatPanel.tsx` is the NEW primary UI that uses OrchestraCopilot as an underlying service
- OR: Merge them and rewrite OrchestraCopilot from scratch as the main chat panel

**Recommendation**: Rewrite `OrchestraCopilot.tsx` as the full `ConversationalChatPanel.tsx`. The current implementation is too small (250 lines) to be the main interface. The new component will be ~500-800 lines.

### Risk 7: Backward Compatibility During Migration

**Risk**: The existing `/workspace` page structure has been tested. Changing it breaks the existing workflows users depend on.

**Mitigation**:
- Keep existing `PatientIntakePanel.tsx` available but move it to the sidebar
- Keep the "Analyze" button but embed it in the chat input
- Keep `AnalysisPanel.tsx` but render it as a collapsible message in chat
- The existing backend API contract is UNCHANGED — only new endpoints added

### Risk 8: Copilot Security

**Risk**: The copilot endpoint is unauthenticated and could be abused.

**Mitigation**:
- Rate limiting: 60/minute (already in rate_limiter.py)
- The existing JWT auth system can be applied to copilot endpoint
- Groq costs: monitor via Sentry + logging

---

## KEY DESIGN INVARIANTS (NEVER VIOLATE)

1. **Emergency bypass**: `risk_level=CRITICAL` ALWAYS skips clarification. Never block emergencies.
2. **Governance preserved**: `finalize_response()` governance code NEVER bypassed.
3. **Observability preserved**: All telemetry hooks preserved in all new code.
4. **No autonomous agent swarm**: Every agent execution is tracked, bounded, supervised.
5. **Evidence filtering is conservative**: Only filter evidence with `overall_quality < 0.30`.
6. **Clarification is non-blocking**: If doctor skips clarification, system proceeds with caveat.
7. **Backward API compat**: `POST /analyze/` signature and response schema only ADD fields, never remove.
8. **LLM for reasoning, rules for safety**: Sufficiency/contradiction engines remain rule-based.
9. **Session is optional**: All endpoints work without a session_id (stateless fallback).
10. **Copilot answers are advisory**: Always include disclaimer that final decision is physician's.

---

## CONTINUATION INSTRUCTIONS FOR NEXT SESSION

```
IMMEDIATE PRIORITY:
1. Implement backend/api/copilot_api.py (Phase 13A)
2. Register it in backend/main.py
3. Test that OrchestraCopilot.tsx now works end-to-end

THEN:
4. Build backend/models/session.py and session_store.py
5. Build backend/api/session_api.py
6. Update agentic.py for session_id support

THEN:
7. Redesign frontend workspace/page.tsx to chat-first layout
8. Build ConversationalChatPanel.tsx
9. Update workspaceStore.ts and analysisService.ts

VERIFY EACH STEP:
- Backend: uvicorn backend.main:app --reload --port 8000
- Frontend: cd frontend && npm run dev
- Test copilot: POST http://localhost:8000/analyze/copilot/ 
  { "question": "What are the contraindications for tPA in this patient?",
    "clinical_context": "65yo male, STEMI, BP 185/105, no known allergies" }
  Expected: 200 OK with contextual medical answer

DO NOT:
- Delete governance code
- Delete observability code
- Delete GraphRAG
- Delete multimodal analysis
- Restart from scratch
- Change existing /analyze/ endpoint signature
```

---

## REFERENCE: COMPLETE FILE INVENTORY

```
backend/
├── agents/
│   ├── orchestration_planner.py   ✅ Phase 12 — KEEP, enhance for multi-turn
│   ├── decision_agent.py          ⚠️ OBSOLETE — delete in Phase 13E
│   ├── query_agent.py             ✅ KEEP unchanged
│   ├── retrieval_agent.py         ✅ KEEP unchanged
│   ├── reasoning_agent.py         ✅ KEEP unchanged
│   ├── validation_agent.py        ✅ KEEP unchanged
│   ├── reflection_agent.py        ✅ KEEP unchanged
│   └── supervisor_agent.py        ✅ KEEP, minor updates for session
│
├── api/
│   ├── agentic.py                 ✅ Extend: session_id, SSE streaming
│   ├── copilot_api.py             🆕 CREATE (Phase 13A — CRITICAL)
│   ├── session_api.py             🆕 CREATE (Phase 13B)
│   ├── governance_api.py          ✅ KEEP unchanged
│   ├── multimodal_api.py          ✅ KEEP unchanged
│   ├── upload.py                  ✅ KEEP unchanged
│   ├── retrieve.py                ✅ KEEP unchanged
│   ├── health.py                  ✅ KEEP unchanged
│   └── rate_limiter.py            ✅ KEEP unchanged
│
├── auth/                          ✅ KEEP unchanged
├── config.py                      ✅ KEEP unchanged
│
├── decision/
│   ├── decision_layer.py          ✅ KEEP unchanged
│   ├── risk_engine.py             ✅ KEEP unchanged
│   ├── workflow_router.py         ✅ KEEP unchanged
│   ├── schemas.py                 ✅ KEEP unchanged
│   ├── source_policy.py           ✅ KEEP unchanged
│   ├── execution_plan.py          ✅ Phase 12 — KEEP
│   ├── information_sufficiency_engine.py  ✅ Phase 12 — KEEP
│   └── clarification_engine.py    ✅ Phase 12 — KEEP
│
├── evaluation/
│   ├── evidence_evaluator.py      ✅ Phase 12 — KEEP
│   ├── contradiction_analyzer.py  ✅ Phase 12 — KEEP
│   ├── grounding_engine.py        ✅ KEEP unchanged
│   ├── failure_analytics.py       ✅ KEEP unchanged
│   └── metrics.py                 ✅ KEEP unchanged
│
├── governance/                    ✅ KEEP ALL unchanged
├── graphrag/                      ✅ KEEP ALL unchanged
├── models/
│   ├── state.py                   ✅ Extend: session_id, conversation_history fields
│   └── session.py                 🆕 CREATE (Phase 13B)
│
├── monitoring/                    ✅ KEEP ALL unchanged
├── multimodal/                    ✅ KEEP ALL unchanged
├── observability/                 ✅ KEEP ALL unchanged
├── orchestration/
│   └── graph.py                   ✅ Extend: session context, stage callbacks
│
├── rag/                           ✅ KEEP ALL unchanged
├── research/                      ✅ KEEP ALL unchanged
├── session/                       🆕 CREATE directory (Phase 13B)
│   ├── __init__.py                🆕 CREATE
│   └── session_store.py           🆕 CREATE
│
├── telemetry/                     ✅ KEEP ALL unchanged
├── utils/                         ✅ KEEP ALL unchanged
├── validation/                    ✅ KEEP ALL unchanged
├── worker.py                      ✅ KEEP unchanged
├── main.py                        ✅ Extend: register new routers, v13.0.0
└── workflows/                     ⚠️ Review for deletion in Phase 13E

frontend/src/
├── app/
│   ├── workspace/page.tsx         🔴 REDESIGN: chat-first layout
│   ├── governance/                ✅ KEEP unchanged
│   ├── dashboard/                 ✅ KEEP unchanged
│   ├── layout.tsx                 ✅ Minor update: title
│   └── globals.css                ✅ Add chat-specific styles
│
├── components/workspace/
│   ├── ConversationalChatPanel.tsx  🆕 CREATE (Phase 13C — PRIMARY INTERFACE)
│   ├── PatientContextSidebar.tsx    🆕 CREATE (Phase 13C)
│   ├── LiveOrchestrationPanel.tsx   🆕 CREATE (Phase 13C)
│   ├── InlineFileUpload.tsx         🆕 CREATE (Phase 13C)
│   ├── MessageBubble.tsx            🆕 CREATE (Phase 13C)
│   ├── OrchestrationStageBar.tsx    🆕 CREATE (Phase 13D)
│   ├── OrchestraCopilot.tsx         ⚠️ Rebuild as part of ChatPanel or absorb
│   ├── AnalysisPanel.tsx            ✅ KEEP (used inside MessageBubble as report)
│   ├── PatientIntakePanel.tsx       ✅ Adapt for sidebar context display
│   ├── GovernancePanel.tsx          ✅ KEEP (shown in right panel)
│   ├── FileUploadZone.tsx           ✅ KEEP (also used in InlineFileUpload)
│   ├── ClarificationPanel.tsx       ✅ KEEP (now appears as message type)
│   ├── ExecutionPlanViewer.tsx      ✅ KEEP (shown in right panel)
│   ├── EvidenceScorecard.tsx        ✅ KEEP (shown in right panel)
│   ├── ContradictionAlert.tsx       ✅ KEEP (shown in right panel + as message)
│   └── SufficiencyGauge.tsx         ✅ KEEP (shown in sidebar)
│
├── services/
│   └── analysisService.ts          ✅ Extend: session, SSE, copilot functions
│
├── stores/
│   └── workspaceStore.ts           ✅ Redesign: session + conversation state
│
└── types/
    └── clinical.ts                 ✅ Extend: Session, ConversationMessage types
```

---

*Last updated: 2026-05-21 by Antigravity (Principal AI Orchestration Architect)*  
*Phase: 13 — Conversational Adaptive Orchestration Copilot*  
*Status: PLAN COMPLETE — Implementation begins with Phase 13A*
