"""
BeatStitch Worker Tasks

This module exports all background task functions for the RQ worker.

Tasks:
- analyze_beats: Analyze audio for beat detection
- process_media: Process uploaded media (thumbnails, metadata extraction)
- generate_timeline: Generate timeline (EDL) from beats and media assets
- render_video: Render video output (preview or final quality)

Enqueue helpers (use these for proper timeout handling):
- enqueue_beat_analysis: Enqueue beat analysis with 5-minute timeout
- enqueue_media_processing: Enqueue media processing with 2-minute timeout
- enqueue_timeline_generation: Enqueue timeline generation with 1-minute timeout
- enqueue_render: Enqueue render with 10-minute (preview) or 30-minute (final) timeout
"""

from .beat_analysis import (
    analyze_beats,
    enqueue_beat_analysis,
    BEAT_ANALYSIS_TIMEOUT,
)
from .media import (
    process_media,
    enqueue_media_processing,
    MEDIA_PROCESSING_TIMEOUT,
)
from .timeline import (
    generate_timeline,
    enqueue_timeline_generation,
    TIMELINE_GENERATION_TIMEOUT,
)
from .render import (
    render_video,
    enqueue_render,
    RENDER_PREVIEW_TIMEOUT,
    RENDER_FINAL_TIMEOUT,
)

__all__ = [
    # Task functions
    "analyze_beats",
    "process_media",
    "generate_timeline",
    "render_video",
    # Enqueue helpers
    "enqueue_beat_analysis",
    "enqueue_media_processing",
    "enqueue_timeline_generation",
    "enqueue_render",
    # Constants
    "BEAT_ANALYSIS_TIMEOUT",
    "MEDIA_PROCESSING_TIMEOUT",
    "TIMELINE_GENERATION_TIMEOUT",
    "RENDER_PREVIEW_TIMEOUT",
    "RENDER_FINAL_TIMEOUT",
]
