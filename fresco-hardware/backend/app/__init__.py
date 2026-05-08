"""
Fresco Hardware Sets Extraction — Backend Application Package

Five-stage pipeline for extracting hardware sets from Division 08 specbooks:
  1. Ingest     — PyMuPDF text block extraction with bounding boxes
  2. Filter     — Regex conjunction filter to find schedule pages
  3. Legend     — Per-doc manufacturer/finish code legend extraction (Haiku)
  4. Extract    — Structured hardware set extraction (Opus)
  5. Reconcile  — Multi-page set merging and location snapping
"""
