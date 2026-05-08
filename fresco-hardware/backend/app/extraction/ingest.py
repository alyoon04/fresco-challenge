"""
Stage 1: Document Ingestion

Uses PyMuPDF to extract per-page text blocks with bounding boxes from uploaded
PDF specbooks. Results are stored in Postgres keyed on (doc_id, page_num).

Each text block includes:
  - Raw text content
  - Bounding box coordinates (x0, y0, x1, y1)
  - Page dimensions for coordinate normalization
"""

import logging
from dataclasses import dataclass, field
from typing import List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    """A single text block extracted from a PDF page."""
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    line_idx: int


@dataclass
class PageData:
    """All extracted data for one page of a PDF."""
    page_num: int                       # Zero-indexed
    width: float
    height: float
    text_blocks: List[TextBlock] = field(default_factory=list)
    full_text: str = ""                 # Concatenated text for filtering/search


def ingest_document(pdf_bytes: bytes) -> List[PageData]:
    """
    Extract text blocks with bounding boxes from every page of a PDF.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of PageData, one per page, ordered by page number.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: List[PageData] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        rect = page.rect

        # Extract text blocks: each is (x0, y0, x1, y1, text, block_no, block_type)
        # block_type 0 = text, 1 = image
        raw_blocks = page.get_text("blocks")
        text_blocks: List[TextBlock] = []

        for idx, block in enumerate(raw_blocks):
            if block[6] != 0:  # Skip image blocks
                continue
            text = block[4].strip()
            if not text:
                continue
            text_blocks.append(TextBlock(
                text=text,
                bbox=(block[0], block[1], block[2], block[3]),
                line_idx=idx,
            ))

        full_text = "\n".join(tb.text for tb in text_blocks)

        pages.append(PageData(
            page_num=page_num,
            width=rect.width,
            height=rect.height,
            text_blocks=text_blocks,
            full_text=full_text,
        ))

    doc.close()
    logger.info("Ingested %d pages from PDF (%d bytes)", len(pages), len(pdf_bytes))
    return pages
