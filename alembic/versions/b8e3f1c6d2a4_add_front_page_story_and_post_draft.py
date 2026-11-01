"""Add front_page_story (the top stories at each build) and post_draft (Bluesky post drafts)

Revision ID: b8e3f1c6d2a4
Revises: e7a2c9d4f1b6
Create Date: 2026-11-01 15:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e3f1c6d2a4'
down_revision: Union[str, None] = 'e7a2c9d4f1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'front_page_story',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('story.id'), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('outlets', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_front_page_story_at'), 'front_page_story', ['at'])
    op.create_index(op.f('ix_front_page_story_story_id'), 'front_page_story', ['story_id'])
    op.create_table(
        'post_draft',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('format', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('link', sa.Text(), nullable=False),
        sa.Column('about', sa.Text(), nullable=False),
        sa.Column('event', sa.DateTime(), nullable=False),
        sa.Column('made', sa.DateTime(), nullable=False),
        sa.Column('seen', sa.DateTime(), nullable=False),
        sa.Column('peak', sa.Integer(), nullable=True),
        sa.Column('mark', sa.String(length=8), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_index(op.f('ix_post_draft_format'), 'post_draft', ['format'])
    op.create_index(op.f('ix_post_draft_made'), 'post_draft', ['made'])


def downgrade() -> None:
    op.drop_index(op.f('ix_post_draft_made'), table_name='post_draft')
    op.drop_index(op.f('ix_post_draft_format'), table_name='post_draft')
    op.drop_table('post_draft')
    op.drop_index(op.f('ix_front_page_story_story_id'), table_name='front_page_story')
    op.drop_index(op.f('ix_front_page_story_at'), table_name='front_page_story')
    op.drop_table('front_page_story')
