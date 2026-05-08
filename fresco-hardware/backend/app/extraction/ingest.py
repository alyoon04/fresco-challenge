"""
Stage 1: Document Ingestion

Uses PyMuPDF to extract per-page text blocks with bounding boxes from uploaded
PDF specbooks. Results are stored in Postgres keyed on (doc_id, page_num).

Each text block includes:
  - Raw text content
  - Bounding box coordinates (x0, y0, x1, y1)
  - Page dimensions for coordinate normalization
"""

# TODO: implement ingest_document(), extract_page_blocks()
