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
    r'(?:'
    r'HARDWARE\s+(?:GROUP|SET)'                          # "Hardware Group" / "Hardware Set"
    r'|^\s*(?:Set|Item)\s*#\s*[A-Za-z0-9]'              # "Set #5", "Item #EX-4", requires #
    r'|^\s*(?:Set|Item)\s*:\s*[A-Za-z0-9]'              # "Set: EX-4.0", requires :
    r'|^\s*(?:Set|Item)\s+\d'                            # "Set 5", "Item 21", digit after space
    r'|^\s*(?:SET|ITEM)\s+[A-Z]{1,3}[\s-]?\d'           # "SET EX-4", "ITEM AL 01", short alpha prefix + digit
    r'|^\s*Heading\s*#?\s*\d'                            # "Heading #17", "Heading 5"
    r')',
    re.IGNORECASE | re.MULTILINE,
)

_QTY_RE = re.compile(
    r'\b\d+\s+EA\b',
    re.IGNORECASE,
)

# Lines that look like hardware component rows: start with a small integer (1-9)
# followed by text (not a page number, section number, or date).
# Matches "1 Continuous Hinge FMHD1 Pemko", "2 Surface Closer UNI-7500 Norton", etc.
_COMPONENT_LINE_RE = re.compile(
    r'^\s*[1-9]\d?\s+[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]',
    re.MULTILINE,
)

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
    page_num: int       # One-indexed, matches PageData.page_num
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


def _count_component_lines(text: str) -> int:
    """Count lines that look like hardware component rows.

    Matches lines starting with a small integer followed by capitalized words,
    e.g. '1 Continuous Hinge FMHD1 Pemko'. This is a structural signal that
    works regardless of specific component/manufacturer names.
    """
    return len(_COMPONENT_LINE_RE.findall(text))


def _count_known_codes(text: str) -> int:
    """
    Count how many known mfr or finish codes appear as whole words on the page.

    Uses word-boundary matching to avoid false positives from substrings.
    """
    count = 0
    words = set(re.findall(r'\b[A-Z0-9]+\b', text.upper()))
    for code in _ALL_KNOWN_CODES:
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
        code_count = _count_known_codes(text)
        comp_lines = _count_component_lines(text)

        # A page is a candidate if it has enough structural signals.
        # qty_count covers "3 EA" style, comp_lines covers "1 Continuous Hinge" style.
        line_count = qty_count + comp_lines

        is_candidate = (
            (has_header and (code_count >= 2 or line_count >= 3))
            or
            (code_count >= 4 and line_count >= 5)
        )

        if is_candidate:
            score = int(has_header) + line_count + code_count
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
