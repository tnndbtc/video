"""Make width and height nullable in media_assets

Revision ID: 003
Revises: 002
Create Date: 2026-02-13

The model expects width/height to be NULL on initial upload,
then populated after processing. The original migration incorrectly
made them NOT NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL supports ALTER COLUMN directly
    op.alter_column('media_assets', 'width', nullable=True)
    op.alter_column('media_assets', 'height', nullable=True)


def downgrade() -> None:
    op.alter_column('media_assets', 'width', nullable=False)
    op.alter_column('media_assets', 'height', nullable=False)
