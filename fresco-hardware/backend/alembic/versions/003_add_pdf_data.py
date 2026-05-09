"""003_add_pdf_data

Add pdf_data column to documents table for storing PDF bytes in the database,
enabling deployment without shared filesystem between API and worker.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("pdf_data", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "pdf_data")
