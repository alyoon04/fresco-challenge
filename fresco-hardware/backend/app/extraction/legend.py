"""
Stage 3: Legend Extraction

Scans the document for pages containing explicit manufacturer code lists and
finish code lists. Builds a per-document lookup that overrides global reference
sets during extraction.

Uses Claude Haiku 4.5 (claude-haiku-4-5-20251001) for classification and
extraction of legend entries.

Output: dict with 'mfr_codes' and 'finish_codes' mappings for the document.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, List

from app.extraction.ingest import PageData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 2000

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "legend_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# Load known codes for candidate detection
_REF_DIR = Path(__file__).resolve().parent.parent / "reference"
_KNOWN_CODES: set[str] = set()
try:
    with open(_REF_DIR / "mfr_codes.json") as f:
        _KNOWN_CODES |= set(json.load(f)["codes"].keys())
    with open(_REF_DIR / "finish_codes.json") as f:
        _KNOWN_CODES |= set(json.load(f)["codes"].keys())
except FileNotFoundError:
    logger.warning("Reference code files not found — legend candidate detection may be less effective")


# ---------------------------------------------------------------------------
# Legend candidate detection
# ---------------------------------------------------------------------------

def _is_legend_candidate(text: str) -> bool:
    """
    A page is a legend candidate if it contains BOTH:
      1. The literal strings "Code" and ("Description" or "Name")
      2. At least 5 known mfr or finish codes as whole words
    """
    text_lower = text.lower()

    # Condition 1: must have "code" AND ("description" or "name")
    has_code = "code" in text_lower
    has_desc_or_name = "description" in text_lower or "name" in text_lower
    if not (has_code and has_desc_or_name):
        return False

    # Condition 2: at least 5 known codes as whole words
    words = set(re.findall(r'\b[A-Z0-9]+\b', text.upper()))
    known_count = len(words & _KNOWN_CODES)
    return known_count >= 5


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_haiku(page_text: str, client: Any) -> dict:
    """
    Call Haiku 4.5 to extract legend codes from a single page's text.

    Returns: {"mfr_codes": {...}, "finish_codes": {...}}
    """
    response = client.messages.create(
        model=_HAIKU_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Extract the manufacturer and finish code legends from this page:\n\n{page_text}",
            }
        ],
    )

    # Parse JSON from the response text
    response_text = response.content[0].text

    # Try to extract JSON from the response (may be wrapped in markdown code blocks)
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        logger.warning("No JSON found in Haiku response, returning empty legend")
        return {"mfr_codes": {}, "finish_codes": {}}

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError:
        logger.warning("Failed to parse Haiku JSON response, returning empty legend")
        return {"mfr_codes": {}, "finish_codes": {}}

    # Validate structure
    if not isinstance(result.get("mfr_codes"), dict):
        result["mfr_codes"] = {}
    if not isinstance(result.get("finish_codes"), dict):
        result["finish_codes"] = {}

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_legend(pages: List[PageData], anthropic_client: Any) -> dict:
    """
    Extract per-document manufacturer and finish code legends.

    Algorithm:
      1. Identify pages likely to contain legends (conjunction of "Code" +
         "Description"/"Name" keywords, plus >=5 known codes).
      2. Call Haiku 4.5 on each candidate page to extract code→name mappings.
      3. Merge results across pages. On conflict, last write wins (later pages
         tend to have more authoritative legends).

    Args:
        pages: All pages from Stage 1 ingest.
        anthropic_client: Initialized Anthropic client.

    Returns:
        {"mfr_codes": {code: name, ...}, "finish_codes": {code: name, ...}}
    """
    merged: dict = {"mfr_codes": {}, "finish_codes": {}}

    # Find candidate pages
    candidate_pages = [p for p in pages if _is_legend_candidate(p.full_text)]
    logger.info(
        "Found %d legend candidate pages out of %d total",
        len(candidate_pages), len(pages),
    )

    if not candidate_pages:
        return merged

    # Extract from each candidate
    for page in candidate_pages:
        logger.info("Extracting legend from page %d", page.page_num)
        result = _call_haiku(page.full_text, anthropic_client)

        # Merge — last write wins for conflicts
        merged["mfr_codes"].update(result.get("mfr_codes", {}))
        merged["finish_codes"].update(result.get("finish_codes", {}))

    logger.info(
        "Legend extraction complete: %d mfr codes, %d finish codes",
        len(merged["mfr_codes"]), len(merged["finish_codes"]),
    )
    return merged
