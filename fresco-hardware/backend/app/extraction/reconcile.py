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


def _candidate_has_own_header(candidate: HardwareSet) -> bool:
    """
    Check if the candidate looks like an independent set with its own header,
    vs. orphaned continuation rows from a page break.

    A continuation typically has no description (or re-uses the same one),
    because the header was on the previous page. An independent set with the
    same number would have its own distinct header line.
    """
    # No description at all — almost certainly a continuation
    if not candidate.description:
        return False
    # Very short description that's just the set number — likely a continuation
    desc = candidate.description.strip()
    if desc == candidate.set_number.strip():
        return False
    return True


def _should_merge(primary: HardwareSet, candidate: HardwareSet) -> bool:
    """
    Decide whether `candidate` is a continuation of `primary` (same set
    spanning a page break) rather than a distinct set that happens to share
    the same set_number.

    Rules:
      - Same set_number.
      - Overlapping pages (batch overlap) — always merge.
      - Pages are near-adjacent (within 2 pages) AND the candidate looks
        like a continuation (no independent header) — merge regardless of
        how many components it has.
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

    # Adjacent pages with same set_number: merge unless the candidate
    # clearly has its own independent header (a distinct re-use of the
    # same set number, which is rare but possible).
    if not _candidate_has_own_header(candidate):
        return True

    # Has its own header but few components — still likely a continuation
    # where the model repeated the header text
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


def _components_overlap(a: HardwareSet, b: HardwareSet) -> bool:
    """
    Check if two sets share most of the same components (by description+catalog).
    Used to detect Format D duplicates from overlapping batches where the
    set_number differs (e.g. "21" vs "67") because each batch used a different
    first item number.
    """
    if not a.components or not b.components:
        return False

    def _comp_keys(s: HardwareSet) -> set:
        return {
            (c.description.value, c.catalog_number.value if c.catalog_number else None)
            for c in s.components
        }

    a_keys = _comp_keys(a)
    b_keys = _comp_keys(b)
    if not a_keys or not b_keys:
        return False

    overlap = len(a_keys & b_keys)
    smaller = min(len(a_keys), len(b_keys))
    # If 70%+ of the smaller set's components match, they're the same set
    return overlap >= smaller * 0.7


def _dedup_format_d(sets: List[HardwareSet]) -> List[HardwareSet]:
    """
    Remove Format D duplicates from overlapping batches.

    When a Format D item list spans pages, overlapping batches may each produce
    a set with different set_numbers (first item on their visible page) but
    identical components. Keep the one with more items (broader description)
    and drop the subset.
    """
    if len(sets) < 2:
        return sets

    absorbed: set = set()  # indices to remove

    for i in range(len(sets)):
        if i in absorbed:
            continue
        for j in range(i + 1, len(sets)):
            if j in absorbed:
                continue

            a, b = sets[i], sets[j]

            # Must be on overlapping or adjacent pages
            if not _sets_overlap(a, b):
                a_pages = {loc.page_num for loc in a.locations}
                b_pages = {loc.page_num for loc in b.locations}
                if a_pages and b_pages:
                    min_gap = min(
                        abs(cp - pp) for cp in b_pages for pp in a_pages
                    )
                    if min_gap > 2:
                        continue

            # Check if components are mostly the same
            if _components_overlap(a, b):
                # Keep the one with the longer description (more items listed)
                desc_a = a.description or ""
                desc_b = b.description or ""
                if len(desc_a) >= len(desc_b):
                    absorbed.add(j)
                    logger.info(
                        "Dedup Format D: dropping set %s (pages %s), "
                        "subsumed by set %s (pages %s)",
                        b.set_number,
                        [l.page_num for l in b.locations],
                        a.set_number,
                        [l.page_num for l in a.locations],
                    )
                else:
                    absorbed.add(i)
                    logger.info(
                        "Dedup Format D: dropping set %s (pages %s), "
                        "subsumed by set %s (pages %s)",
                        a.set_number,
                        [l.page_num for l in a.locations],
                        b.set_number,
                        [l.page_num for l in b.locations],
                    )
                    break  # i is absorbed, stop comparing

    return [s for idx, s in enumerate(sets) if idx not in absorbed]


def _merge_sets(sets: List[HardwareSet]) -> List[HardwareSet]:
    """
    Group sets by set_number and merge continuations, then dedup Format D
    duplicates from overlapping batches.

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

    # Dedup Format D sets that got different set_numbers from overlapping batches
    merged = _dedup_format_d(merged)

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
    Refine this set's location by searching nearby pages for identifying text.

    The model already reports approximate page numbers from its batch. We search
    only near those pages (±2) to avoid false positives from generic terms
    matching on unrelated pages (e.g., standards sections early in the PDF).

    If the model has no locations, falls back to searching all pages.
    """
    search_terms = _extract_search_terms(hw_set.set_number, hw_set.description)

    # Determine which pages to search: near the model's reported pages
    model_pages = {loc.page_num for loc in hw_set.locations}
    if model_pages:
        # Search within ±2 pages of the model's locations
        search_pages = set()
        for p in model_pages:
            for offset in range(-2, 3):
                candidate = p + offset
                if candidate in pages_by_num:
                    search_pages.add(candidate)
    else:
        # No model locations — search all pages
        search_pages = set(pages_by_num.keys())

    locations: list[Location] = []
    seen_pages: set[int] = set()

    for term in search_terms:
        term_lower = term.lower()
        for page_num in sorted(search_pages):
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
