"""Add story_snapshot: each story's meters at every run

Revision ID: b4d8f2a6c173
Revises: a7c3e1d5b962
Create Date: 2026-10-04 08:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4d8f2a6c173'
down_revision: Union[str, None] = 'a7c3e1d5b962'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'story_snapshot',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('story.id'), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('lean', sa.Float(), nullable=False),
        sa.Column('mood', sa.Float(), nullable=False),
        sa.Column('outlets', sa.Integer(), nullable=False),
    )
    op.create_index('ix_story_snapshot_story_id', 'story_snapshot', ['story_id'])
    op.create_index('ix_story_snapshot_at', 'story_snapshot', ['at'])


def downgrade() -> None:
    op.drop_index('ix_story_snapshot_at', 'story_snapshot')
    op.drop_index('ix_story_snapshot_story_id', 'story_snapshot')
    op.drop_table('story_snapshot')
