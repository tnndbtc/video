"""Add duration_seconds to render_jobs

Revision ID: 006
Revises: 005
Create Date: 2026-02-15

Store the output video duration in seconds for display in the UI.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('render_jobs', sa.Column('duration_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('render_jobs', 'duration_seconds')
