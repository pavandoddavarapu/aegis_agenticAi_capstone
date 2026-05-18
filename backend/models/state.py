from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    query: str
    retrieved_docs: List[Dict[str, Any]]
    reasoning_output: str
    validation_score: float
    retry_count: int
    workflow_path: List[str]
    final_response: str
