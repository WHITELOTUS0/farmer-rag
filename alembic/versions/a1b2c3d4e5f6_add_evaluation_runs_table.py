"""add_evaluation_runs_table

Revision ID: a1b2c3d4e5f6
Revises: 2b6e9c4d7a1f
Create Date: 2026-02-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2b6e9c4d7a1f'  # After conversation_tags
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evaluation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('summary', postgresql.JSON, nullable=False),
        sa.Column('results', postgresql.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['run_by'], ['users.id'], ),
    )
    op.create_index('ix_evaluation_runs_created_at', 'evaluation_runs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_evaluation_runs_created_at', table_name='evaluation_runs')
    op.drop_table('evaluation_runs')
