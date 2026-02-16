"""
Pydantic schemas for Render API endpoints.

Includes request/response models for starting render jobs, checking status,
and downloading rendered files.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from .edit_request import EditRequest


# --- Request Schemas ---


class RenderRequest(BaseModel):
    """Request to start a render job."""

    type: Literal["preview", "final"] = Field(
        ..., description="Render type: 'preview' for quick draft, 'final' for full quality"
    )
    rule_text: Optional[str] = Field(
        None,
        max_length=500,
        description="Natural language rule for beat-synced cuts (e.g., '8 beats', 'fast', '每4拍')",
    )
    video_length_seconds: Optional[int] = Field(
        None,
        gt=0,
        le=600,
        description="Target video length in seconds (max 10 minutes)",
    )
    edit_request: Optional[EditRequest] = Field(
        None,
        description="Optional EditRequest (EDL v1) to use instead of auto-generated timeline. "
                    "When provided, rule_text and video_length_seconds are ignored.",
    )
    # Note: edl_hash removed - timeline is now auto-generated during render


# --- Response Schemas ---


class RenderResponse(BaseModel):
    """Response when render job is queued successfully (202 Accepted)."""

    job_id: str = Field(..., description="Unique identifier for the render job")
    job_type: Literal["preview", "final"] = Field(..., description="Type of render job")
    status: Literal["queued"] = Field("queued", description="Initial job status")
    created_at: datetime = Field(..., description="When the job was created")
    # Note: edl_hash is set during render, not at queue time

    class Config:
        from_attributes = True


class RenderJobStatus(BaseModel):
    """Full status of a render job."""

    id: Optional[str] = Field(None, description="Render job UUID (null if idle)")
    project_id: Optional[str] = Field(None, description="Project UUID (null if idle)")
    job_type: Optional[Literal["preview", "final"]] = Field(
        None, description="Type of render (null if idle)"
    )
    status: Literal["idle", "queued", "running", "complete", "failed", "cancelled"] = Field(
        ..., description="Current job status ('idle' means no render job exists)"
    )
    edl_hash: Optional[str] = Field(None, description="EDL hash of the rendered timeline")
    progress_percent: int = Field(
        0, ge=0, le=100, description="Progress percentage (0-100)"
    )
    progress_message: Optional[str] = Field(
        None, description="Human-readable progress message"
    )
    output_url: Optional[str] = Field(
        None, description="Download URL when complete"
    )
    file_size: Optional[int] = Field(
        None, description="Output file size in bytes when complete"
    )
    duration_seconds: Optional[float] = Field(
        None, description="Output video duration in seconds when complete"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: Optional[datetime] = Field(None, description="When job was created")
    started_at: Optional[datetime] = Field(
        None, description="When rendering started"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When rendering completed"
    )

    class Config:
        from_attributes = True


# --- Error Response Schemas ---


class RenderEdlHashMismatchResponse(BaseModel):
    """Response when provided EDL hash doesn't match current timeline (409 Conflict)."""

    error: Literal["edl_hash_mismatch"] = "edl_hash_mismatch"
    message: str = Field(
        "Timeline has changed since request was initiated",
        description="Error description",
    )
    details: Dict[str, str] = Field(
        ..., description="Details including provided_hash and current_hash"
    )
    hint: str = Field(
        "Fetch updated timeline and retry with current edl_hash",
        description="Suggestion for resolving the error",
    )


class RenderPreconditionFailedResponse(BaseModel):
    """Response when timeline is not available for rendering (400 Bad Request)."""

    error: Literal["precondition_failed"] = "precondition_failed"
    message: str = Field(
        "Timeline not available for rendering", description="Error description"
    )
    details: Dict[str, Any] = Field(
        ..., description="Details about the precondition failure"
    )


class RenderConflictResponse(BaseModel):
    """Response when render of same type is already in progress (409 Conflict)."""

    error: Literal["conflict"] = "conflict"
    message: str = Field(
        "Render job already in progress", description="Error description"
    )
    existing_job_id: str = Field(
        ..., description="ID of the existing in-progress render job"
    )


class RenderNotFoundResponse(BaseModel):
    """Response when requested render is not available (404 Not Found)."""

    error: Literal["not_found"] = "not_found"
    message: str = Field(..., description="Error description")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional details"
    )
