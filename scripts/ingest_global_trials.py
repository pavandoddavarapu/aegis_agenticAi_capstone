"""
ingest_global_trials.py — Massive global clinical trials graph ingestion
"""
import asyncio
import sys
import os
import aiohttp
from dotenv import load_dotenv

# ─── Project root on path ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

from backend.graphrag.graph_client import GraphClient
from scripts.ingest_lung_trials_graph import fetch_completed_trials, parse_study, ingest_trials_to_graph

GLOBAL_DISEASES = [
    # Cardio
    "Myocardial Infarction", "Heart Failure", "Atrial Fibrillation",
    "Coronary Artery Disease", "Hypertension", "Aortic Aneurysm",
    # Neuro
    "Stroke", "Alzheimer's Disease", "Parkinson's Disease",
    "Multiple Sclerosis", "Epilepsy", "Migraine",
    # Oncology
    "Breast Cancer", "Colorectal Cancer", "Prostate Cancer",
    "Melanoma", "Leukemia", "Lymphoma", "Pancreatic Cancer", "Ovarian Cancer",
    # Gastro
    "Cirrhosis", "Hepatitis C", "Crohn's Disease", "Ulcerative Colitis",
    "Peptic Ulcer", "Gastroesophageal Reflux Disease",
    # Endo
    "Type 1 Diabetes", "Type 2 Diabetes", "Hyperthyroidism", "Hypothyroidism",
    "Polycystic Ovary Syndrome", "Osteoporosis",
    # Nephro
    "Chronic Kidney Disease", "Acute Kidney Injury", "Nephrotic Syndrome",
    "Polycystic Kidney Disease", "Kidney Stones", "Glomerulonephritis"
]

async def main():
    print(f"\n{'='*70}")
    print("  MASSIVE GLOBAL CLINICAL TRIALS GRAPH INGESTION")
    print(f"{'='*70}")
    
    client = GraphClient.get_instance()
    success = await client.initialize()
    if not success:
        print("ERROR: Could not connect to Neo4j.")
        sys.exit(1)
        
    print(f"Fetching trials for {len(GLOBAL_DISEASES)} major conditions...\n")
    
    total_trials = 0
    total_interventions = 0
    
    async with aiohttp.ClientSession() as session:
        for disease in GLOBAL_DISEASES:
            print(f"[{disease}] Fetching...", end=" ", flush=True)
            studies = await fetch_completed_trials(disease, session, limit=15)
            
            if not studies:
                print("No data.")
                continue
                
            parsed = [parse_study(s) for s in studies]
            await ingest_trials_to_graph(client, disease, parsed)
            
            valid_trials = [p for p in parsed if p["interventions"]]
            num_inv = sum(len(p["interventions"]) for p in valid_trials)
            total_trials += len(valid_trials)
            total_interventions += num_inv
            
            print(f"Ingested {len(valid_trials)} trials, {num_inv} treatments.")
            await asyncio.sleep(1)
            
    await client.close()
    print(f"\n{'='*70}")
    print(f"  COMPLETE: Added {total_interventions} trial-backed treatments across {total_trials} studies.")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())
