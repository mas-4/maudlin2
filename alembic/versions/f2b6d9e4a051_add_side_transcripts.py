"""Add side_transcript: podcast transcripts made locally with Whisper

Revision ID: f2b6d9e4a051
Revises: e9a4c2b7f318
Create Date: 2026-10-03 21:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b6d9e4a051'
down_revision: Union[str, None] = 'e9a4c2b7f318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'side_transcript',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('side_item.id'), nullable=False, unique=True),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('seconds', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('segments', sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('side_transcript')
