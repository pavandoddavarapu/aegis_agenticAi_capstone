from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.api.health import router as health_router
from backend.api.upload import router as upload_router
from backend.api.retrieve import router as retrieve_router

app = FastAPI(
    title="Aegis Clinical Intelligence System",
    version="2.0.0",
    description="Production Medical Evidence Retrieval Engine — Phase 2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core routes ────────────────────────────────────────────────────────────────
app.include_router(router)
app.include_router(health_router)

# ── Phase 2: RAG Pipeline routes ───────────────────────────────────────────────
app.include_router(upload_router)
app.include_router(retrieve_router)


@app.get("/")
def root():
    return {
        "message": "Aegis Clinical AI Backend Running",
        "phase": "Phase 2 — Medical Evidence Retrieval Engine",
        "endpoints": {
            "upload":   "POST /upload/",
            "retrieve": "POST /retrieve/",
            "health":   "GET  /health/qdrant | /health/redis | /health/postgres",
            "docs":     "GET  /docs",
        }
    }

