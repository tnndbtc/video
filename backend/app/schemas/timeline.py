"""
Pydantic schemas for Timeline endpoints.

Includes request/response models for timeline generation, status, and retrieval.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --- Request Schemas ---


# No request body needed for timeline generation - uses path parameter


# --- Response Schemas ---


class TimelineGenerateResponse(BaseModel):
    """Response after triggering timeline generation."""

    job_id: str = Field(..., description="RQ job ID for timeline generation")
    status: Literal["queued"] = Field("queued", description="Job status")
    message: str = Field("Timeline generation queued", description="Human-readable message")


class TimelineGenerateConflictResponse(BaseModel):
    """Response when timeline generation is already in progress."""

    error: Literal["conflict"] = "conflict"
    message: str = Field(..., description="Error message")
    existing_job_id: str = Field(..., description="ID of the existing job")


class TimelineGeneratePreconditionResponse(BaseModel):
    """Response when prerequisites for timeline generation are not met."""

    error: Literal["precondition_failed"] = "precondition_failed"
    message: str = Field("Cannot generate timeline", description="Error message")
    details: Dict[str, Any] = Field(..., description="Details about missing prerequisites")


class TimelineTransition(BaseModel):
    """Transition information for a timeline segment."""

    type: str = Field(..., description="Transition type (cut, crossfade, fade_black)")
    duration_ms: int = Field(..., description="Transition duration in milliseconds")


class SegmentEffects(BaseModel):
    """Motion effects configuration for a segment."""

    motion_preset: Optional[str] = Field(
        None,
        description="Motion preset name (slow_zoom_in, slow_zoom_out, pan_left, pan_right, diagonal_push, subtle_drift)"
    )
    motion_strength: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Motion effect strength (0.0 = no motion, 1.0 = full motion)"
    )
    beat_sync_mode: Literal["none", "downbeat", "every_n_beats"] = Field(
        "none",
        description="Beat synchronization mode for zoom pulses"
    )
    beat_sync_n: int = Field(
        4,
        ge=1,
        le=32,
        description="For every_n_beats mode, pulse every N beats"
    )


class TimelineEffects(BaseModel):
    """Effects applied to a timeline segment."""

    ken_burns: Optional[Dict[str, Any]] = Field(None, description="Ken Burns effect settings")
    motion: Optional[SegmentEffects] = Field(None, description="Motion engine effects")


class TimelineSegment(BaseModel):
    """Individual segment in the timeline."""

    index: int = Field(..., description="Segment index (0-based)")
    media_asset_id: str = Field(..., description="UUID of the media asset")
    media_type: Literal["image", "video"] = Field(..., description="Type of media")
    thumbnail_url: str = Field(..., description="URL to segment thumbnail")
    timeline_in_ms: int = Field(..., description="Start time in timeline (milliseconds)")
    timeline_out_ms: int = Field(..., description="End time in timeline (milliseconds)")
    render_duration_ms: int = Field(..., description="Duration for rendering (milliseconds)")
    source_in_ms: int = Field(0, description="Start time in source media (milliseconds)")
    source_out_ms: int = Field(..., description="End time in source media (milliseconds)")
    effects: Optional[TimelineEffects] = Field(default_factory=TimelineEffects, description="Effects applied to segment")
    transition_in: Optional[TimelineTransition] = Field(None, description="Transition at start of segment")


class TimelineSettingsUsed(BaseModel):
    """Settings that were used to generate the timeline."""

    beats_per_cut: int = Field(..., description="Number of beats between cuts")
    transition_type: str = Field(..., description="Transition type used")


class TimelineResponse(BaseModel):
    """Full timeline response with segments."""

    id: str = Field(..., description="Timeline UUID")
    edl_hash: str = Field(..., description="SHA-256 hash of EDL for cache validation")
    segment_count: int = Field(..., description="Total number of segments")
    total_duration_ms: int = Field(..., description="Total timeline duration in milliseconds")
    segments: List[TimelineSegment] = Field(..., description="List of timeline segments")
    settings_used: TimelineSettingsUsed = Field(..., description="Settings used for generation")
    generated_at: datetime = Field(..., description="When timeline was generated")

    class Config:
        from_attributes = True


class TimelineNotFoundResponse(BaseModel):
    """Response when timeline doesn't exist."""

    error: Literal["not_found"] = "not_found"
    message: str = Field("Timeline not generated", description="Error message")
    hint: str = Field(..., description="Hint for how to generate timeline")


class SegmentDeleteResponse(BaseModel):
    """Response after deleting a segment from the timeline."""

    success: bool = Field(True, description="Whether deletion was successful")
    deleted_index: int = Field(..., description="Index of the deleted segment")
    new_segment_count: int = Field(..., description="New total segment count")
    new_total_duration_ms: int = Field(..., description="New total duration in milliseconds")
    new_edl_hash: str = Field(..., description="New EDL hash after modification")


class TimelineStatusResponse(BaseModel):
    """Lightweight timeline status response for polling."""

    project_id: str = Field(..., description="Project UUID")
    generated: bool = Field(False, description="Whether a timeline has been generated")
    generation_status: Literal["none", "queued", "generating", "ready", "failed"] = Field(
        ..., description="Current generation status"
    )

    # Optional fields - only present in certain states
    generation_job_id: Optional[str] = Field(None, description="Job ID if generation in progress")
    progress_percent: Optional[int] = Field(None, description="Progress percentage if generating")

    # Present when timeline is ready
    edl_hash: Optional[str] = Field(None, description="EDL hash if timeline is ready")
    segment_count: Optional[int] = Field(None, description="Number of segments if ready")
    total_duration_ms: Optional[int] = Field(None, description="Duration in ms if ready")
    stale: Optional[bool] = Field(None, description="Whether timeline is stale (settings changed)")
    stale_reason: Optional[str] = Field(None, description="Reason timeline is stale")
    generated_at: Optional[datetime] = Field(None, description="When timeline was generated")

    # Present when generation failed
    error_message: Optional[str] = Field(None, description="Error message if failed")
