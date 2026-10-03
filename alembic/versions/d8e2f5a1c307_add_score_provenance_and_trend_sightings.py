"""Add score provenance (who scored a headline, when, and its note) and a log of every trend sighting

Revision ID: d8e2f5a1c307
Revises: c4f1a8e2d905
Create Date: 2026-10-03 20:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8e2f5a1c307'
down_revision: Union[str, None] = 'c4f1a8e2d905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.add_column(sa.Column('scored_by', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('scored_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('affected', sa.String(length=128), nullable=True))
        batch_op.create_index('ix_headline_scored_by', ['scored_by'])
    # Every score so far came from qwen3:8b; the rubric version before tracking began is unknown
    op.execute("UPDATE headline SET scored_by = 'qwen3:8b rubric:pre-tracking' WHERE event_score IS NOT NULL")
    op.create_table(
        'trend_sighting',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trend_id', sa.Integer(), sa.ForeignKey('trend.id'), nullable=False),
        sa.Column('seen_at', sa.DateTime(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('post_count', sa.Integer(), nullable=True),
    )
    op.create_index('ix_trend_sighting_trend_id', 'trend_sighting', ['trend_id'])
    op.create_index('ix_trend_sighting_seen_at', 'trend_sighting', ['seen_at'])


def downgrade() -> None:
    op.drop_index('ix_trend_sighting_seen_at', 'trend_sighting')
    op.drop_index('ix_trend_sighting_trend_id', 'trend_sighting')
    op.drop_table('trend_sighting')
    with op.batch_alter_table('headline') as batch_op:
        batch_op.drop_index('ix_headline_scored_by')
        batch_op.drop_column('affected')
        batch_op.drop_column('scored_at')
        batch_op.drop_column('scored_by')
