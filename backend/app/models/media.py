"""
MediaAsset model for BeatStitch.

Stores metadata for uploaded images and videos.
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


class MediaAsset(Base):
    """
    MediaAsset model representing an uploaded image or video.

    Stores file metadata, dimensions, and processing status.
    The renderer uses this to resolve file paths during rendering.
    """

    __tablename__ = "media_assets"

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

    # File information
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
    mime_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="MIME type (e.g., image/jpeg, video/mp4)"
    )

    # Media type
    media_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        doc="Media type: image or video"
    )

    # Processing status
    processing_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        doc="Processing status: pending, processing, ready, or failed"
    )
    processing_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Error message if processing failed"
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        doc="Timestamp when processing completed"
    )

    # Dimensions (native/storage dimensions) - populated after processing
    width: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Native width in pixels (populated after processing)"
    )
    height: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Native height in pixels (populated after processing)"
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Duration in milliseconds (videos only)"
    )
    fps: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Frames per second (videos only)"
    )

    # Display corrections
    rotation_deg: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Rotation in degrees: 0, 90, 180, or 270"
    )
    display_aspect_ratio: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        doc="Display aspect ratio override (e.g., '16:9', '4:3')"
    )

    # Derived assets
    thumbnail_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Path to generated thumbnail"
    )
    proxy_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Path to proxy file for preview"
    )

    # Ordering and timestamps
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        doc="Sort order within project"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Upload timestamp"
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="media_assets"
    )

    def __repr__(self) -> str:
        return f"<MediaAsset(id={self.id!r}, media_type={self.media_type!r}, filename={self.original_filename!r})>"

    def get_display_dimensions(self) -> tuple[int, int] | None:
        """
        Returns (width, height) accounting for rotation and display aspect ratio.

        The renderer must use this method to compute effective display dimensions.

        Returns:
            Tuple of (width, height) or None if dimensions not yet available.
        """
        if self.width is None or self.height is None:
            return None

        w, h = self.width, self.height

        # Apply rotation
        if self.rotation_deg in (90, 270):
            w, h = h, w

        # Apply display aspect ratio override if present
        if self.display_aspect_ratio:
            try:
                dar_w, dar_h = map(int, self.display_aspect_ratio.split(":"))
                w = int(h * dar_w / dar_h)
            except (ValueError, ZeroDivisionError):
                pass  # Keep original dimensions on parse error

        return w, h
