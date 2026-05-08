"""
Stage 2: Page Filtering (Conjunction Filter)

Filters candidate hardware schedule pages from full specbooks using a conjunction
of regex patterns. This is critical for reducing 600+ page specbooks down to the
~20-50 pages that actually contain hardware set definitions.

Filter logic:
  A page is a hardware schedule candidate if:
    (has_set_header AND (mfr_code_density >= 2 OR qty_pattern_count >= 2))
    OR
    (mfr_code_density >= 4 AND qty_pattern_count >= 5)  # continuation pages

  Set header pattern: r'(?:HARDWARE\\s+(?:GROUP|SET)|^\\s*Set\\s*#)' (case-insensitive)
  Qty pattern: r'\\b\\d+\\s+EA\\b'

Validated on a 611-page specbook: 611 -> 23 pages, zero false positives.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from app.extraction.ingest import PageData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SET_HEADER_RE = re.compile(
    r'(?:HARDWARE\s+(?:GROUP|SET)|^\s*Set\s*#)',
    re.IGNORECASE | re.MULTILINE,
)

_QTY_RE = re.compile(r'\b\d+\s+EA\b', re.IGNORECASE)

# Load known mfr codes for density counting
_REF_DIR = Path(__file__).resolve().parent.parent / "reference"
_MFR_CODES: set[str] = set()
_FINISH_CODES: set[str] = set()

try:
    with open(_REF_DIR / "mfr_codes.json") as f:
        _MFR_CODES = set(json.load(f)["codes"].keys())
    with open(_REF_DIR / "finish_codes.json") as f:
        _FINISH_CODES = set(json.load(f)["codes"].keys())
except FileNotFoundError:
    logger.warning("Reference code files not found — mfr density filter will be less effective")

# Combine for matching: a "known code" on a page suggests it's a schedule page
_ALL_KNOWN_CODES = _MFR_CODES | _FINISH_CODES


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CandidatePage:
    """A page that passed the conjunction filter."""
    page_num: int       # Zero-indexed, matches PageData.page_num
    full_text: str
    filter_score: int   # Sum of signals that triggered the filter


# ---------------------------------------------------------------------------
# Filter implementation
# ---------------------------------------------------------------------------

def _has_set_header(text: str) -> bool:
    """Check if the page text contains a hardware set/group header."""
    return bool(_SET_HEADER_RE.search(text))


def _count_qty_patterns(text: str) -> int:
    """Count occurrences of quantity patterns like '3 EA' on the page."""
    return len(_QTY_RE.findall(text))


def _count_mfr_codes(text: str) -> int:
    """
    Count how many known manufacturer codes appear as whole words on the page.

    Uses word-boundary matching to avoid false positives from substrings.
    """
    count = 0
    # Tokenize to whitespace-separated words, strip punctuation
    words = set(re.findall(r'\b[A-Z0-9]+\b', text.upper()))
    for code in _MFR_CODES:
        if code in words:
            count += 1
    return count


def filter_pages(pages: List[PageData]) -> List[CandidatePage]:
    """
    Apply the conjunction filter to identify hardware schedule pages.

    Args:
        pages: All pages from Stage 1 ingest.

    Returns:
        List of CandidatePage for pages that pass the filter, ordered by page_num.
    """
    candidates: List[CandidatePage] = []

    for page in pages:
        text = page.full_text
        has_header = _has_set_header(text)
        qty_count = _count_qty_patterns(text)
        mfr_count = _count_mfr_codes(text)

        # Conjunction filter logic
        is_candidate = (
            (has_header and (mfr_count >= 2 or qty_count >= 2))
            or
            (mfr_count >= 4 and qty_count >= 5)
        )

        if is_candidate:
            score = int(has_header) + qty_count + mfr_count
            candidates.append(CandidatePage(
                page_num=page.page_num,
                full_text=text,
                filter_score=score,
            ))

    logger.info(
        "Filtered %d pages -> %d candidates",
        len(pages), len(candidates),
    )
    return candidates
