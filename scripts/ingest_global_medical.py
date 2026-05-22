"""
ingest_global_medical.py — Massive multi-organ medical knowledge ingestion

Ingests hundreds of diseases and anatomy topics from Cardiology, Neurology,
Oncology, Gastroenterology, Endocrinology, and Nephrology into Qdrant.
"""
from __future__ import annotations

import argparse
import sys
import time
import os
from dotenv import load_dotenv

# ─── Project root on path ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

from backend.rag.validators.medical_validator import MedicalValidator
from backend.rag.qdrant_store import ensure_collection
from backend.utils.logger import logger
from scripts.ingest_lungs import ingest_lung_domain, IngestionSummary

# Massive Medical Registry
GLOBAL_DOMAINS = {
    # ── CARDIOLOGY ──────────────────────────────────────────────────────
    "cardiology": {
        "wikipedia_articles": [
            "Heart", "Cardiology", "Myocardial infarction", "Heart failure",
            "Atrial fibrillation", "Coronary artery disease", "Hypertension",
            "Aortic aneurysm", "Endocarditis", "Pericarditis", "Cardiomyopathy"
        ],
        "medlineplus_queries": [
            "heart attack symptoms", "high blood pressure treatment",
            "heart failure signs", "atrial fibrillation stroke risk"
        ],
        "pubmed_queries": [
            "myocardial infarction stemi percutaneous coronary intervention",
            "heart failure preserved ejection fraction empagliflozin",
            "atrial fibrillation doac ablation anticoagulation",
            "hypertension guidelines sprint trial blood pressure"
        ],
    },
    
    # ── NEUROLOGY ───────────────────────────────────────────────────────
    "neurology": {
        "wikipedia_articles": [
            "Brain", "Neurology", "Stroke", "Alzheimer's disease",
            "Parkinson's disease", "Multiple sclerosis", "Epilepsy",
            "Migraine", "Amyotrophic lateral sclerosis", "Concussion"
        ],
        "medlineplus_queries": [
            "stroke warning signs", "alzheimers dementia progression",
            "parkinsons tremor treatment", "multiple sclerosis demyelination"
        ],
        "pubmed_queries": [
            "ischemic stroke tpa thrombectomy time window",
            "alzheimers amyloid beta monoclonal antibody lecanemab",
            "parkinsons levodopa deep brain stimulation",
            "multiple sclerosis ocrelizumab disease modifying therapy"
        ],
    },

    # ── ONCOLOGY ────────────────────────────────────────────────────────
    "oncology": {
        "wikipedia_articles": [
            "Cancer", "Oncology", "Breast cancer", "Colorectal cancer",
            "Prostate cancer", "Melanoma", "Leukemia", "Lymphoma",
            "Pancreatic cancer", "Ovarian cancer", "Chemotherapy", "Immunotherapy"
        ],
        "medlineplus_queries": [
            "breast cancer screening mammogram", "colon cancer colonoscopy",
            "prostate cancer psa test", "melanoma skin cancer abcde"
        ],
        "pubmed_queries": [
            "breast cancer her2 targeted therapy trastuzumab deruxtecan",
            "colorectal cancer mismatch repair pembrolizumab",
            "prostate cancer castration resistant parp inhibitor",
            "melanoma braf inhibitor immune checkpoint pd1 ctl4"
        ],
    },

    # ── GASTROENTEROLOGY ────────────────────────────────────────────────
    "gastroenterology": {
        "wikipedia_articles": [
            "Gastrointestinal tract", "Liver", "Cirrhosis", "Hepatitis C",
            "Crohn's disease", "Ulcerative colitis", "Peptic ulcer disease",
            "Gastroesophageal reflux disease", "Celiac disease", "Pancreatitis"
        ],
        "medlineplus_queries": [
            "gerd acid reflux omeprazole", "crohns disease ibd",
            "ulcerative colitis bleeding", "hepatitis c cure"
        ],
        "pubmed_queries": [
            "inflammatory bowel disease crohns infliximab vedolizumab",
            "cirrhosis portal hypertension variceal bleeding",
            "hepatitis c direct acting antivirals svr",
            "acute pancreatitis fluid resuscitation ranson criteria"
        ],
    },
    
    # ── ENDOCRINOLOGY ───────────────────────────────────────────────────
    "endocrinology": {
        "wikipedia_articles": [
            "Endocrine system", "Diabetes mellitus type 1", "Diabetes mellitus type 2",
            "Hyperthyroidism", "Hypothyroidism", "Cushing's syndrome",
            "Addison's disease", "Polycystic ovary syndrome", "Osteoporosis"
        ],
        "medlineplus_queries": [
            "type 2 diabetes metformin a1c", "hypothyroidism levothyroxine",
            "osteoporosis bone density dex scan"
        ],
        "pubmed_queries": [
            "type 2 diabetes sglt2 inhibitor glp1 agonist cardiovascular",
            "type 1 diabetes continuous glucose monitor closed loop",
            "hypothyroidism hashimotos levothyroxine tsh",
            "osteoporosis bisphosphonate denosumab fracture risk"
        ],
    },
    
    # ── NEPHROLOGY ──────────────────────────────────────────────────────
    "nephrology": {
        "wikipedia_articles": [
            "Kidney", "Chronic kidney disease", "Acute kidney injury",
            "Nephrotic syndrome", "Polycystic kidney disease", "Kidney stone",
            "Dialysis", "Glomerulonephritis"
        ],
        "medlineplus_queries": [
            "chronic kidney disease gfr", "kidney stones calcium oxalate",
            "dialysis esrd"
        ],
        "pubmed_queries": [
            "chronic kidney disease sglt2 inhibitor dapagliflozin progression",
            "acute kidney injury rrt indications biomarker",
            "nephrotic syndrome membranous nephropathy rituximab",
            "kidney stone nephrolithiasis tamsulosin lithotripsy"
        ],
    }
}

def main():
    print(f"\n{'='*70}")
    print("  MASSIVE GLOBAL MEDICAL INGESTION (Qdrant)")
    print(f"{'='*70}\n")
    print("  Ingesting 6 major systems: Cardio, Neuro, Onco, Gastro, Endo, Nephro")

    try:
        ensure_collection()
    except Exception as exc:
        print(f"ERROR: Cannot connect to Qdrant: {exc}")
        sys.exit(1)

    validator = MedicalValidator(strict=False)
    summary = IngestionSummary()
    start_t = time.time()

    for domain_name, config in GLOBAL_DOMAINS.items():
        # Reusing the ingest_lung_domain function since the logic is identical
        stats = ingest_lung_domain(
            domain_name=domain_name,
            config=config,
            validator=validator,
            dry_run=False,
            skip_wikipedia=False,
            skip_medlineplus=False,
            skip_pubmed=False,
            pubmed_max=20,
            request_delay=0.5,
        )
        summary.domain_stats.append(stats)
        summary.total_fetched  += stats.pages_fetched
        summary.total_valid    += stats.pages_valid
        summary.total_rejected += stats.pages_rejected
        summary.total_stored   += stats.chunks_stored

    summary.elapsed_s = time.time() - start_t

    print(f"\n{'='*70}")
    print(f"  GLOBAL INGESTION COMPLETE — {summary.elapsed_s:.1f}s elapsed")
    print(f"{'='*70}")
    print(f"  Total Stored Chunks: {summary.total_stored}")

if __name__ == "__main__":
    sys.exit(main())
