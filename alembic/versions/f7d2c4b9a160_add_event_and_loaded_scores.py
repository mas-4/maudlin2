"""Add event and loaded scores to headlines

Revision ID: f7d2c4b9a160
Revises: e5b1a9c3d742
Create Date: 2026-10-03 10:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7d2c4b9a160'
down_revision: Union[str, None] = 'e5b1a9c3d742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.add_column(sa.Column('event_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('loaded_score', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.drop_column('loaded_score')
        batch_op.drop_column('event_score')
