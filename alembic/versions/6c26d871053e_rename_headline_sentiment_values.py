"""Rename headline sentiment values

Revision ID: 6c26d871053e
Revises: 49d362b5456c
Create Date: 2024-02-17 14:04:21.230505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c26d871053e'
down_revision: Union[str, None] = '49d362b5456c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

columns = {
    'headneg': 'neg',
    'headneu': 'neu',
    'headpos': 'pos',
    'headcompound': 'comp'
}

def upgrade() -> None:
    # need to create new column, copy data, drop old column
    for old, new in columns.items():
        op.add_column('headline', sa.Column(new, sa.Float(), nullable=True))
        op.execute(f'UPDATE headline SET {new} = {old}')
        op.drop_column('headline', old)



def downgrade() -> None:
    for old, new in columns.items():
        op.add_column('headline', sa.Column(old, sa.Float(), nullable=True))
        op.execute(f'UPDATE headline SET {old} = {new}')
        op.drop_column('headline', new)
