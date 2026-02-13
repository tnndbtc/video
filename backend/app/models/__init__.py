"""
SQLAlchemy models for BeatStitch.

This module exports all database models for convenient importing:

    from app.models import User, Project, MediaAsset, AudioTrack, Timeline, RenderJob

All models use UUID strings as primary keys for SQLite compatibility.
"""

from .user import User
from .project import Project
from .media import MediaAsset
from .audio import AudioTrack
from .timeline import Timeline
from .job import RenderJob

__all__ = [
    "User",
    "Project",
    "MediaAsset",
    "AudioTrack",
    "Timeline",
    "RenderJob",
]
