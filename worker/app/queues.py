"""
BeatStitch Queue Definitions

Defines 5 queues in priority order:
- beatstitch:render_preview (high) - Quick preview renders need fast turnaround
- beatstitch:beat_analysis (medium) - Audio analysis for beat detection
- beatstitch:timeline (medium) - Timeline generation from beats
- beatstitch:render_final (low) - Full quality final renders
- beatstitch:thumbnails (low) - Thumbnail generation for media assets
"""

import os
from redis import Redis
from rq import Queue
from typing import Optional

# Redis connection singleton
_redis_connection: Optional[Redis] = None


def get_redis_connection() -> Redis:
    """
    Get or create a Redis connection from environment variable REDIS_URL.

    Returns:
        Redis: A Redis connection instance

    Raises:
        ValueError: If REDIS_URL environment variable is not set
    """
    global _redis_connection

    if _redis_connection is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_connection = Redis.from_url(redis_url, decode_responses=False)

    return _redis_connection


def create_queues(connection: Optional[Redis] = None) -> tuple:
    """
    Create all queues with the given Redis connection.

    Args:
        connection: Optional Redis connection. If not provided,
                   will use get_redis_connection().

    Returns:
        Tuple of (preview_queue, beat_queue, timeline_queue, final_queue, thumbnail_queue)
    """
    if connection is None:
        connection = get_redis_connection()

    preview = Queue("beatstitch:render_preview", connection=connection)
    beat = Queue("beatstitch:beat_analysis", connection=connection)
    timeline = Queue("beatstitch:timeline", connection=connection)
    final = Queue("beatstitch:render_final", connection=connection)
    thumbnail = Queue("beatstitch:thumbnails", connection=connection)

    return preview, beat, timeline, final, thumbnail


# Queue instances - created lazily when first accessed
# These are module-level for convenience but use lazy initialization
class _LazyQueue:
    """Lazy queue wrapper that initializes on first access."""

    def __init__(self, name: str):
        self._name = name
        self._queue: Optional[Queue] = None

    def _get_queue(self) -> Queue:
        if self._queue is None:
            self._queue = Queue(self._name, connection=get_redis_connection())
        return self._queue

    def __getattr__(self, name):
        return getattr(self._get_queue(), name)

    def enqueue(self, *args, **kwargs):
        return self._get_queue().enqueue(*args, **kwargs)

    def enqueue_call(self, *args, **kwargs):
        return self._get_queue().enqueue_call(*args, **kwargs)


# Queue instances in priority order (highest first)
preview_queue = _LazyQueue("beatstitch:render_preview")
beat_queue = _LazyQueue("beatstitch:beat_analysis")
timeline_queue = _LazyQueue("beatstitch:timeline")
final_queue = _LazyQueue("beatstitch:render_final")
thumbnail_queue = _LazyQueue("beatstitch:thumbnails")

# All queues in priority order for worker initialization
ALL_QUEUES = [
    "beatstitch:render_preview",   # High priority
    "beatstitch:beat_analysis",    # Medium priority
    "beatstitch:timeline",         # Medium priority
    "beatstitch:render_final",     # Low priority
    "beatstitch:thumbnails",       # Low priority
]

# Queue name constants for use in enqueue functions
QUEUE_NAMES = {
    "render_preview": "beatstitch:render_preview",
    "beat_analysis": "beatstitch:beat_analysis",
    "timeline": "beatstitch:timeline",
    "render_final": "beatstitch:render_final",
    "thumbnails": "beatstitch:thumbnails",
}
