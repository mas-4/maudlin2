"""Add station_sighting: headlines on Sinclair's station homepages and The National Desk's, kept for research

Revision ID: e7a2c9d4f1b6
Revises: d6f1a8c3e925
Create Date: 2026-10-28 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7a2c9d4f1b6'
down_revision: str | None = 'd6f1a8c3e925'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'station_sighting',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agency_id', sa.Integer(), sa.ForeignKey('agency.id'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('agency_id', 'url', 'title', name='uq_station_sighting_agency_url_title'),
    )
    op.create_index('ix_station_sighting_agency_id', 'station_sighting', ['agency_id'])
    op.create_index('ix_station_sighting_slug', 'station_sighting', ['slug'])


def downgrade() -> None:
    op.drop_index('ix_station_sighting_slug', 'station_sighting')
    op.drop_index('ix_station_sighting_agency_id', 'station_sighting')
    op.drop_table('station_sighting')
