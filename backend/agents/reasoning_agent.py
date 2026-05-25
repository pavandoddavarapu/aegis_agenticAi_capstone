"""
reasoning_agent.py — Clinical Reasoning Agent (Phase 8 — Multimodal upgrade)

Responsibilities
────────────────
• Receive retrieved evidence from state.
• Build a grounded clinical analysis using an LLM.
• ALWAYS ground reasoning in retrieved evidence — never hallucinate.
• Store structured analysis in state["reasoning_output"].

Design principle: the LLM is a *synthesizer*, not an oracle.
It only interprets evidence that the retrieval agent already fetched.
"""
import os
import json
from backend.models.state import AgentState
from backend.utils.logger import logger
from backend.utils.groq_pool import groq_chat_with_retry
from backend.guardrails import PromptGuardrail  # Phase 14

_prompt_guardrail = PromptGuardrail()


# ── LLM Configuration ─────────────────────────────────────────────────────────
REASONING_MODEL = "llama-3.3-70b-versatile" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"
MAX_TOKENS      = 800
TEMPERATURE     = 0.2                    # low temp → consistent medical output


# ── Evidence Formatting ────────────────────────────────────────────────────────

def _format_evidence(docs: list) -> str:
    """Format retrieved docs into a numbered evidence block for the prompt."""
    if not docs:
        return "No evidence retrieved."

    lines = []
    for i, doc in enumerate(docs, 1):
        conf   = doc.get("confidence", "unknown")
        score  = doc.get("score", 0)
        source = doc.get("source", "unknown")
        page   = doc.get("page", 0)
        text   = doc.get("text", "").strip()[:600]       # cap each chunk
        lines.append(
            f"[Evidence {i}] (confidence={conf}, score={score:.3f}, "
            f"source={source}, page={page})\n{text}"
        )
    return "\n\n".join(lines)


# ── Prompt Template ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Aegis, an expert clinical AI assistant.
Your role is to analyze medical evidence and provide structured clinical reasoning.

STRICT RULES:
1. Base ALL analysis solely on the provided evidence — never invent facts.
2. Cite evidence numbers (e.g., [Evidence 1]) and research refs ([Research 1]) in reasoning.
3. Explicitly state when evidence is insufficient or conflicting.
4. Structure your response EXACTLY with these sections: Summary | Key Findings | Similar Cases (if provided) | Clinical Implications | Limitations.
5. Use professional medical language appropriate for clinicians.
6. MULTIMODAL RULES (when visual evidence is present):
   a. Explicitly acknowledge visual findings before drawing implications.
   b. Clearly label AI-derived visual observations vs. established evidence.
   c. State: "These are AI-assisted observations and require clinical confirmation."
   d. If an emergency flag is raised (ECG/Radiology), highlight this prominently in Summary.
   e. Distinguish: [Visual Finding] vs [Guideline Evidence] vs [Research Evidence]
"""

USER_PROMPT_TEMPLATE = """CLINICAL QUERY:
{query}

{visual_block}

{graph_block}

{cases_block}

{research_block}

SEMANTIC EVIDENCE:
{evidence}

Provide a structured clinical analysis grounded in all evidence above.
When visual findings are present, acknowledge and integrate them explicitly.
"""


# ── Patient Context Extraction from Report ─────────────────────────────────────

def _extract_patient_context_from_report(reasoning_text: str) -> dict:
    try:
        model = "llama-3.1-8b-instant" if os.getenv("GROQ_API_KEY") else "gpt-4o-mini"
        prompt = f"""You are a clinical data extraction assistant.
Analyze the following clinical reasoning report and extract structured patient data.

Return ONLY a JSON object with this exact structure:
{{
  "age": "<string, e.g. 65>",
  "gender": "<string, male or female>",
  "chief_complaint": "<string, primary complaint>",
  "vitals": {{
    "bp": "<string, e.g. 140/92>",
    "hr": "<string, e.g. 92>",
    "o2": "<string, e.g. 89%>",
    "temp": "<string, e.g. 37.1>",
    "rr": "<string, e.g. 20>"
  }},
  "symptoms": ["<list of strings>"],
  "extracted_conditions": ["<list of conditions like diabetes, hypertension>"],
  "medications": ["<list of medications>"],
  "allergies": ["<list of allergies>"]
}}

No other text or formatting. If a field is missing, use null or empty list/dict.

Report:
{reasoning_text}
"""
        messages = [{"role": "user", "content": prompt}]
        res = groq_chat_with_retry(
            model=model,
            messages=messages,
            max_tokens=300,
            temperature=0.0
        )
        content = res.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content.strip())
        return data
    except Exception as e:
        logger.warning(f"Failed to extract patient context from report: {e}")
        return {}


# ── Agent Node ────────────────────────────────────────────────────────────────

def reasoning_agent(state: AgentState) -> dict:
    """
    Clinical Reasoning Agent node (Phase 8 — Multimodal).

    Synthesizes: semantic + graph + cases + research + visual findings.
    Reads:  state["query"], state["compressed_context"], state["retrieved_docs"],
            state["graph_context"], state["similar_cases_context"],
            state["live_research_context"], state["visual_context"]
    Writes: state["reasoning_output"], state["workflow_path"]
    """
    query   = state.get("query", "")
    docs    = state.get("retrieved_docs", [])

    # Phase 4: prefer pre-compressed context; fall back to raw formatting
    compressed = state.get("compressed_context", "").strip()

    logger.info(
        f"[ReasoningAgent] Reasoning over {len(docs)} chunks "
        f"for query: '{query[:80]}'"
    )

    # Phase 6, 7 & 8: Graph, Case, Research, and Visual Context
    graph_ctx    = state.get("graph_context", "").strip()
    cases_ctx    = state.get("similar_cases_context", "").strip()
    research_ctx = state.get("live_research_context", "").strip()
    visual_ctx   = state.get("visual_context", "").strip()

    # Multimodal: allow visual, research, cases, or graph context to substitute for missing docs
    if not docs and not visual_ctx and not graph_ctx and not cases_ctx and not research_ctx:
        logger.warning("[ReasoningAgent] No evidence — returning fallback.")
        return {
            "reasoning_output": (
                "Insufficient evidence: no relevant documents or visual inputs were retrieved "
                "for this query. Please ingest relevant medical literature or upload an image."
            ),
            "workflow_path": ["reason"],
        }

    # Phase 8 emergency flag — prepend prominent warning if raised
    emergency_flag   = state.get("image_emergency_flag", False)
    emergency_reason = state.get("image_emergency_reason", "")
    emergency_prefix = ""
    if emergency_flag:
        emergency_prefix = (
            f"\n\n⚠️ EMERGENCY SIGNAL DETECTED: {emergency_reason}\n"
            "This requires IMMEDIATE clinical evaluation. See visual findings below.\n"
        )

    visual_block   = (emergency_prefix + visual_ctx) if visual_ctx else emergency_prefix
    graph_block    = f"RELATIONAL GRAPH KNOWLEDGE:\n{graph_ctx}" if graph_ctx else ""
    cases_block    = cases_ctx if cases_ctx else ""
    research_block = research_ctx if research_ctx else ""

    evidence_block = compressed if compressed else _format_evidence(docs)
    prompt         = USER_PROMPT_TEMPLATE.format(
        query=query,
        evidence=evidence_block,
        visual_block=visual_block,
        graph_block=graph_block,
        cases_block=cases_block,
        research_block=research_block,
    )

    try:
        # Phase 14: Prompt Guardrail — validate messages before LLM call
        messages_to_send = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
        prompt_check = _prompt_guardrail.check(messages_to_send)
        if not prompt_check.safe:
            logger.warning(f"[ReasoningAgent] Prompt blocked by guardrail: {prompt_check.block_reason}")
            return {
                "reasoning_output": (
                    f"⚠️ Clinical reasoning blocked by safety guardrail: "
                    f"{prompt_check.block_reason}"
                ),
                "workflow_path": ["reason"],
                "error": f"PromptGuardrail: {prompt_check.block_reason}",
            }
        if prompt_check.warnings:
            for w in prompt_check.warnings:
                logger.warning(f"[ReasoningAgent] PromptGuardrail warning: {w}")

        # Use key pool — automatically rotates to next key on 429/connection errors
        response = groq_chat_with_retry(
            model=REASONING_MODEL,
            messages=prompt_check.sanitized_messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        reasoning = response.choices[0].message.content.strip()
        logger.info("[ReasoningAgent] Reasoning complete.")

        # Extract patient context dynamically from the reasoning report
        extracted_ctx = _extract_patient_context_from_report(reasoning)
        state_ctx = dict(state.get("patient_context") or {})
        if extracted_ctx:
            for k, v in extracted_ctx.items():
                if v:
                    state_ctx[k] = v
            # Set presence flags for orchestration planners / UI
            if extracted_ctx.get("vitals"):
                state_ctx["vitals_present"] = True
                # Map structured vitals to expected flat format if needed
                state_ctx["extracted_vitals"] = {**state_ctx.get("extracted_vitals", {}), **extracted_ctx["vitals"]}
            if extracted_ctx.get("medications"):
                state_ctx["medications_present"] = True
                state_ctx["extracted_medications"] = list(set(state_ctx.get("extracted_medications", []) + extracted_ctx["medications"]))
            if extracted_ctx.get("allergies"):
                state_ctx["allergies_present"] = True
            if extracted_ctx.get("extracted_conditions"):
                state_ctx["history_present"] = True

        return {
            "reasoning_output": reasoning,
            "patient_context":  state_ctx,
            "workflow_path":    ["reason"],
        }

    except Exception as exc:
        logger.exception(f"[ReasoningAgent] LLM call failed: {exc}")
        # Graceful degradation: return evidence summary without LLM
        fallback = (
            f"LLM reasoning unavailable ({str(exc)}). "
            f"Raw evidence summary:\n\n{evidence_block[:1200]}"
        )
        return {
            "reasoning_output": fallback,
            "workflow_path":    ["reason"],
            "error":            f"Reasoning error: {str(exc)}",
        }
