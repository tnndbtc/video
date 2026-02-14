"""
Job Queue Utilities

Functions for enqueueing jobs to specific queues and tracking progress.
Uses RQ (Redis Queue) for job management.
"""

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from rq import Queue
from rq.job import Job

from .redis import get_redis_connection


# Job timeout constants in seconds
JOB_TIMEOUTS: Dict[str, int] = {
    "beat_analysis": 300,       # 5 minutes
    "timeline_generation": 60,  # 1 minute
    "media_processing": 120,    # 2 minutes
    "render_preview": 600,      # 10 minutes
    "render_final": 1800,       # 30 minutes
}

# Queue names mapped to their Redis keys
QUEUE_NAMES: Dict[str, str] = {
    "render_preview": "beatstitch:render_preview",
    "beat_analysis": "beatstitch:beat_analysis",
    "timeline": "beatstitch:timeline",
    "render_final": "beatstitch:render_final",
    "thumbnails": "beatstitch:thumbnails",
}

# Progress key prefix
PROGRESS_KEY_PREFIX = "beatstitch:progress"

# Progress expiry time in seconds (1 hour)
PROGRESS_EXPIRY_SECONDS = 3600


def get_queue(queue_name: str) -> Queue:
    """
    Get an RQ Queue instance by name.

    Args:
        queue_name: Short queue name (e.g., "beat_analysis") or
                   full queue name (e.g., "beatstitch:beat_analysis")

    Returns:
        Queue: RQ Queue instance

    Raises:
        ValueError: If queue name is not recognized
    """
    # Check if it's a short name that needs mapping
    if queue_name in QUEUE_NAMES:
        full_name = QUEUE_NAMES[queue_name]
    elif queue_name.startswith("beatstitch:"):
        full_name = queue_name
    else:
        raise ValueError(f"Unknown queue name: {queue_name}")

    connection = get_redis_connection()
    return Queue(full_name, connection=connection)


def enqueue_job(
    queue_name: str,
    func: Callable,
    *args,
    job_timeout: Optional[int] = None,
    job_id: Optional[str] = None,
    **kwargs,
) -> Job:
    """
    Enqueue a job to the specified queue.

    Args:
        queue_name: Name of the queue (short or full name)
        func: The function to execute
        *args: Positional arguments for the function
        job_timeout: Optional timeout override in seconds
        job_id: Optional custom job ID
        **kwargs: Keyword arguments for the function

    Returns:
        Job: The enqueued RQ job

    Example:
        >>> job = enqueue_job(
        ...     "beat_analysis",
        ...     analyze_beats,
        ...     project_id="proj_123",
        ...     audio_id="audio_456",
        ... )
        >>> print(f"Job ID: {job.id}")
    """
    queue = get_queue(queue_name)

    # Use default timeout if not specified
    if job_timeout is None:
        # Try to infer timeout from queue name
        for key, timeout in JOB_TIMEOUTS.items():
            if key in queue_name:
                job_timeout = timeout
                break
        else:
            job_timeout = 300  # Default 5 minutes

    job = queue.enqueue(
        func,
        *args,
        job_timeout=job_timeout,
        job_id=job_id,
        **kwargs,
    )

    return job


def enqueue_beat_analysis(
    project_id: str,
    audio_id: str,
    func: Callable,
    job_id: Optional[str] = None,
) -> Job:
    """
    Enqueue a beat analysis job.

    Args:
        project_id: Project UUID
        audio_id: Audio track UUID
        func: Beat analysis function to execute
        job_id: Optional custom job ID

    Returns:
        Job: The enqueued RQ job
    """
    return enqueue_job(
        "beat_analysis",
        func,
        project_id=project_id,
        audio_id=audio_id,
        job_timeout=JOB_TIMEOUTS["beat_analysis"],
        job_id=job_id,
    )


def enqueue_timeline_generation(
    project_id: str,
    func: Callable,
    job_id: Optional[str] = None,
    **kwargs,
) -> Job:
    """
    Enqueue a timeline generation job.

    Args:
        project_id: Project UUID
        func: Timeline generation function to execute
        job_id: Optional custom job ID
        **kwargs: Additional arguments for the function

    Returns:
        Job: The enqueued RQ job
    """
    return enqueue_job(
        "timeline",
        func,
        project_id=project_id,
        job_timeout=JOB_TIMEOUTS["timeline_generation"],
        job_id=job_id,
        **kwargs,
    )


def enqueue_render_preview(
    project_id: str,
    func: Callable,
    job_id: Optional[str] = None,
    edl_hash: Optional[str] = None,  # Deprecated, kept for backwards compatibility
) -> Job:
    """
    Enqueue a preview render job (high priority).

    Timeline is now auto-generated during render, so edl_hash is not required.

    Args:
        project_id: Project UUID
        func: Render function to execute
        job_id: Optional custom job ID
        edl_hash: Deprecated, ignored

    Returns:
        Job: The enqueued RQ job
    """
    return enqueue_job(
        "render_preview",
        func,
        project_id=project_id,
        job_type="preview",
        job_timeout=JOB_TIMEOUTS["render_preview"],
        job_id=job_id,
    )


def enqueue_render_final(
    project_id: str,
    func: Callable,
    job_id: Optional[str] = None,
    edl_hash: Optional[str] = None,  # Deprecated, kept for backwards compatibility
) -> Job:
    """
    Enqueue a final render job (low priority).

    Timeline is now auto-generated during render, so edl_hash is not required.

    Args:
        project_id: Project UUID
        func: Render function to execute
        job_id: Optional custom job ID
        edl_hash: Deprecated, ignored

    Returns:
        Job: The enqueued RQ job
    """
    return enqueue_job(
        "render_final",
        func,
        project_id=project_id,
        job_type="final",
        job_timeout=JOB_TIMEOUTS["render_final"],
        job_id=job_id,
    )


def enqueue_thumbnail_generation(
    project_id: str,
    media_asset_id: str,
    func: Callable,
    job_id: Optional[str] = None,
) -> Job:
    """
    Enqueue a thumbnail generation job.

    Args:
        project_id: Project UUID
        media_asset_id: Media asset UUID
        func: Thumbnail generation function to execute
        job_id: Optional custom job ID

    Returns:
        Job: The enqueued RQ job
    """
    return enqueue_job(
        "thumbnails",
        func,
        project_id=project_id,
        media_asset_id=media_asset_id,
        job_timeout=JOB_TIMEOUTS["media_processing"],
        job_id=job_id,
    )


# ============================================================================
# Progress Tracking
# ============================================================================


def _get_progress_key(job_id: str) -> str:
    """Get the Redis key for a job's progress."""
    return f"{PROGRESS_KEY_PREFIX}:{job_id}"


def update_progress(job_id: str, percent: int, message: str) -> None:
    """
    Update the progress of a job in Redis.

    Progress is stored in a Redis hash with 1-hour expiry.

    Args:
        job_id: The RQ job ID
        percent: Progress percentage (0-100)
        message: Human-readable progress message

    Example:
        >>> update_progress("job_123", 50, "Processing audio...")
    """
    redis = get_redis_connection()
    key = _get_progress_key(job_id)

    progress_data = {
        "percent": str(percent),
        "message": message,
        "updated_at": datetime.utcnow().isoformat(),
    }

    # Use pipeline for atomic operation
    pipe = redis.pipeline()
    pipe.hset(key, mapping=progress_data)
    pipe.expire(key, PROGRESS_EXPIRY_SECONDS)
    pipe.execute()


def get_progress(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the progress of a job from Redis.

    Args:
        job_id: The RQ job ID

    Returns:
        Dict containing progress info or None if not found:
        {
            "percent": int,
            "message": str,
            "updated_at": str (ISO format)
        }

    Example:
        >>> progress = get_progress("job_123")
        >>> if progress:
        ...     print(f"{progress['percent']}% - {progress['message']}")
    """
    redis = get_redis_connection()
    key = _get_progress_key(job_id)

    data = redis.hgetall(key)

    if not data:
        return None

    return {
        "percent": int(data.get("percent", 0)),
        "message": data.get("message", ""),
        "updated_at": data.get("updated_at", ""),
    }


def delete_progress(job_id: str) -> bool:
    """
    Delete progress data for a job.

    Args:
        job_id: The RQ job ID

    Returns:
        bool: True if deleted, False if not found
    """
    redis = get_redis_connection()
    key = _get_progress_key(job_id)
    return redis.delete(key) > 0


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive job status including RQ job status and progress.

    Args:
        job_id: The RQ job ID

    Returns:
        Dict containing job status or None if not found:
        {
            "job_id": str,
            "status": str (queued, started, finished, failed, etc.),
            "progress": dict or None,
            "result": any or None,
            "error": str or None,
            "enqueued_at": str or None,
            "started_at": str or None,
            "ended_at": str or None,
        }
    """
    redis = get_redis_connection()

    try:
        job = Job.fetch(job_id, connection=redis)
    except Exception:
        return None

    progress = get_progress(job_id)

    return {
        "job_id": job_id,
        "status": job.get_status(),
        "progress": progress,
        "result": job.result if job.is_finished else None,
        "error": str(job.exc_info) if job.is_failed else None,
        "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
    }
