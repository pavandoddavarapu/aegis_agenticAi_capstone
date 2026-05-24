"""
copilot_api.py — Aegis Clinical Copilot Endpoint (Phase 13)

This endpoint powers the OrchestraCopilot chat panel.

Previously: OrchestraCopilot.tsx called POST /analyze/copilot/ which did NOT exist
→ 404 error on every copilot question → graceful degradation to offline fallbacks.

Phase 13 fix: This endpoint implements the copilot using the Groq LLM with
full access to:
  - Current patient clinical context (extracted patient data)
  - Last analysis findings (confidence, clinical intent, risk, evidence quality)
  - Contradiction report (if conflicts detected)
  - Missing information gaps
  - Conversation history (last N turns)

Design principles:
  1. The copilot is ADVISORY — never presents answers as final clinical decisions.
  2. Context-grounded — always references provided patient/evidence context.
  3. Concise — physicians are busy; default max 250 words.
  4. Evidence-aware — references evidence quality when making recommendations.
  5. Graceful degradation — if LLM fails, returns a rule-based fallback.
  6. Rate-limited — 60/minute (same as /analyze/).
"""
import os
import time
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from openai import OpenAI

from backend.utils.logger import logger
from backend.api.rate_limiter import limiter
from backend.session.session_store import session_store
from backend.utils.groq_pool import groq_chat_with_retry

router = APIRouter(prefix="/analyze", tags=["copilot"])


# ── LLM Configuration ─────────────────────────────────────────────────────────

COPILOT_MODEL   = "gemini-2.0-flash" if os.getenv("GEMINI_API_KEY") else ("llama-3.3-70b-versatile" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini")
COPILOT_TOKENS  = 400
COPILOT_TEMP    = 0.25       # low temperature → consistent, reproducible answers


# ── System Prompt ─────────────────────────────────────────────────────────────

COPILOT_SYSTEM_PROMPT = """You are Aegis Copilot, a clinical intelligence assistant embedded inside the Aegis Clinical AI System.

You serve two modes:

**Mode 1 — General Medical Knowledge Q&A** (when no patient context is provided)
Answer educational and factual medical questions directly and concisely. Examples:
- "What are the symptoms of sinusitis?"
- "How does metformin work?"
- "Explain the pathophysiology of pulmonary embolism"
For these, give a clear, evidence-based answer. Do NOT ask for patient details.

**Mode 2 — Patient Case Analysis Q&A** (when patient context is provided)
Answer specific questions about the analyzed case. Ground every answer in the provided context.

STRICT GUIDELINES:
1. NEVER ask for patient demographics/vitals for general knowledge questions.
2. GROUND patient-specific answers in the provided clinical context and evidence. Never invent clinical facts.
3. Be CONCISE. Physicians are busy. Aim for 100-200 words unless the question demands detail.
4. When evidence quality is LOW or WEAK, explicitly say so in your answer.
5. When contradictions exist, mention them and recommend physician judgment.
6. Always end answers that involve clinical recommendations with a disclaimer about professional judgment.
7. Use clinical language appropriate for physicians.
8. Format responses with bullet points or short sections when listing multiple items.

DISCLAIMER TO INCLUDE when making clinical recommendations:
"⚕️ This is AI-assisted analysis. Final clinical decisions require physician judgment."
"""



# ── Request / Response Models ──────────────────────────────────────────────────

class CopilotRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The physician's question about the current patient case.",
    )
    clinical_context: str = Field(
        default="",
        max_length=4000,
        description=(
            "Serialized patient context string from the frontend. Should include: "
            "clinical intent, confidence, evidence quality, key findings, "
            "missing info, patient demographics."
        ),
    )
    conversation_history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Last N turns of conversation. Each item: {role, content}.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for persistent conversation state.",
    )


class CopilotResponse(BaseModel):
    answer: str
    sources_used: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    processing_ms: int = 0
    session_id: Optional[str] = None


# ── Context Builder ────────────────────────────────────────────────────────────

def _build_copilot_user_message(
    question: str,
    clinical_context: str,
) -> str:
    """
    Build the user-turn message for the copilot LLM.
    Combines the clinical context with the physician's question.
    """
    context_block = ""
    if clinical_context.strip():
        context_block = (
            f"## Current Patient & Analysis Context\n"
            f"{clinical_context.strip()}\n\n"
        )

    return (
        f"{context_block}"
        f"## Physician Question\n"
        f"{question.strip()}"
    )


def _build_messages(
    question: str,
    clinical_context: str,
    conversation_history: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    Build the full messages list for the LLM call.
    - System prompt (always first)
    - Last ≤6 conversation turns (for multi-turn continuity)
    - Current user message (with clinical context injected)
    """
    messages = [{"role": "system", "content": COPILOT_SYSTEM_PROMPT}]

    # Include last 6 turns of conversation history (3 user + 3 assistant)
    safe_history = conversation_history[-6:] if conversation_history else []
    for turn in safe_history:
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content.strip():
            messages.append({"role": role, "content": content[:800]})  # cap each turn

    # Current question with context
    user_message = _build_copilot_user_message(question, clinical_context)
    messages.append({"role": "user", "content": user_message})

    return messages


# ── Rule-Based Fallback ────────────────────────────────────────────────────────

def _rule_based_fallback(question: str, clinical_context: str) -> str:
    """
    Context-aware rule-based fallback when the LLM is unavailable.
    Returns a useful answer based on pattern matching.
    """
    q = question.lower().strip()
    ctx = clinical_context.lower()

    # Friendly greeting fallback
    if q in ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings") or len(q) < 5:
        return "Hello! How can I assist you with your patient cases today?"

    if not clinical_context.strip():
        # No patient context — check if this is a general medical knowledge question
        q_lower = q.lower()
        import re
        is_general = bool(re.match(
            r"^(what|how|why|when|is|are|can|does|do|explain|define|describe|list|which|who|where)",
            q_lower
        ))
        if is_general:
            return (
                "I'd be happy to answer that general medical question. "
                "However, I'm running in offline mode right now — please check that the backend LLM service is available. "
                "In the meantime, I recommend consulting UpToDate, PubMed, or clinical guidelines for this topic."
            )
        return (
            "Please describe your clinical question or patient case, and I'll assist you. "
            "You can also run a full patient analysis to get detailed AI-powered insights."
        )


    # Confidence-related questions
    if any(k in q for k in ["confidence", "why low", "why medium", "score"]):
        if "evidence_quality: weak" in ctx or "overall_sufficiency: weak" in ctx:
            return (
                "The confidence score was reduced due to weak evidence quality. "
                "Some retrieved sources had low trust scores or were filtered out. "
                "Consider providing additional clinical details (vitals, medications, ECG) "
                "to improve evidence retrieval quality."
            )
        if "missing" in ctx:
            return (
                "The confidence score reflects information gaps in the clinical picture. "
                "The system detected missing critical information (check the 'Information Gaps' section). "
                "Providing complete vitals, medication list, and history would improve confidence."
            )
        return (
            "Confidence reflects the combined quality of retrieved evidence and "
            "the grounding of the clinical analysis. Review the Evidence tab for "
            "source quality scores."
        )

    # Contraindication / drug interaction questions
    if any(k in q for k in ["contraindication", "drug", "interaction", "medication", "allerg"]):
        if "contradiction" in ctx and "has_contradictions: true" in ctx:
            return (
                "⚠️ Contradictions were detected in the evidence sources. "
                "The system identified conflicting recommendations — review the Contradiction Alert "
                "for details. Always verify medication decisions against current drug references.\n\n"
                "⚕️ This is AI-assisted analysis. Final clinical decisions require physician judgment."
            )
        return (
            "No drug contradictions were flagged in this analysis. "
            "However, always cross-reference the patient's current medication list "
            "against the most current prescribing guidelines.\n\n"
            "⚕️ This is AI-assisted analysis. Final clinical decisions require physician judgment."
        )

    # Differential diagnosis
    if any(k in q for k in ["differential", "diagnosis", "rule out", "ddx"]):
        return (
            "The differential diagnosis is detailed in the Clinical Intelligence Report. "
            "Review the 'Differential Diagnosis' section for the prioritized list "
            "based on current evidence and clinical context."
        )

    # Evidence quality questions
    if any(k in q for k in ["evidence", "quality", "sources", "trust", "research"]):
        return (
            "Evidence quality details are in the Evidence tab (right panel). "
            "Key metrics: avg trust score, high-quality source count, filtered count. "
            "Sources are ranked by: guidelines > RCTs > observational studies."
        )

    # Risk / escalation questions
    if any(k in q for k in ["risk", "escalat", "critical", "urgent", "emergenc"]):
        return (
            "Risk assessment is shown in the execution plan. "
            "If escalation was flagged, the case requires clinical review. "
            "Emergency cases automatically bypass clarification and receive priority evidence retrieval."
        )

    # Missing info questions
    if any(k in q for k in ["missing", "gap", "need", "provide", "what else"]):
        return (
            "The Information Gaps panel (Plan tab) shows what clinical data the system "
            "detected as missing. Providing these details in a follow-up analysis "
            "will improve evidence quality and confidence."
        )

    # Generic fallback
    return (
        "Based on the current analysis findings, please refer to the Clinical Intelligence Report "
        "for detailed reasoning. If you have a specific clinical question about this patient, "
        "please be more specific and I'll do my best to address it from the available evidence."
    )


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/copilot/",
    response_model=CopilotResponse,
    summary="Aegis Clinical Copilot Chat (Phase 13)",
)
@limiter.limit("60/minute")
async def copilot_chat(
    request: Request,
    body: CopilotRequest,
) -> CopilotResponse:
    """
    Context-aware clinical copilot chat endpoint.

    Answers physician questions about:
    - The current patient case
    - Evidence quality and source trust
    - Contradiction findings
    - Clinical reasoning explanations
    - Risk and escalation status
    - Missing information gaps

    Uses the Groq LLM (llama-3.3-70b-versatile) with clinical context injection.
    Falls back to rule-based answers if LLM is unavailable.

    NOT a general-purpose chatbot:
    - Always grounded in current patient analysis context
    - Includes evidence quality awareness
    - Includes governance / escalation state awareness
    - Adds clinical disclaimers to all recommendations

    Phase 13: When session_id is provided, context is enriched from the
    accumulated ConversationalPatientSession state.
    """
    import asyncio
    start_ms = time.time()
    question = body.question.strip()
    logger.info(
        f"[CopilotAPI] Question: '{question[:80]}' "
        f"context_len={len(body.clinical_context)} "
        f"history_turns={len(body.conversation_history)} "
        f"session_id={body.session_id}"
    )

    # ── Phase 13: Session-aware context enrichment ────────────────────────────
    clinical_context     = body.clinical_context
    conversation_history = body.conversation_history

    session = None
    if body.session_id:
        session = session_store.get(body.session_id)
        if session:
            # Build richer context from accumulated session state
            session_context = session.build_copilot_context()
            if session_context and session_context != clinical_context:
                # Prefer session context (more complete) but keep body context as fallback
                clinical_context = session_context if session_context.strip() else clinical_context

            # Use session conversation history if not provided
            if not conversation_history:
                conversation_history = session.get_recent_history(6)

            logger.debug(
                f"[CopilotAPI] Session enriched context: "
                f"{len(session_context)} chars, "
                f"{len(conversation_history)} history turns"
            )

    sources_used = ["clinical_context", "conversation_history"]

    # ── Phase 13: Detect research intent and execute live query ───────────────
    lower_question = question.lower()
    research_keywords = ["research", "search", "wikipedia", "pubmed", "clinical trial", "lookup", "find out about", "latest study", "latest literature", "evidence on", "medical data"]
    if any(k in lower_question for k in research_keywords):
        try:
            logger.info(f"[CopilotAPI] Research intent detected in question. Invoking ResearchAgent...")
            from backend.research.research_agent import ResearchAgent
            research_agent = ResearchAgent()
            
            # Extract clean search query
            search_query = question
            for k in research_keywords + ["please", "can you", "for me"]:
                search_query = search_query.replace(k, "")
            search_query = search_query.strip("? . , ! \n\t")
            if not search_query or len(search_query.split()) < 2:
                search_query = question
                
            # Query concurrently
            pubmed_task = research_agent.pubmed.search(search_query, max_results=3)
            trials_task = research_agent.clinical_trials.search_trials(search_query, max_results=2)
            wiki_task = research_agent.wikipedia.search_articles(search_query, max_results=3)
            
            pmids, trials, wiki_docs = await asyncio.gather(pubmed_task, trials_task, wiki_task)
            
            papers = []
            if pmids:
                papers = await research_agent.pubmed.fetch_summaries(pmids)
                
            all_docs = papers + trials + wiki_docs
            if all_docs:
                ranked_docs = research_agent.ranker.rank_papers(search_query, all_docs, top_k=5)
                research_context = research_agent.context_manager.format_research_context(ranked_docs)
                if research_context:
                    clinical_context = f"{clinical_context}\n\n=== DYNAMIC RESEARCH EVIDENCE ===\n{research_context}"
                    for doc in ranked_docs:
                        title = doc.get("title", "")
                        src = doc.get("source", "Wikipedia")
                        sources_used.append(f"{src}: {title}")
                        
            await asyncio.gather(
                research_agent.pubmed.close(),
                research_agent.clinical_trials.close(),
                research_agent.wikipedia.close(),
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"[CopilotAPI] Dynamic research failed: {e}")

    try:
        messages = _build_messages(
            question             = question,
            clinical_context     = clinical_context,
            conversation_history = conversation_history,
        )

        # Use key pool — automatically rotates to next key on 429/connection errors
        response = groq_chat_with_retry(
            model       = COPILOT_MODEL,
            messages    = messages,
            max_tokens  = COPILOT_TOKENS,
            temperature = COPILOT_TEMP,
        )

        answer = response.choices[0].message.content.strip()
        elapsed_ms = int((time.time() - start_ms) * 1000)

        logger.info(
            f"[CopilotAPI] Answer generated: {len(answer)} chars in {elapsed_ms}ms"
        )

        # ── Phase 13: Append to session history ───────────────────────────────
        if session:
            session.add_message("user",      question,  message_type="text")
            session.add_message("assistant",  answer,    message_type="text")
            session_store.update(session)

        return CopilotResponse(
            answer        = answer,
            sources_used  = sources_used,
            confidence    = "high" if len(clinical_context) > 200 else "medium",
            processing_ms = elapsed_ms,
            session_id    = body.session_id,
        )

    except Exception as exc:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        logger.warning(f"[CopilotAPI] LLM call failed: {exc} — using rule-based fallback")

        # Graceful degradation: rule-based fallback
        fallback_answer = _rule_based_fallback(question, clinical_context)

        # Still append to session even on LLM failure
        if session:
            session.add_message("user",     question,        message_type="text")
            session.add_message("assistant", fallback_answer, message_type="text")
            session_store.update(session)

        return CopilotResponse(
            answer        = fallback_answer,
            sources_used  = ["rule_based_fallback"],
            confidence    = "low",
            processing_ms = elapsed_ms,
            session_id    = body.session_id,
        )
