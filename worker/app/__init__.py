"""
BeatStitch Worker Package

RQ-based worker for processing background jobs including:
- Beat analysis
- Timeline generation
- Video rendering (preview and final)
- Thumbnail generation
- Media processing (metadata extraction, thumbnail generation)
"""

from .queues import (
    get_redis_connection,
    preview_queue,
    beat_queue,
    timeline_queue,
    final_queue,
    thumbnail_queue,
    ALL_QUEUES,
)

# Import tasks for convenient access
from .tasks import (
    process_media,
    analyze_beats,
    enqueue_media_processing,
    enqueue_beat_analysis,
    MEDIA_PROCESSING_TIMEOUT,
    BEAT_ANALYSIS_TIMEOUT,
)

__all__ = [
    # Queues
    "get_redis_connection",
    "preview_queue",
    "beat_queue",
    "timeline_queue",
    "final_queue",
    "thumbnail_queue",
    "ALL_QUEUES",
    # Tasks
    "process_media",
    "analyze_beats",
    # Enqueue helpers
    "enqueue_media_processing",
    "enqueue_beat_analysis",
    # Timeout constants
    "MEDIA_PROCESSING_TIMEOUT",
    "BEAT_ANALYSIS_TIMEOUT",
]
