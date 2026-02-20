"""Environment variable and asset management for integration tests.

Provides utilities to:
- Locate test media assets via VIDEO_TEST_ASSETS environment variable
- Skip tests if assets are not available
- Validate asset directory structure
- Create isolated storage layouts for tests
"""

import os
from pathlib import Path
from typing import Optional

import pytest


def get_video_test_assets_path() -> Optional[Path]:
    """Get the VIDEO_TEST_ASSETS path from environment.

    Returns:
        Path to test assets directory, or None if not set
    """
    assets_path = os.environ.get("VIDEO_TEST_ASSETS")
    if not assets_path:
        return None

    path = Path(assets_path)
    if not path.exists():
        return None

    return path


def get_asset_path(asset_type: str, filename: str) -> Path:
    """Get path to a specific test asset.

    Args:
        asset_type: One of "images", "videos", or "audio"
        filename: Name of the asset file

    Returns:
        Path to the asset file

    Raises:
        RuntimeError: If VIDEO_TEST_ASSETS not set
        FileNotFoundError: If asset file doesn't exist
    """
    assets_root = get_video_test_assets_path()
    if not assets_root:
        raise RuntimeError(
            "VIDEO_TEST_ASSETS environment variable not set. "
            "Please set it to the path of your test media directory."
        )

    asset_path = assets_root / asset_type / filename
    if not asset_path.exists():
        raise FileNotFoundError(
            f"Asset not found: {asset_path}\n"
            f"Expected structure: $VIDEO_TEST_ASSETS/{asset_type}/{filename}"
        )

    return asset_path


def skip_if_assets_missing():
    """Pytest decorator to skip or fail tests if VIDEO_TEST_ASSETS not available.

    Behaviour depends on environment:
    - Assets present → no-op (tests run normally)
    - Assets missing + CI (CI=true or GITHUB_ACTIONS=true) → each test calls
      pytest.fail() so the missing-assets problem is never silently hidden
    - Assets missing + not CI → pytest.mark.skipif skip with instructions

    Usage:
        @skip_if_assets_missing()
        def test_something():
            ...

        @skip_if_assets_missing()
        class TestSomething:
            def test_foo(self): ...
    """
    import functools

    assets_path = get_video_test_assets_path()
    is_ci = (
        os.environ.get("CI", "").lower() == "true"
        or os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    )
    RUN_CMD = "./scripts/run_integration_render_real.sh"

    if assets_path is not None:
        def _noop(cls_or_fn):
            return cls_or_fn
        return _noop

    skip_msg = (
        f"VIDEO_TEST_ASSETS not set or directory missing. "
        f"Run: {RUN_CMD}"
    )
    fail_msg = (
        f"[CI] VIDEO_TEST_ASSETS not set. "
        f"Run: bash {RUN_CMD}"
    )

    if is_ci:
        def _ci_fail_decorator(cls_or_fn):
            if isinstance(cls_or_fn, type):
                # Wrap every test method on the class
                for name in list(vars(cls_or_fn)):
                    if name.startswith("test") and callable(getattr(cls_or_fn, name)):
                        orig = getattr(cls_or_fn, name)

                        @functools.wraps(orig)
                        def _fail(*a, _m=fail_msg, **kw):
                            pytest.fail(_m)

                        setattr(cls_or_fn, name, _fail)
                return cls_or_fn

            @functools.wraps(cls_or_fn)
            def _wrap(*a, **kw):
                pytest.fail(fail_msg)

            return _wrap

        return _ci_fail_decorator
    else:
        return pytest.mark.skipif(True, reason=skip_msg)


def list_available_assets() -> dict[str, list[Path]]:
    """Scan VIDEO_TEST_ASSETS and return categorized list of available assets.

    Returns:
        Dictionary with keys "images", "videos", "audio" containing lists of Path objects

    Raises:
        RuntimeError: If VIDEO_TEST_ASSETS not set
    """
    assets_root = get_video_test_assets_path()
    if not assets_root:
        raise RuntimeError("VIDEO_TEST_ASSETS environment variable not set")

    result = {
        "images": [],
        "videos": [],
        "audio": []
    }

    for asset_type in result.keys():
        type_dir = assets_root / asset_type
        if type_dir.exists() and type_dir.is_dir():
            result[asset_type] = sorted(type_dir.iterdir())

    return result


def validate_asset_structure() -> list[str]:
    """Validate that VIDEO_TEST_ASSETS has the expected directory structure.

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    assets_root = get_video_test_assets_path()
    if not assets_root:
        errors.append("VIDEO_TEST_ASSETS environment variable not set")
        return errors

    if not assets_root.is_dir():
        errors.append(f"VIDEO_TEST_ASSETS path is not a directory: {assets_root}")
        return errors

    # Check for expected subdirectories
    for subdir in ["images", "videos", "audio"]:
        subdir_path = assets_root / subdir
        if not subdir_path.exists():
            errors.append(f"Missing subdirectory: {subdir_path}")
        elif not subdir_path.is_dir():
            errors.append(f"Expected directory but found file: {subdir_path}")

    # Check for at least some files in each directory
    assets = list_available_assets()
    for asset_type, files in assets.items():
        if not files:
            errors.append(f"No files found in {asset_type}/ directory")

    return errors


def create_test_storage_layout(project_id: str, base_path: Path) -> dict[str, Path]:
    """Create isolated storage directory structure for a test project.

    Creates the standard storage layout:
        base_path/
            uploads/{project_id}/
            derived/{project_id}/
            outputs/{project_id}/

    Args:
        project_id: Unique project identifier
        base_path: Root path for storage (typically pytest's tmp_path)

    Returns:
        Dictionary with keys "uploads", "derived", "outputs" containing Path objects
    """
    layout = {
        "uploads": base_path / "uploads" / project_id,
        "derived": base_path / "derived" / project_id,
        "outputs": base_path / "outputs" / project_id,
    }

    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)

    return layout
