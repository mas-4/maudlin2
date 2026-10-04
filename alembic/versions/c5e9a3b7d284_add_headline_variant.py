"""Add headline_variant: the wordings an outlet is A/B testing for one article

Revision ID: c5e9a3b7d284
Revises: b4d8f2a6c173
Create Date: 2026-10-04 09:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5e9a3b7d284'
down_revision: Union[str, None] = 'b4d8f2a6c173'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'headline_variant',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agency_id', sa.Integer(), sa.ForeignKey('agency.id'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('url', 'text', name='uq_headline_variant_url_text'),
    )
    op.create_index('ix_headline_variant_url', 'headline_variant', ['url'])


def downgrade() -> None:
    op.drop_index('ix_headline_variant_url', 'headline_variant')
    op.drop_table('headline_variant')
