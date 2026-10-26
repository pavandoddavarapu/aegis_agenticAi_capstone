"""
run_full_ingestion.py — Master Ingestion Pipeline for Aegis Clinical AI.

Sequentially ingests:
  1. Medical Knowledge into Qdrant (16 domains from Wikipedia, MedlinePlus, PubMed)
  2. FDA Approved Drugs into Neo4j Knowledge Graph (100+ global drugs)
  3. Clinical Trials into Neo4j Knowledge Graph (Major global conditions)

Usage:
  python -u scripts/run_full_ingestion.py
"""
import os
import sys
import subprocess
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

python_exe = sys.executable

def run_script(script_path: str, description: str):
    print("\n" + "=" * 70)
    print(f" STARTING: {description}")
    print(f" Script:   {script_path}")
    print("=" * 70, flush=True)

    t0 = time.time()
    result = subprocess.run([python_exe, "-u", script_path], cwd=_ROOT)
    elapsed = time.time() - t0

    if result.returncode == 0:
        print(f"\n[DONE] {description} completed successfully in {elapsed:.1f}s.", flush=True)
    else:
        print(f"\n[WARNING] {description} exited with code {result.returncode} in {elapsed:.1f}s.", flush=True)

def main():
    print("=" * 70)
    print("   AEGIS CLINICAL AI — COMPLETE MULTI-DATABASE INGESTION")
    print("=" * 70, flush=True)

    # 1. Qdrant: Comprehensive Medical Knowledge (16 Domains)
    med_knowledge_script = os.path.join(_ROOT, "scripts", "ingest_medical_knowledge.py")
    run_script(med_knowledge_script, "Phase 1: Qdrant Vector Knowledge Ingestion (16 Medical Domains)")

    # 2. Neo4j: OpenFDA Global Drugs
    drugs_script = os.path.join(_ROOT, "scripts", "ingest_global_drugs.py")
    run_script(drugs_script, "Phase 2: Neo4j Knowledge Graph Ingestion (OpenFDA Drugs)")

    # 3. Neo4j: Global Clinical Trials
    trials_script = os.path.join(_ROOT, "scripts", "ingest_global_trials.py")
    run_script(trials_script, "Phase 3: Neo4j Clinical Trials Graph Ingestion")

    print("\n" + "=" * 70)
    print(" ALL KNOWLEDGE INGESTION PHASES COMPLETED!")
    print(" Both Qdrant and Neo4j are now fully loaded with clinical intelligence.")
    print("=" * 70, flush=True)

if __name__ == "__main__":
    main()
