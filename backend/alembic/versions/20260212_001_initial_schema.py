"""Initial schema with all tables

Revision ID: 001
Revises:
Create Date: 2026-02-12

Creates all BeatStitch database tables:
- users: User authentication
- projects: Video editing projects
- media_assets: Uploaded images and videos
- audio_tracks: Uploaded audio files with beat analysis
- timelines: Edit Decision Lists (EDL)
- render_jobs: Video rendering tasks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_users_username', 'users', ['username'])

    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # Settings
        sa.Column('beats_per_cut', sa.Integer(), nullable=False, default=4),
        sa.Column('transition_type', sa.String(20), nullable=False, default='cut'),
        sa.Column('transition_duration_ms', sa.Integer(), nullable=False, default=500),
        sa.Column('ken_burns_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('output_width', sa.Integer(), nullable=False, default=1920),
        sa.Column('output_height', sa.Integer(), nullable=False, default=1080),
        sa.Column('output_fps', sa.Integer(), nullable=False, default=30),
        # Status
        sa.Column('status', sa.String(20), nullable=False, default='draft'),
        sa.Column('status_message', sa.String(200), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])
    op.create_index('ix_projects_status', 'projects', ['status'])

    # Create media_assets table
    op.create_table(
        'media_assets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        # File info
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(50), nullable=False),
        # Media type
        sa.Column('media_type', sa.String(10), nullable=False),
        # Dimensions
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        # Display corrections
        sa.Column('rotation_deg', sa.Integer(), nullable=False, default=0),
        sa.Column('display_aspect_ratio', sa.String(10), nullable=True),
        # Derived assets
        sa.Column('thumbnail_path', sa.String(500), nullable=True),
        sa.Column('proxy_path', sa.String(500), nullable=True),
        # Ordering and timestamps
        sa.Column('sort_order', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_media_assets_project_id', 'media_assets', ['project_id'])
    op.create_index('ix_media_assets_media_type', 'media_assets', ['media_type'])
    op.create_index('ix_media_assets_sort_order', 'media_assets', ['sort_order'])

    # Create audio_tracks table
    op.create_table(
        'audio_tracks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), unique=True, nullable=False),
        # File info
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        # Audio metadata
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('sample_rate', sa.Integer(), nullable=True),
        # Beat analysis
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('beat_count', sa.Integer(), nullable=True),
        sa.Column('beat_grid_path', sa.String(500), nullable=True),
        # Analysis status
        sa.Column('analysis_status', sa.String(20), nullable=False, default='pending'),
        sa.Column('analysis_error', sa.String(500), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_audio_tracks_project_id', 'audio_tracks', ['project_id'])
    op.create_index('ix_audio_tracks_analysis_status', 'audio_tracks', ['analysis_status'])

    # Create timelines table
    op.create_table(
        'timelines',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), unique=True, nullable=False),
        # EDL storage
        sa.Column('edl_path', sa.String(500), nullable=False),
        # Summary metadata
        sa.Column('total_duration_ms', sa.Integer(), nullable=False, default=0),
        sa.Column('segment_count', sa.Integer(), nullable=False, default=0),
        # Cache validation
        sa.Column('edl_hash', sa.String(64), nullable=False),
        # Timestamps
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('modified_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_timelines_project_id', 'timelines', ['project_id'])
    op.create_index('ix_timelines_edl_hash', 'timelines', ['edl_hash'])

    # Create render_jobs table
    op.create_table(
        'render_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        # Job type
        sa.Column('job_type', sa.String(20), nullable=False),
        # Input snapshot
        sa.Column('edl_hash', sa.String(64), nullable=False),
        sa.Column('render_settings_json', sa.Text(), nullable=False),
        # Status
        sa.Column('status', sa.String(20), nullable=False, default='queued'),
        sa.Column('progress_percent', sa.Integer(), nullable=False, default=0),
        sa.Column('progress_message', sa.String(200), nullable=True),
        # Output
        sa.Column('output_path', sa.String(500), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        # Error handling
        sa.Column('error_message', sa.Text(), nullable=True),
        # RQ job tracking
        sa.Column('rq_job_id', sa.String(50), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_render_jobs_project_id', 'render_jobs', ['project_id'])
    op.create_index('ix_render_jobs_job_type', 'render_jobs', ['job_type'])
    op.create_index('ix_render_jobs_status', 'render_jobs', ['status'])
    op.create_index('ix_render_jobs_edl_hash', 'render_jobs', ['edl_hash'])
    op.create_index('ix_render_jobs_rq_job_id', 'render_jobs', ['rq_job_id'])
    op.create_index('ix_render_jobs_created_at', 'render_jobs', ['created_at'])


def downgrade() -> None:
    # Drop tables in reverse order of creation (respecting foreign keys)
    op.drop_table('render_jobs')
    op.drop_table('timelines')
    op.drop_table('audio_tracks')
    op.drop_table('media_assets')
    op.drop_table('projects')
    op.drop_table('users')
