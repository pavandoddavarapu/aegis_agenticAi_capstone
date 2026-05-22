"""
ingest_medical_knowledge.py — Comprehensive Medical Knowledge Ingestion Script

Ingests structured clinical knowledge from Wikipedia, MedlinePlus (NIH),
and PubMed across ALL major medical specialties into the Aegis RAG pipeline.

Medical Domains Covered:
  1.  Cardiology            — Heart diseases, arrhythmias, heart failure
  2.  Pulmonology           — COPD, asthma, pneumonia, lung cancer
  3.  Neurology             — Stroke, epilepsy, Parkinson's, Alzheimer's
  4.  Endocrinology         — Diabetes, thyroid, adrenal disorders
  5.  Nephrology            — CKD, AKI, dialysis, nephrotic syndrome
  6.  Gastroenterology      — Liver disease, IBD, pancreatitis, GERD
  7.  Oncology              — Major cancers, treatment protocols
  8.  Hematology            — Anemia, coagulopathy, lymphoma, leukemia
  9.  Infectious Diseases   — Sepsis, pneumonia, TB, HIV, malaria
  10. Musculoskeletal       — Arthritis, fractures, osteoporosis
  11. Psychiatry            — Depression, schizophrenia, bipolar, anxiety
  12. Pediatrics            — Neonatal, childhood diseases
  13. Obstetrics/Gynecology — Pregnancy complications, gynecological cancers
  14. Dermatology           — Eczema, psoriasis, melanoma
  15. Ophthalmology         — Glaucoma, cataract, retinal disease
  16. ENT                   — Sinusitis, otitis, hearing loss

Data Sources (all free / public):
  - Wikipedia English (via MediaWiki API)
  - MedlinePlus Health Topics (NIH)
  - PubMed Abstracts (NCBI eutils)

Validation:
  Every piece of content passes through MedicalValidator before storage.
  Failed chunks are logged but not stored.

Usage:
    python scripts/ingest_medical_knowledge.py
    python scripts/ingest_medical_knowledge.py --domains cardiology,neurology
    python scripts/ingest_medical_knowledge.py --dry-run
    python scripts/ingest_medical_knowledge.py --pubmed-only
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict

# ─── Make sure project root is on the path ─────────────────────────────────
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.rag.ingestors.web_ingestor import (
    ingest_wikipedia, ingest_medlineplus, ingest_pubmed,
)
from backend.rag.validators.medical_validator import MedicalValidator
from backend.rag.chunker import chunk_pages
from backend.rag.embeddings import embed_texts
from backend.rag.qdrant_store import store_chunks, ensure_collection
from backend.rag.schemas import ExtractedPage, Chunk
from backend.utils.logger import logger

# ─────────────────────────────────────────────────────────────────────────────
# Medical Knowledge Registry
# Each domain entry defines:
#   - wikipedia_articles: list of Wikipedia article titles to ingest
#   - medlineplus_queries: list of MedlinePlus search queries
#   - pubmed_queries: list of PubMed search queries
# ─────────────────────────────────────────────────────────────────────────────

MEDICAL_DOMAINS: Dict[str, Dict] = {

    # ─── 1. CARDIOLOGY ──────────────────────────────────────────────────────
    "cardiology": {
        "wikipedia_articles": [
            "Myocardial infarction",
            "Heart failure",
            "Atrial fibrillation",
            "Coronary artery disease",
            "Hypertension",
            "Cardiac arrest",
            "Ventricular tachycardia",
            "Aortic stenosis",
            "Dilated cardiomyopathy",
            "Hypertrophic cardiomyopathy",
            "Pericarditis",
            "Mitral valve prolapse",
            "Deep vein thrombosis",
            "Pulmonary embolism",
            "Peripheral artery disease",
            "Aortic dissection",
            "Endocarditis",
        ],
        "medlineplus_queries": [
            "heart attack symptoms treatment",
            "heart failure management",
            "atrial fibrillation anticoagulation",
            "hypertension blood pressure control",
            "coronary artery disease risk factors",
        ],
        "pubmed_queries": [
            "myocardial infarction STEMI treatment guidelines",
            "heart failure reduced ejection fraction management",
            "atrial fibrillation stroke prevention anticoagulation",
            "hypertensive emergency management",
            "coronary artery disease percutaneous coronary intervention",
            "cardiac arrest resuscitation ROSC outcomes",
            "aortic dissection type A emergency surgery",
        ],
    },

    # ─── 2. PULMONOLOGY ────────────────────────────────────────────────────
    "pulmonology": {
        "wikipedia_articles": [
            "Pneumonia",
            "Chronic obstructive pulmonary disease",
            "Asthma",
            "Lung cancer",
            "Pulmonary fibrosis",
            "Pleural effusion",
            "Pneumothorax",
            "Pulmonary hypertension",
            "Respiratory failure",
            "Bronchiectasis",
            "Sarcoidosis",
            "Tuberculosis",
            "Acute respiratory distress syndrome",
            "Pulmonary edema",
            "Cystic fibrosis",
            "Obstructive sleep apnea",
        ],
        "medlineplus_queries": [
            "pneumonia symptoms treatment",
            "COPD management exacerbation",
            "asthma inhaler bronchodilator",
            "lung cancer staging treatment",
            "pulmonary fibrosis diagnosis",
        ],
        "pubmed_queries": [
            "community acquired pneumonia antibiotic treatment guidelines",
            "COPD exacerbation management hospital",
            "asthma severe exacerbation treatment stepwise",
            "non-small cell lung cancer immunotherapy checkpoint inhibitor",
            "idiopathic pulmonary fibrosis nintedanib pirfenidone",
            "ARDS mechanical ventilation protective lung strategy",
            "pulmonary embolism thrombolysis anticoagulation",
            "pleural effusion malignant transudative exudative",
        ],
    },

    # ─── 3. NEUROLOGY ─────────────────────────────────────────────────────
    "neurology": {
        "wikipedia_articles": [
            "Stroke",
            "Ischemic stroke",
            "Hemorrhagic stroke",
            "Epilepsy",
            "Parkinson's disease",
            "Alzheimer's disease",
            "Multiple sclerosis",
            "Meningitis",
            "Encephalitis",
            "Guillain–Barré syndrome",
            "Myasthenia gravis",
            "Amyotrophic lateral sclerosis",
            "Migraine",
            "Brain tumor",
            "Subarachnoid hemorrhage",
            "Transient ischemic attack",
        ],
        "medlineplus_queries": [
            "stroke symptoms tPA thrombolysis",
            "epilepsy seizure treatment antiepileptic",
            "Parkinson disease dopaminergic therapy",
            "Alzheimer dementia management",
            "multiple sclerosis relapsing remitting treatment",
        ],
        "pubmed_queries": [
            "ischemic stroke thrombolysis tPA time window",
            "epilepsy drug resistant surgical treatment",
            "Parkinson disease levodopa motor complications",
            "Alzheimer disease amyloid beta treatment trial",
            "multiple sclerosis disease modifying therapy",
            "bacterial meningitis dexamethasone antibiotic",
            "subarachnoid hemorrhage nimodipine vasospasm",
            "Guillain Barre syndrome plasmapheresis IVIG",
        ],
    },

    # ─── 4. ENDOCRINOLOGY ──────────────────────────────────────────────────
    "endocrinology": {
        "wikipedia_articles": [
            "Type 2 diabetes",
            "Type 1 diabetes",
            "Diabetic ketoacidosis",
            "Hyperosmolar hyperglycemic state",
            "Hypothyroidism",
            "Hyperthyroidism",
            "Graves' disease",
            "Cushing's syndrome",
            "Addison's disease",
            "Polycystic ovary syndrome",
            "Metabolic syndrome",
            "Hypoglycemia",
            "Diabetes insipidus",
            "Pheochromocytoma",
        ],
        "medlineplus_queries": [
            "type 2 diabetes insulin metformin treatment",
            "thyroid disorders hypothyroidism levothyroxine",
            "diabetic ketoacidosis management",
            "cushing syndrome cortisol excess",
            "polycystic ovary syndrome infertility",
        ],
        "pubmed_queries": [
            "type 2 diabetes glycemic control HbA1c target",
            "diabetic ketoacidosis insulin protocol management",
            "hypothyroidism levothyroxine dose titration",
            "thyroid storm emergency treatment",
            "Cushing syndrome diagnosis dexamethasone suppression",
            "polycystic ovary syndrome metformin clomiphene",
            "adrenal insufficiency hydrocortisone replacement",
        ],
    },

    # ─── 5. NEPHROLOGY ────────────────────────────────────────────────────
    "nephrology": {
        "wikipedia_articles": [
            "Chronic kidney disease",
            "Acute kidney injury",
            "Nephrotic syndrome",
            "Nephritic syndrome",
            "Glomerulonephritis",
            "Polycystic kidney disease",
            "Renal calculi",
            "Dialysis",
            "Kidney transplantation",
            "Hypertensive nephropathy",
            "Diabetic nephropathy",
            "Urinary tract infection",
        ],
        "medlineplus_queries": [
            "chronic kidney disease CKD management",
            "acute kidney injury causes treatment",
            "dialysis hemodialysis peritoneal",
            "kidney stones treatment prevention",
            "nephrotic syndrome proteinuria",
        ],
        "pubmed_queries": [
            "chronic kidney disease progression ACE inhibitor ARB",
            "acute kidney injury AKI ICU management",
            "nephrotic syndrome steroid immunosuppression",
            "diabetic nephropathy microalbuminuria treatment",
            "polycystic kidney disease tolvaptan",
            "kidney transplant rejection immunosuppression tacrolimus",
            "renal calculi lithotripsy ureteroscopy",
        ],
    },

    # ─── 6. GASTROENTEROLOGY ──────────────────────────────────────────────
    "gastroenterology": {
        "wikipedia_articles": [
            "Liver cirrhosis",
            "Hepatitis B",
            "Hepatitis C",
            "Crohn's disease",
            "Ulcerative colitis",
            "Pancreatitis",
            "Gastroesophageal reflux disease",
            "Peptic ulcer disease",
            "Hepatocellular carcinoma",
            "Gastrointestinal bleeding",
            "Ascites",
            "Hepatic encephalopathy",
            "Acute liver failure",
            "Irritable bowel syndrome",
            "Celiac disease",
            "Cholecystitis",
        ],
        "medlineplus_queries": [
            "cirrhosis liver failure management",
            "Crohn disease treatment biologics",
            "hepatitis B antiviral treatment",
            "GERD proton pump inhibitor",
            "pancreatitis acute management",
        ],
        "pubmed_queries": [
            "liver cirrhosis complications varices ascites management",
            "Crohn disease infliximab vedolizumab biologic therapy",
            "ulcerative colitis mesalazine corticosteroid treatment",
            "acute pancreatitis severity CT Balthazar score",
            "hepatitis C direct acting antivirals SVR",
            "gastrointestinal bleeding endoscopic hemostasis",
            "hepatocellular carcinoma sorafenib immunotherapy",
            "spontaneous bacterial peritonitis prophylaxis",
        ],
    },

    # ─── 7. ONCOLOGY ──────────────────────────────────────────────────────
    "oncology": {
        "wikipedia_articles": [
            "Breast cancer",
            "Colorectal cancer",
            "Prostate cancer",
            "Lung cancer",
            "Lymphoma",
            "Leukemia",
            "Pancreatic cancer",
            "Ovarian cancer",
            "Melanoma",
            "Cervical cancer",
            "Bladder cancer",
            "Thyroid cancer",
            "Glioblastoma",
            "Chemotherapy",
            "Radiation therapy",
            "Immunotherapy",
        ],
        "medlineplus_queries": [
            "breast cancer screening treatment",
            "colorectal cancer colonoscopy screening",
            "cancer immunotherapy checkpoint inhibitors",
            "leukemia chemotherapy treatment",
            "palliative care cancer pain management",
        ],
        "pubmed_queries": [
            "breast cancer HER2 trastuzumab treatment",
            "colorectal cancer FOLFOX FOLFIRI bevacizumab",
            "non-small cell lung cancer EGFR mutation targeted therapy",
            "melanoma PD-1 checkpoint inhibitor pembrolizumab",
            "acute myeloid leukemia induction chemotherapy",
            "prostate cancer docetaxel enzalutamide hormonal therapy",
            "ovarian cancer platinum paclitaxel BRCA",
            "glioblastoma temozolomide bevacizumab treatment",
        ],
    },

    # ─── 8. HEMATOLOGY ────────────────────────────────────────────────────
    "hematology": {
        "wikipedia_articles": [
            "Anemia",
            "Iron deficiency anemia",
            "Sickle cell disease",
            "Thalassemia",
            "Hemophilia",
            "Thrombocytopenia",
            "Disseminated intravascular coagulation",
            "Thrombosis",
            "Polycythemia vera",
            "Myelodysplastic syndrome",
            "Von Willebrand disease",
        ],
        "medlineplus_queries": [
            "anemia iron deficiency treatment",
            "sickle cell disease complications management",
            "blood clotting disorder anticoagulation",
            "thrombocytopenia platelet transfusion",
        ],
        "pubmed_queries": [
            "iron deficiency anemia intravenous iron therapy",
            "sickle cell disease vaso-occlusive crisis management",
            "disseminated intravascular coagulation DIC management",
            "heparin induced thrombocytopenia HIT management",
            "hemophilia factor replacement prophylaxis",
            "polycythemia vera hydroxyurea phlebotomy",
            "myelodysplastic syndrome azacitidine treatment",
        ],
    },

    # ─── 9. INFECTIOUS DISEASES ──────────────────────────────────────────
    "infectious_diseases": {
        "wikipedia_articles": [
            "Sepsis",
            "Septic shock",
            "COVID-19",
            "Influenza",
            "Tuberculosis",
            "HIV/AIDS",
            "Malaria",
            "Dengue fever",
            "Typhoid fever",
            "Leptospirosis",
            "Urinary tract infection",
            "Cellulitis",
            "Infective endocarditis",
            "Clostridium difficile infection",
            "Methicillin-resistant Staphylococcus aureus",
        ],
        "medlineplus_queries": [
            "sepsis septic shock antibiotic treatment",
            "COVID-19 treatment hospitalized",
            "tuberculosis multi drug resistant treatment",
            "HIV antiretroviral therapy management",
            "malaria antimalarial chloroquine",
        ],
        "pubmed_queries": [
            "sepsis Surviving Sepsis Campaign bundle antibiotic",
            "COVID-19 dexamethasone remdesivir clinical outcome",
            "tuberculosis drug resistance rifampicin isoniazid",
            "HIV ART initiation CD4 viral load monitoring",
            "malaria artemisinin combination therapy",
            "infective endocarditis antibiotic duration prosthetic valve",
            "Clostridium difficile vancomycin fidaxomicin",
            "MRSA vancomycin linezolid treatment",
        ],
    },

    # ─── 10. MUSCULOSKELETAL ──────────────────────────────────────────────
    "musculoskeletal": {
        "wikipedia_articles": [
            "Rheumatoid arthritis",
            "Osteoarthritis",
            "Osteoporosis",
            "Gout",
            "Systemic lupus erythematosus",
            "Ankylosing spondylitis",
            "Fibromyalgia",
            "Polymyalgia rheumatica",
            "Rhabdomyolysis",
            "Fracture",
            "Osteomyelitis",
        ],
        "medlineplus_queries": [
            "rheumatoid arthritis DMARD biologic treatment",
            "osteoporosis bisphosphonate treatment prevention",
            "gout uric acid allopurinol colchicine",
            "lupus SLE management hydroxychloroquine",
        ],
        "pubmed_queries": [
            "rheumatoid arthritis methotrexate TNF inhibitor",
            "osteoporosis bisphosphonate fracture prevention DEXA",
            "gout acute attack colchicine indomethacin",
            "lupus nephritis mycophenolate belimumab",
            "ankylosing spondylitis anti-TNF secukinumab",
            "rhabdomyolysis acute kidney injury hydration",
        ],
    },

    # ─── 11. PSYCHIATRY ───────────────────────────────────────────────────
    "psychiatry": {
        "wikipedia_articles": [
            "Major depressive disorder",
            "Bipolar disorder",
            "Schizophrenia",
            "Generalized anxiety disorder",
            "Post-traumatic stress disorder",
            "Obsessive–compulsive disorder",
            "Anorexia nervosa",
            "Attention deficit hyperactivity disorder",
            "Borderline personality disorder",
            "Serotonin syndrome",
            "Neuroleptic malignant syndrome",
        ],
        "medlineplus_queries": [
            "depression antidepressant SSRI treatment",
            "schizophrenia antipsychotic medication",
            "bipolar disorder mood stabilizer lithium",
            "anxiety disorder CBT treatment",
            "PTSD trauma therapy",
        ],
        "pubmed_queries": [
            "major depression SSRI treatment resistant",
            "schizophrenia clozapine treatment resistant",
            "bipolar disorder lithium valproate quetiapine",
            "PTSD EMDR cognitive processing therapy",
            "OCD fluvoxamine exposure response prevention",
            "serotonin syndrome diagnosis treatment cyproheptadine",
            "neuroleptic malignant syndrome dantrolene bromocriptine",
        ],
    },

    # ─── 12. PEDIATRICS ───────────────────────────────────────────────────
    "pediatrics": {
        "wikipedia_articles": [
            "Neonatal jaundice",
            "Respiratory syncytial virus infection",
            "Kawasaki disease",
            "Meningitis",
            "Febrile seizure",
            "Intussusception",
            "Pyloric stenosis",
            "Neonatal sepsis",
            "Patent ductus arteriosus",
            "Croup",
            "Bronchiolitis",
            "Childhood leukemia",
        ],
        "medlineplus_queries": [
            "neonatal jaundice phototherapy",
            "RSV bronchiolitis infant treatment",
            "febrile seizure childhood management",
            "Kawasaki disease IVIG aspirin treatment",
            "pediatric sepsis early recognition",
        ],
        "pubmed_queries": [
            "neonatal jaundice hyperbilirubinemia phototherapy exchange transfusion",
            "bronchiolitis RSV nebulized saline management",
            "Kawasaki disease intravenous immunoglobulin aspirin",
            "pediatric febrile seizure risk recurrence",
            "neonatal sepsis early onset antibiotic empiric",
            "childhood acute lymphoblastic leukemia treatment protocol",
            "croup nebulized epinephrine dexamethasone",
        ],
    },

    # ─── 13. OBSTETRICS & GYNECOLOGY ─────────────────────────────────────
    "obstetrics_gynecology": {
        "wikipedia_articles": [
            "Preeclampsia",
            "Eclampsia",
            "Gestational diabetes",
            "Placenta praevia",
            "Ectopic pregnancy",
            "Postpartum hemorrhage",
            "Ovarian cancer",
            "Cervical cancer",
            "Uterine fibroid",
            "Endometriosis",
            "Polycystic ovary syndrome",
        ],
        "medlineplus_queries": [
            "preeclampsia eclampsia management magnesium",
            "gestational diabetes insulin management",
            "postpartum hemorrhage uterotonic treatment",
            "ectopic pregnancy methotrexate salpingectomy",
            "cervical cancer HPV screening colposcopy",
        ],
        "pubmed_queries": [
            "preeclampsia magnesium sulfate labetalol treatment",
            "gestational diabetes insulin oral hypoglycemic",
            "postpartum hemorrhage oxytocin tranexamic acid",
            "ectopic pregnancy methotrexate criteria",
            "ovarian cancer platinum paclitaxel BRCA PARP inhibitor",
            "cervical cancer cisplatin chemoradiation",
        ],
    },

    # ─── 14. DERMATOLOGY ─────────────────────────────────────────────────
    "dermatology": {
        "wikipedia_articles": [
            "Psoriasis",
            "Atopic dermatitis",
            "Melanoma",
            "Acne vulgaris",
            "Urticaria",
            "Cellulitis",
            "Herpes zoster",
            "Pemphigus",
            "Stevens–Johnson syndrome",
            "Basal cell carcinoma",
            "Squamous cell carcinoma",
        ],
        "medlineplus_queries": [
            "psoriasis biologic treatment methotrexate",
            "eczema atopic dermatitis steroid dupilumab",
            "melanoma staging immunotherapy treatment",
            "cellulitis antibiotic treatment",
            "herpes zoster antiviral treatment",
        ],
        "pubmed_queries": [
            "psoriasis biologics IL-17 IL-23 treatment",
            "atopic dermatitis dupilumab JAK inhibitor",
            "melanoma immunotherapy anti-PD1 nivolumab",
            "Stevens Johnson syndrome toxic epidermal necrolysis management",
            "pemphigus vulgaris rituximab corticosteroid",
        ],
    },

    # ─── 15. OPHTHALMOLOGY ───────────────────────────────────────────────
    "ophthalmology": {
        "wikipedia_articles": [
            "Glaucoma",
            "Cataract",
            "Age-related macular degeneration",
            "Diabetic retinopathy",
            "Retinal detachment",
            "Uveitis",
            "Conjunctivitis",
            "Keratoconus",
        ],
        "medlineplus_queries": [
            "glaucoma intraocular pressure treatment",
            "macular degeneration anti-VEGF injection",
            "diabetic retinopathy laser treatment",
            "cataract surgery IOL",
            "retinal detachment vitrectomy",
        ],
        "pubmed_queries": [
            "glaucoma prostaglandin analogue trabeculectomy",
            "age related macular degeneration anti-VEGF ranibizumab",
            "diabetic retinopathy bevacizumab photocoagulation",
            "retinal detachment scleral buckle vitrectomy outcomes",
        ],
    },

    # ─── 16. ENT ─────────────────────────────────────────────────────────
    "ent": {
        "wikipedia_articles": [
            "Otitis media",
            "Sinusitis",
            "Rhinitis",
            "Pharyngitis",
            "Tonsillitis",
            "Laryngitis",
            "Hearing loss",
            "Ménière's disease",
            "Benign paroxysmal positional vertigo",
            "Nasal polyps",
            "Epistaxis",
        ],
        "medlineplus_queries": [
            "otitis media antibiotic treatment children",
            "sinusitis nasal steroid amoxicillin",
            "tonsillitis strep throat treatment",
            "hearing loss audiogram management",
            "BPPV vertigo Epley maneuver",
        ],
        "pubmed_queries": [
            "acute otitis media antibiotic amoxicillin watchful waiting",
            "chronic sinusitis functional endoscopic sinus surgery",
            "sensorineural hearing loss cochlear implant",
            "Meniere disease betahistine diuretic treatment",
            "BPPV canalith repositioning procedure",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion Stats Tracker
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DomainStats:
    domain:          str
    pages_fetched:   int = 0
    pages_valid:     int = 0
    pages_rejected:  int = 0
    chunks_created:  int = 0
    chunks_stored:   int = 0
    errors:          List[str] = field(default_factory=list)


@dataclass
class IngestionSummary:
    domain_stats:    List[DomainStats] = field(default_factory=list)
    total_fetched:   int = 0
    total_valid:     int = 0
    total_rejected:  int = 0
    total_stored:    int = 0
    elapsed_s:       float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Core Ingestion Logic
# ─────────────────────────────────────────────────────────────────────────────

def _ingest_pages(
    pages: List[ExtractedPage],
    validator: MedicalValidator,
    dry_run: bool,
    stats: DomainStats,
    source_description: str = "",
) -> None:
    """Validate → chunk → embed → store a list of ExtractedPages."""
    if not pages:
        return

    valid_pages: List[ExtractedPage] = []
    for page in pages:
        result = validator.validate(page.text, source=page.source)
        if result.is_valid:
            valid_pages.append(page)
            stats.pages_valid += 1
        else:
            stats.pages_rejected += 1
            logger.debug(
                f"[Ingestor] REJECTED [{page.source} p{page.page}] "
                f"score={result.score} reasons={result.reasons}"
            )

    stats.pages_fetched += len(pages)

    if not valid_pages:
        return

    # Chunk
    chunks = chunk_pages(valid_pages)
    stats.chunks_created += len(chunks)

    if dry_run or not chunks:
        logger.info(
            f"[Ingestor] DRY-RUN | {source_description}: "
            f"{len(valid_pages)}/{len(pages)} valid pages → "
            f"{len(chunks)} chunks (not stored)"
        )
        return

    # Embed in batches of 64 for memory efficiency
    EMBED_BATCH = 64
    stored_total = 0
    for i in range(0, len(chunks), EMBED_BATCH):
        batch: List[Chunk] = chunks[i:i + EMBED_BATCH]
        texts = [c.text for c in batch]
        vectors = embed_texts(texts)
        if vectors:
            stored = store_chunks(batch, vectors)
            stored_total += stored

    stats.chunks_stored += stored_total
    logger.info(
        f"[Ingestor] {source_description}: "
        f"{len(valid_pages)}/{len(pages)} valid → "
        f"{len(chunks)} chunks → {stored_total} stored"
    )


def ingest_domain(
    domain_name: str,
    config: dict,
    validator: MedicalValidator,
    dry_run: bool = False,
    skip_wikipedia: bool = False,
    skip_medlineplus: bool = False,
    skip_pubmed: bool = False,
    pubmed_max: int = 20,
    request_delay: float = 0.5,
) -> DomainStats:
    """
    Run the full ingestion pipeline for a single medical domain.

    Returns DomainStats with counts for monitoring.
    """
    stats = DomainStats(domain=domain_name)
    logger.info(f"\n{'='*60}")
    logger.info(f"[Ingestor] Starting domain: {domain_name.upper()}")
    logger.info(f"{'='*60}")

    # ── Wikipedia ─────────────────────────────────────────────────────────
    if not skip_wikipedia:
        wiki_articles = config.get("wikipedia_articles", [])
        logger.info(f"[Ingestor] Wikipedia: {len(wiki_articles)} articles")
        for title in wiki_articles:
            try:
                pages = ingest_wikipedia(title)
                _ingest_pages(pages, validator, dry_run, stats, f"wiki/{title}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"Wikipedia error for '{title}': {exc}"
                logger.error(f"[Ingestor] {msg}")
                stats.errors.append(msg)

    # ── MedlinePlus ───────────────────────────────────────────────────────
    if not skip_medlineplus:
        ml_queries = config.get("medlineplus_queries", [])
        logger.info(f"[Ingestor] MedlinePlus: {len(ml_queries)} queries")
        for query in ml_queries:
            try:
                pages = ingest_medlineplus(query)
                _ingest_pages(pages, validator, dry_run, stats, f"medlineplus/{query}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"MedlinePlus error for '{query}': {exc}"
                logger.error(f"[Ingestor] {msg}")
                stats.errors.append(msg)

    # ── PubMed ────────────────────────────────────────────────────────────
    if not skip_pubmed:
        pm_queries = config.get("pubmed_queries", [])
        logger.info(f"[Ingestor] PubMed: {len(pm_queries)} queries (max={pubmed_max} each)")
        for query in pm_queries:
            try:
                pages = ingest_pubmed(query, max_results=pubmed_max)
                _ingest_pages(pages, validator, dry_run, stats, f"pubmed/{query}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"PubMed error for '{query}': {exc}"
                logger.error(f"[Ingestor] {msg}")
                stats.errors.append(msg)

    logger.info(
        f"[Ingestor] Domain '{domain_name}' complete: "
        f"fetched={stats.pages_fetched} valid={stats.pages_valid} "
        f"rejected={stats.pages_rejected} stored={stats.chunks_stored}"
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Main Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest comprehensive medical knowledge into Aegis RAG pipeline"
    )
    parser.add_argument(
        "--domains",
        type=str,
        default="",
        help="Comma-separated domain names to ingest (default: all). "
             f"Available: {', '.join(MEDICAL_DOMAINS.keys())}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and chunk but do NOT store to Qdrant",
    )
    parser.add_argument(
        "--skip-wikipedia",
        action="store_true",
        help="Skip Wikipedia article ingestion",
    )
    parser.add_argument(
        "--skip-medlineplus",
        action="store_true",
        help="Skip MedlinePlus query ingestion",
    )
    parser.add_argument(
        "--skip-pubmed",
        action="store_true",
        help="Skip PubMed abstract ingestion",
    )
    parser.add_argument(
        "--pubmed-only",
        action="store_true",
        help="Only ingest PubMed abstracts (fastest)",
    )
    parser.add_argument(
        "--pubmed-max",
        type=int,
        default=20,
        help="Max PubMed abstracts per query (default: 20)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict validation (higher keyword density threshold)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between web requests (default: 0.5)",
    )
    args = parser.parse_args()

    # Resolve domains
    if args.domains:
        selected = [d.strip() for d in args.domains.split(",")]
        invalid = [d for d in selected if d not in MEDICAL_DOMAINS]
        if invalid:
            print(f"ERROR: Unknown domains: {invalid}")
            print(f"Available: {list(MEDICAL_DOMAINS.keys())}")
            sys.exit(1)
        domains_to_run = {k: v for k, v in MEDICAL_DOMAINS.items() if k in selected}
    else:
        domains_to_run = MEDICAL_DOMAINS

    # pubmed-only mode
    skip_wiki = args.skip_wikipedia or args.pubmed_only
    skip_ml   = args.skip_medlineplus or args.pubmed_only
    skip_pm   = args.skip_pubmed

    print(f"\n{'='*70}")
    print(f"  AEGIS MEDICAL KNOWLEDGE INGESTION")
    print(f"  Domains : {list(domains_to_run.keys())}")
    print(f"  Sources : Wikipedia={'NO' if skip_wiki else 'YES'} | "
          f"MedlinePlus={'NO' if skip_ml else 'YES'} | "
          f"PubMed={'NO' if skip_pm else 'YES'}")
    print(f"  Mode    : {'DRY-RUN (no storage)' if args.dry_run else 'LIVE (storing to Qdrant)'}")
    print(f"  Strict  : {args.strict}")
    print(f"{'='*70}\n")

    # Ensure Qdrant collection exists
    if not args.dry_run:
        try:
            ensure_collection()
            logger.info("[Ingestor] Qdrant collection ready.")
        except Exception as exc:
            print(f"ERROR: Cannot connect to Qdrant: {exc}")
            sys.exit(1)

    validator = MedicalValidator(strict=args.strict)
    summary   = IngestionSummary()
    start_t   = time.time()

    for domain_name, config in domains_to_run.items():
        stats = ingest_domain(
            domain_name     = domain_name,
            config          = config,
            validator       = validator,
            dry_run         = args.dry_run,
            skip_wikipedia  = skip_wiki,
            skip_medlineplus= skip_ml,
            skip_pubmed     = skip_pm,
            pubmed_max      = args.pubmed_max,
            request_delay   = args.delay,
        )
        summary.domain_stats.append(stats)
        summary.total_fetched  += stats.pages_fetched
        summary.total_valid    += stats.pages_valid
        summary.total_rejected += stats.pages_rejected
        summary.total_stored   += stats.chunks_stored

    summary.elapsed_s = time.time() - start_t

    # ── Final Report ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  INGESTION COMPLETE — {summary.elapsed_s:.1f}s elapsed")
    print(f"{'='*70}")
    print(f"  {'Domain':<25} {'Fetched':>8} {'Valid':>7} {'Rejected':>9} {'Stored':>7}")
    print(f"  {'-'*60}")
    for ds in summary.domain_stats:
        print(
            f"  {ds.domain:<25} {ds.pages_fetched:>8} "
            f"{ds.pages_valid:>7} {ds.pages_rejected:>9} "
            f"{ds.chunks_stored:>7}"
        )
        if ds.errors:
            for err in ds.errors[:3]:
                print(f"    ⚠  {err[:80]}")
    print(f"  {'-'*60}")
    print(
        f"  {'TOTAL':<25} {summary.total_fetched:>8} "
        f"{summary.total_valid:>7} {summary.total_rejected:>9} "
        f"{summary.total_stored:>7}"
    )
    print(f"  Validator seen hashes: {validator.seen_count}")
    print(f"{'='*70}\n")

    return 0 if summary.total_stored > 0 or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
