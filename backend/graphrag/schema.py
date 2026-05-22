"""
schema.py — Medical Knowledge Graph Schema (Phase 6)

Defines the complete node/relationship taxonomy and Cypher DDL for
production-grade Neo4j graph constraints and indexes.

Node Labels (13 types):
  Disease, Symptom, Drug, Procedure, Biomarker,
  ClinicalFinding, Treatment, Guideline,
  PatientCase, Medication, LabResult, Gene, RiskFactor

Relationship Types (15 types):
  HAS_SYMPTOM, TREATED_BY, CONTRAINDICATED_WITH,
  ASSOCIATED_WITH, INDICATES, RELATED_TO, CAUSED_BY,
  IMPROVES_WITH, HAS_RISK, HAS_LAB_RESULT,
  INTERACTS_WITH, PART_OF, DIAGNOSED_WITH,
  SIMILAR_TO, HAS_PROCEDURE

Design rules:
  - Every node has a canonical `name` (normalised lowercase)
  - Every node has `source` (ingestion origin) and `confidence` (0.0–1.0)
  - Every relationship has `weight` (0.0–1.0) and `provenance` string
  - `SIMILAR_TO` between PatientCase nodes uses `similarity_score` property
"""
from __future__ import annotations

# ── Cypher DDL: Constraints + Indexes ─────────────────────────────────────────
SCHEMA_CYPHER: list[str] = [
    # Uniqueness constraints
    "CREATE CONSTRAINT disease_name IF NOT EXISTS FOR (n:Disease) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT drug_name IF NOT EXISTS FOR (n:Drug) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT symptom_name IF NOT EXISTS FOR (n:Symptom) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT procedure_name IF NOT EXISTS FOR (n:Procedure) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT biomarker_name IF NOT EXISTS FOR (n:Biomarker) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT treatment_name IF NOT EXISTS FOR (n:Treatment) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT guideline_id IF NOT EXISTS FOR (n:Guideline) REQUIRE n.guideline_id IS UNIQUE",
    "CREATE CONSTRAINT patient_case_id IF NOT EXISTS FOR (n:PatientCase) REQUIRE n.case_id IS UNIQUE",
    "CREATE CONSTRAINT medication_name IF NOT EXISTS FOR (n:Medication) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT lab_result_name IF NOT EXISTS FOR (n:LabResult) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT gene_name IF NOT EXISTS FOR (n:Gene) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT risk_factor_name IF NOT EXISTS FOR (n:RiskFactor) REQUIRE n.name IS UNIQUE",
    # Fulltext index for fuzzy entity lookup
    "CREATE FULLTEXT INDEX medical_entity_text IF NOT EXISTS "
    "FOR (n:Disease|Drug|Symptom|Procedure|Treatment|Medication) ON EACH [n.name, n.aliases]",
    # Relationship property index for filtering by confidence
    "CREATE INDEX rel_confidence IF NOT EXISTS FOR ()-[r:HAS_SYMPTOM]-() ON (r.weight)",
]

# ── Node label taxonomy ────────────────────────────────────────────────────────
NODE_LABELS = {
    "Disease", "Symptom", "Drug", "Procedure", "Biomarker",
    "ClinicalFinding", "Treatment", "Guideline",
    "PatientCase", "Medication", "LabResult", "Gene", "RiskFactor",
}

# ── Relationship type taxonomy ─────────────────────────────────────────────────
RELATIONSHIP_TYPES = {
    "HAS_SYMPTOM",         # Disease → Symptom
    "TREATED_BY",          # Disease → Treatment|Drug|Procedure
    "CONTRAINDICATED_WITH",# Drug → Drug | Drug → Disease
    "ASSOCIATED_WITH",     # Symptom|Biomarker → Disease
    "INDICATES",           # Biomarker|LabResult → Disease|ClinicalFinding
    "RELATED_TO",          # generic bidirectional concept similarity
    "CAUSED_BY",           # Disease → Disease|RiskFactor|Gene
    "IMPROVES_WITH",       # Disease|Symptom → Drug|Treatment
    "HAS_RISK",            # Disease|Drug → RiskFactor
    "HAS_LAB_RESULT",      # Disease|PatientCase → LabResult
    "INTERACTS_WITH",      # Drug → Drug (pharmacological interaction)
    "PART_OF",             # Symptom → Disease (pathophysiology)
    "DIAGNOSED_WITH",      # PatientCase → Disease
    "SIMILAR_TO",          # PatientCase → PatientCase (episodic similarity)
    "HAS_PROCEDURE",       # Disease|PatientCase → Procedure
}

# ── Minimum confidence thresholds by extraction source ───────────────────────
CONFIDENCE_THRESHOLDS = {
    "llm_extraction":   0.70,   # LLM-extracted relationships
    "rule_extraction":  0.85,   # Rule-based / regex extraction
    "human_curated":    0.98,   # Human-validated (guidelines)
    "similarity_calc":  0.65,   # Algorithm-calculated similarity
}

# ── Max traversal depth limits (prevent explosion) ───────────────────────────
TRAVERSAL_LIMITS = {
    "drug_interaction":    2,    # max 2 hops for drug-drug interactions
    "symptom_diagnosis":   3,    # max 3 hops for symptom → disease
    "similar_case":        2,    # max 2 hops for case similarity
    "treatment_pathway":   4,    # max 4 hops for full treatment chain
    "default":             2,
}
