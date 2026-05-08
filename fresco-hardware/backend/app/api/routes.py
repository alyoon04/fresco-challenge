"""
FastAPI route definitions.

Endpoints:
  - POST /documents/upload     Upload a PDF specbook and kick off extraction
  - GET  /documents/{id}       Get document metadata and extraction status
  - GET  /documents/{id}/sets  Get extracted hardware sets for a document
  - PATCH /sets/{id}           Update a hardware set (feedback/corrections)
"""

from fastapi import FastAPI

app = FastAPI(title="Fresco Hardware Sets API")

# TODO: implement routes
