"""
ingest_openfda.py — Ingest OpenFDA drug adverse events to Neo4j Graph.
"""
import asyncio
import sys
import os
import aiohttp

# ─── Project root on path ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.graphrag.graph_client import GraphClient
from backend.utils.logger import logger

COMMON_DRUGS = [
    "paxlovid", "amiodarone", "lisinopril", "metformin", "atorvastatin",
    "omeprazole", "amlodipine", "simvastatin", "losartan", "albuterol",
    "gabapentin", "sertraline", "furosemide", "pantoprazole", "fluticasone",
    "prednisone", "escitalopram", "ibuprofen", "rosuvastatin", "meloxicam",
    "azithromycin", "amoxicillin", "levothyroxine", "citalopram", "tramadol"
]

async def fetch_reactions(drug_name: str, session: aiohttp.ClientSession) -> list[str]:
    """Fetch top 15 reported adverse events for a drug from OpenFDA."""
    url = f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:{drug_name}&count=patient.reaction.reactionmeddrapt.exact&limit=15"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return [r["term"].lower() for r in data.get("results", [])]
    except Exception as e:
        logger.error(f"Failed to fetch {drug_name}: {e}")
    return []

async def main():
    print(f"\n{'='*60}")
    print("  OPENFDA DRUG ADVERSE EVENT GRAPH INGESTION")
    print(f"{'='*60}")
    
    client = GraphClient.get_instance()
    success = await client.initialize()
    if not success:
        print("ERROR: Could not connect to Neo4j. Check if Neo4j is running at localhost:7687 or NEO4J_URI is set.")
        sys.exit(1)
        
    print(f"Connected to Neo4j. Processing {len(COMMON_DRUGS)} common drugs...")
    
    async with aiohttp.ClientSession() as session:
        for drug in COMMON_DRUGS:
            print(f"Fetching FDA Adverse Events for: {drug}...", end=" ", flush=True)
            reactions = await fetch_reactions(drug, session)
            
            if not reactions:
                print("No data.")
                continue
                
            # 1. Create Drug Node
            await client.run_write(
                "MERGE (d:Drug {name: $drug}) SET d.source='OpenFDA', d.confidence=1.0",
                {"drug": drug}
            )
            
            # 2. Create Symptom Nodes and HAS_RISK relationships
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
            await asyncio.sleep(0.5) # Be polite to FDA API
            
    await client.close()
    print(f"{'='*60}")
    print("  GRAPH INGESTION COMPLETE")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(main())
