"""Add raw column

Revision ID: 00b0dddb59f6
Revises: 54c7120556dd
Create Date: 2024-04-27 09:26:51.465414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00b0dddb59f6'
down_revision: Union[str, None] = '54c7120556dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('headline', sa.Column('raw', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('headline', 'raw')
    # ### end Alembic commands ###
