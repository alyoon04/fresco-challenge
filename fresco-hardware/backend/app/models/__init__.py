"""
Database and Pydantic models for the Fresco extraction pipeline.

Public API:
  Pydantic schemas — FieldValue, Component, Location, HardwareSet
  SQLAlchemy ORM   — Base, Document, Page, HardwareSetRecord,
                     ComponentRecord, LocationRecord, Correction
  Enums            — DocumentStatus
"""

# Pydantic schemas (extraction pipeline I/O)
from app.models.schemas import Component, FieldValue, HardwareSet, Location

# SQLAlchemy ORM models (Postgres storage)
from app.models.db import (
    Base,
    ComponentRecord,
    Correction,
    Document,
    DocumentStatus,
    HardwareSetRecord,
    LocationRecord,
    Page,
)

__all__ = [
    # Pydantic
    "FieldValue",
    "Component",
    "Location",
    "HardwareSet",
    # SQLAlchemy
    "Base",
    "Document",
    "DocumentStatus",
    "Page",
    "HardwareSetRecord",
    "ComponentRecord",
    "LocationRecord",
    "Correction",
]
