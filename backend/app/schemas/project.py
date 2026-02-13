"""
Pydantic schemas for Project endpoints.

Includes request/response models for project CRUD operations.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --- Settings Schemas ---

class ProjectSettings(BaseModel):
    """Full project settings schema."""

    beats_per_cut: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Number of beats between cuts (1, 2, 4, 8, or 16)"
    )
    transition_type: Literal["cut", "crossfade", "fade_black"] = Field(
        default="cut",
        description="Transition type between clips"
    )
    transition_duration_ms: int = Field(
        default=500,
        ge=0,
        le=2000,
        description="Transition duration in milliseconds"
    )
    ken_burns_enabled: bool = Field(
        default=True,
        description="Whether Ken Burns effect is enabled for images"
    )
    output_width: int = Field(
        default=1920,
        ge=320,
        le=7680,
        description="Output video width in pixels"
    )
    output_height: int = Field(
        default=1080,
        ge=240,
        le=4320,
        description="Output video height in pixels"
    )
    output_fps: int = Field(
        default=30,
        ge=15,
        le=60,
        description="Output video frames per second"
    )


class ProjectSettingsUpdate(BaseModel):
    """Partial settings update schema."""

    beats_per_cut: Optional[int] = Field(
        default=None,
        ge=1,
        le=16,
        description="Number of beats between cuts (1, 2, 4, 8, or 16)"
    )
    transition_type: Optional[Literal["cut", "crossfade", "fade_black"]] = Field(
        default=None,
        description="Transition type between clips"
    )
    transition_duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
        le=2000,
        description="Transition duration in milliseconds"
    )
    ken_burns_enabled: Optional[bool] = Field(
        default=None,
        description="Whether Ken Burns effect is enabled for images"
    )
    output_width: Optional[int] = Field(
        default=None,
        ge=320,
        le=7680,
        description="Output video width in pixels"
    )
    output_height: Optional[int] = Field(
        default=None,
        ge=240,
        le=4320,
        description="Output video height in pixels"
    )
    output_fps: Optional[int] = Field(
        default=None,
        ge=15,
        le=60,
        description="Output video frames per second"
    )


# --- Request Schemas ---

class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Project display name"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional project description"
    )


class ProjectUpdate(BaseModel):
    """Schema for updating project (name/description)."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Project display name"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional project description"
    )


# --- Response Schemas for Nested Objects ---

class MediaAssetSummary(BaseModel):
    """Summary of a media asset for project detail response."""

    id: str
    filename: str
    original_filename: str
    media_type: str
    processing_status: str = "ready"
    processing_error: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    fps: Optional[float] = None
    file_size: int
    thumbnail_url: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True


class AudioTrackSummary(BaseModel):
    """Summary of audio track for project detail response."""

    id: str
    filename: str
    duration_ms: int
    bpm: Optional[float] = None
    analysis_status: str

    class Config:
        from_attributes = True


class TimelineSummary(BaseModel):
    """Summary of timeline for project detail response."""

    id: str
    segment_count: int
    total_duration_ms: int
    edl_hash: str

    class Config:
        from_attributes = True


# --- Main Response Schemas ---

class ProjectResponse(BaseModel):
    """Full project response with settings and related objects."""

    id: str
    name: str
    description: Optional[str] = None
    status: str
    settings: ProjectSettings
    media_assets: List[MediaAssetSummary] = []
    audio_track: Optional[AudioTrackSummary] = None
    timeline: Optional[TimelineSummary] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectListItem(BaseModel):
    """Project item for list response."""

    id: str
    name: str
    status: str
    media_count: int
    has_audio: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """Response for project list endpoint."""

    projects: List[ProjectListItem]
    total: int


class ProjectSettingsResponse(BaseModel):
    """Response after updating project settings."""

    id: str
    settings: ProjectSettings
    timeline_invalidated: bool
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Status Response Schemas ---

class MediaStatusCounts(BaseModel):
    """Media asset counts by processing status."""

    total: int = 0
    pending: int = 0
    processing: int = 0
    ready: int = 0
    failed: int = 0


class AudioStatus(BaseModel):
    """Audio track status for project status response."""

    uploaded: bool
    analysis_status: Optional[str] = None


class TimelineStatus(BaseModel):
    """Timeline status for project status response."""

    generated: bool
    edl_hash: Optional[str] = None
    stale: bool = False


class ProjectStatusResponse(BaseModel):
    """Lightweight project status response."""

    project_id: str
    media: MediaStatusCounts
    audio: AudioStatus
    timeline: TimelineStatus
    ready_to_render: bool
