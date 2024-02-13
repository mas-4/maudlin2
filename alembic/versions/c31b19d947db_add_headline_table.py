"""Add Headline table

Revision ID: c31b19d947db
Revises: e1ddf3a0373a
Create Date: 2024-02-13 10:08:34.098809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c31b19d947db'
down_revision: Union[str, None] = 'e1ddf3a0373a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('headline',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('headneg', sa.Float(), nullable=True),
    sa.Column('headneu', sa.Float(), nullable=True),
    sa.Column('headpos', sa.Float(), nullable=True),
    sa.Column('headcompound', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['article_id'], ['article.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.drop_column('article', 'artcompound')
    op.drop_column('article', 'headpos')
    op.drop_column('article', 'headneu')
    op.drop_column('article', 'headneg')
    op.drop_column('article', 'artneu')
    op.drop_column('article', 'headcompound')
    op.drop_column('article', 'artneg')
    op.drop_column('article', 'artpos')
    op.drop_column('article', 'title')
    op.drop_column('article', 'body')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('article', sa.Column('body', sa.TEXT(), nullable=True))
    op.add_column('article', sa.Column('title', sa.VARCHAR(length=254), nullable=True))
    op.add_column('article', sa.Column('artpos', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('artneg', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('headcompound', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('artneu', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('headneg', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('headneu', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('headpos', sa.FLOAT(), nullable=True))
    op.add_column('article', sa.Column('artcompound', sa.FLOAT(), nullable=True))
    op.drop_table('headline')
    # ### end Alembic commands ###
