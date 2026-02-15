"""
Motion Engine for Still Image Animation

Provides Ken Burns style animated video clips from still images
using FFmpeg zoompan filters, with caching for performance.

Usage:
    from worker.app.tasks.motion_engine import (
        render_motion_clip,
        render_with_cache,
        PRESET_LIBRARY,
        MotionPreset,
        MotionClipCache,
    )

    # Render a single motion clip
    render_motion_clip(
        image_path="input.jpg",
        output_path="output.mp4",
        preset=PRESET_LIBRARY["slow_zoom_in"],
        duration_sec=4.0,
        config=RenderConfig(width=1920, height=1080, fps=30),
    )

    # Render with caching
    clip_path = render_with_cache(
        image_path="input.jpg",
        preset_name="slow_zoom_in",
        duration_ms=4000,
        config=RenderConfig(),
    )
"""

from .presets import (
    MotionPreset,
    PRESET_LIBRARY,
    get_preset,
    get_preset_for_index,
    list_presets,
)

from .cache import (
    MotionClipCache,
    generate_cache_key,
)

from .ffmpeg_templates import (
    RenderConfig,
    build_motion_filter,
    build_render_command,
)

from .render_image_clip import (
    render_motion_clip,
    render_static_clip,
    render_with_cache,
    prerender_segment_clips,
)

from .beat_sync import (
    build_beat_sync_zoom_expr,
    load_beat_grid,
    get_beat_frames,
)

__all__ = [
    # Presets
    "MotionPreset",
    "PRESET_LIBRARY",
    "get_preset",
    "get_preset_for_index",
    "list_presets",
    # Cache
    "MotionClipCache",
    "generate_cache_key",
    # FFmpeg
    "RenderConfig",
    "build_motion_filter",
    "build_render_command",
    # Rendering
    "render_motion_clip",
    "render_static_clip",
    "render_with_cache",
    "prerender_segment_clips",
    # Beat sync
    "build_beat_sync_zoom_expr",
    "load_beat_grid",
    "get_beat_frames",
]
