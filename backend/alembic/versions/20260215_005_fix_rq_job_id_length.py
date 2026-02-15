"""Fix rq_job_id column length

Revision ID: 005
Revises: 004
Create Date: 2026-02-15

The rq_job_id column was VARCHAR(50) but preview render job IDs
are 51 characters (render_preview_ + 36-char UUID = 51).
Increase to VARCHAR(100) to accommodate both preview and final.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL supports ALTER COLUMN TYPE directly
    op.alter_column(
        'render_jobs',
        'rq_job_id',
        type_=sa.String(100),
        existing_type=sa.String(50),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'render_jobs',
        'rq_job_id',
        type_=sa.String(50),
        existing_type=sa.String(100),
        existing_nullable=True,
    )
