"""Add ranked emotions

Revision ID: b2c7e9a4d813
Revises: a9e4d2f61b07
Create Date: 2026-10-03 12:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c7e9a4d813'
down_revision: Union[str, None] = 'a9e4d2f61b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.add_column(sa.Column('emotion_ranks', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.drop_column('emotion_ranks')
