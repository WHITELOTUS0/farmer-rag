"""remove farmers table

Revision ID: 9c2f0f6a1a8e
Revises: 7e821716ecb6
Create Date: 2026-02-16 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9c2f0f6a1a8e"
down_revision = "7e821716ecb6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("farms", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("advisories", sa.Column("user_id", sa.UUID(), nullable=True))

    op.create_foreign_key(
        "farms_user_id_fkey",
        "farms",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "advisories_user_id_fkey",
        "advisories",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("farms_farmer_id_fkey", "farms", type_="foreignkey")
    op.drop_constraint("advisories_farmer_id_fkey", "advisories", type_="foreignkey")

    op.drop_column("farms", "farmer_id")
    op.drop_column("advisories", "farmer_id")

    op.drop_table("farmers")

    op.alter_column("farms", "user_id", nullable=False)
    op.alter_column("advisories", "user_id", nullable=False)


def downgrade() -> None:
    op.create_table(
        "farmers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lon", sa.Float(), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("preferred_language", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("farms", sa.Column("farmer_id", sa.UUID(), nullable=True))
    op.add_column("advisories", sa.Column("farmer_id", sa.UUID(), nullable=True))

    op.create_foreign_key(
        "farms_farmer_id_fkey",
        "farms",
        "farmers",
        ["farmer_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "advisories_farmer_id_fkey",
        "advisories",
        "farmers",
        ["farmer_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("farms_user_id_fkey", "farms", type_="foreignkey")
    op.drop_constraint("advisories_user_id_fkey", "advisories", type_="foreignkey")

    op.drop_column("farms", "user_id")
    op.drop_column("advisories", "user_id")
