"""Add trend table

Revision ID: a7c2e91d4b10
Revises: 19cf821edad6
Create Date: 2026-10-02 17:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c2e91d4b10'
down_revision: Union[str, None] = '19cf821edad6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trend',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('link', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('post_count', sa.Integer(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('first_accessed', sa.DateTime(), nullable=False),
        sa.Column('last_accessed', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trend_topic'), 'trend', ['topic'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_trend_topic'), table_name='trend')
    op.drop_table('trend')
