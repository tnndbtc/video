"""
Pydantic schemas for EditRequest v1 (EDL v1).

This module defines the user-authored JSON schema that fully defines a video edit
using only media assets, audio asset, and this JSON. Unlike the auto-generated EDL,
this is user input that drives the renderer.

Example usage:
    from app.schemas.edit_request import EditRequest

    request = EditRequest.model_validate(json_data)
"""

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Type Aliases and Literals
# =============================================================================

EffectPreset = Literal[
    "slow_zoom_in",
    "slow_zoom_out",
    "pan_left",
    "pan_right",
    "diagonal_push",
    "subtle_drift",
    "none"
]

TransitionType = Literal["cut", "crossfade"]

RepeatMode = Literal["repeat_all", "repeat_last", "stop"]

FillBehavior = Literal["black", "freeze_last"]


# =============================================================================
# Duration Models (Discriminated Union)
# =============================================================================


class DurationBeats(BaseModel):
    """Duration specified in musical beats.

    Actual duration = count × (60000/bpm) milliseconds.
    Requires audio settings with BPM to be defined.
    """
    mode: Literal["beats"] = "beats"
    count: int = Field(..., ge=1, le=64, description="Number of beats (1-64)")


class DurationMs(BaseModel):
    """Duration specified in explicit milliseconds."""
    mode: Literal["ms"] = "ms"
    value: int = Field(..., ge=250, le=60000, description="Duration in milliseconds (250-60000)")


class DurationNatural(BaseModel):
    """Natural duration based on asset type.

    - Images: 4000ms default
    - Videos: native duration of the source video
    """
    mode: Literal["natural"] = "natural"


# Discriminated union for duration types
Duration = Annotated[
    Union[DurationBeats, DurationMs, DurationNatural],
    Field(discriminator="mode")
]


# =============================================================================
# Component Models
# =============================================================================


class SourceTrim(BaseModel):
    """Video source trimming settings.

    Defines in/out points for extracting a portion of a video asset.
    Only applicable to video segments.
    """
    in_ms: int = Field(default=0, ge=0, description="Start time in source video (milliseconds)")
    out_ms: Optional[int] = Field(default=None, ge=0, description="End time in source video (milliseconds, None = end of video)")


class Transition(BaseModel):
    """Transition settings between segments."""
    type: TransitionType = Field(default="cut", description="Transition type")
    duration_ms: int = Field(default=0, ge=0, le=2000, description="Transition duration in milliseconds (0-2000)")


class OutputSettings(BaseModel):
    """Output video settings."""
    width: int = Field(default=1920, ge=320, le=7680, description="Output width in pixels")
    height: int = Field(default=1080, ge=240, le=4320, description="Output height in pixels")
    fps: int = Field(default=30, ge=15, le=120, description="Frames per second")


class AudioSettings(BaseModel):
    """Audio track settings."""
    asset_id: str = Field(..., description="UUID of the audio asset")
    bpm: Optional[float] = Field(default=None, gt=0, le=300, description="Override BPM (uses analyzed BPM if not set)")
    start_offset_ms: int = Field(default=0, ge=0, description="Audio start offset in milliseconds")
    end_at_audio_end: bool = Field(default=True, description="End video when audio ends")
    trim_end_ms: int = Field(default=0, ge=0, description="Trim from end of audio in milliseconds")


class DefaultSettings(BaseModel):
    """Default settings applied to all segments unless overridden."""
    beats_per_cut: int = Field(default=8, ge=1, le=64, description="Default beats between cuts")
    transition: Transition = Field(default_factory=Transition, description="Default transition settings")
    effect: Optional[EffectPreset] = Field(default=None, description="Default motion effect preset")


class RepeatSettings(BaseModel):
    """Settings for handling timeline shorter than audio."""
    mode: RepeatMode = Field(default="repeat_all", description="How to handle repeating timeline")
    fill_behavior: FillBehavior = Field(default="black", description="Fill behavior when mode=stop")


# =============================================================================
# Timeline Segment Model
# =============================================================================


class TimelineSegment(BaseModel):
    """Individual segment in the timeline.

    Each segment represents a media asset (image or video) with its
    duration, effects, and transition settings.
    """
    asset_id: str = Field(..., description="UUID of the media asset")
    type: Literal["image", "video"] = Field(..., description="Type of media asset")
    duration: Optional[Duration] = Field(default=None, description="Segment duration (uses defaults if not set)")
    effect: Optional[EffectPreset] = Field(default=None, description="Motion effect preset")
    transition_in: Optional[Transition] = Field(default=None, description="Transition at start of segment")
    source: Optional[SourceTrim] = Field(default=None, description="Video source trim settings (video only)")


# =============================================================================
# Main EditRequest Model
# =============================================================================


class EditRequest(BaseModel):
    """
    EditRequest v1 - User-authored JSON schema for video editing.

    This schema fully defines a video edit using only media assets, audio asset,
    and this JSON. It serves as user input that drives the video renderer.

    Example:
        {
            "version": "1.0",
            "audio": { "asset_id": "audio_001", "end_at_audio_end": true },
            "defaults": { "beats_per_cut": 8, "effect": "slow_zoom_in" },
            "timeline": [
                { "asset_id": "img_001", "type": "image" },
                { "asset_id": "img_002", "type": "image" }
            ],
            "repeat": { "mode": "repeat_all" }
        }
    """
    version: Literal["1.0"] = Field(default="1.0", description="Schema version")
    project_id: Optional[str] = Field(default=None, description="Optional project UUID to associate with")
    output: OutputSettings = Field(default_factory=OutputSettings, description="Output video settings")
    audio: Optional[AudioSettings] = Field(default=None, description="Audio track settings")
    defaults: DefaultSettings = Field(default_factory=DefaultSettings, description="Default segment settings")
    timeline: List[TimelineSegment] = Field(..., min_length=1, description="List of timeline segments")
    repeat: RepeatSettings = Field(default_factory=RepeatSettings, description="Timeline repeat settings")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "version": "1.0",
                    "audio": {"asset_id": "audio_001", "end_at_audio_end": True},
                    "defaults": {"beats_per_cut": 8, "effect": "slow_zoom_in"},
                    "timeline": [
                        {"asset_id": "img_001", "type": "image"},
                        {"asset_id": "img_002", "type": "image"},
                        {"asset_id": "vid_001", "type": "video", "duration": {"mode": "beats", "count": 16}}
                    ],
                    "repeat": {"mode": "repeat_all"}
                }
            ]
        }
    }


# =============================================================================
# Validation Result Models
# =============================================================================


class ValidationErrorDetail(BaseModel):
    """Details about a validation error or warning."""
    code: str = Field(..., description="Error code (e.g., 'asset_not_found', 'bpm_required')")
    message: str = Field(..., description="Human-readable error message")
    path: Optional[str] = Field(default=None, description="JSON path to the problematic field")
    asset_id: Optional[str] = Field(default=None, description="Related asset ID if applicable")


class ComputedInfo(BaseModel):
    """Computed information from a valid EditRequest."""
    total_duration_ms: int = Field(..., description="Total timeline duration in milliseconds")
    segment_count: int = Field(..., description="Number of segments in timeline")
    effective_bpm: Optional[float] = Field(default=None, description="BPM used for beat calculations")
    audio_duration_ms: Optional[int] = Field(default=None, description="Audio duration in milliseconds")
    loop_count: Optional[int] = Field(default=None, description="Number of timeline loops needed")


class EditRequestValidationResult(BaseModel):
    """Result of validating an EditRequest.

    Contains validation status, any errors/warnings, and computed metadata.
    """
    valid: bool = Field(..., description="Whether the EditRequest is valid")
    errors: List[ValidationErrorDetail] = Field(
        default_factory=list,
        description="Blocking errors that prevent processing"
    )
    warnings: List[ValidationErrorDetail] = Field(
        default_factory=list,
        description="Non-blocking warnings about potential issues"
    )
    computed: Optional[ComputedInfo] = Field(
        default=None,
        description="Computed metadata (only present if valid)"
    )


class EditRequestSaveResponse(BaseModel):
    """Response when saving an EditRequest."""
    id: str = Field(..., description="Saved EditRequest UUID")
    edl_hash: str = Field(..., description="SHA-256 hash of the EDL for cache validation")
    validation: EditRequestValidationResult = Field(..., description="Validation result")
    created_at: str = Field(..., description="ISO timestamp when saved")
