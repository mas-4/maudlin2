"""Update afinn

Revision ID: 11c586a63e76
Revises: e22cf6452661
Create Date: 2024-03-09 13:19:25.068345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.analysis.metrics import apply_afinn
from afinn import Afinn


# revision identifiers, used by Alembic.
revision: str = '11c586a63e76'
down_revision: Union[str, None] = 'e22cf6452661'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    afinn = Afinn()
    conn = op.get_bind()
    result = conn.execute(sa.text('SELECT id, title FROM headline;'))
    for headline in result.fetchall():
        conn.execute(sa.text(f'UPDATE headline SET afinn = {afinn.score(headline.title) / len(headline.title.split())} WHERE id = {headline.id}'))
    result.close()


def downgrade() -> None:
    afinn = Afinn()
    conn = op.get_bind()
    result = conn.execute(sa.text('SELECT id, title FROM headline;'))
    for headline in result.fetchall():
        conn.execute(sa.text(f'UPDATE headline SET afinn = {afinn.score(headline.title)} WHERE id = {headline.id}'))
    result.close()
