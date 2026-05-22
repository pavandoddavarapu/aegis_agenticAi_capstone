export const mockWorkflowData = {
  request_id: "wf-1092-abc",
  query: "Patient with chest pain ST elevation and hypotension",
  query_type: "emergency",
  risk_level: "critical",
  workflow: "emergency_workflow",
  retrieval_strategy: "hybrid_guideline_priority",
  validation_policy: "critical",
  reflection_strategy: "emergency",
  escalation_decision: true,
  
  timeline: [
    { node: "query_understand", duration_ms: 110, success: true },
    { node: "retrieve", duration_ms: 420, success: true },
    { node: "rerank", duration_ms: 150, success: true },
    { node: "compress", duration_ms: 60, success: true },
    { node: "reason", duration_ms: 2100, success: true },
    { node: "validate", duration_ms: 45, success: false }, // Failed first time
    { node: "reflect", duration_ms: 800, success: true },
    { node: "retrieve", duration_ms: 380, success: true }, // Retry
    { node: "reason", duration_ms: 1850, success: true },
    { node: "validate", duration_ms: 40, success: true },
    { node: "finalize", duration_ms: 15, success: true },
  ],

  retrieval: {
    dense_hits: 15,
    sparse_hits: 10,
    reranker_lift: 0.32,
    compression_ratio: 0.65,
    confidence_evolution: [0.45, 0.62, 0.88, 0.95],
    top_chunks: [
      { id: "guideline_acs_1", score: 0.94, text: "In patients with STEMI and hypotension..." },
      { id: "case_study_55", score: 0.89, text: "Immediate PCI is indicated..." },
      { id: "protocol_v2", score: 0.81, text: "Avoid beta-blockers in cardiogenic shock..." },
    ]
  },

  grounding: {
    hallucination_score: 0.05,
    evidence_coverage: 0.92,
    unsupported_claims: 1,
    grounding_confidence: 0.94,
    claims: [
      { text: "Patient requires immediate PCI.", supported: true },
      { text: "Beta-blockers are contraindicated due to hypotension.", supported: true },
      { text: "Aspirin 300mg should be administered.", supported: false }, // Unsupported by retrieved context
    ]
  },

  reflection: {
    trigger_reason: "Low confidence on medication contraindications",
    retry_count: 1,
    confidence_before: 0.65,
    confidence_after: 0.94,
    expanded_query: "STEMI hypotension cardiogenic shock beta blocker contraindications",
  }
};
