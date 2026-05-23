---
title: Aegis Backend
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---
# Aegis Clinical Intelligence System

Aegis is an advanced Clinical AI platform designed for clinical intelligence, agentic workflows, medical retrieval-augmented generation (RAG), and clinical validation.

## Repository Structure

```text
aegis-clinical-ai/
│
├── backend/
│   ├── api/             # FastAPI routes and endpoints
│   │   ├── health.py    # Infrastructure health checks
│   │   ├── upload.py    # Document ingestion endpoint
│   │   ├── retrieve.py  # Phase 2 direct retrieval endpoint
│   │   └── agentic.py   # Phase 3 POST /analyze — flagship endpoint
│   ├── agents/          # Modular agent implementations (Phase 3)
│   │   ├── retrieval_agent.py   # Fetches evidence from Qdrant
│   │   ├── reasoning_agent.py   # LLM synthesis grounded in evidence
│   │   ├── validation_agent.py  # Deterministic confidence scoring
│   │   ├── reflection_agent.py  # Adaptive query expansion + retry
│   │   └── supervisor_agent.py  # Routing + finalisation brain
│   ├── orchestration/   # LangGraph workflow graph (Phase 3)
│   │   └── graph.py     # Compiled StateGraph, run_workflow()
│   ├── rag/             # Retrieval-augmented generation & search
│   ├── validation/      # Clinical accuracy & guardrails
│   ├── workflows/       # LangGraph and state workflows
│   ├── memory/          # Short and long-term memory
│   ├── observability/   # Tracing, logging, and evaluation
│   ├── models/          # Data schemas and model definitions
│   │   └── state.py     # AgentState — shared workflow state
│   ├── utils/           # Shared utility functions
│   └── main.py          # FastAPI application entrypoint
│
├── frontend/            # Next.js or Vite React interface
├── docker/              # Docker configuration files
├── docs/                # Project documentation and specifications
├── tests/               # Unit, integration, and clinical tests
│
├── .env                 # Environment variables configuration
├── requirements.txt     # Python core dependencies
├── docker-compose.yml   # Multi-container orchestration (Qdrant, Redis, Postgres)
└── README.md            # Project overview & documentation
```

---

## Phase 3 — Adaptive Agentic Workflow

### Architecture

```
User Query
    │
    ▼
Supervisor Agent (orchestration brain)
    │
    ▼
Retrieval Agent  ──>  Qdrant Vector DB
    │
    ▼
Clinical Reasoning Agent  ──>  LLM (gpt-4o-mini)
    │                          [grounded in evidence ONLY]
    ▼
Validation Agent  (deterministic — no LLM)
    │
    ▼  supervisor_router()
   / \
  /   \
GOOD   BAD
  │      │
  ▼      ▼
Final  Reflection Agent
       (expand query, re-retrieve)
            │
            └──── loop back to Retrieval Agent
                  (up to MAX_RETRIES=3)
```

### Agents

| Agent | Role | LLM? |
|-------|------|-------|
| **Retrieval Agent** | Fetches top-k evidence chunks from Qdrant | No |
| **Reasoning Agent** | Synthesises grounded clinical analysis | Yes (gpt-4o-mini) |
| **Validation Agent** | Scores confidence (evidence + grounding + completeness) | No |
| **Reflection Agent** | Diagnoses failure, expands query, re-retrieves | No |
| **Supervisor Agent** | Routes workflow, enforces retries, finalises response | No |

### Validation Scoring

```
composite_score = 0.40 x evidence_score
               + 0.40 x grounding_score
               + 0.20 x completeness_score

confidence_threshold = 0.65   (configurable via env)
```

### Flagship Endpoint

**`POST /analyze/`**

```json
// Request
{ "query": "What are first-line treatments for type 2 diabetes?" }

// Response
{
  "query": "...",
  "reasoning": "## Clinical Analysis\n...",
  "final_response": "...",
  "evidence": [...],
  "evidence_count": 5,
  "confidence_score": 0.782,
  "confidence_label": "HIGH",
  "validation_detail": "Validation PASSED | score=0.782 ...",
  "workflow_trace": ["retrieve", "reason", "validate", "finalize"],
  "retry_count": 0,
  "reflection_notes": "",
  "processing_ms": 2340,
  "status": "success"
}
```

The `workflow_trace` field shows the exact execution path through the agent graph — enabling full explainability.

---

## Getting Started

### 1. Setup Virtual Environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# .env
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333

# Optional Phase 3 tuning
REASONING_MODEL=gpt-4o-mini
CONFIDENCE_THRESHOLD=0.65
MAX_RETRIES=3
RETRIEVAL_TOP_K=5
EXPANDED_TOP_K=8
```

### 4. Start Infrastructure Containers

```bash
docker-compose up -d
```

This will run:
- **Qdrant Vector DB** on port `6333`
- **Redis Cache/Memory** on port `6379`
- **Postgres Database** on port `5432`

### 5. Run the Backend API

```bash
uvicorn backend.main:app --reload
```

The API will be available at `http://127.0.0.1:8000` with interactive documentation at `http://127.0.0.1:8000/docs`.

"# aegis_agenticAi_capstone"
