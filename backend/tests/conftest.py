"""
Shared test fixtures for BeatStitch Backend tests.

Provides:
- Test database (SQLite in-memory)
- Test client (FastAPI TestClient)
- Authenticated client (with JWT token)
- Test user factory
- Test project factory
- Sample media files (small test images/audio)
- Mock Redis/RQ for worker tests
"""

import asyncio
import io
import json
import os
import struct
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-purposes-only-32chars"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Create a temporary directory for test storage
_test_storage_dir = tempfile.mkdtemp(prefix="beatstitch_test_")
os.environ["STORAGE_PATH"] = _test_storage_dir

from app.core.database import Base
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.audio import AudioTrack
from app.models.job import RenderJob
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.timeline import Timeline
from app.models.user import User


# =============================================================================
# Test Database Configuration
# =============================================================================

# Create test engine with in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for testing.

    Creates all tables before the test and drops them after.
    Each test gets a fresh database.
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override database dependency for testing."""
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# =============================================================================
# Mock Redis/Queue Fixtures
# =============================================================================


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    """Mock Redis connection for tests."""
    mock = MagicMock()
    mock.hgetall.return_value = {}
    mock.hset.return_value = True
    mock.expire.return_value = True
    mock.delete.return_value = 1
    mock.pipeline.return_value = MagicMock(
        hset=MagicMock(return_value=mock),
        expire=MagicMock(return_value=mock),
        execute=MagicMock(return_value=[True, True]),
    )

    with patch("app.core.redis.get_redis_connection", return_value=mock):
        with patch("app.core.queue.get_redis_connection", return_value=mock):
            yield mock


@pytest.fixture
def mock_rq_job() -> Generator[MagicMock, None, None]:
    """Mock RQ Job for tests."""
    mock_job = MagicMock()
    mock_job.id = f"test_job_{uuid.uuid4().hex[:8]}"
    mock_job.get_status.return_value = "queued"
    mock_job.is_finished = False
    mock_job.is_failed = False
    mock_job.result = None
    mock_job.exc_info = None
    mock_job.enqueued_at = datetime.utcnow()
    mock_job.started_at = None
    mock_job.ended_at = None

    with patch("app.core.queue.Queue") as mock_queue_class:
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job
        mock_queue_class.return_value = mock_queue
        yield mock_job


@pytest.fixture
def mock_job_status() -> Generator[MagicMock, None, None]:
    """Mock get_job_status function."""
    with patch("app.core.queue.get_job_status") as mock:
        mock.return_value = None  # Default: no existing job
        yield mock


@pytest.fixture
def mock_enqueue_beat_analysis(mock_rq_job: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock beat analysis job enqueueing."""
    with patch("app.api.audio.enqueue_beat_analysis") as mock:
        mock.return_value = mock_rq_job
        yield mock


@pytest.fixture
def mock_enqueue_timeline_generation(mock_rq_job: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock timeline generation job enqueueing."""
    with patch("app.api.timeline.enqueue_timeline_generation") as mock:
        mock.return_value = mock_rq_job
        yield mock


@pytest.fixture
def mock_enqueue_render(mock_rq_job: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock render job enqueueing."""
    with patch("app.api.render.enqueue_render_preview") as mock_preview:
        with patch("app.api.render.enqueue_render_final") as mock_final:
            mock_preview.return_value = mock_rq_job
            mock_final.return_value = mock_rq_job
            yield mock_rq_job


# =============================================================================
# Test Client Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def async_client(
    test_db: AsyncSession,
    mock_redis: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP client for testing the FastAPI application.

    Overrides the database dependency to use the test database.
    """
    from app.api.deps import get_db
    from app.core.database import get_async_session

    # Override database dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_session] = override_get_db

    # Create tables for the test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()

    # Drop tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# =============================================================================
# User Fixtures
# =============================================================================


@pytest.fixture
def test_user_data() -> dict:
    """Provide test user data."""
    return {
        "username": f"testuser_{uuid.uuid4().hex[:8]}",
        "password": "TestPassword123!",
    }


@pytest_asyncio.fixture
async def test_user(async_client: AsyncClient, test_user_data: dict) -> dict:
    """
    Create a test user and return user data with ID.

    Returns dict with id, username, password, and access_token.
    """
    # Register user
    response = await async_client.post(
        "/api/auth/register",
        json={
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        },
    )
    assert response.status_code == 201, f"Failed to create user: {response.text}"
    user_data = response.json()

    # Login to get token
    response = await async_client.post(
        "/api/auth/login",
        json={
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        },
    )
    assert response.status_code == 200, f"Failed to login: {response.text}"
    login_data = response.json()

    return {
        "id": user_data["id"],
        "username": test_user_data["username"],
        "password": test_user_data["password"],
        "access_token": login_data["access_token"],
    }


@pytest.fixture
def auth_headers(test_user: dict) -> dict:
    """Provide authentication headers for the test user."""
    return {"Authorization": f"Bearer {test_user['access_token']}"}


@pytest_asyncio.fixture
async def second_test_user(async_client: AsyncClient) -> dict:
    """
    Create a second test user for authorization tests.

    Returns dict with id, username, password, and access_token.
    """
    username = f"seconduser_{uuid.uuid4().hex[:8]}"
    password = "SecondPassword123!"

    # Register user
    response = await async_client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    user_data = response.json()

    # Login to get token
    response = await async_client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    login_data = response.json()

    return {
        "id": user_data["id"],
        "username": username,
        "password": password,
        "access_token": login_data["access_token"],
    }


@pytest.fixture
def second_auth_headers(second_test_user: dict) -> dict:
    """Provide authentication headers for the second test user."""
    return {"Authorization": f"Bearer {second_test_user['access_token']}"}


# =============================================================================
# Project Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def test_project(
    async_client: AsyncClient,
    auth_headers: dict,
) -> dict:
    """
    Create a test project and return project data.
    """
    response = await async_client.post(
        "/api/projects",
        json={"name": f"Test Project {uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert response.status_code == 201, f"Failed to create project: {response.text}"
    return response.json()


@pytest_asyncio.fixture
async def test_project_with_media(
    async_client: AsyncClient,
    auth_headers: dict,
    test_project: dict,
    sample_image: bytes,
) -> dict:
    """
    Create a test project with uploaded media and return project data.
    """
    # Upload media
    files = {"files": ("test_image.jpg", sample_image, "image/jpeg")}
    response = await async_client.post(
        f"/api/projects/{test_project['id']}/media",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 201, f"Failed to upload media: {response.text}"

    # Get updated project
    response = await async_client.get(
        f"/api/projects/{test_project['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    return response.json()


# =============================================================================
# Sample File Fixtures
# =============================================================================


@pytest.fixture
def sample_image() -> bytes:
    """
    Create a minimal valid JPEG image for testing.

    This is a 1x1 pixel red JPEG image.
    """
    # Minimal valid JPEG (1x1 red pixel)
    jpeg_data = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xBA, 0xDE, 0xBF,
        0xFF, 0xD9
    ])
    return jpeg_data


@pytest.fixture
def sample_png() -> bytes:
    """
    Create a minimal valid PNG image for testing.

    This is a 1x1 pixel red PNG image.
    """
    # Minimal valid PNG (1x1 red pixel)
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk start
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # Width=1, Height=1
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # Bit depth, color type, etc.
        0xDE,                                            # IHDR CRC
        0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41, 0x54,  # IDAT chunk start
        0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00, 0x00,  # Compressed data
        0x01, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D, 0xB4,  # CRC
        0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND chunk
        0xAE, 0x42, 0x60, 0x82                           # IEND CRC
    ])
    return png_data


@pytest.fixture
def sample_audio() -> bytes:
    """
    Create a minimal valid WAV audio file for testing.

    This creates a 0.1 second silent WAV file at 44100Hz mono.
    """
    sample_rate = 44100
    duration = 0.1  # seconds
    num_samples = int(sample_rate * duration)

    # Create silent audio data (all zeros)
    audio_data = b'\x00\x00' * num_samples

    # WAV file structure
    wav_data = io.BytesIO()

    # RIFF header
    wav_data.write(b'RIFF')
    wav_data.write(struct.pack('<I', 36 + len(audio_data)))  # File size - 8
    wav_data.write(b'WAVE')

    # fmt chunk
    wav_data.write(b'fmt ')
    wav_data.write(struct.pack('<I', 16))  # Chunk size
    wav_data.write(struct.pack('<H', 1))   # Audio format (PCM)
    wav_data.write(struct.pack('<H', 1))   # Number of channels
    wav_data.write(struct.pack('<I', sample_rate))  # Sample rate
    wav_data.write(struct.pack('<I', sample_rate * 2))  # Byte rate
    wav_data.write(struct.pack('<H', 2))   # Block align
    wav_data.write(struct.pack('<H', 16))  # Bits per sample

    # data chunk
    wav_data.write(b'data')
    wav_data.write(struct.pack('<I', len(audio_data)))
    wav_data.write(audio_data)

    return wav_data.getvalue()


@pytest.fixture
def sample_mp3() -> bytes:
    """
    Create minimal MP3 header bytes for testing.

    Note: This is not a complete playable MP3, but it has valid MP3 headers
    that should pass basic file type validation.
    """
    # MP3 frame header + minimal frame data
    # Frame sync: 0xFF 0xFB (MPEG Audio Layer 3)
    # Bitrate: 128kbps, Sample rate: 44100Hz, Stereo
    mp3_header = bytes([
        0xFF, 0xFB, 0x90, 0x00,  # Frame header
        0x00, 0x00, 0x00, 0x00,  # Padding
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
    ] * 10)  # Multiple frames to make it look more realistic

    return mp3_header


@pytest.fixture
def sample_video_mp4() -> bytes:
    """
    Create minimal MP4 file bytes for testing.

    Note: This is a minimal ftyp box that identifies as MP4.
    """
    # Minimal MP4 with ftyp box
    mp4_data = bytes([
        0x00, 0x00, 0x00, 0x18,  # Box size (24 bytes)
        0x66, 0x74, 0x79, 0x70,  # 'ftyp' box type
        0x69, 0x73, 0x6F, 0x6D,  # 'isom' brand
        0x00, 0x00, 0x00, 0x00,  # Version
        0x69, 0x73, 0x6F, 0x6D,  # 'isom' compatible brand
        0x61, 0x76, 0x63, 0x31,  # 'avc1' compatible brand
    ])
    return mp4_data


@pytest.fixture
def invalid_file() -> bytes:
    """Create invalid file content for testing rejection."""
    return b"This is not a valid media file content"


@pytest.fixture
def large_file() -> bytes:
    """Create a file that exceeds size limits for testing."""
    # Create a 1MB file (adjust as needed based on your limits)
    return b"x" * (1024 * 1024)


# =============================================================================
# Test Storage Fixtures
# =============================================================================


@pytest.fixture
def test_storage_dir() -> Generator[Path, None, None]:
    """Provide a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory(prefix="beatstitch_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def setup_test_storage(test_storage_dir: Path) -> Generator[None, None, None]:
    """Set up test storage directory for each test."""
    # Create necessary subdirectories
    (test_storage_dir / "uploads").mkdir(exist_ok=True)
    (test_storage_dir / "derived").mkdir(exist_ok=True)
    (test_storage_dir / "outputs").mkdir(exist_ok=True)

    # Patch the storage root
    with patch("app.core.storage.get_storage_root", return_value=test_storage_dir):
        with patch("app.core.storage.STORAGE_ROOT", test_storage_dir):
            yield


# =============================================================================
# Helper Functions
# =============================================================================


def create_test_beats_json(bpm: float = 120.0, beat_count: int = 100) -> dict:
    """Create mock beats.json content for testing."""
    beats = []
    ms_per_beat = 60000 / bpm

    for i in range(beat_count):
        beats.append({
            "time_ms": int(i * ms_per_beat),
            "beat_number": (i % 4) + 1,
            "is_downbeat": (i % 4) == 0,
        })

    return {
        "bpm": bpm,
        "time_signature": "4/4",
        "beats": beats,
    }


def create_test_edl_json(
    segments: list[dict] = None,
    total_duration_ms: int = 30000,
) -> dict:
    """Create mock EDL JSON content for testing."""
    if segments is None:
        segments = [
            {
                "index": 0,
                "media_asset_id": str(uuid.uuid4()),
                "media_type": "image",
                "timeline_in_ms": 0,
                "timeline_out_ms": 10000,
                "render_duration_ms": 10000,
                "source_in_ms": 0,
                "source_out_ms": 0,
                "effects": {"ken_burns": {"start": "center", "end": "center", "zoom_factor": 1.1}},
                "transition_in": {"type": "cut", "duration_ms": 0},
            },
            {
                "index": 1,
                "media_asset_id": str(uuid.uuid4()),
                "media_type": "image",
                "timeline_in_ms": 10000,
                "timeline_out_ms": 20000,
                "render_duration_ms": 10000,
                "source_in_ms": 0,
                "source_out_ms": 0,
                "effects": None,
                "transition_in": {"type": "crossfade", "duration_ms": 500},
            },
        ]

    return {
        "version": "1.0",
        "total_duration_ms": total_duration_ms,
        "segments": segments,
    }


async def create_user_directly(
    db: AsyncSession,
    username: str = None,
    password: str = "TestPassword123!",
) -> User:
    """Create a user directly in the database."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"

    user = User(
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def create_project_directly(
    db: AsyncSession,
    user: User,
    name: str = None,
) -> Project:
    """Create a project directly in the database."""
    if name is None:
        name = f"Test Project {uuid.uuid4().hex[:8]}"

    project = Project(
        owner_id=user.id,
        name=name,
        status="draft",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def create_media_asset_directly(
    db: AsyncSession,
    project: Project,
    media_type: str = "image",
    processing_status: str = "ready",
    filename: str = None,
) -> MediaAsset:
    """Create a media asset directly in the database."""
    if filename is None:
        filename = f"test_{uuid.uuid4().hex[:8]}.jpg"

    asset = MediaAsset(
        project_id=project.id,
        filename=filename,
        original_filename=filename,
        file_path=f"uploads/{project.id}/media/{filename}",
        file_size=1024,
        mime_type="image/jpeg" if media_type == "image" else "video/mp4",
        media_type=media_type,
        processing_status=processing_status,
        sort_order=0,
        width=1920,
        height=1080,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


async def create_audio_track_directly(
    db: AsyncSession,
    project: Project,
    analysis_status: str = "complete",
    bpm: float = 120.0,
    beat_count: int = 100,
) -> AudioTrack:
    """Create an audio track directly in the database."""
    audio = AudioTrack(
        project_id=project.id,
        filename=f"audio_{uuid.uuid4().hex[:8]}.mp3",
        original_filename="test_audio.mp3",
        file_path=f"uploads/{project.id}/audio/test_audio.mp3",
        file_size=1024 * 100,
        duration_ms=30000,
        sample_rate=44100,
        analysis_status=analysis_status,
        bpm=bpm if analysis_status == "complete" else None,
        beat_count=beat_count if analysis_status == "complete" else None,
        beat_grid_path=f"derived/{project.id}/beats.json" if analysis_status == "complete" else None,
    )
    db.add(audio)
    await db.flush()
    await db.refresh(audio)
    return audio


async def create_timeline_directly(
    db: AsyncSession,
    project: Project,
    edl_hash: str = None,
    segment_count: int = 5,
    total_duration_ms: int = 30000,
) -> Timeline:
    """Create a timeline directly in the database."""
    if edl_hash is None:
        edl_hash = uuid.uuid4().hex

    timeline = Timeline(
        project_id=project.id,
        edl_path=f"derived/{project.id}/edl.json",
        total_duration_ms=total_duration_ms,
        segment_count=segment_count,
        edl_hash=edl_hash,
    )
    db.add(timeline)
    await db.flush()
    await db.refresh(timeline)
    return timeline


async def create_render_job_directly(
    db: AsyncSession,
    project: Project,
    edl_hash: str,
    job_type: str = "preview",
    status: str = "complete",
    output_path: str = None,
) -> RenderJob:
    """Create a render job directly in the database."""
    render_job = RenderJob(
        project_id=project.id,
        job_type=job_type,
        edl_hash=edl_hash,
        render_settings_json="{}",
        status=status,
        output_path=output_path,
    )
    db.add(render_job)
    await db.flush()
    await db.refresh(render_job)
    return render_job
