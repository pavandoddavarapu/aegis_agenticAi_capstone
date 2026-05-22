"""
agents/ — Phase 3 agentic workflow components.

Each agent is a pure function:
    (state: AgentState) -> dict   # partial state update

Agents are intentionally small and modular. The Supervisor
orchestrates them via the LangGraph state machine defined in
backend/orchestration/graph.py.
"""
