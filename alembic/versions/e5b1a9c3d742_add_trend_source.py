"""Add trend source

Revision ID: e5b1a9c3d742
Revises: c3d8f0a27e51
Create Date: 2026-10-03 09:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b1a9c3d742'
down_revision: Union[str, None] = 'c3d8f0a27e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('trend') as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=32), nullable=False, server_default='bluesky'))
        batch_op.create_index('ix_trend_source', ['source'])


def downgrade() -> None:
    with op.batch_alter_table('trend') as batch_op:
        batch_op.drop_index('ix_trend_source')
        batch_op.drop_column('source')
