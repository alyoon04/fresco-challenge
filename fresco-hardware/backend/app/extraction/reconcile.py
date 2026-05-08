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

# TODO: implement reconcile_sets(), _merge_sets(), _snap_bboxes()
