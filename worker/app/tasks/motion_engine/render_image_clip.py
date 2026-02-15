"""
Motion Clip Renderer

Renders still images into animated video clips with Ken Burns
style motion effects, with caching for reuse.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .cache import MotionClipCache, generate_cache_key
from .ffmpeg_templates import (
    RenderConfig,
    build_render_command,
    build_simple_scale_command,
)
from .presets import MotionPreset, get_preset

logger = logging.getLogger(__name__)


def render_motion_clip(
    image_path: str,
    output_path: str,
    preset: MotionPreset,
    duration_sec: float,
    config: RenderConfig,
    beat_sync_expr: Optional[str] = None,
    motion_strength: float = 1.0,
    timeout_seconds: int = 120,
) -> bool:
    """
    Render a single motion clip from a still image.

    Uses FFmpeg zoompan filter to apply Ken Burns style
    zoom and pan effects.

    Args:
        image_path: Path to source image
        output_path: Path for output MP4
        preset: MotionPreset to apply
        duration_sec: Duration of the output clip
        config: RenderConfig with resolution/fps/encoding settings
        beat_sync_expr: Optional beat-synced zoom pulse expression
        motion_strength: Scale factor for motion (0.0-1.0)
        timeout_seconds: Maximum render time before abort

    Returns:
        True if render succeeded, False otherwise

    Raises:
        FileNotFoundError: If image_path doesn't exist
        subprocess.TimeoutExpired: If render exceeds timeout
    """
    # Validate input exists
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Build FFmpeg command
    cmd = build_render_command(
        input_path=image_path,
        output_path=output_path,
        preset=preset,
        duration_sec=duration_sec,
        config=config,
        beat_sync_expr=beat_sync_expr,
        motion_strength=motion_strength,
    )

    logger.info(f"Rendering motion clip: {preset.name}, {duration_sec}s @ {config.width}x{config.height}")
    logger.debug(f"FFmpeg command: {' '.join(cmd)}")

    try:
        # Run FFmpeg with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"FFmpeg failed: {stderr[-1000:]}")
            return False

        # Verify output exists and has content
        output = Path(output_path)
        if not output.exists() or output.stat().st_size == 0:
            logger.error(f"Output file missing or empty: {output_path}")
            return False

        logger.info(f"Motion clip rendered: {output.stat().st_size} bytes")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Motion clip render timed out after {timeout_seconds}s")
        # Clean up partial output
        if Path(output_path).exists():
            Path(output_path).unlink()
        raise

    except Exception as e:
        logger.error(f"Motion clip render failed: {e}")
        return False


def render_static_clip(
    image_path: str,
    output_path: str,
    duration_sec: float,
    config: RenderConfig,
    timeout_seconds: int = 60,
) -> bool:
    """
    Render a static (no motion) clip from a still image.

    Used for preview renders or when motion is disabled.

    Args:
        image_path: Path to source image
        output_path: Path for output MP4
        duration_sec: Duration of the output clip
        config: RenderConfig with resolution/fps/encoding settings
        timeout_seconds: Maximum render time

    Returns:
        True if render succeeded, False otherwise
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = build_simple_scale_command(
        input_path=image_path,
        output_path=output_path,
        duration_sec=duration_sec,
        config=config,
    )

    logger.info(f"Rendering static clip: {duration_sec}s @ {config.width}x{config.height}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"FFmpeg failed: {stderr[-1000:]}")
            return False

        output = Path(output_path)
        if not output.exists() or output.stat().st_size == 0:
            logger.error(f"Output file missing or empty: {output_path}")
            return False

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Static clip render timed out after {timeout_seconds}s")
        if Path(output_path).exists():
            Path(output_path).unlink()
        raise

    except Exception as e:
        logger.error(f"Static clip render failed: {e}")
        return False


def render_with_cache(
    image_path: str,
    preset_name: str,
    duration_ms: int,
    config: RenderConfig,
    cache: Optional[MotionClipCache] = None,
    beat_sync_mode: str = "none",
    beat_sync_expr: Optional[str] = None,
    motion_strength: float = 1.0,
    timeout_seconds: int = 120,
) -> Optional[str]:
    """
    Render motion clip with caching support.

    Checks cache first; if not found, renders the clip and stores it.

    Args:
        image_path: Path to source image
        preset_name: Motion preset name
        duration_ms: Duration in milliseconds
        config: RenderConfig with resolution/fps/encoding settings
        cache: MotionClipCache instance (creates default if None)
        beat_sync_mode: Beat sync mode for cache key
        beat_sync_expr: Beat-synced zoom expression
        motion_strength: Motion strength factor
        timeout_seconds: Render timeout

    Returns:
        Path to rendered/cached MP4 clip, or None on failure
    """
    # Initialize cache if not provided
    if cache is None:
        cache = MotionClipCache()

    # Get preset
    preset = get_preset(preset_name)
    if preset is None:
        logger.error(f"Unknown preset: {preset_name}")
        return None

    # Generate cache key
    resolution = f"{config.width}x{config.height}"
    cache_key = generate_cache_key(
        image_path=image_path,
        preset_name=preset_name,
        duration_ms=duration_ms,
        resolution=resolution,
        fps=config.fps,
        beat_sync_mode=beat_sync_mode,
        motion_strength=motion_strength,
    )

    # Check cache
    cached_path = cache.get(cache_key)
    if cached_path:
        logger.info(f"Cache hit for motion clip: {cache_key[:16]}...")
        return cached_path

    # Render to temp file, then cache
    duration_sec = duration_ms / 1000.0

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_path = tmp.name

    try:
        success = render_motion_clip(
            image_path=image_path,
            output_path=temp_path,
            preset=preset,
            duration_sec=duration_sec,
            config=config,
            beat_sync_expr=beat_sync_expr,
            motion_strength=motion_strength,
            timeout_seconds=timeout_seconds,
        )

        if not success:
            return None

        # Store in cache
        cached_path = cache.store(cache_key, temp_path)
        logger.info(f"Cached motion clip: {cache_key[:16]}...")
        return cached_path

    finally:
        # Clean up temp file
        if Path(temp_path).exists():
            Path(temp_path).unlink()


def prerender_segment_clips(
    segments: list,
    asset_path_resolver: callable,
    config: RenderConfig,
    cache: Optional[MotionClipCache] = None,
    beat_grid_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> dict:
    """
    Pre-render motion clips for all image segments.

    Used in the render pipeline to pre-render all image segments
    before the main FFmpeg pass.

    Args:
        segments: List of EDL segment dicts with effects data
        asset_path_resolver: Function to resolve asset_id -> file path
        config: RenderConfig for output settings
        cache: MotionClipCache instance
        beat_grid_path: Path to beat_grid.json for beat sync
        progress_callback: Called with (current, total) for progress tracking

    Returns:
        Dict mapping segment_index -> pre-rendered clip path
    """
    from .beat_sync import build_beat_sync_zoom_expr

    if cache is None:
        cache = MotionClipCache()

    clip_paths = {}
    image_segments = [s for s in segments if s.get("media_type") == "image"]
    total = len(image_segments)

    for i, seg in enumerate(image_segments):
        seg_idx = seg["segment_index"]

        # Get effects configuration
        effects = seg.get("effects") or {}
        preset_name = effects.get("motion_preset", "slow_zoom_in")
        motion_strength = effects.get("motion_strength", 1.0)
        beat_sync_mode = effects.get("beat_sync_mode", "none")
        beat_sync_n = effects.get("beat_sync_n", 4)

        # Get clip parameters
        duration_ms = seg["render_duration_ms"]
        asset_id = seg["media_asset_id"]
        image_path = asset_path_resolver(asset_id)

        # Build beat sync expression if needed
        beat_sync_expr = None
        if beat_sync_mode != "none" and beat_grid_path:
            clip_start_sec = seg["timeline_in_ms"] / 1000.0
            clip_duration_sec = duration_ms / 1000.0
            beat_sync_expr = build_beat_sync_zoom_expr(
                beat_grid_path=beat_grid_path,
                clip_start_sec=clip_start_sec,
                clip_duration_sec=clip_duration_sec,
                fps=config.fps,
                mode=beat_sync_mode,
                beat_n=beat_sync_n,
            )

        # Render with cache
        clip_path = render_with_cache(
            image_path=image_path,
            preset_name=preset_name,
            duration_ms=duration_ms,
            config=config,
            cache=cache,
            beat_sync_mode=beat_sync_mode,
            beat_sync_expr=beat_sync_expr,
            motion_strength=motion_strength,
        )

        if clip_path:
            clip_paths[seg_idx] = clip_path
            logger.debug(f"Segment {seg_idx}: motion clip ready")
        else:
            logger.warning(f"Segment {seg_idx}: motion clip render failed")

        # Report progress
        if progress_callback:
            progress_callback(i + 1, total)

    logger.info(f"Pre-rendered {len(clip_paths)}/{total} motion clips")
    return clip_paths
