"""
setup_databases.py — Initialize and Verify Qdrant and Neo4j Databases for Aegis Clinical AI.

This script:
  1. Tests connection to Qdrant (using QDRANT_URL and QDRANT_API_KEY from .env).
  2. Ensures the 'medical_docs' collection exists with 384-dimensional cosine vectors.
  3. Tests connection to Neo4j (using NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD from .env).
  4. Applies the 12 schema constraints and fulltext indexes defined in schema.py.
  5. Reports diagnostic status.

Usage:
  python scripts/setup_databases.py
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Ensure root directory is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from backend.rag.embeddings import EMBEDDING_DIMENSION
from backend.graphrag.schema import SCHEMA_CYPHER


def setup_qdrant() -> bool:
    print("\n" + "=" * 60)
    print(" 1. QDRANT VECTOR DATABASE VERIFICATION & SETUP")
    print("=" * 60)

    raw_url = os.getenv("QDRANT_URL", "http://localhost:6333").strip()
    raw_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    collection_name = "medical_docs"

    print(f"Connecting to Qdrant at: {raw_url}")
    print(f"API Key configured: {'YES (hidden)' if raw_api_key else 'NO (Local or None)'}")

    try:
        client = QdrantClient(url=raw_url, api_key=raw_api_key, timeout=30)
        collections = client.get_collections().collections
        existing_names = [c.name for c in collections]
        print(f"Existing collections in Qdrant: {existing_names or 'None'}")

        if collection_name not in existing_names:
            print(f"Creating collection '{collection_name}' (vector size: {EMBEDDING_DIMENSION}, distance: Cosine)...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            print(f"Collection '{collection_name}' successfully created!")
        else:
            info = client.get_collection(collection_name=collection_name)
            points_count = getattr(info, "points_count", 0)
            print(f"Collection '{collection_name}' already exists (Current points: {points_count}).")

        print("[SUCCESS] Qdrant connection and collection verified successfully!")
        return True

    except Exception as exc:
        print(f"\n[ERROR] Failed to connect to Qdrant: {exc}")
        print("\nTroubleshooting tips for Qdrant:")
        print(" - If using Qdrant Cloud:")
        print("   * Verify QDRANT_URL starts with https:// and ends with :6333 (or your cluster port).")
        print("   * Verify QDRANT_API_KEY is correctly pasted in your .env file.")
        print(" - If using Local Qdrant:")
        print("   * Ensure Qdrant is running on http://localhost:6333 or http://127.0.0.1:6333.")
        return False


async def setup_neo4j() -> bool:
    print("\n" + "=" * 60)
    print(" 2. NEO4J GRAPH DATABASE VERIFICATION & SETUP")
    print("=" * 60)

    uri = (os.getenv("NEO4J_URI") or "bolt://localhost:7687").strip()
    user = (os.getenv("NEO4J_USER") or "neo4j").strip()
    password = (os.getenv("NEO4J_PASSWORD") or "password").strip()

    print(f"Connecting to Neo4j at: {uri}")
    print(f"User: {user}")
    print(f"Password configured: {'YES (hidden)' if password else 'NO'}")

    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=20.0,
        )

        print("Testing connectivity to Neo4j...")
        try:
            await driver.verify_connectivity()
            print(f"Connection established with user '{user}'!")
        except Exception as auth_err:
            if "unauthorized" in str(auth_err).lower() or "authentication" in str(auth_err).lower():
                alt_user = "neo4j" if user != "neo4j" else "f3041047"
                print(f"Authentication with user '{user}' failed. Trying alternate user '{alt_user}'...")
                await driver.close()
                driver = AsyncGraphDatabase.driver(
                    uri,
                    auth=(alt_user, password),
                    connection_timeout=20.0,
                )
                await driver.verify_connectivity()
                print(f"Connection established with alternate user '{alt_user}'!")
                user = alt_user
            else:
                raise auth_err

        print("\nApplying schema constraints and indexes...")
        applied_count = 0
        async with driver.session() as session:
            for cypher in SCHEMA_CYPHER:
                try:
                    await session.run(cypher)
                    applied_count += 1
                except Exception as ddl_err:
                    print(f"  Note on DDL: {ddl_err}")

        print(f"Schema applied ({applied_count}/{len(SCHEMA_CYPHER)} statements verified).")

        # Check existing node count
        async with driver.session() as session:
            res = await session.run("MATCH (n) RETURN count(n) AS total_nodes")
            rec = await res.single()
            node_count = rec["total_nodes"] if rec else 0

            res_rel = await session.run("MATCH ()-[r]->() RETURN count(r) AS total_rels")
            rec_rel = await res_rel.single()
            rel_count = rec_rel["total_rels"] if rec_rel else 0

        print(f"Current graph size: {node_count} nodes, {rel_count} relationships.")
        await driver.close()

        print("[SUCCESS] Neo4j connection and schema verified successfully!")
        return True

    except Exception as exc:
        print(f"\n[ERROR] Failed to connect to Neo4j: {exc}")
        print("\nTroubleshooting tips for Neo4j:")
        print(" - If using Neo4j AuraDB (Cloud):")
        print("   * Note: AuraDB instances can take 1-3 minutes to finish provisioning ('Creating' -> 'Running').")
        print("   * Verify NEO4J_URI starts with neo4j+s:// (e.g. neo4j+s://<instance-id>.databases.neo4j.io)")
        print("   * Verify NEO4J_USER is 'neo4j' or your instance ID.")
        print("   * Verify NEO4J_PASSWORD matches the password provided when creating the AuraDB instance.")
        return False


async def main():
    print("=" * 60)
    print("   AEGIS CLINICAL AI — DATABASE INITIALIZATION & VERIFICATION")
    print("=" * 60)

    qdrant_ok = setup_qdrant()
    neo4j_ok = await setup_neo4j()

    print("\n" + "=" * 60)
    print(" SUMMARY")
    print("=" * 60)
    print(f" Qdrant Status: {'READY' if qdrant_ok else 'FAILED'}")
    print(f" Neo4j Status:  {'READY' if neo4j_ok else 'FAILED'}")
    print("=" * 60)

    if qdrant_ok and neo4j_ok:
        print("\nBoth databases are online, schemas are applied, and Aegis is ready!")
    else:
        print("\nPlease update your .env file with valid credentials and re-run this script.")


if __name__ == "__main__":
    asyncio.run(main())
