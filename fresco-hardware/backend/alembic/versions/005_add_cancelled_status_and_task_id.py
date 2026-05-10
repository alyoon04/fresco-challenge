"""005_add_cancelled_status_and_task_id

Add 'cancelled' value to document_status enum and celery_task_id column
to support stopping document processing.

Revision ID: 005
Revises: 004
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'cancelled'")
    op.add_column("documents", sa.Column("celery_task_id", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "celery_task_id")
    # Note: PostgreSQL does not support removing enum values directly.
