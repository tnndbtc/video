# BeatStitch - Risks, Testing & Phase 2 Roadmap

[<- Back to Index](./00-index.md) | [<- Previous](./05-infrastructure.md)

---

## 1. Risk Matrix

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **FFmpeg crashes on malformed input** | High | Medium | Validate with ffprobe; sandbox ffmpeg; timeouts |
| **Disk space exhaustion** | High | Medium | Monitor storage; quotas; auto-cleanup old renders |
| **Memory exhaustion during render** | High | Low | Limit concurrent jobs; memory limits in Docker |
| **Beat detection fails** | Medium | Low | Fallback to librosa; allow manual BPM input |
| **Long renders block workers** | Medium | Medium | Multiple workers; timeouts; priority queues |
| **Malicious file uploads** | High | Low | File type validation; no user-controlled ffmpeg params |
| **Data loss** | Critical | Low | Regular backups; DB transactions; atomic writes |
| **SQLite concurrency issues** | Medium | Medium | Single-writer; consider PostgreSQL for Phase 2 |
| **Too many segments / filtergraph too large** | Medium | Medium | Cap segment count; unique-input strategy; chunked rendering |

---

## 2. Mitigation Implementations

### 2.1 FFmpeg Sandboxing

> **Important**: `resource.setrlimit()` is Linux-only and best-effort in containerized environments (cgroups may override). The primary controls should be:
>
> 1. **Process timeouts** (subprocess timeout parameter)
> 2. **Non-root execution** (worker runs as unprivileged user)
> 3. **Container resource limits** (Docker/cgroups: `cpus`, `mem_limit`)
> 4. **setrlimit as secondary defense** (may not work in all containers)

```python
import os
import subprocess
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class RenderTimeout(Exception):
    pass


class FFmpegError(Exception):
    pass


def run_ffmpeg_sandboxed(
    cmd: List[str],
    timeout: int = 1800,
    memory_limit_gb: int = 4,
) -> tuple[bytes, bytes]:
    """
    Run FFmpeg with resource constraints.

    Primary controls:
    - timeout: Hard timeout via subprocess (always works)
    - Non-root: Worker container runs as non-root user

    Secondary controls (Linux/best-effort):
    - resource.setrlimit for memory/CPU (may be overridden by cgroups)

    Container-level controls (configure in docker-compose):
    - cpus: "2"
    - mem_limit: "4g"
    """

    def set_limits():
        """Set process resource limits (Linux only, best-effort)."""
        try:
            import resource
            # Memory limit (may not work in all container setups)
            mem_bytes = memory_limit_gb * 1024**3
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
        except (ImportError, OSError) as e:
            # resource module not available (non-Linux) or limits failed
            logger.warning(f"Could not set resource limits: {e}")

    # Only use preexec_fn on Unix systems
    preexec = set_limits if os.name == 'posix' else None

    process = subprocess.Popen(
        cmd,
        preexec_fn=preexec,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise RenderTimeout(f"FFmpeg exceeded {timeout}s timeout")

    if process.returncode != 0:
        raise FFmpegError(f"FFmpeg failed (code {process.returncode}): {stderr.decode()}")

    return stdout, stderr
```

### 2.2 Segment Count Limits

To prevent FFmpeg filtergraph issues with very long timelines:

```python
# Maximum segments before requiring chunked rendering
MAX_SEGMENTS_PER_RENDER = 200

# Maximum unique inputs (one per unique asset)
MAX_UNIQUE_INPUTS = 100

def validate_edl_limits(edl: dict) -> List[str]:
    """Validate EDL doesn't exceed FFmpeg limits."""
    errors = []

    segment_count = len(edl.get("segments", []))
    if segment_count > MAX_SEGMENTS_PER_RENDER:
        errors.append(
            f"Too many segments ({segment_count}). "
            f"Maximum supported: {MAX_SEGMENTS_PER_RENDER}. "
            "Consider shorter audio or fewer beats_per_cut."
        )

    # Count unique assets
    unique_assets = set(s["media_asset_id"] for s in edl.get("segments", []))
    if len(unique_assets) > MAX_UNIQUE_INPUTS:
        errors.append(
            f"Too many unique media assets ({len(unique_assets)}). "
            f"Maximum supported: {MAX_UNIQUE_INPUTS}."
        )

    return errors
```

### 2.3 Storage Cleanup

```python
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def cleanup_old_files(storage_path: str):
    """
    Clean up old files across all storage locations.

    Cleanup policy:
    - /data/temp/*: Delete after 1 hour (failed/interrupted renders)
    - /data/outputs/*/preview/*: Delete after 24 hours
    - /data/outputs/*/final/*: Delete after 7 days
    - /data/derived/*/thumbnails/*: Delete if project deleted
    - /data/derived/*/proxies/*: Delete after 7 days (can regenerate)
    """
    base = Path(storage_path)

    # Clean temp directory (stale render intermediates)
    _cleanup_directory(
        base / "temp",
        max_age=timedelta(hours=1),
        recursive=True,
        description="temp files"
    )

    # Clean outputs and derived per-project
    for project_dir in (base / "outputs").iterdir():
        if not project_dir.is_dir():
            continue

        project_id = project_dir.name

        # Clean old previews (24 hours)
        _cleanup_directory(
            project_dir / "preview",
            max_age=timedelta(hours=24),
            description=f"previews for {project_id}"
        )

        # Clean old finals (7 days)
        _cleanup_directory(
            project_dir / "final",
            max_age=timedelta(days=7),
            description=f"finals for {project_id}"
        )

    # Clean derived assets (proxies regeneratable)
    for project_dir in (base / "derived").iterdir():
        if not project_dir.is_dir():
            continue

        project_id = project_dir.name

        # Clean old proxies (7 days, can regenerate)
        _cleanup_directory(
            project_dir / "proxies",
            max_age=timedelta(days=7),
            description=f"proxies for {project_id}"
        )

        # Clean old thumbnails (7 days, can regenerate)
        _cleanup_directory(
            project_dir / "thumbnails",
            max_age=timedelta(days=7),
            description=f"thumbnails for {project_id}"
        )


def _cleanup_directory(
    path: Path,
    max_age: timedelta,
    recursive: bool = False,
    description: str = "files"
):
    """Clean files older than max_age from directory."""
    if not path.exists():
        return

    now = datetime.now()
    cleaned = 0

    pattern = "**/*" if recursive else "*"
    for f in path.glob(pattern):
        if not f.is_file():
            continue

        try:
            age = now - datetime.fromtimestamp(f.stat().st_mtime)
            if age > max_age:
                f.unlink()
                cleaned += 1
        except OSError as e:
            logger.warning(f"Failed to clean {f}: {e}")

    if cleaned:
        logger.info(f"Cleaned {cleaned} old {description}")


def cleanup_deleted_projects(storage_path: str, active_project_ids: set[str]):
    """Remove storage for projects that no longer exist in database."""
    base = Path(storage_path)

    for subdir in ["uploads", "derived", "outputs"]:
        parent = base / subdir
        if not parent.exists():
            continue

        for project_dir in parent.iterdir():
            if project_dir.is_dir() and project_dir.name not in active_project_ids:
                logger.info(f"Cleaning orphaned project storage: {project_dir}")
                import shutil
                shutil.rmtree(project_dir, ignore_errors=True)
```

### 2.4 Media Validation

```python
import subprocess
import json
from typing import Optional


class InvalidMediaError(Exception):
    pass


def validate_media(file_path: str) -> dict:
    """Validate media file with ffprobe before processing."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            raise InvalidMediaError("ffprobe failed to read file")

        probe = json.loads(result.stdout)

        if not probe.get("streams"):
            raise InvalidMediaError("No media streams found")

        return probe

    except subprocess.TimeoutExpired:
        raise InvalidMediaError("Media validation timed out")
    except json.JSONDecodeError:
        raise InvalidMediaError("Invalid ffprobe output")
```

---

## 3. Testing Strategy

### 3.1 Test Categories

| Category | Coverage | Tools |
|----------|----------|-------|
| **Unit** | Beat detection, timeline logic, ffmpeg commands | pytest |
| **Integration** | API endpoints, job queue, database | pytest + TestClient |
| **End-to-End** | Full user workflows | Playwright |

### 3.2 Unit Tests

```python
# tests/worker/test_beat_detection.py
import pytest
from pathlib import Path
from worker.engines.beat_detector import BeatDetector


@pytest.fixture
def detector():
    return BeatDetector()


@pytest.fixture
def output_path(tmp_path):
    return str(tmp_path / "beats.json")


def test_beat_detection_returns_valid_structure(detector, output_path):
    """Test that beat detection returns expected structure."""
    result = detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    # BPM should be within reasonable range
    assert 60 <= result.bpm <= 200, "BPM should be in reasonable range"

    # Beats list should exist and be non-empty
    assert result.beats is not None
    assert len(result.beats) > 0, "Should detect at least some beats"

    # Each beat should have required fields
    for beat in result.beats:
        assert "time_ms" in beat
        assert "beat_number" in beat
        assert "is_downbeat" in beat


def test_beat_times_are_monotonically_increasing(detector, output_path):
    """Test that beat times increase monotonically."""
    result = detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    times = [b["time_ms"] for b in result.beats]
    for i in range(1, len(times)):
        assert times[i] > times[i - 1], f"Beat {i} should be after beat {i-1}"


def test_beat_bpm_within_tolerance(detector, output_path):
    """Test BPM detection accuracy for known-tempo file."""
    result = detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    # Allow 3 BPM tolerance for beat detection
    assert 117 <= result.bpm <= 123, f"Expected ~120 BPM, got {result.bpm}"


def test_beat_number_rules_when_derived(detector, output_path):
    """
    Test beat_number follows 4/4 pattern.

    Note: We derive beat_number synthetically (not from actual downbeat detection)
    so this tests our synthetic assignment, not musical accuracy.
    """
    result = detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    for i, beat in enumerate(result.beats):
        expected_beat_number = (i % 4) + 1
        assert beat["beat_number"] == expected_beat_number, \
            f"Beat {i} should be beat_number {expected_beat_number}"
        assert beat["is_downbeat"] == (expected_beat_number == 1), \
            f"Beat {i} is_downbeat should match beat_number == 1"


def test_beat_detection_fallback_to_librosa(detector, output_path):
    """Test fallback to librosa when madmom unavailable."""
    detector.madmom_available = False  # Force fallback

    result = detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    assert result.analyzer == "librosa"
    assert result.bpm_confidence == 0.7  # librosa default confidence
    assert len(result.beats) > 0


def test_beat_grid_persisted_to_filesystem(detector, output_path):
    """Test that beat grid is saved to specified path."""
    detector.analyze("tests/fixtures/120bpm_track.mp3", output_path)

    assert Path(output_path).exists()

    import json
    with open(output_path) as f:
        data = json.load(f)

    assert "version" in data
    assert "beats" in data
    assert "bpm" in data
```

```python
# tests/worker/test_timeline.py
import pytest
from worker.engines.timeline_builder import TimelineBuilder


class MockMediaAsset:
    def __init__(self, id, media_type, sort_order, duration_ms=None):
        self.id = id
        self.media_type = media_type
        self.sort_order = sort_order
        self.duration_ms = duration_ms


def test_timeline_generation_basic():
    """Test basic timeline generation from beat grid."""
    media = [
        MockMediaAsset(id="1", media_type="image", sort_order=0),
        MockMediaAsset(id="2", media_type="video", duration_ms=10000, sort_order=1),
    ]
    beat_grid = {
        "bpm": 120,
        "beats": [{"time_ms": i * 500, "beat_number": (i % 4) + 1, "is_downbeat": i % 4 == 0}
                  for i in range(16)]  # 8 seconds of beats
    }
    settings = {"beats_per_cut": 4, "output_width": 1920, "output_height": 1080, "output_fps": 30}

    builder = TimelineBuilder(media, beat_grid, settings, audio_duration_ms=8000, project_id="test")
    edl = builder.build()

    assert edl["version"] == "1.0"
    assert len(edl["segments"]) == 4  # 8000ms / (4 beats * 500ms) = 4 segments


def test_timeline_uses_timeline_in_out_ms():
    """Test that segments use timeline_in_ms and timeline_out_ms fields."""
    media = [MockMediaAsset(id="1", media_type="image", sort_order=0)]
    beat_grid = {
        "bpm": 120,
        "beats": [{"time_ms": i * 500, "beat_number": (i % 4) + 1, "is_downbeat": i % 4 == 0}
                  for i in range(8)]
    }
    settings = {"beats_per_cut": 4}

    builder = TimelineBuilder(media, beat_grid, settings, audio_duration_ms=4000, project_id="test")
    edl = builder.build()

    for segment in edl["segments"]:
        assert "timeline_in_ms" in segment
        assert "timeline_out_ms" in segment
        assert "render_duration_ms" in segment
        assert segment["render_duration_ms"] == segment["timeline_out_ms"] - segment["timeline_in_ms"]


def test_timeline_loops_media():
    """Test that single image loops to fill timeline."""
    media = [MockMediaAsset(id="1", media_type="image", sort_order=0)]
    beat_grid = {
        "bpm": 120,
        "beats": [{"time_ms": i * 500, "beat_number": (i % 4) + 1, "is_downbeat": i % 4 == 0}
                  for i in range(12)]
    }
    settings = {"beats_per_cut": 4}

    builder = TimelineBuilder(media, beat_grid, settings, audio_duration_ms=6000, project_id="test")
    edl = builder.build()

    assert len(edl["segments"]) == 3
    # All segments should use the same asset
    assert all(s["media_asset_id"] == "1" for s in edl["segments"])


def test_timeline_no_source_path_in_edl():
    """Test that source_path is NOT stored in EDL (resolved at render time)."""
    media = [MockMediaAsset(id="1", media_type="image", sort_order=0)]
    beat_grid = {"bpm": 120, "beats": [{"time_ms": 0}, {"time_ms": 2000}]}
    settings = {"beats_per_cut": 4}

    builder = TimelineBuilder(media, beat_grid, settings, audio_duration_ms=2000, project_id="test")
    edl = builder.build()

    for segment in edl["segments"]:
        assert "source_path" not in segment
        assert "media_asset_id" in segment  # Uses ID for resolution
```

### 3.3 Integration Tests

```python
# tests/integration/test_full_workflow.py
import pytest
import time
from fastapi.testclient import TestClient


def wait_for_job(client: TestClient, job_id: str, headers: dict, timeout: int = 60) -> dict:
    """Poll job status until complete or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        resp = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        job = resp.json()
        if job["status"] in ("complete", "failed"):
            return job
        time.sleep(1)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def test_full_render_workflow(client: TestClient, auth_headers: dict):
    """
    Test complete workflow: upload -> analyze -> build timeline -> render.

    Key assertions:
    - Audio upload auto-triggers beat analysis (202 returned)
    - Timeline generation is async (202 + job_id)
    - Render request includes edl_hash
    """

    # 1. Create project
    resp = client.post("/api/projects", json={"name": "Test"}, headers=auth_headers)
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    # 2. Upload media
    with open("tests/fixtures/test_image.jpg", "rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/media",
            files={"files": ("test.jpg", f, "image/jpeg")},
            headers=auth_headers
        )
    assert resp.status_code == 201

    # 3. Upload audio (auto-triggers beat analysis job)
    with open("tests/fixtures/test_audio.mp3", "rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/audio",
            files={"file": ("audio.mp3", f, "audio/mpeg")},
            headers=auth_headers
        )
    assert resp.status_code == 202  # Accepted, analysis job started
    analysis_job_id = resp.json()["analysis_job_id"]

    # 4. Wait for beat analysis to complete
    job = wait_for_job(client, analysis_job_id, auth_headers)
    assert job["status"] == "complete", f"Beat analysis failed: {job.get('error_message')}"

    # 5. Generate timeline (async job)
    resp = client.post(
        f"/api/projects/{project_id}/timeline/generate",
        headers=auth_headers
    )
    assert resp.status_code == 202  # Accepted, timeline generation is async
    timeline_job_id = resp.json()["job_id"]

    # 6. Wait for timeline generation
    job = wait_for_job(client, timeline_job_id, auth_headers)
    assert job["status"] == "complete"

    # 7. Get timeline to obtain edl_hash
    resp = client.get(f"/api/projects/{project_id}/timeline", headers=auth_headers)
    assert resp.status_code == 200
    timeline = resp.json()
    edl_hash = timeline["edl_hash"]
    assert edl_hash is not None

    # 8. Render preview (requires edl_hash)
    resp = client.post(
        f"/api/projects/{project_id}/render",
        json={
            "job_type": "preview",
            "edl_hash": edl_hash  # Required for reproducibility
        },
        headers=auth_headers
    )
    assert resp.status_code == 202
    render_job_id = resp.json()["job_id"]

    # 9. Wait for render and verify completion
    job = wait_for_job(client, render_job_id, auth_headers, timeout=120)
    assert job["status"] == "complete", f"Render failed: {job.get('error_message')}"
    assert job["edl_hash"] == edl_hash  # Confirms render used correct EDL

    # 10. Download rendered file
    resp = client.get(
        f"/api/projects/{project_id}/outputs/preview",
        headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert len(resp.content) > 0


def test_audio_upload_triggers_analysis(client: TestClient, auth_headers: dict):
    """Test that audio upload automatically triggers beat analysis."""
    # Create project
    resp = client.post("/api/projects", json={"name": "Test"}, headers=auth_headers)
    project_id = resp.json()["id"]

    # Upload audio
    with open("tests/fixtures/test_audio.mp3", "rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/audio",
            files={"file": ("audio.mp3", f, "audio/mpeg")},
            headers=auth_headers
        )

    # Should return 202 with job_id for auto-triggered analysis
    assert resp.status_code == 202
    data = resp.json()
    assert "analysis_job_id" in data
    assert data["message"] == "Audio uploaded, beat analysis started"


def test_render_requires_edl_hash(client: TestClient, auth_headers: dict):
    """Test that render request without edl_hash is rejected."""
    resp = client.post("/api/projects", json={"name": "Test"}, headers=auth_headers)
    project_id = resp.json()["id"]

    # Attempt render without edl_hash
    resp = client.post(
        f"/api/projects/{project_id}/render",
        json={"job_type": "preview"},  # Missing edl_hash
        headers=auth_headers
    )

    # Should fail with validation error
    assert resp.status_code == 422  # Unprocessable Entity
    assert "edl_hash" in resp.json()["detail"][0]["loc"]


def test_timeline_generation_is_async(client: TestClient, auth_headers: dict):
    """Test that timeline generation returns 202 with job_id."""
    # Setup: create project with media and analyzed audio
    resp = client.post("/api/projects", json={"name": "Test"}, headers=auth_headers)
    project_id = resp.json()["id"]

    # ... (upload media and audio, wait for analysis) ...

    # Generate timeline
    resp = client.post(
        f"/api/projects/{project_id}/timeline/generate",
        headers=auth_headers
    )

    # Should be async
    assert resp.status_code == 202
    assert "job_id" in resp.json()
```

### 3.4 Test Fixtures

```
tests/
+-- conftest.py              # Shared fixtures (client, auth, cleanup)
+-- fixtures/
|   +-- test_image.jpg       # 1920x1080 test image
|   +-- test_video.mp4       # 10s test video
|   +-- test_audio.mp3       # 30s audio file
|   +-- 120bpm_track.mp3     # Known 120 BPM for beat detection tests
|   +-- variable_tempo.mp3   # Variable tempo for edge case testing
+-- unit/
|   +-- test_beat_detection.py
|   +-- test_timeline.py
|   +-- test_ffmpeg_builder.py
+-- integration/
|   +-- test_full_workflow.py
|   +-- test_job_queue.py
|   +-- test_auth.py
+-- e2e/
    +-- test_user_workflows.py
```

---

## 4. Phase 2 Roadmap

### 4.1 Planned Features

| Feature | Description | Complexity | Priority | Est. Time |
|---------|-------------|------------|----------|-----------|
| **Drag-and-drop timeline** | Visual segment reordering with drag handles | High | High | 2-3 weeks |
| **Waveform display** | Audio waveform with beat markers overlay | High | High | 2 weeks |
| **Snap to beat grid** | Snap segment edges to beat markers | Medium | High | 1 week |
| **Per-clip overrides** | Override duration/effect per clip | Medium | Medium | 1 week |
| **Section rules** | Different beats_per_cut for intro/chorus | Medium | Medium | 1-2 weeks |
| **Templates/presets** | Save and reuse project settings | Low | Medium | 3-4 days |
| **Export presets** | YouTube, Instagram, TikTok formats | Low | Medium | 3-4 days |
| **More transitions** | Wipe, slide, zoom transitions | Low | Low | 1 week |
| **Multi-user support** | Separate user data, basic permissions | Medium | Low | 2 weeks |
| **Remote storage** | S3/MinIO support | Medium | Low | 1-2 weeks |

> **Scope Note**: Phase 2 aims for a "simple beat-aware editor" with basic reordering and beat-snap functionality. This is NOT a full non-linear editor (NLE). Complex features like multi-track, nested timelines, or frame-accurate editing are out of scope.

### 4.2 Architecture Changes

**PostgreSQL Migration:**
- Required for multi-user concurrent access
- Better locking and transactions
- Migration via Alembic
- Repository abstraction makes this straightforward

**WebSocket Progress:**
- Replace polling with WebSocket for job progress
- Real-time updates reduce API load
- Consider Socket.io or native WebSocket

**Shared Storage:**
- NFS or MinIO for multi-server deployment
- Required for horizontal scaling of workers

### 4.3 Multi-Server Architecture (Future)

```
+---------------------------------------------------------------------+
|                        Load Balancer                                |
+--------------------------------+------------------------------------+
                                 |
               +-----------------+-----------------+
               v                                   v
+---------------------------+       +---------------------------+
|       App Server 1        |       |       App Server 2        |
+---------------------------+       +---------------------------+
               |                                   |
               +-----------------+-----------------+
                                 v
+---------------------------------------------------------------------+
|  +-------------+  +-------------+  +---------------------------+    |
|  |   Redis     |  |  PostgreSQL |  |     MinIO (Storage)       |    |
|  +-------------+  +-------------+  +---------------------------+    |
+---------------------------------------------------------------------+
                                 |
               +-----------------+-----------------+
               v                                   v
+---------------------------+       +---------------------------+
|       Worker Server 1     |       |       Worker Server 2     |
+---------------------------+       +---------------------------+
```

### 4.4 Phase 2 Timeline (Realistic)

```
Week 1-2:   Waveform display component (canvas rendering, zoom/scroll)
Week 3-4:   Drag-and-drop segment reordering (complex state management)
Week 5:     Snap to beat grid integration
Week 6:     Per-clip duration/effect overrides
Week 7-8:   Section rules (beat variation per section)
Week 9:     Templates/presets system
Week 10:    Export presets (platform-specific encoding)
Week 11-12: Testing, polish, documentation, bug fixes

Total: ~12 weeks for core Phase 2 features
```

> **Complexity Notes**:
> - Drag-and-drop timeline with waveform is the most complex UI work
> - Requires careful state synchronization between visual timeline and EDL
> - Waveform rendering at scale (30+ minute audio) needs virtualization
> - Consider using existing libraries (wavesurfer.js) vs custom implementation

---

## 5. Quick Reference

### 5.1 Make Commands

```bash
make dev        # Start development environment
make prod       # Start production environment
make logs       # View all container logs
make logs-worker # View worker logs only
make migrate    # Run DB migrations
make test       # Run all tests
make test-unit  # Run unit tests only
make test-int   # Run integration tests only
make backup     # Create database backup
make clean      # Clean up temp files and old renders
make shell-api  # Shell into API container
make shell-worker # Shell into worker container
```

### 5.2 Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Main deployment config |
| `docker-compose.dev.yml` | Development overrides |
| `.env` | Environment variables |
| `backend/app/main.py` | FastAPI entry point |
| `worker/app/main.py` | RQ worker entry point |
| `backend/alembic/` | Database migrations |
| `backend/app/repositories/` | Data access layer |

### 5.3 Important Paths

| Path | Contents |
|------|----------|
| `/data/uploads/{project_id}/media/` | Original uploaded images/videos |
| `/data/uploads/{project_id}/audio/` | Original audio tracks |
| `/data/derived/{project_id}/beats.json` | Beat analysis results |
| `/data/derived/{project_id}/edl.json` | Timeline EDL |
| `/data/derived/{project_id}/thumbnails/` | Generated thumbnails |
| `/data/derived/{project_id}/proxies/` | Low-res proxy files |
| `/data/outputs/{project_id}/preview/` | Preview renders |
| `/data/outputs/{project_id}/final/` | Final renders |
| `/data/temp/` | In-progress render intermediates |
| `/db/beatstitch.db` | SQLite database |

### 5.4 Job Types

| Job Type | Triggered By | Duration | Notes |
|----------|--------------|----------|-------|
| `beat_analysis` | Audio upload (auto) | 10-60s | CPU-intensive |
| `timeline_build` | POST /timeline/generate | 1-5s | Light processing |
| `thumbnail_gen` | Media upload (auto) | 2-10s | Per asset |
| `render_preview` | POST /render (preview) | 30s-5min | Low quality |
| `render_final` | POST /render (final) | 2-30min | Full quality |

---

## 6. Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial MVP design |
| 1.1 | 2024-01 | Updated for async job architecture |
| | | - Audio upload auto-triggers analysis |
| | | - Timeline generation is async |
| | | - Render requires edl_hash |
| | | - Added segment count risk |
| | | - Updated sandboxing notes for containers |
| | | - Expanded cleanup to include derived assets |
| | | - Realistic Phase 2 timeline estimates |

---

*End of Architecture Design Documentation*

[<- Back to Index](./00-index.md)
