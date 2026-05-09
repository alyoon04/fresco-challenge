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


def _get_strikethrough_lines(page: fitz.Page) -> List[tuple]:
    """
    Collect horizontal lines used for strikethrough on a page.

    Detects both:
      1. StrikeOut annotations (PDF_ANNOT_STRIKE_OUT)
      2. Thin horizontal vector lines drawn over text (common in spec editing)

    Returns list of (x0, y, x1) tuples representing horizontal line segments.
    """
    lines = []

    # Method 1: StrikeOut annotations
    for annot in page.annots() or []:
        if annot.type[0] == fitz.PDF_ANNOT_STRIKE_OUT:
            r = annot.rect
            y_mid = (r.y0 + r.y1) / 2
            lines.append((r.x0, y_mid, r.x1))

    # Method 2: Vector drawings — thin horizontal lines
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            # Lines: ("l", start_point, end_point)
            if item[0] == "l":
                p1, p2 = fitz.Point(item[1]), fitz.Point(item[2])
                dy = abs(p2.y - p1.y)
                dx = abs(p2.x - p1.x)
                # Horizontal line: minimal vertical change, meaningful width
                if dy < 2 and dx > 20:
                    lines.append((min(p1.x, p2.x), (p1.y + p2.y) / 2, max(p1.x, p2.x)))

            # Thin rectangles also used as strikethrough lines
            elif item[0] == "re":
                r = fitz.Rect(item[1])
                # Very thin horizontally (< 3pt tall, > 20pt wide)
                if r.height < 3 and r.width > 20:
                    lines.append((r.x0, (r.y0 + r.y1) / 2, r.x1))

    return lines


def _is_line_struck_out(text_lines: list, strike_lines: List[tuple]) -> List[bool]:
    """
    For each text line (from get_text("dict")), check if a strikethrough
    line crosses through its vertical midpoint.

    Args:
        text_lines: List of dicts with "bbox" and "spans" from PyMuPDF dict output.
        strike_lines: List of (x0, y, x1) horizontal line segments.

    Returns:
        List of booleans, one per text line.
    """
    results = []
    for line in text_lines:
        bbox = line["bbox"]  # (x0, y0, x1, y1)
        line_y_mid = (bbox[1] + bbox[3]) / 2
        line_height = bbox[3] - bbox[1]
        struck = False

        for sx0, sy, sx1 in strike_lines:
            # The strike line's y must be near the text line's vertical center
            # (within 40% of line height from center — generous for varying fonts)
            if abs(sy - line_y_mid) < line_height * 0.4:
                # And horizontally overlap the text significantly
                overlap_x0 = max(bbox[0], sx0)
                overlap_x1 = min(bbox[2], sx1)
                if overlap_x1 - overlap_x0 > (bbox[2] - bbox[0]) * 0.5:
                    struck = True
                    break

        results.append(struck)
    return results


def ingest_document(pdf_bytes: bytes) -> List[PageData]:
    """
    Extract text blocks with bounding boxes from every page of a PDF.

    Detects strikethrough text (via annotations and vector drawings) and
    prefixes it with [STRUCK OUT] so downstream extraction can skip it.

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
        strike_lines = _get_strikethrough_lines(page)

        # Use "dict" mode to get per-line detail for strikethrough detection
        page_dict = page.get_text("dict")
        struck_line_indices: set = set()

        if strike_lines:
            # Flatten all lines from all blocks with their block/line index
            all_lines = []
            line_map = []  # (block_idx, line_idx) for each entry in all_lines
            for bi, block in enumerate(page_dict["blocks"]):
                if block.get("type", 0) != 0:
                    continue
                for li, line in enumerate(block.get("lines", [])):
                    all_lines.append(line)
                    line_map.append((bi, li))

            struck_flags = _is_line_struck_out(all_lines, strike_lines)
            for idx, struck in enumerate(struck_flags):
                if struck:
                    struck_line_indices.add(line_map[idx])

        # Build text blocks, marking struck-out lines
        text_blocks: List[TextBlock] = []
        block_idx = 0

        for bi, block in enumerate(page_dict["blocks"]):
            if block.get("type", 0) != 0:  # Skip image blocks
                continue

            block_lines = []
            for li, line in enumerate(block.get("lines", [])):
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                if not line_text:
                    continue
                if (bi, li) in struck_line_indices:
                    line_text = f"[STRUCK OUT] {line_text}"
                block_lines.append(line_text)

            text = "\n".join(block_lines)
            if not text:
                continue

            bbox = (block["bbox"][0], block["bbox"][1],
                    block["bbox"][2], block["bbox"][3])
            text_blocks.append(TextBlock(
                text=text,
                bbox=bbox,
                line_idx=block_idx,
            ))
            block_idx += 1

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
