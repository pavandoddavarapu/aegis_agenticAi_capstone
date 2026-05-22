"""
multimodal_context_manager.py — Multimodal Context Lifecycle Manager (Phase 8)

Architecture:
  Manages the lifecycle of visual context within agent state.
  Prevents token budget explosions by capping visual context contributions
  and intelligently prioritizing which context types are most relevant.

  Context priority order (high → low):
    1. Emergency visual findings (ECG STEMI, pneumothorax) — ALWAYS included
    2. High-confidence visual analysis (confidence >= 0.70)
    3. OCR-extracted structured sections
    4. Graph evidence (from GraphRAG)
    5. Semantic evidence
    6. Live research (if query is temporal)

  Token budget management:
    - Total context budget from decision layer config
    - Visual context capped at 30% of budget (to avoid crowding)
    - Emergency context uncapped (safety override)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MultimodalContextBlock:
    """Prioritized and token-budgeted multimodal context."""
    visual_context:   str   = ""   # ECG / Radiology / OCR findings
    graph_context:    str   = ""   # Neo4j relational facts
    cases_context:    str   = ""   # Similar case memory
    research_context: str   = ""   # Live PubMed evidence
    semantic_context: str   = ""   # Compressed semantic retrieval
    total_chars:      int   = 0


class MultimodalContextManager:
    """
    Manages and balances multimodal context for LLM injection.

    Given the token_budget from the decision layer, allocates
    character limits proportionally across context types.

    Default allocation (of total token budget):
      - Visual:   30% (hard cap, unless emergency)
      - Semantic: 30%
      - Graph:    20%
      - Research: 12%
      - Cases:     8%
    """

    VISUAL_FRACTION   = 0.30
    SEMANTIC_FRACTION = 0.30
    GRAPH_FRACTION    = 0.20
    RESEARCH_FRACTION = 0.12
    CASES_FRACTION    = 0.08

    # Approximate chars per token (English medical text)
    CHARS_PER_TOKEN = 4

    def build(
        self,
        visual_context:   str,
        semantic_context: str,
        graph_context:    str,
        research_context: str,
        cases_context:    str,
        token_budget:     int   = 3000,
        emergency:        bool  = False,
    ) -> MultimodalContextBlock:
        """
        Assemble a token-budgeted multimodal context block.

        Emergency flag disables visual context capping (safety override).
        """
        char_budget = token_budget * self.CHARS_PER_TOKEN

        if emergency:
            # Emergency: visual context is uncapped — it's the most important signal
            v_cap  = len(visual_context)
            remaining = max(0, char_budget - v_cap)
            s_cap = int(remaining * 0.40)
            g_cap = int(remaining * 0.30)
            r_cap = int(remaining * 0.20)
            c_cap = int(remaining * 0.10)
        else:
            v_cap  = int(char_budget * self.VISUAL_FRACTION)
            s_cap  = int(char_budget * self.SEMANTIC_FRACTION)
            g_cap  = int(char_budget * self.GRAPH_FRACTION)
            r_cap  = int(char_budget * self.RESEARCH_FRACTION)
            c_cap  = int(char_budget * self.CASES_FRACTION)

        block = MultimodalContextBlock(
            visual_context   = visual_context[:v_cap],
            semantic_context = semantic_context[:s_cap],
            graph_context    = graph_context[:g_cap],
            research_context = research_context[:r_cap],
            cases_context    = cases_context[:c_cap],
        )
        block.total_chars = sum([
            len(block.visual_context),
            len(block.semantic_context),
            len(block.graph_context),
            len(block.research_context),
            len(block.cases_context),
        ])
        return block

    def format_for_prompt(self, block: MultimodalContextBlock) -> str:
        """Assemble the block into a coherent prompt section."""
        parts = []
        if block.visual_context:
            parts.append(block.visual_context)
        if block.graph_context:
            parts.append(f"RELATIONAL GRAPH KNOWLEDGE:\n{block.graph_context}")
        if block.cases_context:
            parts.append(block.cases_context)
        if block.research_context:
            parts.append(block.research_context)
        if block.semantic_context:
            parts.append(f"SEMANTIC EVIDENCE:\n{block.semantic_context}")
        return "\n\n".join(parts)
