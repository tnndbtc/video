"""
Unit tests for storage module.

Tests file storage, path handling, and directory permissions.
Ensures directories are created with proper permissions for multi-user/container access.

NOTE: These tests require the full app environment (conftest.py sets up env vars).
For standalone permission tests without app dependencies, see test_storage_permissions.py.
"""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import from app after conftest.py has set up environment
from app.core.storage import (
    _mkdir_world_writable,
    ensure_project_directories,
    sanitize_filename,
    validate_file_type,
)


class TestMkdirWorldWritable:
    """Tests for _mkdir_world_writable helper function."""

    def test_creates_directory(self, tmp_path: Path):
        """Test that directory is created."""
        test_dir = tmp_path / "test_dir"
        assert not test_dir.exists()

        _mkdir_world_writable(test_dir)

        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_creates_nested_directories(self, tmp_path: Path):
        """Test that nested directories are created (parents=True)."""
        test_dir = tmp_path / "level1" / "level2" / "level3"
        assert not test_dir.exists()

        _mkdir_world_writable(test_dir)

        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_directory_has_world_writable_permissions(self, tmp_path: Path):
        """
        Test that created directory has world-writable (777) permissions.

        This is critical for multi-container setups where:
        - Backend (running as root) creates directories
        - Worker (running as non-root uid 1000) needs to write to them
        """
        test_dir = tmp_path / "world_writable_dir"

        _mkdir_world_writable(test_dir)

        # Get the actual permissions
        mode = test_dir.stat().st_mode

        # Check that all permission bits are set (rwxrwxrwx = 0o777)
        assert mode & stat.S_IRWXU == stat.S_IRWXU, "Owner should have rwx"
        assert mode & stat.S_IRWXG == stat.S_IRWXG, "Group should have rwx"
        assert mode & stat.S_IRWXO == stat.S_IRWXO, "Others should have rwx"

    def test_existing_directory_permissions_updated(self, tmp_path: Path):
        """Test that existing directory permissions are updated to 777."""
        test_dir = tmp_path / "existing_dir"

        # Create with restrictive permissions first
        test_dir.mkdir(mode=0o700)
        assert test_dir.exists()

        # Now call our function
        _mkdir_world_writable(test_dir)

        # Permissions should be updated
        mode = test_dir.stat().st_mode
        assert mode & stat.S_IRWXO == stat.S_IRWXO, "Others should have rwx after update"

    def test_idempotent_on_existing_directory(self, tmp_path: Path):
        """Test that calling on existing directory doesn't raise error."""
        test_dir = tmp_path / "idempotent_test"
        test_dir.mkdir()

        # Should not raise
        _mkdir_world_writable(test_dir)
        _mkdir_world_writable(test_dir)

        assert test_dir.exists()


class TestEnsureProjectDirectories:
    """Tests for ensure_project_directories function."""

    def test_creates_all_required_directories(self, tmp_path: Path):
        """Test that all project directories are created."""
        project_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("app.core.storage.get_storage_root", return_value=tmp_path):
            directories = ensure_project_directories(project_id)

        # Check all expected directories exist
        assert "media" in directories
        assert "audio" in directories
        assert "image" in directories
        assert "video" in directories
        assert "derived" in directories
        assert "outputs" in directories

        for name, dir_path in directories.items():
            assert dir_path.exists(), f"Directory {name} should exist"
            assert dir_path.is_dir(), f"{name} should be a directory"

    def test_directories_have_world_writable_permissions(self, tmp_path: Path):
        """
        Test that all project directories have world-writable permissions.

        REGRESSION TEST: This catches the bug where directories were created
        with 755 permissions, preventing the worker container from writing.
        """
        project_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("app.core.storage.get_storage_root", return_value=tmp_path):
            directories = ensure_project_directories(project_id)

        # Check permissions on key directories that worker needs to write to
        critical_dirs = ["derived", "outputs"]

        for dir_name in critical_dirs:
            dir_path = directories[dir_name]
            mode = dir_path.stat().st_mode

            # Must have world-writable permissions
            assert mode & stat.S_IWOTH, (
                f"Directory '{dir_name}' must be world-writable. "
                f"Got mode {oct(mode)}. "
                "Worker container (uid 1000) cannot write to directories "
                "created by backend (root) without world-write permission."
            )

    def test_derived_thumbnails_parent_is_writable(self, tmp_path: Path):
        """
        Test that derived directory allows creating subdirectories.

        REGRESSION TEST: Worker failed with 'Permission denied' when trying to
        create /data/derived/{project_id}/thumbnails because the parent
        directory didn't have write permissions for non-root users.
        """
        project_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("app.core.storage.get_storage_root", return_value=tmp_path):
            directories = ensure_project_directories(project_id)

        derived_dir = directories["derived"]

        # Simulate what worker does: create thumbnails subdirectory
        thumbnails_dir = derived_dir / "thumbnails"

        # This should NOT raise PermissionError
        try:
            thumbnails_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            pytest.fail(
                f"Worker cannot create thumbnails directory: {e}. "
                "This indicates derived directory permissions are too restrictive."
            )

        assert thumbnails_dir.exists()

    def test_invalid_project_id_raises_error(self, tmp_path: Path):
        """Test that invalid project ID raises ValueError."""
        with patch("app.core.storage.get_storage_root", return_value=tmp_path):
            with pytest.raises(ValueError, match="Invalid project ID"):
                ensure_project_directories("not-a-valid-uuid")

            with pytest.raises(ValueError, match="Invalid project ID"):
                ensure_project_directories("../../../etc/passwd")


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_removes_path_separators(self):
        """Test that path separators are removed."""
        assert "/" not in sanitize_filename("test/file.jpg")
        assert "\\" not in sanitize_filename("test\\file.jpg")

    def test_removes_null_bytes(self):
        """Test that null bytes are removed."""
        assert "\x00" not in sanitize_filename("test\x00file.jpg")

    def test_preserves_extension(self):
        """Test that file extension is preserved."""
        result = sanitize_filename("my file.jpg")
        assert result.endswith(".jpg")

    def test_handles_empty_string(self):
        """Test handling of empty filename."""
        result = sanitize_filename("")
        assert result  # Should return something, not empty


class TestValidateFileType:
    """Tests for file type validation."""

    def test_valid_image_extensions(self):
        """Test that valid image extensions are accepted."""
        assert validate_file_type("photo.jpg", "image")
        assert validate_file_type("photo.jpeg", "image")
        assert validate_file_type("photo.png", "image")
        assert validate_file_type("photo.gif", "image")
        assert validate_file_type("photo.webp", "image")

    def test_valid_video_extensions(self):
        """Test that valid video extensions are accepted."""
        assert validate_file_type("video.mp4", "video")
        assert validate_file_type("video.mov", "video")
        assert validate_file_type("video.avi", "video")
        assert validate_file_type("video.mkv", "video")
        assert validate_file_type("video.webm", "video")

    def test_valid_audio_extensions(self):
        """Test that valid audio extensions are accepted."""
        assert validate_file_type("audio.mp3", "audio")
        assert validate_file_type("audio.wav", "audio")
        assert validate_file_type("audio.flac", "audio")

    def test_invalid_extension_rejected(self):
        """Test that invalid extensions are rejected."""
        assert not validate_file_type("script.exe", "image")
        assert not validate_file_type("document.pdf", "video")
        assert not validate_file_type("malware.sh", "audio")

    def test_case_insensitive(self):
        """Test that extension validation is case-insensitive."""
        assert validate_file_type("PHOTO.JPG", "image")
        assert validate_file_type("Video.MP4", "video")
        assert validate_file_type("AUDIO.MP3", "audio")
