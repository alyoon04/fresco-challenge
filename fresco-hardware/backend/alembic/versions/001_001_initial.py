"""001_initial

Create all tables for the Fresco hardware sets extraction pipeline:
  - documents, pages, hardware_sets, components, locations, corrections

Revision ID: 001
Revises:
Create Date: 2026-05-07 22:01:59.257676

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""

    # -- Enum type ---------------------------------------------------------
    document_status = sa.Enum(
        "uploaded", "processing", "done", "failed",
        name="document_status",
    )
    document_status.create(op.get_bind(), checkfirst=True)

    # -- documents ---------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("r2_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("page_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", document_status, nullable=False, server_default="uploaded"),
        sa.Column("legend_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # -- pages -------------------------------------------------------------
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doc_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_num", sa.Integer, nullable=False),
        sa.Column("text_blocks", JSONB, nullable=True),
        sa.Column("is_candidate", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("filter_score", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_pages_doc_id", "pages", ["doc_id"])
    op.create_index("ix_pages_doc_page", "pages", ["doc_id", "page_num"], unique=True)

    # -- hardware_sets -----------------------------------------------------
    op.create_table(
        "hardware_sets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doc_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("set_number", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_not_used", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("overall_confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("column_reasoning", sa.Text, nullable=True),
        sa.Column("raw_json", JSONB, nullable=False),
    )
    op.create_index("ix_hardware_sets_doc_id", "hardware_sets", ["doc_id"])

    # -- components --------------------------------------------------------
    op.create_table(
        "components",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.Integer, sa.ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("qty", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("catalog_number", sa.Text, nullable=True),
        sa.Column("mfr", sa.Text, nullable=True),
        sa.Column("finish", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("confidences", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_components_set_id", "components", ["set_id"])

    # -- locations ---------------------------------------------------------
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.Integer, sa.ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_num", sa.Integer, nullable=False),
        sa.Column("bbox", sa.ARRAY(sa.Float), nullable=True),
        sa.Column("line_start", sa.Integer, nullable=True),
        sa.Column("line_end", sa.Integer, nullable=True),
    )
    op.create_index("ix_locations_set_id", "locations", ["set_id"])

    # -- corrections -------------------------------------------------------
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.Integer, sa.ForeignKey("hardware_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_idx", sa.Integer, nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("original_value", sa.Text, nullable=True),
        sa.Column("corrected_value", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_corrections_set_id", "corrections", ["set_id"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("corrections")
    op.drop_table("locations")
    op.drop_table("components")
    op.drop_table("hardware_sets")
    op.drop_table("pages")
    op.drop_table("documents")
    sa.Enum(name="document_status").drop(op.get_bind(), checkfirst=True)
