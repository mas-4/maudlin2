"""Add position

Revision ID: 6dac021b8b04
Revises: dc1d9812e857
Create Date: 2024-02-24 14:30:18.548661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dac021b8b04'
down_revision: Union[str, None] = 'dc1d9812e857'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('headline', sa.Column('position', sa.Integer(), nullable=True))
    op.execute("UPDATE headline SET position = 0")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('headline', 'position')
    # ### end Alembic commands ###