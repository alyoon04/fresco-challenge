"""
Stage 5: Reconciliation

Groups extracted hardware sets by set_number across pages, merges components
from multi-page sets, and snaps approximate bounding box locations to the
nearest PyMuPDF text block coordinates.

Handles:
  - Sets that span page breaks (same set_number on consecutive pages)
  - Deduplication of components extracted from overlapping page batches
  - Location refinement using stored PyMuPDF bounding boxes from Stage 1
"""

import logging
from collections import defaultdict
from typing import List, Optional

from app.extraction.ingest import PageData, TextBlock
from app.models.schemas import HardwareSet, Location

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Multi-page merging
# ---------------------------------------------------------------------------

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
    """Merge a continuation set into the primary set."""
    return HardwareSet(
        set_number=primary.set_number,
        description=primary.description or candidate.description,
        locations=primary.locations + candidate.locations,
        components=primary.components + candidate.components,
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
# Bbox snapping
# ---------------------------------------------------------------------------

def _find_matching_blocks(
    page_data: PageData,
    set_number: str,
    description: Optional[str],
) -> List[TextBlock]:
    """
    Find text blocks on a page that reference the given set number or description.

    Matches blocks whose text contains the set_number as a distinct token,
    or contains the description text (case-insensitive).
    """
    matches: List[TextBlock] = []
    set_num_lower = set_number.lower()

    for block in page_data.text_blocks:
        text_lower = block.text.lower()

        # Check for set number (as a word boundary match)
        if set_num_lower in text_lower:
            matches.append(block)
            continue

        # Check for description match
        if description and description.lower() in text_lower:
            matches.append(block)

    return matches


def _union_bbox(
    bboxes: List[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Compute the union bounding box of multiple bboxes."""
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    y1 = max(b[3] for b in bboxes)
    return (x0, y0, x1, y1)


def _snap_locations(
    hw_set: HardwareSet,
    pages_by_num: dict[int, PageData],
) -> HardwareSet:
    """
    Refine each Location in a hardware set by snapping to actual text block
    bounding boxes from PyMuPDF.

    For each location:
      - Find text blocks on that page referencing the set number or description.
      - Set bbox to the union of those blocks' bboxes.
      - Set line_range to (min line_idx, max line_idx) of matched blocks.
      - If no blocks match, leave bbox/line_range as-is.
    """
    snapped_locations: List[Location] = []

    for loc in hw_set.locations:
        page_data = pages_by_num.get(loc.page_num)
        if not page_data:
            snapped_locations.append(loc)
            continue

        matching = _find_matching_blocks(page_data, hw_set.set_number, hw_set.description)

        if matching:
            bbox = _union_bbox([b.bbox for b in matching])
            line_idxs = [b.line_idx for b in matching]
            snapped_locations.append(Location(
                page_num=loc.page_num,
                bbox=bbox,
                line_range=(min(line_idxs), max(line_idxs)),
            ))
        else:
            # No match — keep original location, log a note
            logger.debug(
                "No matching text blocks for set %s on page %d",
                hw_set.set_number, loc.page_num,
            )
            snapped_locations.append(loc)

    return hw_set.model_copy(update={"locations": snapped_locations})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile_sets(
    sets: List[HardwareSet],
    pages: List[PageData],
) -> List[HardwareSet]:
    """
    Post-process extracted hardware sets: merge multi-page sets and snap locations.

    1. Multi-page merging: group by set_number, merge continuations (same number,
       adjacent pages, <3 components in the later occurrence).
    2. Bbox snapping: for each location, find matching text blocks from PyMuPDF
       and compute union bounding box + line range.

    Args:
        sets: Raw hardware sets from Stage 4 extraction.
        pages: All pages from Stage 1 ingest (for bbox data).

    Returns:
        Reconciled list of HardwareSet with merged components and snapped locations.
    """
    if not sets:
        return []

    # Step 1: Merge multi-page sets
    merged = _merge_sets(sets)

    # Step 2: Snap bounding boxes
    pages_by_num = {p.page_num: p for p in pages}
    snapped = [_snap_locations(s, pages_by_num) for s in merged]

    return snapped
