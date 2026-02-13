"""
BeatStitch Worker Entry Point

Starts the RQ worker that processes background jobs for:
- Beat analysis
- Timeline generation
- Video rendering (preview and final)
- Thumbnail generation

Usage:
    python -m app.main

Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379/0)
"""

import logging
import sys
from redis import Redis
from rq import Queue, Worker

from .queues import get_redis_connection, ALL_QUEUES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("beatstitch.worker")


def create_worker(connection: Redis) -> Worker:
    """
    Create an RQ worker that listens to all BeatStitch queues.

    Queues are listed in priority order (highest first):
    1. beatstitch:render_preview - Quick preview renders
    2. beatstitch:beat_analysis - Audio analysis
    3. beatstitch:timeline - Timeline generation
    4. beatstitch:render_final - Full quality renders
    5. beatstitch:thumbnails - Thumbnail generation

    Args:
        connection: Redis connection instance

    Returns:
        Worker: Configured RQ worker instance
    """
    queues = [Queue(name, connection=connection) for name in ALL_QUEUES]

    worker = Worker(
        queues=queues,
        connection=connection,
        name="beatstitch-worker",
    )

    return worker


def start_worker() -> None:
    """
    Initialize Redis connection and start the RQ worker.

    This function blocks and runs until the worker is terminated.
    """
    logger.info("Starting BeatStitch worker...")

    try:
        connection = get_redis_connection()

        # Verify Redis connection
        connection.ping()
        logger.info("Successfully connected to Redis")

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    logger.info(f"Listening on queues: {', '.join(ALL_QUEUES)}")

    worker = create_worker(connection)

    try:
        worker.work(with_scheduler=False)
    except KeyboardInterrupt:
        logger.info("Worker shutdown requested")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        sys.exit(1)

    logger.info("Worker stopped")


def main() -> None:
    """Main entry point for the worker module."""
    start_worker()


if __name__ == "__main__":
    main()
