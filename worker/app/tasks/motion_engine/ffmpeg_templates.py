"""
FFmpeg Filter Templates for Motion Clips

Builds FFmpeg filter expressions and full render commands
for Ken Burns style motion effects on still images.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from .presets import MotionPreset

logger = logging.getLogger(__name__)


@dataclass
class RenderConfig:
    """Configuration for motion clip rendering."""

    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    pix_fmt: str = "yuv420p"


# =============================================================================
# Filter Expression Builders
# =============================================================================


def build_zoom_expression(
    preset: MotionPreset,
    total_frames: int,
    beat_sync_expr: Optional[str] = None,
) -> str:
    """
    Build FFmpeg zoompan zoom expression.

    The zoom expression interpolates from start_zoom to end_zoom
    over total_frames, with optional beat-synced pulse overlay.

    Formula: z='if(eq(on,1),{sz},{sz}+(({ez}-{sz})/{frames})*on)'

    Args:
        preset: MotionPreset with zoom parameters
        total_frames: Total number of output frames
        beat_sync_expr: Optional beat pulse expression to add to zoom

    Returns:
        FFmpeg zoom expression string
    """
    sz = preset.start_zoom
    ez = preset.end_zoom

    # Apply easing if specified
    if preset.easing == "ease_in":
        # Quadratic ease-in: slower start, faster end
        zoom_expr = f"if(eq(on,1),{sz},{sz}+(({ez}-{sz})*(on/{total_frames})*(on/{total_frames})))"
    elif preset.easing == "ease_out":
        # Quadratic ease-out: faster start, slower end
        zoom_expr = f"if(eq(on,1),{sz},{ez}-(({ez}-{sz})*(1-on/{total_frames})*(1-on/{total_frames})))"
    elif preset.easing == "ease_in_out":
        # Smooth ease-in-out using smoothstep
        zoom_expr = (
            f"if(eq(on,1),{sz},"
            f"{sz}+({ez}-{sz})*(3*(on/{total_frames})*(on/{total_frames})"
            f"-2*(on/{total_frames})*(on/{total_frames})*(on/{total_frames})))"
        )
    else:
        # Linear interpolation (default)
        zoom_expr = f"if(eq(on,1),{sz},{sz}+(({ez}-{sz})/{total_frames})*on)"

    # Add beat sync pulse if provided
    if beat_sync_expr:
        # Wrap the base zoom with the pulse additive
        zoom_expr = f"({zoom_expr})+({beat_sync_expr})"

    return zoom_expr


def build_pan_x_expression(
    preset: MotionPreset,
    total_frames: int,
) -> str:
    """
    Build FFmpeg zoompan x (horizontal pan) expression.

    Formula: x='(iw-iw/zoom)*({sx}+({ex}-{sx})*on/{frames})'

    Args:
        preset: MotionPreset with pan parameters
        total_frames: Total number of output frames

    Returns:
        FFmpeg x expression string
    """
    sx = preset.pan_start_x
    ex = preset.pan_end_x

    return f"(iw-iw/zoom)*({sx}+({ex}-{sx})*on/{total_frames})"


def build_pan_y_expression(
    preset: MotionPreset,
    total_frames: int,
) -> str:
    """
    Build FFmpeg zoompan y (vertical pan) expression.

    Formula: y='(ih-ih/zoom)*({sy}+({ey}-{sy})*on/{frames})'

    Args:
        preset: MotionPreset with pan parameters
        total_frames: Total number of output frames

    Returns:
        FFmpeg y expression string
    """
    sy = preset.pan_start_y
    ey = preset.pan_end_y

    return f"(ih-ih/zoom)*({sy}+({ey}-{sy})*on/{total_frames})"


def build_motion_filter(
    preset: MotionPreset,
    duration_sec: float,
    config: RenderConfig,
    beat_sync_expr: Optional[str] = None,
    motion_strength: float = 1.0,
) -> str:
    """
    Build complete zoompan filter string for motion effect.

    Args:
        preset: MotionPreset to apply
        duration_sec: Duration of the clip in seconds
        config: RenderConfig with output settings
        beat_sync_expr: Optional beat-synced zoom pulse expression
        motion_strength: Scale factor for motion (0.0 to 1.0)

    Returns:
        Complete filter string for FFmpeg -vf
    """
    total_frames = int(duration_sec * config.fps)

    # Apply motion strength to zoom range
    if motion_strength < 1.0:
        # Scale the zoom delta by motion_strength
        zoom_delta = (preset.end_zoom - preset.start_zoom) * motion_strength
        adjusted_preset = MotionPreset(
            name=preset.name,
            start_zoom=preset.start_zoom,
            end_zoom=preset.start_zoom + zoom_delta,
            pan_start_x=preset.pan_start_x,
            pan_start_y=preset.pan_start_y,
            pan_end_x=preset.pan_start_x + (preset.pan_end_x - preset.pan_start_x) * motion_strength,
            pan_end_y=preset.pan_start_y + (preset.pan_end_y - preset.pan_start_y) * motion_strength,
            easing=preset.easing,
        )
    else:
        adjusted_preset = preset

    # Build expressions
    zoom_expr = build_zoom_expression(adjusted_preset, total_frames, beat_sync_expr)
    x_expr = build_pan_x_expression(adjusted_preset, total_frames)
    y_expr = build_pan_y_expression(adjusted_preset, total_frames)

    # Scale to 2x output width for quality zoom headroom
    intermediate_width = config.width * 2

    # Build filter chain
    filter_str = (
        f"scale={intermediate_width}:-1,"
        f"zoompan=z='{zoom_expr}':"
        f"x='{x_expr}':"
        f"y='{y_expr}':"
        f"d={total_frames}:"
        f"s={config.width}x{config.height}:"
        f"fps={config.fps},"
        f"setsar=1"
    )

    return filter_str


# =============================================================================
# Full Command Builders
# =============================================================================


def build_render_command(
    input_path: str,
    output_path: str,
    preset: MotionPreset,
    duration_sec: float,
    config: RenderConfig,
    beat_sync_expr: Optional[str] = None,
    motion_strength: float = 1.0,
) -> List[str]:
    """
    Build complete FFmpeg command to render motion clip.

    Args:
        input_path: Path to input image
        output_path: Path for output MP4
        preset: MotionPreset to apply
        duration_sec: Duration of the clip in seconds
        config: RenderConfig with encoding settings
        beat_sync_expr: Optional beat-synced zoom pulse expression
        motion_strength: Scale factor for motion (0.0 to 1.0)

    Returns:
        List of command arguments for subprocess
    """
    # Build the video filter
    vf = build_motion_filter(
        preset=preset,
        duration_sec=duration_sec,
        config=config,
        beat_sync_expr=beat_sync_expr,
        motion_strength=motion_strength,
    )

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-loop", "1",  # Loop input image
        "-i", input_path,
        "-t", str(duration_sec),  # Output duration
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-pix_fmt", config.pix_fmt,
        "-an",  # No audio
        output_path,
    ]

    return cmd


def build_simple_scale_command(
    input_path: str,
    output_path: str,
    duration_sec: float,
    config: RenderConfig,
) -> List[str]:
    """
    Build FFmpeg command for simple static image (no motion).

    Used when motion is disabled or for preview renders.

    Args:
        input_path: Path to input image
        output_path: Path for output MP4
        duration_sec: Duration of the clip in seconds
        config: RenderConfig with encoding settings

    Returns:
        List of command arguments for subprocess
    """
    vf = (
        f"scale={config.width}:{config.height}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={config.fps}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", input_path,
        "-t", str(duration_sec),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-pix_fmt", config.pix_fmt,
        "-an",
        output_path,
    ]

    return cmd
