"""
Root conftest for worker tests.

Sets up Python path to allow 'from app.tasks...' imports.
Provides database fixtures for integration tests.
"""
import json
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ============================================================================
# STEP 1: Mock dependencies FIRST (before adding to sys.path)
# ============================================================================

from types import ModuleType
from unittest.mock import MagicMock

def create_mock_module(name):
    """Create a mock module that can have submodules."""
    module = ModuleType(name)
    module.__dict__.update({
        '__builtins__': __builtins__,
        '__file__': f'<mock {name}>',
        '__package__': name,
        '__path__': [],
    })
    # Add MagicMock for any attribute access
    module.__getattr__ = lambda key: MagicMock()
    return module

# Pre-populate sys.modules with mock modules to avoid import errors
# This must happen BEFORE adding worker/backend to sys.path
MOCK_MODULES = [
    # Web framework dependencies
    'redis',
    'redis.asyncio',
    'redis.exceptions',
    'rq',
    'rq.job',
    'fastapi',
    'fastapi.responses',
    'fastapi.security',
    'starlette',
    'starlette.middleware',
    'starlette.middleware.base',
    'starlette.responses',
    'starlette.requests',
    'starlette.routing',
    'slowapi',
    'slowapi.util',
    'jose',
    'jose.jwt',
    'passlib',
    'passlib.context',
    # Media processing dependencies
    'PIL',
    'PIL.Image',
    'PIL.ExifTags',
    'pydub',
    'pydub.audio_segment',
    'librosa',
    'numpy',
    # Database dependencies (mock psycopg2 to avoid PostgreSQL connection attempts)
    'psycopg2',
    'psycopg2.extensions',
]

for module_name in MOCK_MODULES:
    if module_name not in sys.modules:
        sys.modules[module_name] = create_mock_module(module_name)

# ============================================================================
# STEP 2: Add WORKER directory to sys.path (but NOT backend)
# ============================================================================

WORKER_DIR = Path(__file__).parent.parent.resolve()
BACKEND_DIR = WORKER_DIR.parent / "backend"

if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

# DON'T add backend to sys.path to avoid app package conflicts
# Instead, import backend models directly using importlib

# ============================================================================
# STEP 3: Import backend models (temporarily adding BACKEND to sys.path)
# ============================================================================

# Temporarily add backend to sys.path so backend models can import from app.core
import importlib.util

sys.path.insert(0, str(BACKEND_DIR))

try:
    # Import backend's app.core.database for Base class
    from app.core.database import Base as BackendBase

    # Import backend models
    from app.models.user import User
    from app.models.project import Project
    from app.models.media import MediaAsset
    from app.models.audio import AudioTrack
    from app.models.timeline import Timeline
    from app.models.job import RenderJob

finally:
    # Remove backend from sys.path to avoid conflicts with worker's app
    sys.path.remove(str(BACKEND_DIR))

    # Also remove backend's 'app' from sys.modules if it was cached
    if 'app' in sys.modules:
        backend_app = sys.modules.pop('app')


# ============================================================================
# STEP 4: Set default STORAGE_PATH before importing worker modules
# ============================================================================

# Set a writable default storage path before importing modules that read it
import tempfile
_default_storage = Path(tempfile.mkdtemp(prefix="pytest_storage_"))
os.environ['STORAGE_PATH'] = str(_default_storage)

# ============================================================================
# STEP 5: Now import worker modules normally (worker's app is in sys.path)
# ============================================================================

from app.tasks.render import render_video, Base as WorkerBase, RenderJob as WorkerRenderJob
from app.tasks.ffmpeg_runner import FFmpegError

# ============================================================================
# Module-level exports (accessible from tests via autouse fixtures)
# ============================================================================

# Store references for use in fixtures
_TIMELINE_CLASS = Timeline
_RENDER_VIDEO_FUNC = render_video
_FFMPEG_ERROR_CLASS = FFmpegError

@pytest.fixture(scope="session", autouse=True)
def setup_test_imports():
    """Make backend models and worker functions available to all tests."""
    # Store in pytest's namespace for easy access
    import builtins
    builtins.Timeline = Timeline
    builtins.render_video = render_video
    builtins.FFmpegError = FFmpegError
    yield
    # Clean up
    if hasattr(builtins, 'Timeline'):
        del builtins.Timeline
    if hasattr(builtins, 'render_video'):
        del builtins.render_video
    if hasattr(builtins, 'FFmpegError'):
        del builtins.FFmpegError

# Import test utilities (relative import since we're in tests package)
from .utils.media_env import (
    create_test_storage_layout,
    get_asset_path,
    get_video_test_assets_path,
    skip_if_assets_missing,
)


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def test_db_engine():
    """Create in-memory SQLite engine for tests.

    Each test gets a fresh database with all tables created.
    Uses SQLite for fast, isolated testing.
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True for SQL debugging
    )

    # Create all tables from both backend and worker models
    BackendBase.metadata.create_all(engine)
    WorkerBase.metadata.create_all(engine)

    yield engine

    # Cleanup
    engine.dispose()


@pytest.fixture
def test_db_session(test_db_engine, monkeypatch):
    """Provide database session with automatic rollback.

    Each test gets a clean session. Changes are rolled back after the test
    to ensure test isolation (though with in-memory DB this is redundant).

    Also patches app.db.get_db_session to use this test session.
    """
    # CRITICAL: Reset cached global engine and session factory
    # These are cached in app.db module and must be cleared for each test
    import app.db
    app.db._engine = None
    app.db._SessionLocal = None

    SessionLocal = sessionmaker(bind=test_db_engine)
    session = SessionLocal()

    # Patch get_db_session to yield the test session
    from contextlib import contextmanager

    @contextmanager
    def mock_get_db_session():
        yield session

    # Patch both the function and the engine getter
    monkeypatch.setattr('app.db.get_db_session', mock_get_db_session)
    monkeypatch.setattr('app.db.get_engine', lambda: test_db_engine)

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        # Reset again after test to avoid pollution
        app.db._engine = None
        app.db._SessionLocal = None


@pytest.fixture(scope="session")
def test_assets_env():
    """Get VIDEO_TEST_ASSETS path from environment or skip.

    Returns:
        Path to test assets directory

    Raises:
        pytest.skip: If VIDEO_TEST_ASSETS not set or invalid
    """
    assets_path = get_video_test_assets_path()
    if not assets_path:
        pytest.skip("VIDEO_TEST_ASSETS environment variable not set or directory doesn't exist")

    return assets_path


@pytest.fixture
def isolated_storage(tmp_path):
    """Create isolated storage directory for each test.

    Creates temporary directory with structure:
        tmp_path/
            uploads/
            derived/
            outputs/

    Returns:
        Path to isolated storage root
    """
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    # Create standard subdirectories
    (storage_root / "uploads").mkdir()
    (storage_root / "derived").mkdir()
    (storage_root / "outputs").mkdir()

    return storage_root


# ============================================================================
# Project Factory Fixtures
# ============================================================================


@pytest.fixture
def project_factory(test_db_session: Session, test_assets_env: Path, isolated_storage: Path):
    """Factory to create projects with real media in test database.

    Usage:
        project = project_factory(
            name="Test Project",
            images=["test1.jpg", "test2.jpg"],
            videos=["test3.mp4"],
            audio="audio.mp3",
            bpm=120.0,
            beats_per_cut=8,
        )

    Args:
        name: Project name
        images: List of image filenames from VIDEO_TEST_ASSETS/images/
        videos: List of video filenames from VIDEO_TEST_ASSETS/videos/
        audio: Audio filename from VIDEO_TEST_ASSETS/audio/
        bpm: Beats per minute for audio
        beats_per_cut: Number of beats between cuts
        transition_type: Transition type (cut, crossfade)
        transition_duration_ms: Transition duration in milliseconds
        ken_burns_enabled: Whether to enable Ken Burns effect

    Returns:
        Dictionary with project metadata:
            - id: Project UUID
            - owner_id: User UUID
            - media_assets: List of MediaAsset objects
            - audio_track: AudioTrack object (if audio provided)
            - storage: Dict with paths (uploads, derived, outputs)
    """

    def _create(
        name: str,
        images: List[str] = None,
        videos: List[str] = None,
        audio: str = None,
        bpm: float = 120.0,
        beats_per_cut: int = 8,
        transition_type: str = "cut",
        transition_duration_ms: int = 500,
        ken_burns_enabled: bool = True,
    ) -> Dict:
        images = images or []
        videos = videos or []

        # 1. Create test user
        user = User(
            id=str(uuid.uuid4()),
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            password_hash="test_hash",
            created_at=datetime.utcnow(),
        )
        test_db_session.add(user)
        test_db_session.flush()

        # 2. Create project
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            owner_id=user.id,
            name=name,
            beats_per_cut=beats_per_cut,
            transition_type=transition_type,
            transition_duration_ms=transition_duration_ms,
            ken_burns_enabled=ken_burns_enabled,
            output_width=1920,
            output_height=1080,
            output_fps=30,
            status="ready",
            created_at=datetime.utcnow(),
        )
        test_db_session.add(project)
        test_db_session.flush()

        # 3. Create storage layout
        storage = create_test_storage_layout(project_id, isolated_storage)

        # 4. Create media assets
        media_assets = []
        sort_order = 0

        # Process images
        for img_filename in images:
            # Copy file from test assets to isolated storage
            src_path = get_asset_path("images", img_filename)
            asset_id = str(uuid.uuid4())
            stored_filename = f"{asset_id}{src_path.suffix}"
            dst_path = storage["uploads"] / stored_filename

            shutil.copy2(src_path, dst_path)

            # Get image dimensions (use a simple approach - assume 1920x1080 for tests)
            # In production, this would be extracted via PIL/ffprobe
            width, height = 1920, 1080

            # Create database record
            asset = MediaAsset(
                id=asset_id,
                project_id=project_id,
                filename=stored_filename,
                original_filename=img_filename,
                file_path=str(dst_path.relative_to(isolated_storage)),
                file_size=dst_path.stat().st_size,
                mime_type="image/jpeg",
                media_type="image",
                processing_status="ready",
                width=width,
                height=height,
                sort_order=sort_order,
                created_at=datetime.utcnow(),
            )
            test_db_session.add(asset)
            media_assets.append(asset)
            sort_order += 1

        # Process videos
        for vid_filename in videos:
            # Copy file from test assets to isolated storage
            src_path = get_asset_path("videos", vid_filename)
            asset_id = str(uuid.uuid4())
            stored_filename = f"{asset_id}{src_path.suffix}"
            dst_path = storage["uploads"] / stored_filename

            shutil.copy2(src_path, dst_path)

            # Get video metadata (assume 1920x1080, 5000ms, 30fps for tests)
            # In production, this would be extracted via ffprobe
            width, height = 1920, 1080
            duration_ms = 5000
            fps = 30.0

            # Create database record
            asset = MediaAsset(
                id=asset_id,
                project_id=project_id,
                filename=stored_filename,
                original_filename=vid_filename,
                file_path=str(dst_path.relative_to(isolated_storage)),
                file_size=dst_path.stat().st_size,
                mime_type="video/mp4",
                media_type="video",
                processing_status="ready",
                width=width,
                height=height,
                duration_ms=duration_ms,
                fps=fps,
                sort_order=sort_order,
                created_at=datetime.utcnow(),
            )
            test_db_session.add(asset)
            media_assets.append(asset)
            sort_order += 1

        # 5. Create audio track (if provided)
        audio_track = None
        if audio:
            # Copy audio file
            src_path = get_asset_path("audio", audio)
            audio_id = str(uuid.uuid4())
            stored_filename = f"{audio_id}{src_path.suffix}"
            dst_path = storage["uploads"] / stored_filename

            shutil.copy2(src_path, dst_path)

            # Assume audio duration (would be extracted via ffprobe in production)
            duration_ms = 60000  # 60 seconds default

            # Create database record
            audio_track = AudioTrack(
                id=audio_id,
                project_id=project_id,
                filename=stored_filename,
                original_filename=audio,
                file_path=str(dst_path.relative_to(isolated_storage)),
                file_size=dst_path.stat().st_size,
                duration_ms=duration_ms,
                sample_rate=44100,
                bpm=bpm,
                beat_count=int((duration_ms / 1000) * (bpm / 60)),
                analysis_status="complete",
                analyzed_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            test_db_session.add(audio_track)

        # Commit all changes
        test_db_session.commit()

        return {
            "id": project_id,
            "owner_id": user.id,
            "project": project,
            "media_assets": media_assets,
            "audio_track": audio_track,
            "storage": storage,
        }

    return _create


@pytest.fixture
def edl_factory():
    """Factory to create EDL JSON matching EditRequest v1 schema.

    Usage:
        edl = edl_factory(
            project_id="proj_123",
            segments=[
                {"asset_id": "img_1", "type": "image", "duration": {"mode": "beats", "count": 8}},
                {"asset_id": "img_2", "type": "image", "duration": {"mode": "ms", "value": 4000}},
            ],
            audio_asset_id="audio_1",
            bpm=120.0,
        )

    Returns:
        Dictionary conforming to EditRequest v1 schema
    """

    def _create(
        project_id: str,
        segments: List[Dict],
        audio_asset_id: str = None,
        bpm: float = 120.0,
        beats_per_cut: int = 8,
        transition_type: str = "cut",
        transition_duration_ms: int = 0,
        effect: str = None,
        repeat_mode: str = "repeat_all",
        output_settings: Dict = None,
    ) -> Dict:
        # Default output settings
        if output_settings is None:
            output_settings = {
                "width": 640,  # Use preview settings for faster tests
                "height": 360,
                "fps": 24,
            }

        # Build EDL
        edl = {
            "version": "1.0",
            "project_id": project_id,
            "output": output_settings,
            "defaults": {
                "beats_per_cut": beats_per_cut,
                "transition": {
                    "type": transition_type,
                    "duration_ms": transition_duration_ms,
                },
            },
            "timeline": segments,
            "repeat": {
                "mode": repeat_mode,
                "fill_behavior": "black",
            },
        }

        # Add audio settings if provided
        if audio_asset_id:
            edl["audio"] = {
                "asset_id": audio_asset_id,
                "bpm": bpm,
                "start_offset_ms": 0,
                "end_at_audio_end": True,
                "trim_end_ms": 0,
            }

        # Add default effect if provided
        if effect:
            edl["defaults"]["effect"] = effect

        return edl

    return _create
