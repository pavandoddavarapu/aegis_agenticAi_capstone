"""
ingest_global_drugs.py — Massive OpenFDA graph ingestion (Top 100+ Drugs)
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
from backend.utils.logger import logger

# Top 100+ most prescribed/important drugs globally
GLOBAL_DRUGS = [
    # Cardio / BP / Cholesterol
    "atorvastatin", "simvastatin", "rosuvastatin", "lisinopril", "amlodipine", 
    "losartan", "metoprolol", "carvedilol", "valsartan", "hydrochlorothiazide",
    "furosemide", "spironolactone", "clonidine", "amiodarone", "digoxin", "clopidogrel", "warfarin", "apixaban", "rivaroxaban",
    # Diabetes / Endo
    "metformin", "glipizide", "sitagliptin", "empagliflozin", "dapagliflozin",
    "insulin glargine", "semaglutide", "liraglutide", "levothyroxine",
    # Gastro
    "omeprazole", "pantoprazole", "lansoprazole", "famotidine", "ondansetron",
    # Respiratory
    "albuterol", "fluticasone", "budesonide", "montelukast", "tiotropium",
    # Neuro / Psych
    "gabapentin", "sertraline", "escitalopram", "fluoxetine", "citalopram",
    "bupropion", "trazodone", "venlafaxine", "duloxetine", "alprazolam",
    "clonazepam", "lorazepam", "zolpidem", "donepezil", "memantine",
    "levetiracetam", "topiramate", "lamotrigine", "quetiapine", "aripiprazole",
    # Pain / Anti-inflammatory
    "ibuprofen", "naproxen", "meloxicam", "diclofenac", "celecoxib",
    "acetaminophen", "tramadol", "hydrocodone", "oxycodone", "morphine",
    # Antibiotics / Anti-infectives
    "amoxicillin", "azithromycin", "cephalexin", "ciprofloxacin", "levofloxacin",
    "doxycycline", "sulfamethoxazole", "nitrofurantoin", "fluconazole",
    "valacyclovir", "paxlovid", "remdesivir",
    # Immuno / Rheum / Oncology
    "prednisone", "dexamethasone", "methylprednisolone", "methotrexate",
    "adalimumab", "infliximab", "rituximab", "pembrolizumab", "nivolumab",
    # Misc
    "allopurinol", "tamsulosin", "finasteride", "sildenafil", "tadalafil"
]

async def fetch_reactions(drug_name: str, session: aiohttp.ClientSession) -> list[str]:
    """Fetch top 20 reported adverse events for a drug from OpenFDA."""
    url = f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:{drug_name}&count=patient.reaction.reactionmeddrapt.exact&limit=20"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return [r["term"].lower() for r in data.get("results", [])]
    except Exception:
        pass
    return []

async def main():
    print(f"\n{'='*70}")
    print("  MASSIVE GLOBAL DRUG GRAPH INGESTION (Neo4j)")
    print(f"{'='*70}")
    
    client = GraphClient.get_instance()
    success = await client.initialize()
    if not success:
        print("ERROR: Could not connect to Neo4j.")
        sys.exit(1)
        
    print(f"Processing {len(GLOBAL_DRUGS)} drugs from OpenFDA...\n")
    
    async with aiohttp.ClientSession() as session:
        for drug in GLOBAL_DRUGS:
            print(f"Fetching FDA Adverse Events for: {drug}...", end=" ", flush=True)
            reactions = await fetch_reactions(drug, session)
            
            if not reactions:
                print("No data.")
                continue
                
            await client.run_write(
                "MERGE (d:Drug {name: $drug}) SET d.source='OpenFDA', d.confidence=1.0",
                {"drug": drug}
            )
            
            for reaction in reactions:
                query = """
                MATCH (d:Drug {name: $drug})
                MERGE (s:Symptom {name: $symptom})
                SET s.source = 'OpenFDA', s.confidence = 1.0
                MERGE (d)-[r:HAS_RISK]->(s)
                SET r.weight = 0.85, r.provenance = 'OpenFDA Adverse Event API'
                """
                await client.run_write(query, {"drug": drug, "symptom": reaction})
                
            print(f"Linked to {len(reactions)} adverse events.")
            await asyncio.sleep(0.5) 
            
    await client.close()
    print(f"\n{'='*70}")
    print("  MASSIVE GRAPH INGESTION COMPLETE")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())
