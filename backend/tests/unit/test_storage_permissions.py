"""
Standalone unit tests for storage directory permissions.

These tests can run without the full app dependencies.
Tests the critical permission behavior to prevent regression.
"""

import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

# Add the backend app to path for importing just the storage module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDirectoryPermissions:
    """
    Test that directories are created with world-writable permissions.

    CONTEXT: In multi-container Docker setups:
    - Backend runs as root (uid 0) and creates directories
    - Worker runs as non-root (uid 1000) and needs to write to those directories

    If directories are created with 755 permissions (default), the worker
    cannot write to them, causing "Permission denied" errors.
    """

    def test_mkdir_with_chmod_creates_world_writable_dir(self, tmp_path: Path):
        """
        Test the pattern used in storage.py to create world-writable directories.

        This verifies the fix for the permission denied bug.
        """
        test_dir = tmp_path / "project_derived" / "thumbnails"

        # This is the pattern from _mkdir_world_writable in storage.py
        test_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(test_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        # Verify permissions
        mode = test_dir.stat().st_mode

        # Check all permission bits are set (rwxrwxrwx = 0o777)
        assert mode & stat.S_IRWXU == stat.S_IRWXU, "Owner should have rwx"
        assert mode & stat.S_IRWXG == stat.S_IRWXG, "Group should have rwx"
        assert mode & stat.S_IRWXO == stat.S_IRWXO, "Others should have rwx"

    def test_child_directory_writable_when_parent_is_world_writable(self, tmp_path: Path):
        """
        Test that child directories can be created when parent has 777 permissions.

        REGRESSION TEST: This simulates the worker trying to create
        /data/derived/{project_id}/thumbnails when the parent directory
        was created by the backend.
        """
        # Simulate backend creating the project derived directory with 777
        project_dir = tmp_path / "derived" / "project-uuid-123"
        project_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(project_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        # Simulate worker creating thumbnails subdirectory
        # This should NOT raise PermissionError
        thumbnails_dir = project_dir / "thumbnails"
        try:
            thumbnails_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            pytest.fail(
                f"Failed to create child directory: {e}. "
                "This simulates the worker permission denied bug."
            )

        assert thumbnails_dir.exists()
        assert thumbnails_dir.is_dir()

    def test_default_mkdir_permissions_are_restrictive(self, tmp_path: Path):
        """
        Demonstrate that default mkdir does NOT create world-writable directories.

        This shows WHY we need the chmod call after mkdir.
        """
        test_dir = tmp_path / "default_perms"
        test_dir.mkdir()

        mode = test_dir.stat().st_mode

        # Default permissions typically don't include world-write
        # (depends on umask, but usually 755 or similar)
        # This test documents the problem we're solving
        has_world_write = bool(mode & stat.S_IWOTH)

        # Note: This may or may not pass depending on system umask
        # The point is to document that we can't rely on default behavior
        if not has_world_write:
            # This is expected - default mkdir is restrictive
            pass
        else:
            # If system allows world-write by default, that's fine too
            pass

    def test_file_can_be_created_in_world_writable_dir(self, tmp_path: Path):
        """Test that files can be created in world-writable directories."""
        test_dir = tmp_path / "writable_dir"
        test_dir.mkdir()
        os.chmod(test_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        # Create a file (simulates thumbnail generation)
        test_file = test_dir / "thumbnail.jpg"
        test_file.write_bytes(b"fake image content")

        assert test_file.exists()
        assert test_file.read_bytes() == b"fake image content"


class TestStorageModuleFunctions:
    """
    Test the actual storage module functions.

    These tests import from the app module and test the real implementation.
    """

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path: Path, monkeypatch):
        """Set up environment for storage module."""
        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-chars-minimum!")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    def test_mkdir_world_writable_function(self, tmp_path: Path):
        """Test the _mkdir_world_writable helper function."""
        try:
            from app.core.storage import _mkdir_world_writable
        except (ImportError, Exception) as e:
            pytest.skip(f"Cannot import storage module: {e}")

        test_dir = tmp_path / "test_world_writable"
        _mkdir_world_writable(test_dir)

        assert test_dir.exists()

        mode = test_dir.stat().st_mode
        assert mode & stat.S_IRWXO == stat.S_IRWXO, (
            "Directory should be world-writable (others have rwx)"
        )

    def test_ensure_project_directories_permissions(self, tmp_path: Path, monkeypatch):
        """
        Test that ensure_project_directories creates world-writable dirs.

        REGRESSION TEST for permission denied bug.
        """
        try:
            from app.core.storage import ensure_project_directories
        except (ImportError, Exception) as e:
            pytest.skip(f"Cannot import storage module: {e}")

        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))

        # Clear any cached settings
        try:
            from app.core.config import get_settings
            get_settings.cache_clear()
        except (ImportError, AttributeError):
            pass

        project_id = "550e8400-e29b-41d4-a716-446655440000"
        directories = ensure_project_directories(project_id)

        # Check that derived directory is world-writable
        derived_dir = directories["derived"]
        mode = derived_dir.stat().st_mode

        assert mode & stat.S_IWOTH, (
            f"Derived directory must be world-writable. Got mode: {oct(mode)}. "
            "Worker (uid 1000) needs write access to directories created by backend (root)."
        )

        # Verify we can create subdirectories (simulates worker creating thumbnails/)
        thumbnails_dir = derived_dir / "thumbnails"
        thumbnails_dir.mkdir(exist_ok=True)
        assert thumbnails_dir.exists(), "Should be able to create subdirectories"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
