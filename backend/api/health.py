from fastapi import APIRouter, HTTPException
from qdrant_client import QdrantClient
import redis
import psycopg2
from backend.config import QDRANT_URL

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/qdrant")
def health_qdrant():
    try:
        # Use 127.0.0.1 to avoid local IPv6 resolution delays
        url = QDRANT_URL.replace("localhost", "127.0.0.1") if QDRANT_URL else "http://127.0.0.1:6333"
        client = QdrantClient(url=url)
        client.get_collections()
        return {"status": "healthy", "service": "qdrant"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant unhealthy: {str(e)}")

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
