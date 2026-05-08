"""
Stage 5: Reconciliation

Groups extracted hardware sets by set_number across pages and merges components
from multi-page sets or overlapping batch duplicates.

Handles:
  - Sets that span page breaks (same set_number on consecutive pages)
  - Deduplication of components extracted from overlapping page batches
"""

import logging
from collections import defaultdict
from typing import List

from app.extraction.ingest import PageData
from app.models.schemas import HardwareSet, Location

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Multi-page merging
# ---------------------------------------------------------------------------

def _sets_overlap(a: HardwareSet, b: HardwareSet) -> bool:
    """Check if two sets share any pages (from batch overlap)."""
    a_pages = {loc.page_num for loc in a.locations}
    b_pages = {loc.page_num for loc in b.locations}
    return bool(a_pages & b_pages)


def _should_merge(primary: HardwareSet, candidate: HardwareSet) -> bool:
    """
    Decide whether `candidate` is a continuation of `primary` (same set
    spanning a page break) rather than a distinct set that happens to share
    the same set_number.

    Rules:
      - Same set_number.
      - Pages are near-adjacent (within 2 pages of each other).
      - The candidate has fewer than 3 components (a full independent set
        would typically have 3+; a continuation fragment has 1-2 leftover rows).
    """
    if primary.set_number != candidate.set_number:
        return False

    # Overlapping pages means duplicate from batch overlap — always merge
    if _sets_overlap(primary, candidate):
        return True

    # Check page adjacency
    primary_pages = {loc.page_num for loc in primary.locations}
    candidate_pages = {loc.page_num for loc in candidate.locations}
    if not primary_pages or not candidate_pages:
        return True  # No location info — merge conservatively

    min_gap = min(
        abs(cp - pp)
        for cp in candidate_pages
        for pp in primary_pages
    )
    if min_gap > 2:
        return False

    # Continuation heuristic: the later occurrence has few components
    return len(candidate.components) < 3


def _merge_two_sets(primary: HardwareSet, candidate: HardwareSet) -> HardwareSet:
    """Merge a continuation set into the primary set, deduplicating components."""
    # Deduplicate components by (description, catalog_number)
    seen = set()
    merged_components = []
    for comp in primary.components + candidate.components:
        key = (comp.description.value, comp.catalog_number.value if comp.catalog_number else None)
        if key not in seen:
            seen.add(key)
            merged_components.append(comp)

    # Deduplicate locations by page_num
    seen_pages = set()
    merged_locations = []
    for loc in primary.locations + candidate.locations:
        if loc.page_num not in seen_pages:
            seen_pages.add(loc.page_num)
            merged_locations.append(loc)

    return HardwareSet(
        set_number=primary.set_number,
        description=primary.description or candidate.description,
        locations=merged_locations,
        components=merged_components,
        is_not_used=primary.is_not_used and candidate.is_not_used,
        overall_confidence=min(primary.overall_confidence, candidate.overall_confidence),
        column_classification_reasoning=(
            primary.column_classification_reasoning
            or candidate.column_classification_reasoning
        ),
    )


def _merge_sets(sets: List[HardwareSet]) -> List[HardwareSet]:
    """
    Group sets by set_number and merge continuations.

    Sets are processed in order. For each set_number, the first occurrence
    becomes the primary. Subsequent occurrences are merged if they look like
    continuations (near-adjacent pages, few components); otherwise kept separate.
    """
    if not sets:
        return []

    # Group by set_number, preserving order of first appearance
    groups: dict[str, List[HardwareSet]] = defaultdict(list)
    order: List[str] = []
    for s in sets:
        if s.set_number not in groups:
            order.append(s.set_number)
        groups[s.set_number].append(s)

    merged: List[HardwareSet] = []
    for set_num in order:
        group = groups[set_num]
        primary = group[0]
        for candidate in group[1:]:
            if _should_merge(primary, candidate):
                logger.info(
                    "Merging continuation of set %s (pages %s into %s)",
                    set_num,
                    [l.page_num for l in candidate.locations],
                    [l.page_num for l in primary.locations],
                )
                primary = _merge_two_sets(primary, candidate)
            else:
                # Distinct set with same number — keep both
                merged.append(primary)
                primary = candidate
        merged.append(primary)

    logger.info("Merged %d raw sets -> %d reconciled sets", len(sets), len(merged))
    return merged


# ---------------------------------------------------------------------------
# Location fixing — search PDF text blocks for identifying text
# ---------------------------------------------------------------------------

def _locate_set(
    hw_set: HardwareSet,
    pages_by_num: dict[int, PageData],
) -> HardwareSet:
    """
    Find this set's location by searching all page text blocks for identifying
    strings from the set_number and description.

    Extracts search terms like "Doors: D118A", "Item #131", "Set #U-02"
    from the description, then finds the first text block containing each term.
    """
    search_terms = _extract_search_terms(hw_set.set_number, hw_set.description)

    locations: list[Location] = []
    seen_pages: set[int] = set()

    for term in search_terms:
        term_lower = term.lower()
        for page_num in sorted(pages_by_num.keys()):
            if page_num in seen_pages:
                continue
            page_data = pages_by_num[page_num]
            for tb in page_data.text_blocks:
                if term_lower in tb.text.lower():
                    locations.append(Location(
                        page_num=page_num,
                        bbox=tb.bbox,
                        line_range=(tb.line_idx, tb.line_idx),
                    ))
                    seen_pages.add(page_num)
                    break

    if locations:
        return hw_set.model_copy(update={"locations": locations})

    # Fallback: keep model's locations
    return hw_set


def _extract_search_terms(set_number: str, description: str | None) -> list[str]:
    """
    Pull out the best identifying strings to search for in the PDF.

    Prioritizes specific identifiers like door numbers and item references
    over generic text.
    """
    import re
    terms: list[str] = []

    if description:
        # "Doors: D118A" or "Doors: D101A, D149A"
        doors_match = re.search(r'Doors?:\s*([^\n]+)', description, re.IGNORECASE)
        if doors_match:
            # Use the first door number as search term
            door_text = doors_match.group(1).strip()
            first_door = re.split(r'[,;]', door_text)[0].strip()
            if first_door:
                terms.append(first_door)

        # "Item #131" or "Items #8"
        item_match = re.search(r'Items?\s*#?\s*(\d+)', description)
        if item_match:
            terms.append(f'Item #{item_match.group(1)}')

    # Fallback: "Set #N" or "Item #N" using set_number
    sn = set_number.strip()
    terms.append(f'Set #{sn}')
    terms.append(f'Item #{sn}')

    return terms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile_sets(
    sets: List[HardwareSet],
    pages: List[PageData],
) -> List[HardwareSet]:
    """
    Post-process extracted hardware sets: merge multi-page sets and attach bboxes.

    1. Multi-page merging: group by set_number, merge continuations.
    2. Bbox attachment: map line_range to PyMuPDF bboxes from ingest.

    Args:
        sets: Raw hardware sets from Stage 4 extraction.
        pages: All pages from Stage 1 ingest (for bbox data).

    Returns:
        Reconciled list of HardwareSet with merged components and bboxes.
    """
    if not sets:
        return []

    merged = _merge_sets(sets)

    pages_by_num = {p.page_num: p for p in pages}
    result = [_locate_set(s, pages_by_num) for s in merged]

    return result
