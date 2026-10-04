"""Add saga (running stories kept across days) and story.saga_id

Revision ID: a7c3e1d5b962
Revises: f2b6d9e4a051
Create Date: 2026-10-04 08:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e1d5b962'
down_revision: Union[str, None] = 'f2b6d9e4a051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saga',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('named_with', sa.Integer(), nullable=True),
        sa.Column('words', sa.String(length=255), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table('story') as batch_op:
        batch_op.add_column(sa.Column('saga_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_story_saga_id', ['saga_id'])
        batch_op.create_foreign_key('fk_story_saga_id', 'saga', ['saga_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('story') as batch_op:
        batch_op.drop_constraint('fk_story_saga_id', type_='foreignkey')
        batch_op.drop_index('ix_story_saga_id')
        batch_op.drop_column('saga_id')
    op.drop_table('saga')
