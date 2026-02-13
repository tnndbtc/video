"""
Timeline model for BeatStitch.

Stores metadata about the Edit Decision List (EDL) for a project.
"""

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .project import Project


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Timeline(Base):
    """
    Timeline model representing the Edit Decision List (EDL) for a project.

    One timeline per project (1:1 relationship enforced by unique constraint).
    The full EDL JSON is stored on the filesystem at edl_path for efficiency.
    This table stores metadata for display and cache invalidation.
    """

    __tablename__ = "timelines"

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
        doc="Foreign key to parent project (unique - one timeline per project)"
    )

    # EDL storage path
    edl_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Path to edl.json file"
    )

    # Summary metadata (for display without parsing EDL)
    total_duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Total timeline duration in milliseconds"
    )
    segment_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of segments in timeline"
    )

    # Cache invalidation hash
    edl_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="SHA-256 hash of inputs for cache validation"
    )

    # Timestamps
    generated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="When timeline was originally generated"
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        doc="When timeline was last modified"
    )

    # Note: created_at from user request maps to generated_at

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="timeline"
    )

    def __repr__(self) -> str:
        return f"<Timeline(id={self.id!r}, segments={self.segment_count}, duration_ms={self.total_duration_ms})>"
