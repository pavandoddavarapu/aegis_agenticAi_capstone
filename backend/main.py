"""
main.py — Aegis Clinical Intelligence System (Phase 13)

Phase 12 additions:
  - OrchestrationPlanner (replaces decision_agent) — adaptive intent-aware planning
  - InformationSufficiencyEngine — pre-execution clinical context check
  - ClarificationEngine — pre-execution clarification loop
  - EvidenceEvaluator — per-source trust + quality scoring
  - ContradictionAnalyzer — cross-source conflict detection
  - POST /analyze/clarify/ — new clarification endpoint
  - ContinuousSupervisorMonitor — proactive evidence quality monitoring

Phase 13 additions (Conversational Orchestration Copilot):
  - POST /analyze/copilot/ — context-aware clinical copilot chat endpoint
  - POST /session/ — conversational session management (create/get/delete)
  - ConversationalPatientSession — persistent multi-turn patient state
  - Version bumped to 13.0.0
"""
import os
from dotenv import load_dotenv
load_dotenv(override=True)

import sentry_sdk
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes          import router
from backend.api.health          import router as health_router
from backend.api.upload          import router as upload_router
from backend.api.retrieve        import router as retrieve_router
from backend.api.agentic         import router as agentic_router
from backend.api.multimodal_api  import router as multimodal_router
from backend.api.governance_api  import router as governance_router
from backend.auth.router         import router as auth_router
from backend.api.rate_limiter    import setup_rate_limiting
from backend.api.copilot_api     import router as copilot_router   # Phase 13
from backend.api.session_api     import router as session_router    # Phase 13
from backend.monitoring          import monitoring_router
from backend.telemetry           import telemetry_bus
from backend.utils.logger        import logger


# ── Sentry Setup ─────────────────────────────────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    logger.info("[Main] Sentry initialized.")

# ── Lifespan: start / gracefully stop the telemetry bus ──────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context — initialises and drains the telemetry bus."""
    logger.info("[Main] Starting Aegis Clinical Intelligence System v13.0.0")
    await telemetry_bus.start()
    logger.info("[Main] TelemetryBus started.")
    yield
    logger.info("[Main] Shutting down — flushing telemetry...")
    await telemetry_bus.stop()
    logger.info("[Main] Shutdown complete.")


app = FastAPI(
    title       = "Aegis Clinical Intelligence System",
    version     = "13.0.0",
    description = (
        "Conversational Adaptive Clinical Orchestration Copilot — Phase 13: "
        "OrchestrationPlanner + ClinicalCopilot + ConversationalPatientSession + "
        "EvidenceEvaluator + ContradictionAnalyzer + ContinuousSupervisorMonitor"
    ),
    lifespan    = lifespan,
)

# ── Phase 11: Setup Rate Limiting ─────────────────────────────────────────────
setup_rate_limiting(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route registration ────────────────────────────────────────────────────────
app.include_router(auth_router)          # Phase 11: auth endpoints
app.include_router(router)
app.include_router(health_router)
app.include_router(upload_router)
app.include_router(retrieve_router)
app.include_router(agentic_router)
app.include_router(copilot_router)       # Phase 13: clinical copilot chat
app.include_router(session_router)       # Phase 13: conversational session management
app.include_router(monitoring_router)    # Phase 5: observability endpoints
app.include_router(multimodal_router)    # Phase 8: ECG/Radiology/OCR endpoints
app.include_router(governance_router)    # Phase 9: HITL governance endpoints


@app.get("/")
def root():
    return {
        "message": "Aegis Clinical AI Backend Running",
        "phase":   "Phase 13 — Conversational Adaptive Orchestration Copilot",
        "endpoints": {
            # Core agentic
            "analyze":         "POST /analyze/",
            "clarify":         "POST /analyze/clarify/",
            # Phase 13: Conversational Copilot
            "copilot":         "POST /analyze/copilot/",
            "session_create":  "POST /session/",
            "session_get":     "GET  /session/{session_id}",
            "session_delete":  "DELETE /session/{session_id}",
            # RAG pipeline
            "upload":          "POST /upload/",
            "retrieve":        "POST /retrieve/",
            # Infrastructure health
            "health":          "GET  /health/qdrant | /health/redis | /health/postgres",
            # Phase 5: Observability
            "metrics":         "GET  /monitoring/metrics",
            "workflow_trace":  "GET  /monitoring/workflow/{request_id}",
            "timeline":        "GET  /monitoring/timeline/{request_id}",
            "agent_latency":   "GET  /monitoring/agent-latency",
            "retrieval_stats": "GET  /monitoring/retrieval-stats",
            "failure_analysis":"GET  /monitoring/failure-analysis",
            "eval_summary":    "GET  /monitoring/evaluation/summary",
            "mon_health":      "GET  /monitoring/health",
            # API docs
            "docs":            "GET  /docs",
        },
        "observability": {
            "telemetry_bus": telemetry_bus.get_stats(),
        },
    }
