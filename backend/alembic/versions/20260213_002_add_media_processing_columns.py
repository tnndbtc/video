"""Add processing columns to media_assets

Revision ID: 002
Revises: 001
Create Date: 2026-02-13

Adds processing_status, processing_error, and processed_at columns
to media_assets table. Also makes width and height nullable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add processing status columns
    op.add_column('media_assets', sa.Column('processing_status', sa.String(20), nullable=False, server_default='pending'))
    op.add_column('media_assets', sa.Column('processing_error', sa.Text(), nullable=True))
    op.add_column('media_assets', sa.Column('processed_at', sa.DateTime(), nullable=True))

    # Create index on processing_status
    op.create_index('ix_media_assets_processing_status', 'media_assets', ['processing_status'])


def downgrade() -> None:
    op.drop_index('ix_media_assets_processing_status', 'media_assets')
    op.drop_column('media_assets', 'processed_at')
    op.drop_column('media_assets', 'processing_error')
    op.drop_column('media_assets', 'processing_status')
