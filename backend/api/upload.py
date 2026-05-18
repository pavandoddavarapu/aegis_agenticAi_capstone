"""
upload.py — Document Upload API.

POST /upload
  - Accepts multipart file upload
  - Detects file type (pdf / image / dicom)
  - Saves to a temp file
  - Triggers the correct ingestion pipeline
  - Returns structured UploadResponse
"""
import os
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.rag.schemas import UploadResponse
from backend.rag.pipeline import run_pipeline
from backend.rag.utils import detect_file_type
from backend.utils.logger import logger

router = APIRouter(prefix="/upload", tags=["upload"])

# Maximum file size: 50 MB
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


@router.post("/", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a medical document and trigger the RAG ingestion pipeline.

    Supported types:
      - PDF  (.pdf)        → pdf_ingestor → full text extraction
      - Image (.png/.jpg)  → image_ingestor (placeholder, multimodal-ready)
      - DICOM (.dcm)       → dicom_ingestor (placeholder, multimodal-ready)

    Returns:
      UploadResponse with chunk counts and ingestion status.
    """
    filename = file.filename
    logger.info(f"[Upload API] Received file: '{filename}'")

    # ── File type detection ──────────────────────────────────────────────────
    document_type = detect_file_type(filename)
    if document_type is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{filename}'. Supported: .pdf, .png, .jpg, .dcm"
        )

    # ── Read and size-check ──────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is 50 MB."
        )

    # ── Write to temp file ────────────────────────────────────────────────────
    suffix = os.path.splitext(filename)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    logger.info(f"[Upload API] Saved to temp: {tmp_path} ({len(content)} bytes)")

    # ── Run ingestion pipeline ────────────────────────────────────────────────
    try:
        result = run_pipeline(
            filepath=tmp_path,
            filename=filename,
            document_type=document_type,
        )
    finally:
        # Always clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info(f"[Upload API] Cleaned up temp file: {tmp_path}")

    return UploadResponse(
        status=result.status,
        filename=filename,
        document_type=document_type,
        chunks_stored=result.chunks_stored,
        message=(
            f"Successfully ingested '{filename}': "
            f"{result.pages_extracted} pages, {result.chunks_stored} chunks stored."
        ),
    )
