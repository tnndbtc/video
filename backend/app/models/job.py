"""
RenderJob model for BeatStitch.

Tracks video rendering jobs and their progress.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .project import Project


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class RenderJob(Base):
    """
    RenderJob model representing a video rendering task.

    Captures a snapshot of EDL and render settings at creation time
    for reproducibility. Multiple render jobs can exist per project.
    """

    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
        doc="UUID primary key"
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to parent project"
    )

    # Job type
    job_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Job type: preview or final"
    )

    # Input snapshot (for reproducibility)
    edl_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="SHA-256 hash of EDL at render time"
    )
    render_settings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JSON snapshot of render settings"
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default="queued",
        nullable=False,
        index=True,
        doc="Status: queued, running, complete, failed, cancelled"
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Progress percentage (0-100)"
    )
    progress_message: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Human-readable progress message"
    )

    # Output
    output_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Path to rendered output file"
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        doc="Output file size in bytes"
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Output video duration in seconds"
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Error message if job failed"
    )

    # RQ job tracking
    rq_job_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Redis Queue job ID"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        doc="Job creation timestamp"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="When rendering started"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="When rendering completed (success or failure)"
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="render_jobs"
    )

    def __repr__(self) -> str:
        return f"<RenderJob(id={self.id!r}, type={self.job_type!r}, status={self.status!r}, progress={self.progress_percent}%)>"
