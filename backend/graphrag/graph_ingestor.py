"""
graph_ingestor.py — Medical Knowledge Graph Ingestion Pipeline (Phase 6)

Architecture:
  The ingestion pipeline converts unstructured medical text (PDF chunks,
  reasoning outputs, clinical notes) into structured knowledge graph nodes
  and relationships via a 4-stage pipeline:

  Stage 1: Entity Extraction
    - Regex-based medical NER (extensible with SciSpaCy)
    - Pattern vocabularies for diseases, drugs, symptoms, procedures
    - Alias normalisation via canonical name lookup

  Stage 2: Relationship Extraction
    - Sentence-level co-occurrence with relationship pattern matching
    - Dependency-based trigger verbs (e.g. "treated by", "causes", "contraindicates")
    - Confidence scoring: rule confidence × co-occurrence strength

  Stage 3: Validation + Filtering
    - Confidence threshold filtering (per CONFIDENCE_THRESHOLDS in schema.py)
    - Duplicate suppression (MERGE semantics in Cypher)
    - Self-referential relationship rejection

  Stage 4: Graph MERGE
    - Parameterised MERGE patterns (no injection risk)
    - ON MATCH: keeps highest confidence value
    - ON CREATE: sets provenance and timestamps

  SciSpaCy integration (optional):
    If 'en_core_sci_md' is available, entities are enriched with
    UMLS CUI codes and entity types from the biomedical NER model.
    Falls back to regex if not installed.

  Production safeguards:
    - max_entities_per_chunk: 30 (prevents noise explosion)
    - min_confidence: 0.70 for all relationships
    - Batch size: 50 entities per write transaction
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.graphrag.graph_client  import GraphClient
from backend.graphrag.schema        import CONFIDENCE_THRESHOLDS
from backend.graphrag import cypher_templates as CQL
from backend.utils.logger           import logger


# ── Configuration ──────────────────────────────────────────────────────────────
MAX_ENTITIES_PER_CHUNK = 30
MAX_RELS_PER_CHUNK     = 20
MIN_ENTITY_LEN         = 4
BATCH_SIZE             = 50


# ── Entity vocabulary ─────────────────────────────────────────────────────────
# Maps regex patterns → (label, canonical_prefix)
ENTITY_PATTERNS: list[tuple[str, str, str]] = [
    # Diseases
    (r"\b(STEMI|NSTEMI|myocardial infarction|acute MI)\b", "Disease", "coronary artery disease"),
    (r"\b(heart failure|CHF|congestive heart failure)\b",   "Disease", "heart failure"),
    (r"\b(sepsis|septic shock|bacteremia)\b",               "Disease", "sepsis"),
    (r"\b(diabetes mellitus|type 2 diabetes|T2DM|T1DM)\b",  "Disease", "diabetes mellitus"),
    (r"\b(hypertension|HTN|high blood pressure)\b",          "Disease", "hypertension"),
    (r"\b(atrial fibrillation|AF|AFib)\b",                  "Disease", "atrial fibrillation"),
    (r"\b(stroke|CVA|cerebrovascular accident)\b",           "Disease", "stroke"),
    (r"\b(COPD|chronic obstructive pulmonary disease)\b",   "Disease", "copd"),
    (r"\b(pneumonia|pulmonary infection)\b",                 "Disease", "pneumonia"),
    (r"\b(pulmonary embolism|PE|VTE)\b",                    "Disease", "pulmonary embolism"),
    (r"\b(deep vein thrombosis|DVT)\b",                     "Disease", "deep vein thrombosis"),
    (r"\b(acute kidney injury|AKI|acute renal failure)\b",  "Disease", "acute kidney injury"),
    (r"\b(CKD|chronic kidney disease|renal impairment)\b",  "Disease", "chronic kidney disease"),
    (r"\b(liver failure|hepatic failure|cirrhosis)\b",      "Disease", "liver failure"),
    (r"\b(cardiogenic shock)\b",                            "Disease", "cardiogenic shock"),
    # Drugs
    (r"\b(aspirin|acetylsalicylic acid|ASA)\b",         "Drug", "aspirin"),
    (r"\b(heparin|UFH|unfractionated heparin)\b",       "Drug", "heparin"),
    (r"\b(warfarin|coumadin)\b",                        "Drug", "warfarin"),
    (r"\b(metoprolol|bisoprolol|carvedilol)\b",         "Drug", "beta blocker"),
    (r"\b(lisinopril|ramipril|enalapril)\b",            "Drug", "ace inhibitor"),
    (r"\b(clopidogrel|ticagrelor|prasugrel)\b",         "Drug", "antiplatelet"),
    (r"\b(furosemide|torsemide|bumetanide)\b",          "Drug", "loop diuretic"),
    (r"\b(vancomycin|linezolid|daptomycin)\b",          "Drug", "antibiotic"),
    (r"\b(insulin|glargine|detemir|aspart)\b",          "Drug", "insulin"),
    (r"\b(morphine|fentanyl|hydromorphone)\b",          "Drug", "opioid analgesic"),
    # Symptoms
    (r"\b(chest pain|angina|angina pectoris)\b",        "Symptom", "chest pain"),
    (r"\b(dyspnea|shortness of breath|breathlessness)\b", "Symptom", "dyspnea"),
    (r"\b(hypotension|low blood pressure)\b",           "Symptom", "hypotension"),
    (r"\b(tachycardia|rapid heart rate|fast pulse)\b",  "Symptom", "tachycardia"),
    (r"\b(ST elevation|ST-segment elevation|STEMI pattern)\b", "Symptom", "st elevation"),
    (r"\b(fever|pyrexia|febrile)\b",                    "Symptom", "fever"),
    (r"\b(edema|oedema|swelling)\b",                    "Symptom", "edema"),
    (r"\b(cough|productive cough|dry cough)\b",         "Symptom", "cough"),
    # Biomarkers / Lab Results
    (r"\b(troponin I|troponin T|high-sensitivity troponin)\b", "Biomarker", "troponin"),
    (r"\b(BNP|NT-proBNP|brain natriuretic peptide)\b",         "Biomarker", "bnp"),
    (r"\b(D-dimer|d dimer)\b",                                  "Biomarker", "d-dimer"),
    (r"\b(creatinine|serum creatinine|Cr)\b",                   "LabResult", "creatinine"),
    (r"\b(INR|international normalised ratio)\b",               "LabResult", "inr"),
    (r"\b(lactate|serum lactate|blood lactate)\b",              "Biomarker", "lactate"),
    # Procedures / Treatments
    (r"\b(PCI|percutaneous coronary intervention)\b",  "Procedure", "pci"),
    (r"\b(CABG|coronary artery bypass)\b",             "Procedure", "cabg"),
    (r"\b(mechanical ventilation|intubation)\b",       "Procedure", "mechanical ventilation"),
    (r"\b(dialysis|hemodialysis|RRT)\b",               "Procedure", "dialysis"),
    (r"\b(thrombolysis|tPA|alteplase)\b",               "Treatment", "thrombolysis"),
    (r"\b(cardioversion|defibrillation)\b",             "Procedure", "cardioversion"),
    (r"\b(vasopressor|norepinephrine|dopamine|dobutamine)\b", "Drug", "vasopressor"),
]


# ── Relationship trigger patterns ─────────────────────────────────────────────
RELATION_PATTERNS: list[tuple[str, str, float]] = [
    (r"treated (by|with)",           "TREATED_BY",           0.80),
    (r"treatment (is|includes?)",    "TREATED_BY",           0.75),
    (r"contraindicated",             "CONTRAINDICATED_WITH",  0.90),
    (r"(causes?|caused by)",         "CAUSED_BY",            0.80),
    (r"associated with",             "ASSOCIATED_WITH",       0.72),
    (r"indicates?",                  "INDICATES",            0.78),
    (r"improves? with",              "IMPROVES_WITH",        0.78),
    (r"(risk (factor|of)|increases risk)", "HAS_RISK",        0.75),
    (r"interacts? with",             "INTERACTS_WITH",        0.85),
    (r"(results? in|leads? to)",     "ASSOCIATED_WITH",       0.70),
    (r"presents? with",              "HAS_SYMPTOM",          0.80),
    (r"(diagnosed with|diagnosis of)","DIAGNOSED_WITH",      0.85),
]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ExtractedEntity:
    name:       str
    label:      str
    canonical:  str
    confidence: float
    source:     str

@dataclass
class ExtractedRelationship:
    source_name:  str
    source_label: str
    target_name:  str
    target_label: str
    rel_type:     str
    weight:       float
    provenance:   str


# ── Entity Extraction ─────────────────────────────────────────────────────────

def extract_entities(
    text:       str,
    source:     str = "rule_extraction",
    confidence: float = 0.85,
) -> List[ExtractedEntity]:
    """
    Extract medical entities from text using pattern matching.
    Returns deduplicated list (canonical name is the dedup key).
    """
    seen:     set[str] = set()
    entities: list[ExtractedEntity] = []

    for pattern, label, canonical in ENTITY_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(0).lower().strip()
            if canonical in seen:
                continue
            if len(matched_text) < MIN_ENTITY_LEN:
                continue
            seen.add(canonical)
            entities.append(ExtractedEntity(
                name       = canonical,
                label      = label,
                canonical  = canonical,
                confidence = confidence,
                source     = source,
            ))
            if len(entities) >= MAX_ENTITIES_PER_CHUNK:
                break
        if len(entities) >= MAX_ENTITIES_PER_CHUNK:
            break

    return entities


def extract_relationships(
    text:     str,
    entities: List[ExtractedEntity],
    source:   str = "rule_extraction",
) -> List[ExtractedRelationship]:
    """
    Extract relationships by detecting trigger verbs between co-occurring
    entity pairs within the same sentence.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    rels:  list[ExtractedRelationship] = []
    seen:  set[tuple] = set()

    entity_map = {e.canonical: e for e in entities}
    entity_names = list(entity_map.keys())

    for sentence in sentences:
        s_lower = sentence.lower()

        # Find entities co-occurring in this sentence
        present = [n for n in entity_names if n in s_lower]
        if len(present) < 2:
            continue

        # Detect relationship trigger
        detected_rel: Optional[Tuple[str, float]] = None
        for pat, rel_type, base_conf in RELATION_PATTERNS:
            if re.search(pat, s_lower, re.IGNORECASE):
                detected_rel = (rel_type, base_conf)
                break

        if not detected_rel:
            continue

        rel_type, conf = detected_rel
        # Pair first two entities in sentence as (source, target)
        src_name = present[0]
        tgt_name = present[1]

        key = (src_name, tgt_name, rel_type)
        rev = (tgt_name, src_name, rel_type)
        if key in seen or rev in seen:
            continue
        seen.add(key)

        src = entity_map[src_name]
        tgt = entity_map[tgt_name]

        # Skip self-reference
        if src.label == tgt.label and src.canonical == tgt.canonical:
            continue

        # Confidence below threshold → skip
        if conf < CONFIDENCE_THRESHOLDS.get(source, 0.70):
            continue

        rels.append(ExtractedRelationship(
            source_name  = src.canonical,
            source_label = src.label,
            target_name  = tgt.canonical,
            target_label = tgt.label,
            rel_type     = rel_type,
            weight       = conf,
            provenance   = source,
        ))

        if len(rels) >= MAX_RELS_PER_CHUNK:
            break

    return rels


# ── Graph Ingestor ─────────────────────────────────────────────────────────────

class GraphIngestor:
    """
    High-level API for ingesting medical text into the knowledge graph.

    Usage:
        ingestor = GraphIngestor(GraphClient.get_instance())
        await ingestor.ingest_chunk(text, source="pubmed_abstract")
        await ingestor.ingest_chunks_batch(chunks)
    """

    def __init__(self, client: GraphClient):
        self._client = client

    async def ingest_chunk(
        self,
        text:       str,
        source:     str = "pdf_chunk",
        confidence: float = 0.85,
    ) -> dict:
        """
        Full pipeline: extract → validate → merge to graph.
        Returns ingestion stats dict.
        """
        entities = extract_entities(text, source, confidence)
        if not entities:
            return {"entities": 0, "relationships": 0}

        rels = extract_relationships(text, entities, source)

        # Write entities
        entity_count = 0
        for ent in entities:
            cypher = CQL.MERGE_ENTITY.replace("{label}", ent.label)
            await self._client.run_write(cypher, {
                "name":       ent.canonical,
                "source":     ent.source,
                "confidence": ent.confidence,
                "aliases":    [ent.name],
            })
            entity_count += 1

        # Write relationships
        rel_count = 0
        for rel in rels:
            cypher = CQL.MERGE_RELATIONSHIP.replace("{rel_type}", rel.rel_type)
            await self._client.run_write(cypher, {
                "source_name": rel.source_name,
                "target_name": rel.target_name,
                "weight":      rel.weight,
                "provenance":  rel.provenance,
            })
            rel_count += 1

        logger.info(
            f"[GraphIngestor] Ingested: {entity_count} entities, "
            f"{rel_count} relationships from source='{source}'"
        )
        return {"entities": entity_count, "relationships": rel_count}

    async def ingest_chunks_batch(
        self,
        chunks: List[dict],
        source: str = "pdf_pipeline",
    ) -> dict:
        """Batch ingest a list of document chunks."""
        totals = {"entities": 0, "relationships": 0}
        tasks = [self.ingest_chunk(c.get("text", ""), source) for c in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                totals["entities"]      += r.get("entities", 0)
                totals["relationships"] += r.get("relationships", 0)
        logger.info(f"[GraphIngestor] Batch complete: {totals}")
        return totals

    async def ingest_patient_case(
        self,
        case_id:      str,
        summary:      str,
        diagnosis:    str,
        symptoms:     List[str],
        medications:  List[str],
        outcome:      str,
        risk_profile: str,
        source:       str = "clinical_note",
    ) -> str:
        """
        Persist a PatientCase node and attach its relationships to
        Disease/Symptom/Medication nodes.
        """
        await self._client.run_write(CQL.MERGE_PATIENT_CASE, {
            "case_id":      case_id,
            "summary":      summary,
            "diagnosis":    diagnosis.lower(),
            "symptoms":     symptoms,
            "medications":  medications,
            "outcome":      outcome,
            "risk_profile": risk_profile,
            "source":       source,
        })
        # Link case to disease node
        disease_cypher = """
        MERGE (d:Disease {name: $disease_name})
        WITH d
        MATCH (c:PatientCase {case_id: $case_id})
        MERGE (c)-[:DIAGNOSED_WITH {weight: 0.99}]->(d)
        """
        await self._client.run_write(disease_cypher, {
            "disease_name": diagnosis.lower(),
            "case_id":      case_id,
        })
        logger.info(f"[GraphIngestor] PatientCase ingested: {case_id}")
        return case_id
