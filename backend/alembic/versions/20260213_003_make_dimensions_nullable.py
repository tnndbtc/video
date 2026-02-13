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
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Create new table with correct schema
    op.execute('''
        CREATE TABLE media_assets_new (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            filename VARCHAR(255) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            file_size BIGINT NOT NULL,
            mime_type VARCHAR(50) NOT NULL,
            media_type VARCHAR(10) NOT NULL,
            processing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            processing_error TEXT,
            processed_at DATETIME,
            width INTEGER,
            height INTEGER,
            duration_ms INTEGER,
            fps FLOAT,
            rotation_deg INTEGER NOT NULL DEFAULT 0,
            display_aspect_ratio VARCHAR(10),
            thumbnail_path VARCHAR(500),
            proxy_path VARCHAR(500),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL
        )
    ''')

    # Copy data from old table
    op.execute('''
        INSERT INTO media_assets_new
        SELECT id, project_id, filename, original_filename, file_path, file_size,
               mime_type, media_type, processing_status, processing_error, processed_at,
               width, height, duration_ms, fps, rotation_deg, display_aspect_ratio,
               thumbnail_path, proxy_path, sort_order, created_at
        FROM media_assets
    ''')

    # Drop old table and rename new one
    op.execute('DROP TABLE media_assets')
    op.execute('ALTER TABLE media_assets_new RENAME TO media_assets')

    # Recreate indexes
    op.create_index('ix_media_assets_project_id', 'media_assets', ['project_id'])
    op.create_index('ix_media_assets_media_type', 'media_assets', ['media_type'])
    op.create_index('ix_media_assets_sort_order', 'media_assets', ['sort_order'])
    op.create_index('ix_media_assets_processing_status', 'media_assets', ['processing_status'])


def downgrade() -> None:
    # This is a one-way migration for simplicity
    pass
