from dotenv import load_dotenv
import os

load_dotenv()

# ── Infrastructure ────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL     = os.getenv("QDRANT_URL", "http://localhost:6333")

# ── Phase 3 — Agentic Workflow Settings ───────────────────────────────────────
REASONING_MODEL      = os.getenv("REASONING_MODEL", "gpt-4o-mini")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
MAX_RETRIES          = int(os.getenv("MAX_RETRIES", "3"))
RETRIEVAL_TOP_K      = int(os.getenv("RETRIEVAL_TOP_K", "5"))
EXPANDED_TOP_K       = int(os.getenv("EXPANDED_TOP_K", "8"))
