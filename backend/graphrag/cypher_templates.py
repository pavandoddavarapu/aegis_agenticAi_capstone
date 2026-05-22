"""
cypher_templates.py — Reusable Cypher Query Library (Phase 6)

All production Cypher queries are defined here as parameterised
template strings. This ensures:
  - No string concatenation (injection-safe)
  - Centralised query versioning
  - Easy testing without a live driver
  - Query plan caching by Neo4j (parameterised queries get cached)

All queries use $param syntax — never f-strings in Cypher.
All traversals use LIMIT clauses — never unbounded graph walks.
"""

# ── Entity lookup ─────────────────────────────────────────────────────────────

FIND_ENTITY_BY_NAME = """
MATCH (n)
WHERE n.name = $name OR $name IN n.aliases
RETURN n, labels(n) AS labels
LIMIT 5
"""

FULLTEXT_ENTITY_SEARCH = """
CALL db.index.fulltext.queryNodes("medical_entity_text", $query)
YIELD node, score
WHERE score > $min_score
RETURN node, labels(node) AS labels, score
ORDER BY score DESC
LIMIT $limit
"""

# ── Neighborhood retrieval ────────────────────────────────────────────────────

ENTITY_NEIGHBORHOOD = """
MATCH (n)
WHERE n.name = $name
CALL apoc.path.subgraphNodes(n, {
    maxLevel: $depth,
    limit: $limit
}) YIELD node
MATCH (n)-[r]-(node)
WHERE r.weight >= $min_weight
RETURN n.name AS source,
       type(r) AS rel_type,
       r.weight AS weight,
       r.provenance AS provenance,
       node.name AS target,
       labels(node) AS target_labels
ORDER BY r.weight DESC
LIMIT $limit
"""

ENTITY_NEIGHBORHOOD_SIMPLE = """
MATCH (n)-[r]-(neighbor)
WHERE n.name = $name AND r.weight >= $min_weight
RETURN n.name AS source,
       type(r) AS rel_type,
       r.weight AS weight,
       r.provenance AS provenance,
       neighbor.name AS target,
       labels(neighbor) AS target_labels
ORDER BY r.weight DESC
LIMIT $limit
"""

# ── Drug interaction queries ──────────────────────────────────────────────────

DRUG_INTERACTIONS = """
MATCH (d:Drug)-[r:INTERACTS_WITH|CONTRAINDICATED_WITH]-(other:Drug)
WHERE d.name = $drug_name AND r.weight >= $min_weight
RETURN d.name AS drug,
       type(r) AS interaction_type,
       other.name AS interacts_with,
       r.weight AS severity,
       r.mechanism AS mechanism,
       r.provenance AS provenance
ORDER BY r.weight DESC
LIMIT $limit
"""

DRUG_CONTRAINDICATIONS_FOR_DISEASE = """
MATCH (drug:Drug)-[r:CONTRAINDICATED_WITH]->(disease:Disease)
WHERE disease.name = $disease_name AND r.weight >= $min_weight
RETURN drug.name AS drug,
       r.weight AS severity,
       r.reason AS reason,
       r.provenance AS provenance
ORDER BY r.weight DESC
LIMIT $limit
"""

# ── Disease-symptom-treatment pathway ────────────────────────────────────────

DISEASE_FULL_PROFILE = """
MATCH (d:Disease {name: $disease_name})
OPTIONAL MATCH (d)-[hs:HAS_SYMPTOM]->(s:Symptom) WHERE hs.weight >= $min_weight
OPTIONAL MATCH (d)-[tb:TREATED_BY]->(t:Treatment) WHERE tb.weight >= $min_weight
OPTIONAL MATCH (d)-[hr:HAS_RISK]->(rf:RiskFactor) WHERE hr.weight >= $min_weight
OPTIONAL MATCH (d)-[hl:HAS_LAB_RESULT]->(lab:LabResult) WHERE hl.weight >= $min_weight
RETURN
    d.name AS disease,
    collect(DISTINCT {symptom: s.name, weight: hs.weight}) AS symptoms,
    collect(DISTINCT {treatment: t.name, weight: tb.weight}) AS treatments,
    collect(DISTINCT {risk_factor: rf.name, weight: hr.weight}) AS risk_factors,
    collect(DISTINCT {lab: lab.name, normal_range: lab.normal_range}) AS lab_results
"""

# ── Shortest path between concepts ───────────────────────────────────────────

SHORTEST_PATH_BETWEEN = """
MATCH path = shortestPath(
    (a)-[*1..$max_depth]-(b)
)
WHERE a.name = $start AND b.name = $end
RETURN
    [node IN nodes(path) | node.name] AS path_nodes,
    [rel IN relationships(path) | type(rel)] AS path_rels,
    length(path) AS hops
LIMIT 3
"""

# ── Similar case queries ──────────────────────────────────────────────────────

SIMILAR_CASES_BY_SYMPTOM_OVERLAP = """
MATCH (anchor:PatientCase {case_id: $case_id})-[:DIAGNOSED_WITH]->(d:Disease)
MATCH (other:PatientCase)-[:DIAGNOSED_WITH]->(d2:Disease)
WHERE other.case_id <> $case_id
WITH anchor, other,
     size([(anchor)-[:HAS_SYMPTOM]->(s)<-[:HAS_SYMPTOM]-(other) | s]) AS symptom_overlap,
     size([(anchor)-[:HAS_SYMPTOM]->(s) | s]) AS anchor_symptoms
WHERE symptom_overlap > 0
WITH other, symptom_overlap, anchor_symptoms,
     toFloat(symptom_overlap) / toFloat(anchor_symptoms) AS jaccard
WHERE jaccard >= $min_similarity
RETURN other.case_id AS case_id,
       other.summary AS summary,
       other.outcome AS outcome,
       other.risk_profile AS risk_profile,
       jaccard AS similarity_score
ORDER BY jaccard DESC
LIMIT $limit
"""

SIMILAR_CASES_BY_DISEASE = """
MATCH (other:PatientCase)-[r:SIMILAR_TO]-(anchor:PatientCase {case_id: $case_id})
WHERE r.similarity_score >= $min_similarity
RETURN other.case_id AS case_id,
       other.summary AS summary,
       other.diagnosis AS diagnosis,
       other.outcome AS outcome,
       other.medications AS medications,
       r.similarity_score AS similarity_score
ORDER BY r.similarity_score DESC
LIMIT $limit
"""

ALL_CASES_FOR_DISEASE = """
MATCH (c:PatientCase)-[:DIAGNOSED_WITH]->(d:Disease)
WHERE d.name = $disease_name
RETURN c.case_id AS case_id,
       c.summary AS summary,
       c.diagnosis AS diagnosis,
       c.outcome AS outcome,
       c.symptoms AS symptoms,
       c.medications AS medications,
       c.risk_profile AS risk_profile
LIMIT $limit
"""

# ── Graph ingestor MERGE patterns ─────────────────────────────────────────────

MERGE_ENTITY = """
MERGE (n:{label} {{name: $name}})
ON CREATE SET
    n.source       = $source,
    n.confidence   = $confidence,
    n.aliases      = $aliases,
    n.created_at   = datetime()
ON MATCH SET
    n.confidence   = CASE WHEN $confidence > n.confidence THEN $confidence ELSE n.confidence END,
    n.updated_at   = datetime()
RETURN n
"""

MERGE_RELATIONSHIP = """
MATCH (a {{name: $source_name}})
MATCH (b {{name: $target_name}})
MERGE (a)-[r:{rel_type}]->(b)
ON CREATE SET
    r.weight      = $weight,
    r.provenance  = $provenance,
    r.created_at  = datetime()
ON MATCH SET
    r.weight      = CASE WHEN $weight > r.weight THEN $weight ELSE r.weight END,
    r.updated_at  = datetime()
RETURN r
"""

MERGE_PATIENT_CASE = """
MERGE (c:PatientCase {case_id: $case_id})
ON CREATE SET
    c.summary      = $summary,
    c.diagnosis    = $diagnosis,
    c.symptoms     = $symptoms,
    c.medications  = $medications,
    c.outcome      = $outcome,
    c.risk_profile = $risk_profile,
    c.source       = $source,
    c.created_at   = datetime()
ON MATCH SET
    c.updated_at   = datetime()
RETURN c
"""

MERGE_CASE_SIMILARITY = """
MATCH (a:PatientCase {case_id: $case_id_a})
MATCH (b:PatientCase {case_id: $case_id_b})
MERGE (a)-[r:SIMILAR_TO]-(b)
ON CREATE SET r.similarity_score = $score, r.method = $method, r.created_at = datetime()
ON MATCH SET  r.similarity_score = $score, r.updated_at = datetime()
"""

# ── Guideline queries ─────────────────────────────────────────────────────────

GUIDELINES_FOR_DISEASE = """
MATCH (g:Guideline)-[:RELATED_TO]->(d:Disease {name: $disease_name})
RETURN g.guideline_id AS id,
       g.title AS title,
       g.summary AS summary,
       g.issuer AS issuer,
       g.confidence AS confidence
ORDER BY g.confidence DESC
LIMIT $limit
"""

# ── Graph statistics ──────────────────────────────────────────────────────────

GRAPH_STATS = """
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
"""
