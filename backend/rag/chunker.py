"""
chunker.py — Medical-section-aware + semantic chunking for RAG ingestion.

Strategy:
  - Detect known medical section headers first (section-aware chunking)
  - Slide a fixed window with overlap across each section (semantic chunking)
  - Preserve section context in every chunk's metadata
  - Never discard the section label — it massively improves retrieval quality
"""
import re
from typing import List, Optional
from backend.rag.schemas import ExtractedPage, Chunk
from backend.rag.utils import generate_chunk_id, get_timestamp
from backend.utils.logger import logger

# ─── Medical Section Header Patterns ──────────────────────────────────────────
# These cover standard clinical document sections.
# Expand this list as you process more document types.
MEDICAL_SECTIONS = [
    "chief complaint", "history of present illness", "past medical history",
    "family history", "social history", "review of systems",
    "physical examination", "vital signs", "assessment", "plan",
    "diagnosis", "differential diagnosis", "treatment", "medications",
    "allergies", "laboratory results", "imaging", "findings",
    "impression", "recommendations", "discussion", "conclusion",
    "background", "methods", "results", "abstract", "introduction",
    "symptoms", "history",
]

SECTION_PATTERN = re.compile(
    r"(?i)^(" + "|".join(re.escape(s) for s in MEDICAL_SECTIONS) + r")\s*[:\-]?\s*$",
    re.MULTILINE,
)

# ─── Chunking Configuration ────────────────────────────────────────────────────
CHUNK_SIZE = 500       # characters
CHUNK_OVERLAP = 100    # characters


def _detect_section(text_before: str) -> Optional[str]:
    """
    Look backwards in text to find the most recent medical section heading.
    Returns the section name if found, else None.
    """
    matches = list(SECTION_PATTERN.finditer(text_before))
    if matches:
        return matches[-1].group(1).strip().lower()
    return None


def _slide_chunks(text: str, source: str, page: int,
                  section: Optional[str], start_index: int) -> List[Chunk]:
    """
    Slide a fixed window with overlap across text.
    Preserves section label and page provenance in every chunk.
    """
    chunks: List[Chunk] = []
    text_len = len(text)
    pos = 0
    local_idx = 0

    while pos < text_len:
        end = min(pos + CHUNK_SIZE, text_len)
        chunk_text = text[pos:end].strip()

        if chunk_text:
            chunk_id = generate_chunk_id(source, page, start_index + local_idx)
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=chunk_text,
                source=source,
                page=page,
                section=section,
                document_type="medical_report",
                timestamp=get_timestamp(),
                chunk_index=start_index + local_idx,
                metadata={},
            ))
            local_idx += 1

        if end == text_len:
            break
        pos += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def chunk_pages(pages: List[ExtractedPage]) -> List[Chunk]:
    """
    Main chunking entry point.

    Strategy:
      1. Iterate over each extracted page.
      2. Split the page text on detected medical section headers.
      3. For each section block, slide fixed-size overlapping windows.
      4. Tag every chunk with its detected section name (or None).

    Args:
        pages: List of ExtractedPage objects from any ingestor.

    Returns:
        List of Chunk objects ready for embedding.
    """
    all_chunks: List[Chunk] = []
    global_index = 0

    for page in pages:
        text = page.text
        source = page.source

        # Split on section headers, keeping the delimiter
        parts = SECTION_PATTERN.split(text)

        if len(parts) == 1:
            # No sections detected — treat whole page as one block
            chunks = _slide_chunks(text, source, page.page, None, global_index)
            all_chunks.extend(chunks)
            global_index += len(chunks)
        else:
            # parts alternates: [pre-section text, section_name, section_body, ...]
            # After split with capturing group: [prefix, name, body, name, body ...]
            current_section: Optional[str] = None
            i = 0
            # Handle any leading text before first section
            if parts[0].strip():
                chunks = _slide_chunks(parts[0], source, page.page, None, global_index)
                all_chunks.extend(chunks)
                global_index += len(chunks)
                i = 1
            else:
                i = 1

            while i < len(parts) - 1:
                section_name = parts[i].strip().lower() if i < len(parts) else None
                section_body = parts[i + 1] if i + 1 < len(parts) else ""
                current_section = section_name
                if section_body.strip():
                    chunks = _slide_chunks(section_body, source, page.page,
                                           current_section, global_index)
                    all_chunks.extend(chunks)
                    global_index += len(chunks)
                i += 2

    # Back-fill total_chunks
    total = len(all_chunks)
    for c in all_chunks:
        c.total_chunks = total

    logger.info(f"[Chunker] Created {total} chunks from {len(pages)} pages")
    return all_chunks
