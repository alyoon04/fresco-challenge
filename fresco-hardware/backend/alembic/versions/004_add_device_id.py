"""004_add_device_id

Add device_id column to documents table so each browser/device
sees only its own uploaded documents.

Revision ID: 004
Revises: 003
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("device_id", sa.String(64), nullable=True))
    op.create_index("ix_documents_device_id", "documents", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_device_id", table_name="documents")
    op.drop_column("documents", "device_id")
