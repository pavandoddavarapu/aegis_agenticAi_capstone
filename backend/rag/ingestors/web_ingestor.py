"""
web_ingestor.py — Wikipedia + MedlinePlus + PubMed Web Content Ingestor

Fetches clean medical text from public sources:
  1. Wikipedia           — full article text via wikipedia-api
  2. MedlinePlus         — NIH consumer health summaries (JSON API)
  3. PubMed Abstracts    — via NCBI eutils (no API key for basic use)

Returns List[ExtractedPage] — compatible with the existing chunker pipeline.
"""
from __future__ import annotations

import time
import re
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx

from backend.rag.schemas import ExtractedPage
from backend.utils.logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Client (shared, sync)
# ─────────────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "AegisClinicalAI/1.0 (medical-knowledge-ingestion; "
        "contact: aegis-ai@research.org)"
    )
}
_TIMEOUT = httpx.Timeout(30.0)

# SSL verification disabled to handle corporate proxy / self-signed cert chains.
# httpx will still connect securely; only certificate chain validation is skipped.
_VERIFY_SSL = False


def _get(url: str, params: dict = None) -> Optional[httpx.Response]:
    try:
        r = httpx.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT,
                      follow_redirects=True, verify=_VERIFY_SSL)
        r.raise_for_status()
        return r
    except Exception as exc:
        logger.warning(f"[WebIngestor] HTTP error for {url}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Wikipedia Ingestor
# ─────────────────────────────────────────────────────────────────────────────

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def _clean_wikipedia_text(raw: str) -> str:
    """Remove wiki markup, citations, and boilerplate."""
    # Remove section headers like == References ==
    raw = re.sub(r"==+\s*(References|External links|See also|Bibliography|"
                 r"Further reading|Notes|Sources)\s*==+.*", "", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    # Remove {{templates}}
    raw = re.sub(r"\{\{[^}]+\}\}", " ", raw)
    # Remove [[wikilinks]] keeping visible text
    raw = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", raw)
    # Remove [1], [2] citations
    raw = re.sub(r"\[\d+\]", "", raw)
    # Remove multiple spaces / blank lines
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw.strip()


def ingest_wikipedia(title: str, source_tag: str = "") -> List[ExtractedPage]:
    """
    Fetch full Wikipedia article text for a given title.

    Args:
        title:      Wikipedia article title (e.g. "Pneumonia").
        source_tag: Optional prefix for source attribution.

    Returns:
        List of ExtractedPage (one page per ~3000-char section block).
    """
    source_label = f"wikipedia/{source_tag or title.lower().replace(' ', '_')}"
    logger.info(f"[WikiIngestor] Fetching: '{title}'")

    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": True,
        "exsectionformat": "plain",
        "format": "json",
        "redirects": 1,
    }
    resp = _get(WIKIPEDIA_API, params)
    if not resp:
        return []

    data = resp.json()
    pages_data = data.get("query", {}).get("pages", {})
    if not pages_data:
        return []

    page_data = next(iter(pages_data.values()))
    if "missing" in page_data:
        logger.warning(f"[WikiIngestor] Article not found: '{title}'")
        return []

    raw_text = page_data.get("extract", "")
    if not raw_text:
        return []

    clean_text = _clean_wikipedia_text(raw_text)

    # Split into ~3000-char logical pages (section-by-section)
    BLOCK_SIZE = 3000
    pages: List[ExtractedPage] = []
    blocks = [clean_text[i:i + BLOCK_SIZE]
              for i in range(0, len(clean_text), BLOCK_SIZE)]

    for idx, block in enumerate(blocks):
        if block.strip():
            pages.append(ExtractedPage(
                page=idx + 1,
                text=block,
                source=source_label,
                document_type="clinical_reference",
                metadata={
                    "article_title": title,
                    "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "block_index": idx,
                    "total_blocks": len(blocks),
                }
            ))

    logger.info(f"[WikiIngestor] '{title}' → {len(pages)} page blocks")
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# 2. MedlinePlus Ingestor
# ─────────────────────────────────────────────────────────────────────────────

MEDLINEPLUS_API = "https://wsearch.nlm.nih.gov/ws/query"


def ingest_medlineplus(query: str, max_results: int = 5) -> List[ExtractedPage]:
    """
    Search MedlinePlus health topics for a query and ingest summaries.

    Args:
        query:       Medical topic query (e.g. "asthma symptoms treatment").
        max_results: Maximum number of topic summaries to fetch.

    Returns:
        List of ExtractedPage with clean MedlinePlus consumer summaries.
    """
    logger.info(f"[MedlinePlusIngestor] Searching: '{query}'")
    source_label = f"medlineplus/{query.lower().replace(' ', '_')}"

    params = {
        "db": "healthTopics",
        "term": query,
        "retmax": max_results,
        "rettype": "brief",
    }
    resp = _get(MEDLINEPLUS_API, params)
    if not resp:
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.warning(f"[MedlinePlusIngestor] XML parse error: {exc}")
        return []

    pages: List[ExtractedPage] = []
    for idx, doc_elem in enumerate(root.iter("document")):
        url_elem = doc_elem.find("url")
        title_elem = doc_elem.find(".//content[@name='title']")
        summary_elem = doc_elem.find(".//content[@name='FullSummary']")
        if summary_elem is None:
            summary_elem = doc_elem.find(".//content[@name='snippet']")

        if summary_elem is None or not summary_elem.text:
            continue

        # Strip HTML tags from MedlinePlus summaries
        raw_summary = re.sub(r"<[^>]+>", " ", summary_elem.text)
        raw_summary = re.sub(r"\s+", " ", raw_summary).strip()

        title = title_elem.text if title_elem is not None else query
        url   = url_elem.text if url_elem is not None else ""

        if raw_summary:
            pages.append(ExtractedPage(
                page=idx + 1,
                text=f"{title}\n\n{raw_summary}",
                source=source_label,
                document_type="patient_education",
                metadata={
                    "article_title": title,
                    "source_url": url,
                    "provider": "MedlinePlus/NIH",
                }
            ))

    logger.info(f"[MedlinePlusIngestor] '{query}' → {len(pages)} summaries")
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# 3. PubMed Abstract Ingestor
# ─────────────────────────────────────────────────────────────────────────────

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def ingest_pubmed(
    query: str,
    max_results: int = 20,
    delay_s: float = 0.35,
) -> List[ExtractedPage]:
    """
    Fetch PubMed abstracts for a query.

    Args:
        query:      PubMed search query (e.g. "COPD exacerbation treatment").
        max_results: Maximum abstracts to fetch (NCBI allows burst up to 500).
        delay_s:    Polite delay between requests (NCBI asks <3/second).

    Returns:
        List of ExtractedPage — one per abstract.
    """
    logger.info(f"[PubMedIngestor] Searching: '{query}' (max={max_results})")
    source_label = f"pubmed/{query.lower().replace(' ', '_')[:40]}"

    # Step 1: Search for PMIDs
    search_resp = _get(PUBMED_SEARCH, {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
        "sort": "relevance",
    })
    if not search_resp:
        return []

    id_list = search_resp.json().get("esearchresult", {}).get("idlist", [])
    if not id_list:
        logger.warning(f"[PubMedIngestor] No results for '{query}'")
        return []

    time.sleep(delay_s)

    # Step 2: Fetch abstracts
    ids_str = ",".join(id_list)
    fetch_resp = _get(PUBMED_FETCH, {
        "db": "pubmed",
        "id": ids_str,
        "retmode": "xml",
        "rettype": "abstract",
    })
    if not fetch_resp:
        return []

    pages: List[ExtractedPage] = []
    try:
        root = ET.fromstring(fetch_resp.content)
    except ET.ParseError as exc:
        logger.warning(f"[PubMedIngestor] XML parse error: {exc}")
        return []

    for idx, article in enumerate(root.findall(".//PubmedArticle")):
        # Title
        title_elem = article.find(".//ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

        # Abstract text (may have multiple AbstractText sections)
        abstract_parts = []
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label", "")
            content = "".join(abs_text.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {content}")
            elif content:
                abstract_parts.append(content)
        abstract = " ".join(abstract_parts).strip()

        if not abstract:
            continue  # Skip articles without abstracts

        # Journal
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else "Unknown Journal"

        # Year
        year_elem = article.find(".//PubDate/Year")
        year = year_elem.text if year_elem is not None else ""

        # PMID
        pmid_elem = article.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""

        full_text = f"Title: {title}\nJournal: {journal} ({year})\n\n{abstract}"

        pages.append(ExtractedPage(
            page=idx + 1,
            text=full_text,
            source=source_label,
            document_type="research_paper",
            metadata={
                "article_title": title,
                "journal": journal,
                "year": year,
                "pmid": pmid,
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "provider": "PubMed/NCBI",
            }
        ))

    logger.info(f"[PubMedIngestor] '{query}' → {len(pages)} abstracts")
    return pages
