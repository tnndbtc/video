"""
Unit tests for motion_engine.cache module.
"""

import os
import tempfile
from pathlib import Path

import pytest

from app.tasks.motion_engine.cache import (
    generate_cache_key,
    MotionClipCache,
)


class TestGenerateCacheKey:
    """Tests for cache key generation."""

    def test_deterministic_key(self):
        """Test that same inputs produce same key."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key1 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            key2 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            assert key1 == key2
        finally:
            os.unlink(temp_path)

    def test_different_preset_different_key(self):
        """Test that different preset produces different key."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key1 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            key2 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_out",  # Different
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            assert key1 != key2
        finally:
            os.unlink(temp_path)

    def test_different_duration_different_key(self):
        """Test that different duration produces different key."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key1 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            key2 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=6000,  # Different
                resolution="1920x1080",
                fps=30,
            )
            assert key1 != key2
        finally:
            os.unlink(temp_path)

    def test_different_resolution_different_key(self):
        """Test that different resolution produces different key."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key1 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            key2 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="640x360",  # Different
                fps=30,
            )
            assert key1 != key2
        finally:
            os.unlink(temp_path)

    def test_key_format(self):
        """Test that key is valid SHA-256 hex string."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
            )
            # SHA-256 produces 64 hex characters
            assert len(key) == 64
            assert all(c in "0123456789abcdef" for c in key)
        finally:
            os.unlink(temp_path)

    def test_beat_sync_mode_affects_key(self):
        """Test that beat_sync_mode affects the cache key."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test image data")
            temp_path = f.name

        try:
            key1 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
                beat_sync_mode="none",
            )
            key2 = generate_cache_key(
                image_path=temp_path,
                preset_name="slow_zoom_in",
                duration_ms=4000,
                resolution="1920x1080",
                fps=30,
                beat_sync_mode="downbeat",
            )
            assert key1 != key2
        finally:
            os.unlink(temp_path)


class TestMotionClipCache:
    """Tests for MotionClipCache class."""

    def test_cache_miss(self):
        """Test cache returns None for missing key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))
            result = cache.get("nonexistent_key_1234567890abcdef")
            assert result is None

    def test_cache_store_and_get(self):
        """Test storing and retrieving from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))

            # Create a test "clip" file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(b"test video content")
                source_path = f.name

            try:
                cache_key = "a" * 64  # Valid hex key

                # Store in cache
                cached_path = cache.store(cache_key, source_path)
                assert cached_path is not None
                assert Path(cached_path).exists()

                # Retrieve from cache
                retrieved = cache.get(cache_key)
                assert retrieved == cached_path
            finally:
                os.unlink(source_path)

    def test_cache_delete(self):
        """Test deleting from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))

            # Create and store a test clip
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(b"test video content")
                source_path = f.name

            try:
                cache_key = "b" * 64
                cache.store(cache_key, source_path)

                # Verify it exists
                assert cache.get(cache_key) is not None

                # Delete it
                assert cache.delete(cache_key) is True

                # Verify it's gone
                assert cache.get(cache_key) is None

                # Deleting again returns False
                assert cache.delete(cache_key) is False
            finally:
                os.unlink(source_path)

    def test_cache_sharding(self):
        """Test that cache uses sharded directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(b"test video content")
                source_path = f.name

            try:
                cache_key = "ab" + "c" * 62  # Key starting with "ab"
                cached_path = cache.store(cache_key, source_path)

                # Check that it's in the "ab" shard directory
                assert "/ab/" in cached_path or "\\ab\\" in cached_path
            finally:
                os.unlink(source_path)

    def test_cache_stats(self):
        """Test cache statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))

            # Empty cache
            stats = cache.get_stats()
            assert stats["total_clips"] == 0
            assert stats["total_size_mb"] == 0.0

            # Add some clips
            for i in range(3):
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                    f.write(b"x" * 1024 * 10)  # 10KB each - survives rounding
                    source_path = f.name

                cache_key = f"{i:02x}" + "d" * 62
                cache.store(cache_key, source_path)
                os.unlink(source_path)

            stats = cache.get_stats()
            assert stats["total_clips"] == 3
            assert stats["total_size_mb"] > 0

    def test_empty_file_not_cached(self):
        """Test that empty files are not considered cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = MotionClipCache(cache_root=Path(tmpdir))
            cache_key = "e" * 64

            # Manually create an empty file in cache location
            cache_path = cache._get_cache_path(cache_key)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.touch()  # Creates empty file

            # Should return None for empty file
            assert cache.get(cache_key) is None
