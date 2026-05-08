"""
Extraction pipeline stages.

Stage 1 — ingest.py:      PyMuPDF per-page text block extraction
Stage 2 — page_filter.py: Conjunction filter to identify schedule pages
Stage 3 — legend.py:      Per-doc legend extraction via Haiku 4.5
Stage 4 — extract.py:     Hardware set extraction via Opus 4.7
Stage 5 — reconcile.py:   Multi-page set merging and bbox snapping
"""
