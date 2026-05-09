"""
SQLAlchemy 2.0 ORM models for Postgres storage.

Tables:
  - documents          Uploaded PDF metadata and processing status
  - pages              Per-page text blocks with bounding boxes (Stage 1 output)
  - hardware_sets      Extracted sets with full JSON dump
  - components         Individual hardware components within a set
  - locations          Page + bbox pointers for each set occurrence
  - corrections        User feedback / inline edits on extracted data
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentStatus(str, enum.Enum):
    """Processing lifecycle for an uploaded specbook."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(Base):
    """An uploaded Division 08 specbook PDF."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    r2_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    pdf_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    legend_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    pages: Mapped[list["Page"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    hardware_sets: Mapped[list["HardwareSetRecord"]] = relationship(back_populates="document", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class Page(Base):
    """
    One page of a specbook, with extracted text blocks from PyMuPDF.

    text_blocks is a JSONB list of: {text: str, bbox: [x0, y0, x1, y1], line_idx: int}
    """

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    text_blocks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filter_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="pages")

    __table_args__ = (
        Index("ix_pages_doc_id", "doc_id"),
        Index("ix_pages_doc_page", "doc_id", "page_num", unique=True),
    )


# ---------------------------------------------------------------------------
# HardwareSetRecord
# ---------------------------------------------------------------------------

class HardwareSetRecord(Base):
    """
    A hardware set extracted from a specbook.

    raw_json stores the full HardwareSet pydantic .model_dump() for lossless
    round-tripping. Denormalized fields (set_number, description, etc.) enable
    efficient queries without JSONB path lookups.
    """

    __tablename__ = "hardware_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    set_number: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_not_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    column_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="hardware_sets")
    components: Mapped[list["ComponentRecord"]] = relationship(back_populates="hardware_set", cascade="all, delete-orphan")
    locations: Mapped[list["LocationRecord"]] = relationship(back_populates="hardware_set", cascade="all, delete-orphan")
    corrections: Mapped[list["Correction"]] = relationship(back_populates="hardware_set", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_hardware_sets_doc_id", "doc_id"),
    )


# ---------------------------------------------------------------------------
# ComponentRecord
# ---------------------------------------------------------------------------

class ComponentRecord(Base):
    """
    One hardware component within a set, stored as a flat row for queryability.

    Per-field confidence scores are stored in a JSONB dict keyed by field name:
      {"description": 0.95, "catalog_number": 0.8, "mfr": 0.9, ...}
    """

    __tablename__ = "components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(Integer, ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False, doc="Position within the set (0-indexed)")
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfr: Mapped[str | None] = mapped_column(Text, nullable=True)
    finish: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    hardware_set: Mapped["HardwareSetRecord"] = relationship(back_populates="components")

    __table_args__ = (
        Index("ix_components_set_id", "set_id"),
    )


# ---------------------------------------------------------------------------
# LocationRecord
# ---------------------------------------------------------------------------

class LocationRecord(Base):
    """Where a hardware set appears in the PDF: page number + optional bbox/line range."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(Integer, ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list | None] = mapped_column(ARRAY(Float), nullable=True, doc="[x0, y0, x1, y1] in PDF points")
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    hardware_set: Mapped["HardwareSetRecord"] = relationship(back_populates="locations")

    __table_args__ = (
        Index("ix_locations_set_id", "set_id"),
    )


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------

class Correction(Base):
    """
    A user-submitted correction to an extracted field.

    Tracks original vs. corrected value for feedback loop and eval.
    """

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(Integer, ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False)
    component_idx: Mapped[int] = mapped_column(Integer, nullable=False, doc="Which component in the set (0-indexed)")
    field_name: Mapped[str] = mapped_column(String(64), nullable=False, doc="Field that was corrected (e.g., 'mfr', 'finish')")
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    hardware_set: Mapped["HardwareSetRecord"] = relationship(back_populates="corrections")

    __table_args__ = (
        Index("ix_corrections_set_id", "set_id"),
    )
