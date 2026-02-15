"""
Motion Clip Cache Management

Provides deterministic cache key generation and storage
for pre-rendered motion clips.
"""

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default cache root from environment
# Use 'derived' subdirectory which has write permissions in Docker
CACHE_ROOT = Path(os.environ.get("STORAGE_PATH", "/data")) / "derived" / "cache" / "motion_clips"


def generate_cache_key(
    image_path: str,
    preset_name: str,
    duration_ms: int,
    resolution: str,
    fps: int,
    beat_sync_mode: str = "none",
    motion_strength: float = 1.0,
) -> str:
    """
    Generate deterministic cache key for a motion clip.

    The key is a SHA-256 hash of all parameters that affect
    the rendered output.

    Args:
        image_path: Path to source image
        preset_name: Motion preset name (e.g., "slow_zoom_in")
        duration_ms: Clip duration in milliseconds
        resolution: Output resolution string (e.g., "1920x1080")
        fps: Output frame rate
        beat_sync_mode: Beat sync mode ("none", "downbeat", "every_n_beats")
        motion_strength: Motion strength factor (0.0-1.0)

    Returns:
        SHA-256 hash string (64 characters)
    """
    # Hash the image file content for deterministic key
    # Use only first 64KB + file size for performance on large images
    image_hash = _hash_file_partial(image_path)

    payload = {
        "image_hash": image_hash,
        "preset": preset_name,
        "duration_ms": duration_ms,
        "resolution": resolution,
        "fps": fps,
        "beat_sync_mode": beat_sync_mode,
        "motion_strength": round(motion_strength, 3),
    }

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _hash_file_partial(file_path: str, chunk_size: int = 65536) -> str:
    """
    Generate partial hash of file for cache key.

    Uses first chunk + file size for fast hashing.

    Args:
        file_path: Path to file
        chunk_size: Bytes to read for hashing

    Returns:
        SHA-256 hash of first chunk concatenated with file size
    """
    try:
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            first_chunk = f.read(chunk_size)
        content = first_chunk + str(file_size).encode()
        return hashlib.sha256(content).hexdigest()[:16]
    except (IOError, OSError) as e:
        logger.warning(f"Failed to hash file {file_path}: {e}")
        # Fall back to path-based hash (less reliable but functional)
        return hashlib.sha256(file_path.encode()).hexdigest()[:16]


class MotionClipCache:
    """
    Cache manager for pre-rendered motion clips.

    Stores clips in a sharded directory structure:
    {cache_root}/{key[:2]}/{key}.mp4

    Usage:
        cache = MotionClipCache()

        # Check for cached clip
        cached_path = cache.get(cache_key)
        if cached_path:
            # Use cached clip
            ...
        else:
            # Render clip
            render_motion_clip(...)
            # Store in cache
            cache.store(cache_key, rendered_path)
    """

    def __init__(self, cache_root: Optional[Path] = None):
        """
        Initialize cache manager.

        Args:
            cache_root: Root directory for cache storage.
                       Defaults to /data/cache/motion_clips/
        """
        self.cache_root = cache_root or CACHE_ROOT
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, cache_key: str) -> Path:
        """
        Get filesystem path for cache key.

        Uses first 2 characters for sharding to avoid
        too many files in one directory.

        Args:
            cache_key: SHA-256 hash string

        Returns:
            Path to cached clip
        """
        shard = cache_key[:2]
        return self.cache_root / shard / f"{cache_key}.mp4"

    def get(self, cache_key: str) -> Optional[str]:
        """
        Get cached clip path if it exists.

        Args:
            cache_key: SHA-256 hash string

        Returns:
            Absolute path to cached MP4 if exists, None otherwise
        """
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            logger.debug(f"Cache hit: {cache_key[:16]}...")
            return str(cache_path)
        return None

    def store(self, cache_key: str, source_path: str) -> str:
        """
        Store rendered clip in cache.

        Copies the rendered clip to the cache location.

        Args:
            cache_key: SHA-256 hash string
            source_path: Path to rendered MP4 to cache

        Returns:
            Path to cached clip

        Raises:
            FileNotFoundError: If source_path doesn't exist
            IOError: If copy fails
        """
        cache_path = self._get_cache_path(cache_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Use atomic copy via temp file to prevent partial writes
        temp_path = cache_path.with_suffix(".tmp")
        try:
            shutil.copy2(source_path, temp_path)
            temp_path.rename(cache_path)
            logger.debug(f"Cached: {cache_key[:16]}... ({cache_path.stat().st_size} bytes)")
            return str(cache_path)
        except Exception as e:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to cache clip: {e}") from e

    def delete(self, cache_key: str) -> bool:
        """
        Delete cached clip.

        Args:
            cache_key: SHA-256 hash string

        Returns:
            True if deleted, False if not found
        """
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            cache_path.unlink()
            logger.debug(f"Deleted: {cache_key[:16]}...")
            return True
        return False

    def cleanup_old(self, max_age_hours: int = 168) -> int:
        """
        Remove cached clips older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours (default 7 days)

        Returns:
            Number of clips removed
        """
        import time

        max_age_seconds = max_age_hours * 3600
        cutoff_time = time.time() - max_age_seconds
        removed = 0

        for shard_dir in self.cache_root.iterdir():
            if not shard_dir.is_dir():
                continue
            for clip_path in shard_dir.glob("*.mp4"):
                try:
                    if clip_path.stat().st_mtime < cutoff_time:
                        clip_path.unlink()
                        removed += 1
                except (IOError, OSError) as e:
                    logger.warning(f"Failed to clean up {clip_path}: {e}")

        if removed > 0:
            logger.info(f"Cache cleanup: removed {removed} old clips")

        return removed

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with total_clips, total_size_mb, oldest_hours
        """
        import time

        total_clips = 0
        total_size = 0
        oldest_mtime = time.time()

        for shard_dir in self.cache_root.iterdir():
            if not shard_dir.is_dir():
                continue
            for clip_path in shard_dir.glob("*.mp4"):
                try:
                    stat = clip_path.stat()
                    total_clips += 1
                    total_size += stat.st_size
                    oldest_mtime = min(oldest_mtime, stat.st_mtime)
                except (IOError, OSError):
                    pass

        oldest_hours = (time.time() - oldest_mtime) / 3600 if total_clips > 0 else 0

        return {
            "total_clips": total_clips,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_hours": round(oldest_hours, 1),
        }
