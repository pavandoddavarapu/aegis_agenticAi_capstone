"""
utils.py — Shared utility helpers for the RAG pipeline.
"""
import hashlib
import re
from datetime import datetime
from typing import Optional


def generate_chunk_id(source: str, page: int, chunk_index: int) -> str:
    """Generate a deterministic unique ID for a chunk."""
    raw = f"{source}::page{page}::chunk{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def clean_text(text: str) -> str:
    """
    Normalize raw extracted text:
    - collapse multiple whitespace/newlines
    - strip leading/trailing whitespace
    - remove control characters
    """
    # Remove non-printable control characters (except newline/tab)
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", text)
    # Collapse multiple spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_timestamp() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.utcnow().isoformat()


def detect_file_type(filename: str) -> Optional[str]:
    """
    Detect document type from file extension.
    Returns: 'pdf' | 'image' | 'dicom' | None
    """
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        return "pdf"
    elif filename_lower.endswith((".dcm", ".dicom")):
        return "dicom"
    elif filename_lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp")):
        return "image"
    return None


def confidence_label(score: float) -> str:
    """
    Convert a similarity score float to a human-readable confidence label.
    Powers validation agents and reflection loops later.
    """
    if score >= 0.85:
        return "high"
    elif score >= 0.65:
        return "medium"
    return "low"
