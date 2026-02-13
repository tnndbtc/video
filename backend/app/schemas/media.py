"""
Pydantic schemas for Media endpoints.

Includes request/response models for media asset operations.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --- Processing Status Type ---

ProcessingStatus = Literal["pending", "processing", "ready", "failed"]
MediaType = Literal["image", "video"]


# --- Response Schemas ---


class MediaUploadItem(BaseModel):
    """Single uploaded media asset response."""

    id: str
    filename: str
    media_type: MediaType
    processing_status: ProcessingStatus
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    fps: Optional[float] = None
    file_size: int

    class Config:
        from_attributes = True


class MediaUploadResponse(BaseModel):
    """Response for media upload endpoint."""

    uploaded: List[MediaUploadItem]
    failed: List[dict] = Field(
        default_factory=list,
        description="List of files that failed to upload with error details"
    )
    total_uploaded: int


class MediaAssetResponse(BaseModel):
    """Full media asset details response."""

    id: str
    project_id: str
    filename: str
    media_type: MediaType
    processing_status: ProcessingStatus
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    fps: Optional[float] = None
    file_size: int
    thumbnail_url: Optional[str] = None
    sort_order: int
    created_at: datetime
    processed_at: Optional[datetime] = None
    processing_error: Optional[str] = None

    class Config:
        from_attributes = True


# --- Request Schemas ---


class MediaReorderRequest(BaseModel):
    """Request to reorder media assets."""

    order: List[str] = Field(
        ...,
        min_length=1,
        description="List of media asset IDs in the new order"
    )


class MediaReorderItem(BaseModel):
    """Single item in reorder response."""

    id: str
    sort_order: int


class MediaReorderResponse(BaseModel):
    """Response for media reorder endpoint."""

    success: bool
    new_order: List[MediaReorderItem]
    timeline_invalidated: bool
