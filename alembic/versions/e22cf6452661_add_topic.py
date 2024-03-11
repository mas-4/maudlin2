"""Add topic

Revision ID: e22cf6452661
Revises: 6dac021b8b04
Create Date: 2024-03-09 10:14:08.160180

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e22cf6452661'
down_revision: Union[str, None] = '6dac021b8b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('topic',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('_keywords', sa.Text(), nullable=False),
    sa.Column('_essential', sa.Text(), nullable=False),
    sa.Column('first_accessed', sa.DateTime(), nullable=False),
    sa.Column('last_accessed', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('article') as batch_op:
        batch_op.add_column(sa.Column('topic_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('topic_id_fk', 'topic', ['topic_id'], ['id'])
    # ### end Alembic commands ###



def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('article') as batch_op:
        batch_op.drop_constraint('topic_id_fk', type_='foreignkey')
        batch_op.drop_column('topic_id')
    op.drop_table('topic')
    # ### end Alembic commands ###
