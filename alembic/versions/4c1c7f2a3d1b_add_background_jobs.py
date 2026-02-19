"""add background jobs table

Revision ID: 4c1c7f2a3d1b
Revises: 9c2f0f6a1a8e
Create Date: 2026-02-17 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4c1c7f2a3d1b"
down_revision = "9c2f0f6a1a8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("run_after", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("background_jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
