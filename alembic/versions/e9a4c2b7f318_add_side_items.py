"""Add side_item: newsletters, podcasts and political video channels, archived

Revision ID: e9a4c2b7f318
Revises: d8e2f5a1c307
Create Date: 2026-10-03 21:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e9a4c2b7f318'
down_revision: Union[str, None] = 'd8e2f5a1c307'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'side_item',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('published', sa.DateTime(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('audio', sa.String(length=500), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('source', 'url', name='uq_side_item_source_url'),
    )
    op.create_index('ix_side_item_source', 'side_item', ['source'])
    op.create_index('ix_side_item_published', 'side_item', ['published'])


def downgrade() -> None:
    op.drop_index('ix_side_item_published', 'side_item')
    op.drop_index('ix_side_item_source', 'side_item')
    op.drop_table('side_item')
