"""
Integration test for the full extraction pipeline.

Runs ingest → filter → legend → extract on a real specbook PDF.
Requires ANTHROPIC_API_KEY to be set; skips otherwise.
"""

import os
import sys
from pathlib import Path

import pytest

# Add backend to sys.path so imports work when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.extraction.ingest import ingest_document
from app.extraction.page_filter import filter_pages
from app.extraction.legend import extract_legend
from app.extraction.extract import extract_sets_from_pages
from app.models.schemas import HardwareSet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "Hdw_Spec___Sch-IFT_5.pdf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY")

skip_no_api_key = pytest.mark.skipif(
    not API_KEY,
    reason="ANTHROPIC_API_KEY not set — skipping integration test",
)

skip_no_fixture = pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason=f"Fixture PDF not found at {FIXTURE_PATH}",
)


# ---------------------------------------------------------------------------
# Unit tests (always run)
# ---------------------------------------------------------------------------

def test_imports():
    """Verify all pipeline modules import without error."""
    from app.extraction.ingest import ingest_document
    from app.extraction.page_filter import filter_pages
    from app.extraction.legend import extract_legend
    from app.extraction.extract import extract_sets_from_pages
    from app.models.schemas import HardwareSet, Component, FieldValue, Location
    assert callable(ingest_document)
    assert callable(filter_pages)
    assert callable(extract_legend)
    assert callable(extract_sets_from_pages)


# ---------------------------------------------------------------------------
# Integration test (requires API key + fixture PDF)
# ---------------------------------------------------------------------------

@skip_no_api_key
@skip_no_fixture
def test_end_to_end_extraction():
    """
    Full pipeline test on Hdw_Spec___Sch-IFT_5.pdf (36 pages).

    Expected: hardware schedule on pages 19-36, containing 30+ sets with
    both numeric ("01", "02") and alphanumeric ("AL 01", "U-01") set numbers.
    """
    import anthropic

    # Stage 1: Ingest
    pdf_bytes = FIXTURE_PATH.read_bytes()
    pages = ingest_document(pdf_bytes)
    assert len(pages) > 0, "Ingest should return at least one page"
    print(f"\n  Ingested {len(pages)} pages")

    # Stage 2: Filter
    candidates = filter_pages(pages)
    assert len(candidates) > 0, "Filter should find at least some candidate pages"
    print(f"  Filtered to {len(candidates)} candidate pages: {[c.page_num for c in candidates]}")

    # Stage 3: Legend extraction
    client = anthropic.Anthropic(api_key=API_KEY)
    legend = extract_legend(pages, client)
    print(f"  Legend: {len(legend.get('mfr_codes', {}))} mfr codes, {len(legend.get('finish_codes', {}))} finish codes")

    # Stage 4: Extraction
    sets = extract_sets_from_pages(pdf_bytes, candidates, legend, client)
    print(f"  Extracted {len(sets)} hardware sets")

    # --- Assertions ---

    # At least 30 sets expected from this specbook
    assert len(sets) >= 30, f"Expected >= 30 sets, got {len(sets)}"

    # All sets with components should have non-empty components
    for s in sets:
        if not s.is_not_used:
            assert len(s.components) > 0, (
                f"Set {s.set_number} is not marked NOT USED but has no components"
            )

    # Check for presence of both numeric and alphanumeric set numbers
    set_numbers = {s.set_number for s in sets}
    print(f"  Set numbers: {sorted(set_numbers)}")

    has_numeric = any(sn.isdigit() or sn.lstrip("0").isdigit() for sn in set_numbers)
    has_alpha = any(
        any(c.isalpha() for c in sn) for sn in set_numbers
    )
    assert has_numeric, f"Expected some numeric set numbers, got: {set_numbers}"
    assert has_alpha, f"Expected some alphanumeric set numbers, got: {set_numbers}"

    # Spot-check: every component should have a non-null description
    for s in sets:
        for i, comp in enumerate(s.components):
            assert comp.description.value is not None, (
                f"Set {s.set_number} component {i} has null description"
            )

    # Print a sample set for manual review
    sample = next((s for s in sets if not s.is_not_used and len(s.components) >= 3), None)
    if sample:
        print(f"\n  Sample set {sample.set_number} ({sample.description}):")
        for comp in sample.components:
            print(
                f"    {comp.qty} EA | {comp.description.value} | "
                f"cat={comp.catalog_number.value} | mfr={comp.mfr.value} | "
                f"finish={comp.finish.value}"
            )
