"""Add timeline preview settings to project

Revision ID: 004
Revises: 003
Create Date: 2026-02-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('timeline_media_ids', sa.JSON(), nullable=True))
    op.add_column('projects', sa.Column('video_length_seconds', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('rule_text', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'rule_text')
    op.drop_column('projects', 'video_length_seconds')
    op.drop_column('projects', 'timeline_media_ids')
