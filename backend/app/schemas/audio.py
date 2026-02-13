"""
Pydantic schemas for Audio endpoints.

Includes request/response models for audio upload, beat analysis, and status.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --- Response Schemas ---


class AudioUploadResponse(BaseModel):
    """Response after uploading an audio file."""

    id: str = Field(..., description="Audio track UUID")
    filename: str = Field(..., description="Original filename")
    duration_ms: int = Field(..., description="Audio duration in milliseconds")
    sample_rate: Optional[int] = Field(None, description="Sample rate in Hz")
    file_size: int = Field(..., description="File size in bytes")
    analysis_status: Literal["queued", "processing", "complete", "failed"] = Field(
        ..., description="Beat analysis status"
    )
    analysis_job_id: Optional[str] = Field(None, description="RQ job ID for beat analysis")

    class Config:
        from_attributes = True


class AnalyzeResponse(BaseModel):
    """Response after triggering beat analysis."""

    job_id: str = Field(..., description="RQ job ID")
    status: Literal["queued", "processing"] = Field(..., description="Job status")
    message: str = Field(..., description="Human-readable message")


class AnalyzeConflictResponse(BaseModel):
    """Response when analysis is already in progress."""

    error: Literal["conflict"] = "conflict"
    message: str = Field(..., description="Error message")
    existing_job_id: str = Field(..., description="ID of the existing job")


class Beat(BaseModel):
    """Individual beat in the beat grid."""

    time_ms: int = Field(..., description="Beat time in milliseconds")
    beat_number: int = Field(..., description="Beat number in measure (1-based)")
    is_downbeat: bool = Field(..., description="Whether this is a downbeat")


class BeatsResponse(BaseModel):
    """Response containing beat analysis results."""

    status: Literal["complete", "processing", "queued", "failed"] = Field(
        ..., description="Analysis status"
    )
    bpm: Optional[float] = Field(None, description="Detected BPM")
    total_beats: Optional[int] = Field(None, description="Total number of beats detected")
    time_signature: Optional[str] = Field(None, description="Detected time signature")
    beats: Optional[List[Beat]] = Field(None, description="Beat grid data")
    analyzed_at: Optional[datetime] = Field(None, description="When analysis completed")

    # Fields for processing state
    job_id: Optional[str] = Field(None, description="Job ID if processing")
    progress_percent: Optional[int] = Field(None, description="Progress percentage if processing")
    message: Optional[str] = Field(None, description="Status message")

    class Config:
        from_attributes = True


class BeatsStatusResponse(BaseModel):
    """Lightweight status check for beat analysis."""

    project_id: str = Field(..., description="Project UUID")
    audio_uploaded: bool = Field(..., description="Whether audio is uploaded")
    analysis_status: Optional[Literal["queued", "processing", "complete", "failed"]] = Field(
        None, description="Beat analysis status"
    )
    bpm: Optional[float] = Field(None, description="Detected BPM if complete")
    total_beats: Optional[int] = Field(None, description="Total beats if complete")
    analyzed_at: Optional[datetime] = Field(None, description="When analysis completed")


# --- Error Response Schemas ---


class AudioNotFoundError(BaseModel):
    """Response when audio is not found."""

    error: Literal["not_found"] = "not_found"
    message: str = "Audio track not found for this project"
    resource_type: Literal["audio_track"] = "audio_track"


class BeatsNotFoundError(BaseModel):
    """Response when beats are not found (not yet analyzed)."""

    error: Literal["not_found"] = "not_found"
    message: str = "Beat analysis not complete"
    hint: str = Field(..., description="Hint for the user")
