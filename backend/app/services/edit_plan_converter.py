"""
EditPlan v1 to EditRequest converter for BeatStitch.

Converts an AI-generated EditPlanV1 into the renderer-compatible EditRequest format.
"""

from typing import Optional

from ..schemas.edit_plan import EditPlanV1
from ..schemas.edit_request import (
    AudioSettings,
    DefaultSettings,
    DurationMs,
    EditRequest,
    OutputSettings,
    SourceTrim,
    TimelineSegment,
    Transition,
)


def convert_edit_plan_to_edit_request(
    plan: EditPlanV1,
    audio_asset_id: Optional[str] = None,
    asset_map: Optional[dict] = None,
) -> EditRequest:
    """
    Convert an EditPlanV1 to an EditRequest.

    Args:
        plan: The EditPlanV1 to convert
        audio_asset_id: Optional audio asset ID for the audio track
        asset_map: Optional map of asset_id -> asset object for clamping video source_out_ms

    Returns:
        EditRequest ready for validation and rendering
    """
    ps = plan.project_settings

    # Output settings
    output = OutputSettings(
        width=ps.output_width,
        height=ps.output_height,
        fps=ps.output_fps,
    )

    # Default transition
    default_transition = Transition(
        type=ps.transition_type,
        duration_ms=ps.transition_duration_ms,
    )

    # Default effect
    default_effect = "slow_zoom_in" if ps.ken_burns_enabled else None

    defaults = DefaultSettings(
        transition=default_transition,
        effect=default_effect,
    )

    # Audio settings
    audio = None
    if plan.mode == "with_audio" and audio_asset_id:
        audio = AudioSettings(asset_id=audio_asset_id)

    # Build timeline segments (skip audio-type segments)
    non_audio_segments = [s for s in plan.timeline.segments if s.media_type != "audio"]

    timeline = []
    for i, seg in enumerate(non_audio_segments):
        # Duration
        duration = DurationMs(mode="ms", value=seg.render_duration_ms)

        # Source trim for video segments
        source = None
        if seg.media_type == "video":
            source_out = seg.source_out_ms
            # Clamp to asset duration if asset_map is provided
            if asset_map and seg.media_asset_id in asset_map:
                asset = asset_map[seg.media_asset_id]
                if hasattr(asset, "duration_ms") and asset.duration_ms:
                    source_out = min(source_out, asset.duration_ms)
            source = SourceTrim(in_ms=seg.source_in_ms, out_ms=source_out)

        # Effect
        effect = None
        if seg.effects and seg.effects.ken_burns and seg.effects.ken_burns.enabled:
            effect = "slow_zoom_in"

        # Transition in: shift-by-1 mapping
        # segment[i]'s transition_in comes from segment[i-1]'s transition_out
        transition_in = None
        if i > 0:
            prev_seg = non_audio_segments[i - 1]
            if prev_seg.transition_out:
                transition_in = Transition(
                    type=prev_seg.transition_out.type,
                    duration_ms=prev_seg.transition_out.duration_ms,
                )
            else:
                # Use project_settings default transition
                transition_in = Transition(
                    type=ps.transition_type,
                    duration_ms=ps.transition_duration_ms,
                )

        timeline.append(
            TimelineSegment(
                asset_id=seg.media_asset_id,
                type=seg.media_type,
                duration=duration,
                effect=effect,
                transition_in=transition_in,
                source=source,
            )
        )

    return EditRequest(
        version="1.0",
        project_id=plan.project_id,
        output=output,
        audio=audio,
        defaults=defaults,
        timeline=timeline,
    )
