"""Add licensed outlet ratings: whether lean is rated, its AllSides page, and Wikipedia reliability

Revision ID: c4f1a8e2d905
Revises: b2c7e9a4d813
Create Date: 2026-10-03 14:50:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4f1a8e2d905'
down_revision: Union[str, None] = 'b2c7e9a4d813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('agency') as batch_op:
        batch_op.add_column(sa.Column('lean_rated', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('lean_url', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('reliability', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('reliability_note', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('agency') as batch_op:
        batch_op.drop_column('reliability_note')
        batch_op.drop_column('reliability')
        batch_op.drop_column('lean_url')
        batch_op.drop_column('lean_rated')
