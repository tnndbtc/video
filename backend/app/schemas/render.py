"""
Pydantic schemas for Render API endpoints.

Includes request/response models for starting render jobs, checking status,
and downloading rendered files.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


# --- Request Schemas ---


class RenderRequest(BaseModel):
    """Request to start a render job."""

    type: Literal["preview", "final"] = Field(
        ..., description="Render type: 'preview' for quick draft, 'final' for full quality"
    )
    edl_hash: str = Field(
        ...,
        description="EDL hash for race condition prevention",
        min_length=64,
        max_length=64,
    )


# --- Response Schemas ---


class RenderResponse(BaseModel):
    """Response when render job is queued successfully (202 Accepted)."""

    job_id: str = Field(..., description="Unique identifier for the render job")
    job_type: Literal["preview", "final"] = Field(..., description="Type of render job")
    status: Literal["queued"] = Field("queued", description="Initial job status")
    edl_hash: str = Field(..., description="EDL hash used for this render")
    created_at: datetime = Field(..., description="When the job was created")

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
