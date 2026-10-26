from fastapi import APIRouter, HTTPException
from qdrant_client import QdrantClient
import redis
import psycopg2
import os
from backend.config import QDRANT_URL, QDRANT_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/qdrant")
def health_qdrant():
    try:
        url = QDRANT_URL or "http://127.0.0.1:6333"
        if "localhost" in url:
            url = url.replace("localhost", "127.0.0.1")
        client = QdrantClient(url=url, api_key=QDRANT_API_KEY, timeout=10)
        collections = client.get_collections()
        col_names = [c.name for c in collections.collections]
        return {
            "status": "healthy",
            "service": "qdrant",
            "collections": col_names,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant unhealthy: {str(e)}")

@router.get("/neo4j")
async def health_neo4j():
    try:
        from backend.graphrag.graph_client import GraphClient
        client = GraphClient.get_instance()
        if not client._ready:
            await client.initialize()
        if client._ready and client._driver:
            await client._driver.verify_connectivity()
            return {"status": "healthy", "service": "neo4j"}
        raise Exception("Neo4j driver failed to initialize")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j unhealthy: {str(e)}")

@router.get("/redis")
def health_redis():
    try:
        r = redis.Redis(host="127.0.0.1", port=6379, socket_timeout=2)
        r.ping()
        return {"status": "healthy", "service": "redis"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis unhealthy: {str(e)}")

@router.get("/postgres")
def health_postgres():
    try:
        conn = psycopg2.connect(
            dbname="aegis_db",
            user="aegis",
            password="aegis",
            host="127.0.0.1",
            port="5432",
            connect_timeout=2
        )
        conn.close()
        return {"status": "healthy", "service": "postgres"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres unhealthy: {str(e)}")

