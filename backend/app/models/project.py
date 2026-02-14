"""
Project model for BeatStitch.

Central entity that organizes media assets, audio, timeline, and render jobs.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .audio import AudioTrack
    from .job import RenderJob
    from .media import MediaAsset
    from .timeline import Timeline
    from .user import User


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Project(Base):
    """
    Project model representing a video editing project.

    A project contains media assets, an audio track, timeline configuration,
    and render jobs. Status tracks the project lifecycle from draft through
    rendering to completion.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
        doc="UUID primary key"
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to owning user"
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Project display name"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional project description"
    )

    # Settings
    beats_per_cut: Mapped[int] = mapped_column(
        Integer,
        default=4,
        nullable=False,
        doc="Number of beats between cuts (1, 2, 4, 8, or 16)"
    )
    transition_type: Mapped[str] = mapped_column(
        String(20),
        default="cut",
        nullable=False,
        doc="Transition type: cut, crossfade, fade_black"
    )
    transition_duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
        doc="Transition duration in milliseconds"
    )
    ken_burns_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether Ken Burns effect is enabled for images"
    )
    output_width: Mapped[int] = mapped_column(
        Integer,
        default=1920,
        nullable=False,
        doc="Output video width in pixels"
    )
    output_height: Mapped[int] = mapped_column(
        Integer,
        default=1080,
        nullable=False,
        doc="Output video height in pixels"
    )
    output_fps: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        doc="Output video frames per second"
    )

    # Timeline preview settings (auto-saved from editor)
    timeline_media_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        doc="Ordered list of media IDs in timeline preview"
    )
    video_length_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        doc="Target video length in seconds"
    )
    rule_text: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default=None,
        doc="Beat rule text (e.g., '2 beats', 'fast')"
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
        index=True,
        doc="Project status: draft, analyzing, ready, rendering, complete, error"
    )
    status_message: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Human-readable status message or error details"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Project creation timestamp"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=datetime.utcnow,
        nullable=True,
        doc="Last update timestamp"
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="projects"
    )
    media_assets: Mapped[List["MediaAsset"]] = relationship(
        "MediaAsset",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="MediaAsset.sort_order"
    )
    audio_track: Mapped[Optional["AudioTrack"]] = relationship(
        "AudioTrack",
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False
    )
    timeline: Mapped[Optional["Timeline"]] = relationship(
        "Timeline",
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False
    )
    render_jobs: Mapped[List["RenderJob"]] = relationship(
        "RenderJob",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="RenderJob.created_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id!r}, name={self.name!r}, status={self.status!r})>"
