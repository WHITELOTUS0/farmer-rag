"""Add tags to conversations.

Revision ID: 2b6e9c4d7a1f
Revises: 4c1c7f2a3d1b
Create Date: 2026-02-17 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2b6e9c4d7a1f"
down_revision = "4c1c7f2a3d1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "tags")
