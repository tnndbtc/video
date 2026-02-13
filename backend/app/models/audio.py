"""
AudioTrack model for BeatStitch.

Stores uploaded audio track metadata and beat analysis results.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .project import Project


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class AudioTrack(Base):
    """
    AudioTrack model representing an uploaded audio file.

    One audio track per project (1:1 relationship enforced by unique constraint).
    Stores file metadata and beat analysis results. The beat grid JSON payload
    is stored on the filesystem at beat_grid_path for efficiency.
    """

    __tablename__ = "audio_tracks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
        doc="UUID primary key"
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        doc="Foreign key to parent project (unique - one audio per project)"
    )

    # File information (original upload)
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Stored filename (UUID-based)"
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Original uploaded filename"
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Path to file relative to data directory"
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="File size in bytes"
    )

    # Audio metadata
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Audio duration in milliseconds"
    )
    sample_rate: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Sample rate in Hz (e.g., 44100, 48000)"
    )

    # Beat analysis results (metadata only - full grid on filesystem)
    bpm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Detected tempo in beats per minute"
    )
    beat_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Total number of beats detected"
    )
    beat_grid_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Path to beats.json file with full beat grid"
    )

    # Analysis status
    analysis_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        doc="Analysis status: pending, analyzing, complete, failed"
    )
    analysis_error: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Error message if analysis failed"
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="Timestamp when analysis completed"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Upload timestamp"
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="audio_track"
    )

    def __repr__(self) -> str:
        return f"<AudioTrack(id={self.id!r}, bpm={self.bpm}, status={self.analysis_status!r})>"
