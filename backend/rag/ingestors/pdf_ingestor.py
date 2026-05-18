"""
pdf_ingestor.py — Extracts text and page metadata from PDF documents.

Responsibilities:
  - Load PDF using pypdf
  - Extract raw text per page
  - Preserve page numbers, source filename, timestamps
  - Output a list of ExtractedPage objects
"""
from typing import List
from pypdf import PdfReader
from backend.rag.schemas import ExtractedPage
from backend.rag.utils import clean_text, get_timestamp
from backend.utils.logger import logger


def ingest_pdf(filepath: str, filename: str) -> List[ExtractedPage]:
    """
    Extract text and metadata from each page of a PDF file.

    Args:
        filepath: Absolute path to the PDF file on disk.
        filename: Original filename (used as source attribution).

    Returns:
        List of ExtractedPage objects, one per PDF page.
    """
    pages: List[ExtractedPage] = []

    try:
        reader = PdfReader(filepath)
        total_pages = len(reader.pages)
        logger.info(f"[PDF Ingestor] Reading '{filename}' — {total_pages} pages")

        for i, page in enumerate(reader.pages):
            raw_text = page.extract_text() or ""
            cleaned = clean_text(raw_text)

            if not cleaned:
                logger.warning(f"[PDF Ingestor] Page {i + 1} of '{filename}' yielded no text, skipping.")
                continue

            pages.append(ExtractedPage(
                page=i + 1,
                text=cleaned,
                source=filename,
                document_type="medical_report",
                metadata={
                    "total_pages": total_pages,
                    "ingested_at": get_timestamp(),
                }
            ))

        logger.info(f"[PDF Ingestor] Extracted {len(pages)} pages from '{filename}'")

    except Exception as e:
        logger.error(f"[PDF Ingestor] Failed to process '{filename}': {e}")
        raise

    return pages
