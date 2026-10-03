"""Add headline emotion

Revision ID: a9e4d2f61b07
Revises: f7d2c4b9a160
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9e4d2f61b07'
down_revision: Union[str, None] = 'f7d2c4b9a160'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.add_column(sa.Column('emotion', sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.drop_column('emotion')
