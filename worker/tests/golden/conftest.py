"""
Fixtures for golden render tests.

Provides:
- golden_dir: Path to the golden test directory
- temp_output_dir: Temporary directory for render output (cleaned up after test)
- test_assets_path: Path to assets/ directory
- mock_asset_resolver: Callable that maps asset_id to test asset paths
- test_audio_path: Path to test_audio.wav file
"""
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable

import pytest

# Add worker directory to path for imports
# This allows 'from app.tasks.render import ...' to work
WORKER_DIR = Path(__file__).parent.parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))


GOLDEN_DIR = Path(__file__).parent


@pytest.fixture
def golden_dir() -> Path:
    """Path to the golden test directory."""
    return GOLDEN_DIR


@pytest.fixture
def test_assets_path() -> Path:
    """Path to the assets/ directory containing test media files."""
    return GOLDEN_DIR / "assets"


@pytest.fixture
def test_audio_path(test_assets_path: Path) -> Path:
    """Path to the test_audio.wav file."""
    audio_path = test_assets_path / "test_audio.wav"
    if not audio_path.exists():
        pytest.skip(f"Test audio not found: {audio_path}")
    return audio_path


@pytest.fixture
def temp_output_dir():
    """
    Temporary directory for render output.

    Cleaned up automatically after each test.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="golden_render_"))
    yield temp_dir
    # Cleanup after test
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def mock_asset_resolver(test_assets_path: Path) -> Callable[[str], str]:
    """
    Factory that creates an asset path resolver for test assets.

    Maps asset_id to actual file paths in the test assets directory:
    - "test_image_001" -> assets/test_image_001.png
    - "test_image_002" -> assets/test_image_002.png
    - etc.
    """
    def resolver(asset_id: str) -> str:
        # Try common image extensions
        for ext in [".png", ".jpg", ".jpeg"]:
            path = test_assets_path / f"{asset_id}{ext}"
            if path.exists():
                return str(path)

        # If not found, raise error
        raise ValueError(f"Test asset not found: {asset_id}")

    return resolver


@pytest.fixture
def ffmpeg_available() -> bool:
    """
    Check if FFmpeg is available in the environment.

    Returns True if ffmpeg command exists, False otherwise.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def require_ffmpeg(ffmpeg_available: bool):
    """Skip test if FFmpeg is not available."""
    if not ffmpeg_available:
        pytest.skip("FFmpeg not available - run in Docker container")
