"""Add processed column

Revision ID: 54c7120556dd
Revises: b76fcafdbd07
Create Date: 2024-04-05 18:15:59.852373

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54c7120556dd'
down_revision: Union[str, None] = 'b76fcafdbd07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('headline', sa.Column('processed', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('headline', 'processed')
    # ### end Alembic commands ###