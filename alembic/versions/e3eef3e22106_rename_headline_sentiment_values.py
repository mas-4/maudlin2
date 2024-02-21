"""Rename headline sentiment values

Revision ID: e3eef3e22106
Revises: 6c26d871053e
Create Date: 2024-02-21 15:55:01.048219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3eef3e22106'
down_revision: Union[str, None] = '6c26d871053e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

column_changes = {
    'pos': 'vader_pos',
    'neg': 'vader_neg',
    'neu': 'vader_neu',
    'comp': 'vader_compound'
}

def upgrade() -> None:
    # for sqlite we have to create the new column, copy the data, and then drop the old:
    for old, new in column_changes.items():
        op.add_column('headline', sa.Column(new, sa.Float(), nullable=True))
        op.execute(f'UPDATE headline SET {new} = {old}')
        op.drop_column('headline', old)


def downgrade() -> None:
    for new, old in column_changes.items():
        op.add_column('headline', sa.Column(old, sa.Float(), nullable=True))
        op.execute(f'UPDATE headline SET {old} = {new}')
        op.drop_column('headline', new)
