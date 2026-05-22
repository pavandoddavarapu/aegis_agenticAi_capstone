"""
ingest_lung_trials_graph.py — Ingest ClinicalTrials.gov lung disease trials into Neo4j Graph.
"""
import asyncio
import sys
import os
import aiohttp
from typing import List, Dict, Any

# ─── Project root on path ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.graphrag.graph_client import GraphClient
from backend.utils.logger import logger

LUNG_DISEASES = [
    "Chronic Obstructive Pulmonary Disease",
    "Asthma",
    "Non-Small Cell Lung Cancer",
    "Small Cell Lung Cancer",
    "Idiopathic Pulmonary Fibrosis",
    "Pulmonary Arterial Hypertension",
    "Cystic Fibrosis",
    "Bronchiectasis",
    "COVID-19 Pneumonia",
    "Acute Respiratory Distress Syndrome",
    "Sarcoidosis",
    "Mesothelioma"
]

async def fetch_completed_trials(disease: str, session: aiohttp.ClientSession, limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch completed clinical trials for a specific condition using CT.gov v2 API."""
    # CT.gov v2 API endpoint
    # Docs: https://clinicaltrials.gov/data-about-studies/learn-about-api
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.cond": disease,
        "filter.overallStatus": "COMPLETED",
        "pageSize": limit,
        "fields": "NCTId,Condition,InterventionName,InterventionType"
    }
    
    try:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("studies", [])
            else:
                logger.error(f"CT.gov API Error for {disease}: Status {response.status}")
    except Exception as e:
        logger.error(f"Failed to fetch trials for {disease}: {e}")
    return []

def parse_study(study: dict) -> dict:
    """Extract condition and intervention data from the V2 study JSON."""
    protocol = study.get("protocolSection", {})
    
    nct_id = protocol.get("identificationModule", {}).get("nctId", "Unknown")
    
    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    
    interventions = []
    inv_module = protocol.get("armsInterventionsModule", {}).get("interventions", [])
    for inv in inv_module:
        name = inv.get("name", "")
        itype = inv.get("type", "OTHER")
        if name:
            interventions.append({"name": name.lower(), "type": itype})
            
    return {
        "nct_id": nct_id,
        "conditions": [c.lower() for c in conditions],
        "interventions": interventions
    }

async def ingest_trials_to_graph(client: GraphClient, query_disease: str, parsed_studies: list):
    """Insert diseases, treatments, and their relationships into Neo4j."""
    
    for study in parsed_studies:
        nct_id = study["nct_id"]
        
        # Ingest conditions as Disease nodes
        for cond in study["conditions"]:
            await client.run_write(
                "MERGE (d:Disease {name: $cond}) SET d.source='ClinicalTrials.gov', d.confidence=0.9",
                {"cond": cond}
            )
            
            # Ingest interventions and link them to the condition
            for inv in study["interventions"]:
                inv_name = inv["name"]
                inv_type = inv["type"]
                
                # Use Drug label for medications, Treatment for others (device, procedure, etc)
                label = "Drug" if inv_type in ["DRUG", "BIOLOGICAL"] else "Treatment"
                
                # Merge the intervention node
                await client.run_write(f"""
                    MERGE (t:{label} {{name: $name}})
                    SET t.source='ClinicalTrials.gov', t.confidence=0.9
                """, {"name": inv_name})
                
                # Link Disease -> Treatment (TREATED_BY)
                await client.run_write(f"""
                    MATCH (d:Disease {{name: $cond}})
                    MATCH (t:{label} {{name: $name}})
                    MERGE (d)-[r:TREATED_BY]->(t)
                    SET r.provenance = $provenance, r.weight = 0.85
                """, {
                    "cond": cond,
                    "name": inv_name,
                    "provenance": f"CT.gov Trial: {nct_id}"
                })

async def main():
    print(f"\n{'='*70}")
    print("  CLINICAL TRIALS (LUNG DISEASES) GRAPH INGESTION")
    print(f"{'='*70}")
    
    client = GraphClient.get_instance()
    success = await client.initialize()
    if not success:
        print("ERROR: Could not connect to Neo4j.")
        sys.exit(1)
        
    print(f"Connected to Neo4j. Fetching Phase 3/4 trial data for {len(LUNG_DISEASES)} lung conditions...\n")
    
    total_trials = 0
    total_interventions = 0
    
    async with aiohttp.ClientSession() as session:
        for disease in LUNG_DISEASES:
            print(f"[{disease}] Fetching completed trials...", end=" ", flush=True)
            studies = await fetch_completed_trials(disease, session, limit=20)
            
            if not studies:
                print("No data.")
                continue
                
            parsed = [parse_study(s) for s in studies]
            await ingest_trials_to_graph(client, disease, parsed)
            
            # Count stats
            valid_trials = [p for p in parsed if p["interventions"]]
            num_inv = sum(len(p["interventions"]) for p in valid_trials)
            total_trials += len(valid_trials)
            total_interventions += num_inv
            
            print(f"Ingested {len(valid_trials)} trials linking to {num_inv} treatments/drugs.")
            await asyncio.sleep(1) # Be polite to CT.gov API
            
    await client.close()
    print(f"\n{'='*70}")
    print(f"  INGESTION COMPLETE: Added {total_interventions} trial-backed treatments across {total_trials} studies.")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())
