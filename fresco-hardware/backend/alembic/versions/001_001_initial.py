"""001_initial

Create all tables for the Fresco hardware sets extraction pipeline:
  - documents, pages, hardware_sets, components, locations, corrections

Revision ID: 001
Revises:
Create Date: 2026-05-07 22:01:59.257676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UP_SQL = """
-- Enum
DO $$ BEGIN
    CREATE TYPE document_status AS ENUM ('uploaded', 'processing', 'done', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- documents
CREATE TABLE documents (
    id          UUID PRIMARY KEY,
    filename    VARCHAR(512)    NOT NULL,
    r2_key      VARCHAR(1024)   NOT NULL UNIQUE,
    page_count  INTEGER         NOT NULL DEFAULT 0,
    status      document_status NOT NULL DEFAULT 'uploaded',
    legend_json JSONB,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- pages
CREATE TABLE pages (
    id           SERIAL PRIMARY KEY,
    doc_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_num     INTEGER NOT NULL,
    text_blocks  JSONB,
    is_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    filter_score INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_pages_doc_id   ON pages (doc_id);
CREATE UNIQUE INDEX ix_pages_doc_page ON pages (doc_id, page_num);

-- hardware_sets
CREATE TABLE hardware_sets (
    id                   SERIAL PRIMARY KEY,
    doc_id               UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    set_number           VARCHAR(32)  NOT NULL,
    description          TEXT,
    is_not_used          BOOLEAN NOT NULL DEFAULT FALSE,
    overall_confidence   FLOAT   NOT NULL DEFAULT 0.0,
    column_reasoning     TEXT,
    raw_json             JSONB   NOT NULL
);
CREATE INDEX ix_hardware_sets_doc_id ON hardware_sets (doc_id);

-- components
CREATE TABLE components (
    id             SERIAL PRIMARY KEY,
    set_id         INTEGER NOT NULL REFERENCES hardware_sets(id) ON DELETE CASCADE,
    idx            INTEGER NOT NULL,
    qty            INTEGER,
    description    TEXT    NOT NULL,
    catalog_number TEXT,
    mfr            TEXT,
    finish         TEXT,
    notes          TEXT,
    confidences    JSONB   NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_components_set_id ON components (set_id);

-- locations
CREATE TABLE locations (
    id         SERIAL PRIMARY KEY,
    set_id     INTEGER NOT NULL REFERENCES hardware_sets(id) ON DELETE CASCADE,
    page_num   INTEGER NOT NULL,
    bbox       FLOAT[],
    line_start INTEGER,
    line_end   INTEGER
);
CREATE INDEX ix_locations_set_id ON locations (set_id);

-- corrections
CREATE TABLE corrections (
    id              SERIAL PRIMARY KEY,
    set_id          INTEGER NOT NULL REFERENCES hardware_sets(id) ON DELETE CASCADE,
    component_idx   INTEGER      NOT NULL,
    field_name      VARCHAR(64)  NOT NULL,
    original_value  TEXT,
    corrected_value TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_corrections_set_id ON corrections (set_id);
"""

_DOWN_SQL = """
DROP TABLE IF EXISTS corrections CASCADE;
DROP TABLE IF EXISTS locations   CASCADE;
DROP TABLE IF EXISTS components  CASCADE;
DROP TABLE IF EXISTS hardware_sets CASCADE;
DROP TABLE IF EXISTS pages       CASCADE;
DROP TABLE IF EXISTS documents   CASCADE;
DROP TYPE  IF EXISTS document_status;
"""


def upgrade() -> None:
    """Create initial schema."""
    op.execute(sa.text(_UP_SQL))


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.execute(sa.text(_DOWN_SQL))
