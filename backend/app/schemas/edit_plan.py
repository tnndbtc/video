"""
Pydantic v2 schemas for EditPlan v1 (AI-generated edit plan).

This module defines the schema for AI-generated edit plans that describe
how to assemble media assets into a video. The EditPlan is validated and
then converted to an EditRequest for rendering.

Example usage:
    from app.schemas.edit_plan import EditPlanV1, validate_edit_plan

    plan = EditPlanV1.model_validate(json_data)
    validate_edit_plan(plan, asset_map)
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EditPlanProjectSettings(BaseModel):
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    transition_type: Literal["cut", "crossfade"] = "cut"
    transition_duration_ms: int = Field(default=500, ge=0, le=2000)
    ken_burns_enabled: bool = False


class EditPlanKenBurns(BaseModel):
    enabled: bool
    zoom: Optional[float] = None
    pan: Optional[str] = None


class EditPlanSegmentEffects(BaseModel):
    ken_burns: Optional[EditPlanKenBurns] = None


class EditPlanTransition(BaseModel):
    type: Literal["cut", "crossfade"] = "cut"
    duration_ms: int = Field(default=500, ge=0, le=2000)


class EditPlanSegment(BaseModel):
    index: int = Field(..., ge=0)
    media_asset_id: str
    media_type: Literal["image", "video", "audio"]
    render_duration_ms: int = Field(..., gt=0)
    source_in_ms: int = Field(default=0, ge=0)
    source_out_ms: int = Field(..., gt=0)
    effects: EditPlanSegmentEffects = Field(default_factory=EditPlanSegmentEffects)
    transition_out: Optional[EditPlanTransition] = None


class EditPlanTimeline(BaseModel):
    total_duration_ms: int = Field(..., gt=0)
    segments: List[EditPlanSegment] = Field(..., min_length=1)


class EditPlanV1(BaseModel):
    plan_version: Literal["v1"] = "v1"
    mode: Literal["no_audio", "with_audio"] = "no_audio"
    project_id: str
    project_settings: EditPlanProjectSettings = Field(
        default_factory=EditPlanProjectSettings
    )
    timeline: EditPlanTimeline
    notes: Optional[str] = None
    warnings: Optional[List[str]] = None


def validate_edit_plan(plan: EditPlanV1, asset_map: dict) -> None:
    """
    Validate an EditPlan against available assets.

    Args:
        plan: The EditPlanV1 to validate
        asset_map: Maps media_asset_id -> object with .processing_status attribute

    Raises:
        ValueError: If any validation rule is violated
    """
    segments = plan.timeline.segments

    # 1. Check contiguous indices 0..N-1
    expected_indices = list(range(len(segments)))
    actual_indices = [s.index for s in segments]
    if actual_indices != expected_indices:
        raise ValueError(
            f"Segment indices must be contiguous 0..{len(segments) - 1}, "
            f"got {actual_indices}"
        )

    # 2. Check each segment's asset exists and is ready
    for seg in segments:
        if seg.media_asset_id not in asset_map:
            raise ValueError(
                f"Segment {seg.index}: media_asset_id '{seg.media_asset_id}' "
                f"not found in asset_map"
            )
        asset = asset_map[seg.media_asset_id]
        if asset.processing_status != "ready":
            raise ValueError(
                f"Segment {seg.index}: asset '{seg.media_asset_id}' has "
                f"processing_status='{asset.processing_status}', expected 'ready'"
            )

    # 3. Check source_out_ms > source_in_ms
    for seg in segments:
        if seg.source_out_ms <= seg.source_in_ms:
            raise ValueError(
                f"Segment {seg.index}: source_out_ms ({seg.source_out_ms}) "
                f"must be greater than source_in_ms ({seg.source_in_ms})"
            )

    # 4. Check total_duration_ms matches computed sum
    non_audio_segments = [s for s in segments if s.media_type != "audio"]
    if not non_audio_segments:
        return

    render_sum = sum(s.render_duration_ms for s in non_audio_segments)
    n = len(non_audio_segments)

    transition_type = plan.project_settings.transition_type
    transition_duration_ms = plan.project_settings.transition_duration_ms

    if transition_type == "crossfade" and n > 1:
        expected_total = render_sum - (n - 1) * transition_duration_ms
    else:
        expected_total = render_sum

    actual_total = plan.timeline.total_duration_ms
    tolerance = 50

    if abs(actual_total - expected_total) > tolerance:
        raise ValueError(
            f"total_duration_ms mismatch: declared={actual_total}, "
            f"computed={expected_total} (tolerance={tolerance}ms, "
            f"transition_type='{transition_type}')"
        )
