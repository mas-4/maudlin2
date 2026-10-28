"""Add feed_sighting: articles an outlet's RSS feed listed, read alongside its front page for first sightings

Revision ID: d6f1a8c3e925
Revises: c5e9a3b7d284
Create Date: 2026-10-28 12:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd6f1a8c3e925'
down_revision: str | None = 'c5e9a3b7d284'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'feed_sighting',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agency_id', sa.Integer(), sa.ForeignKey('agency.id'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('published', sa.DateTime(), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('agency_id', 'url', name='uq_feed_sighting_agency_url'),
    )
    op.create_index('ix_feed_sighting_url', 'feed_sighting', ['url'])


def downgrade() -> None:
    op.drop_index('ix_feed_sighting_url', 'feed_sighting')
    op.drop_table('feed_sighting')
