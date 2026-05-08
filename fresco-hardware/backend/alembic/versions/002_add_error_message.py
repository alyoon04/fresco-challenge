"""002_add_error_message

Add error_message column to documents table for storing failure details.

Revision ID: 002
Revises: 001
Create Date: 2026-05-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_message column to documents."""
    op.add_column("documents", sa.Column("error_message", sa.Text, nullable=True))


def downgrade() -> None:
    """Remove error_message column from documents."""
    op.drop_column("documents", "error_message")
