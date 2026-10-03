"""Add stories and headline news score

Revision ID: c3d8f0a27e51
Revises: a7c2e91d4b10
Create Date: 2026-10-02 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d8f0a27e51'
down_revision: Union[str, None] = 'a7c2e91d4b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('headline') as batch_op:
        batch_op.add_column(sa.Column('news_score', sa.Float(), nullable=True))
    op.create_table(
        'story',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('labeled_with', sa.Integer(), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'story_headline',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('story.id'), nullable=False),
        sa.Column('headline_id', sa.Integer(), sa.ForeignKey('headline.id'), nullable=False),
        sa.Column('sentiment', sa.Float(), nullable=False),
        sa.Column('deviation', sa.Float(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_story_headline_story_id'), 'story_headline', ['story_id'])
    op.create_index(op.f('ix_story_headline_headline_id'), 'story_headline', ['headline_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_story_headline_headline_id'), table_name='story_headline')
    op.drop_index(op.f('ix_story_headline_story_id'), table_name='story_headline')
    op.drop_table('story_headline')
    op.drop_table('story')
    with op.batch_alter_table('headline') as batch_op:
        batch_op.drop_column('news_score')
