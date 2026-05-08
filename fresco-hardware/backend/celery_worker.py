"""
Celery worker configuration and task definitions.

Runs the extraction pipeline asynchronously:
  1. ingest_document  — extract text blocks from uploaded PDF
  2. filter_pages     — identify candidate schedule pages
  3. extract_legend   — build per-doc mfr/finish lookup
  4. extract_sets     — run Opus extraction on page batches
  5. reconcile_sets   — merge multi-page sets and snap locations
"""

# TODO: configure Celery app, define task chain
