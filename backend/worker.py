"""
worker.py — Celery Background Workers (Phase 11)

Moves heavy IO-bound or CPU-bound jobs (PDF ingestion, large OCR tasks)
to asynchronous background workers backed by Redis.
"""
import os
from celery import Celery
from backend.utils.logger import logger

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app
celery_app = Celery(
    "aegis_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600, # 10 mins max
)

@celery_app.task(bind=True, name="tasks.process_document")
def process_document_task(self, file_path: str, user_id: str):
    """
    Background task for processing heavy PDFs.
    In a real app, this would call the chunker and Qdrant ingestion.
    """
    logger.info(f"[Celery] Processing document: {file_path} for user: {user_id}")
    # Simulating long-running ingestion
    import time
    time.sleep(5)
    logger.info(f"[Celery] Document {file_path} processed successfully.")
    return {"status": "success", "file_path": file_path}

@celery_app.task(bind=True, name="tasks.process_multimodal")
def process_multimodal_task(self, image_hash: str):
    """
    Background task for heavy OCR or vision analysis.
    """
    logger.info(f"[Celery] Processing multimodal image hash: {image_hash}")
    import time
    time.sleep(3)
    logger.info(f"[Celery] Image {image_hash} analysis complete.")
    return {"status": "success", "image_hash": image_hash}
