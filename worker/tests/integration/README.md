# Real Render Pipeline Integration Tests

Production-ready integration tests that validate the entire video render pipeline end-to-end using **real media files** and **real FFmpeg rendering** (no mocks).

## Overview

These tests verify that the render engine correctly processes images, videos, and audio according to the JSON EDL v1 schema. They test:

- ✅ Real FFmpeg execution (no mocks or simulation)
- ✅ Actual output video file generation
- ✅ Video validation using ffprobe (duration, streams, readability)
- ✅ Database-backed workflow with real fixtures
- ✅ File I/O and storage operations

## Requirements

### System Dependencies

- **ffmpeg** - Must be installed and in PATH
- **ffprobe** - Must be installed and in PATH (usually comes with ffmpeg)
- **Python 3.10+** - With all project dependencies installed

### Test Media Assets

Tests require the `VIDEO_TEST_ASSETS` environment variable pointing to a directory with test media files:

```bash
export VIDEO_TEST_ASSETS=/path/to/test/media
```

**Expected directory structure:**

```
$VIDEO_TEST_ASSETS/
├── images/
│   ├── test1.jpg
│   ├── test2.jpg
│   └── test3.jpg
├── videos/
│   ├── test1.mp4
│   └── test2.mp4
└── audio/
    └── audio.mp3
```

**Minimum requirements:**

- **Images:** At least 3 JPG or PNG files (any resolution, recommend 1920x1080+)
- **Videos:** At least 2 MP4 files (H.264, any resolution, 5+ seconds recommended)
- **Audio:** At least 1 MP3 or WAV file (recommend 60+ seconds for repeat tests)

### Generating Test Assets

If you don't have test media, you can generate minimal test assets programmatically:

```bash
# TODO: Create a script to generate test media
python scripts/generate_test_media.py $VIDEO_TEST_ASSETS
```

Or use ffmpeg to create simple test files:

```bash
# Create test images (colored frames)
ffmpeg -f lavfi -i color=c=blue:s=1920x1080:d=1 -frames:v 1 test1.jpg
ffmpeg -f lavfi -i color=c=red:s=1920x1080:d=1 -frames:v 1 test2.jpg
ffmpeg -f lavfi -i color=c=green:s=1920x1080:d=1 -frames:v 1 test3.jpg

# Create test videos (5 seconds each)
ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -pix_fmt yuv420p test1.mp4
ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -pix_fmt yuv420p test2.mp4

# Create test audio (60 seconds, 120 BPM click track)
ffmpeg -f lavfi -i "sine=frequency=1000:duration=60" -ac 2 -ar 44100 audio.mp3
```

## Running Tests

### Run All Integration Tests

```bash
# From project root
cd worker
export VIDEO_TEST_ASSETS=/path/to/test/media
pytest tests/integration/ -v
```

### Run Specific Test

```bash
pytest tests/integration/test_render_real.py::TestRenderRealPipeline::test_render_image_sequence_beat_timing -v
```

### Run with Markers

```bash
# Run all integration tests
pytest -m integration -v

# Skip slow tests
pytest -m "integration and not slow" -v
```

### Auto-Skip if Assets Missing

Tests will automatically skip if `VIDEO_TEST_ASSETS` is not set:

```
SKIPPED [8] worker/tests/utils/media_env.py:48: VIDEO_TEST_ASSETS environment variable not set or directory doesn't exist
```

## Test Scenarios

### TestRenderRealPipeline

Main integration tests validating core render functionality:

#### Test A: Image Sequence with Beat Timing

- **Setup:** 3 images, 8 beats each (4000ms @ 120 BPM), Ken Burns effect
- **Expected:** ~12s duration ±300ms, video + audio streams
- **Validates:** Beat-to-millisecond conversion, Ken Burns effects, audio sync

#### Test B: Mixed Video + Image

- **Setup:** video (5s) → image (4s) → video (5s)
- **Expected:** ~14s duration ±300ms
- **Validates:** Mixed media handling, video trimming, sequence assembly

#### Test C: Repeat Timeline Until Audio End

- **Setup:** 2 images (4s each), repeat mode, 60s audio
- **Expected:** Duration matches audio ±300ms
- **Validates:** Timeline looping, audio-driven duration

#### Test D: Crossfade Transitions

- **Setup:** 3 images with 500ms crossfade
- **Expected:** ~11s duration (overlaps accounted for) ±300ms
- **Validates:** Crossfade rendering, overlap calculations

#### Test E: Beats vs Milliseconds Duration

- **Setup:** One segment with 8 beats @ 120 BPM, one with 4000ms explicit
- **Expected:** Both segments ~4000ms, total ~8s ±300ms
- **Validates:** Duration mode equivalence

### TestRenderEdgeCases

Error handling and edge case tests:

#### Test: Missing Asset

- **Setup:** Create project, delete media file, attempt render
- **Expected:** Graceful failure with FileNotFoundError
- **Validates:** Error handling for missing files

#### Test: Corrupted Media

- **Setup:** Replace media with corrupted data, attempt render
- **Expected:** Graceful failure with FFmpegError
- **Validates:** Error handling for invalid media

#### Test: Timeout (marked @pytest.mark.slow)

- **Setup:** Long-running render with reduced timeout
- **Expected:** FFmpegTimeout error
- **Validates:** Timeout enforcement
- **Note:** Currently skipped (would take too long in CI)

## Validation Criteria

Each test verifies:

1. ✅ **Output exists:** File created at expected path
2. ✅ **Output readable:** `ffprobe` can parse the file
3. ✅ **Duration correct:** Within ±300ms of expected
4. ✅ **Video stream exists:** `ffprobe` shows video stream
5. ✅ **Audio stream exists:** `ffprobe` shows audio stream
6. ✅ **Resolution correct:** Matches PreviewSettings (640x360) or RenderSettings (1920x1080)
7. ✅ **File size > 0:** Non-empty output

## Test Architecture

### Database Fixtures

Tests use **real database fixtures** (not mocks):

- `test_db_engine` - In-memory SQLite database
- `test_db_session` - Clean session per test
- `project_factory` - Factory to create projects with media assets
- `edl_factory` - Factory to create EditRequest JSON

### Storage Isolation

Each test gets isolated temporary storage:

```
tmp_path/storage/
├── uploads/{project_id}/    - Media uploads
├── derived/{project_id}/    - Generated EDL files
└── outputs/{project_id}/    - Rendered videos
```

### Utilities

- `utils/media_env.py` - Asset environment helpers
- `utils/ffprobe.py` - Video validation utilities

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Install ffmpeg
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          cd worker
          pip install -r requirements.txt
          pip install pytest

      - name: Generate test media
        run: |
          mkdir -p /tmp/test_assets/{images,videos,audio}
          # Generate test files with ffmpeg
          ffmpeg -f lavfi -i color=c=blue:s=1920x1080:d=1 -frames:v 1 /tmp/test_assets/images/test1.jpg
          ffmpeg -f lavfi -i color=c=red:s=1920x1080:d=1 -frames:v 1 /tmp/test_assets/images/test2.jpg
          ffmpeg -f lavfi -i color=c=green:s=1920x1080:d=1 -frames:v 1 /tmp/test_assets/images/test3.jpg
          ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -pix_fmt yuv420p /tmp/test_assets/videos/test1.mp4
          ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -pix_fmt yuv420p /tmp/test_assets/videos/test2.mp4
          ffmpeg -f lavfi -i "sine=frequency=1000:duration=60" -ac 2 -ar 44100 /tmp/test_assets/audio/audio.mp3

      - name: Run integration tests
        env:
          VIDEO_TEST_ASSETS: /tmp/test_assets
        run: |
          cd worker
          pytest tests/integration/ -v --tb=short
```

## Troubleshooting

### Tests Skip Automatically

**Problem:** All tests skip with message about VIDEO_TEST_ASSETS

**Solution:** Set the environment variable:
```bash
export VIDEO_TEST_ASSETS=/path/to/test/media
```

### FFmpeg Not Found

**Problem:** Tests fail with "ffmpeg: command not found"

**Solution:** Install ffmpeg:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Verify installation
ffmpeg -version
ffprobe -version
```

### Duration Validation Fails

**Problem:** Tests fail with duration mismatch beyond ±300ms tolerance

**Possible causes:**
- FFmpeg encoding settings producing different durations
- Test audio file is shorter than expected
- BPM calculations are incorrect

**Solution:**
- Check test audio file duration: `ffprobe audio.mp3`
- Verify BPM: 8 beats @ 120 BPM = (8 × 60000) / 120 = 4000ms
- Increase tolerance if consistently off by small amount

### Database Import Errors

**Problem:** Cannot import models from backend

**Solution:** Verify Python path setup in conftest.py includes both worker and backend directories

## Development

### Adding New Tests

1. Create test method in `TestRenderRealPipeline` class
2. Use `project_factory` to create project with media
3. Use `edl_factory` to create EditRequest JSON
4. Save EDL to filesystem and create Timeline record
5. Call `render_video(project_id, job_type="preview")`
6. Validate output with `probe_video()` and `verify_duration()`

### Test Template

```python
def test_my_new_scenario(
    self,
    test_db_session,
    project_factory,
    edl_factory,
    isolated_storage,
):
    """Test description.

    Setup:
        - Describe test setup

    Expected:
        - Describe expected outcome
    """
    with patch.dict(os.environ, {"STORAGE_PATH": str(isolated_storage)}):
        # 1. Create project
        project = project_factory(
            name="Test Name",
            images=["test1.jpg"],
            audio="audio.mp3",
        )

        # 2. Create EDL
        edl = edl_factory(
            project_id=project["id"],
            segments=[...],
            audio_asset_id=project["audio_track"].id,
        )

        # 3. Save EDL and Timeline
        # ... (see existing tests for pattern)

        # 4. Render
        result = render_video(project["id"], job_type="preview")

        # 5. Validate
        output_path = isolated_storage / result["output_path"]
        assert output_path.exists()
        assert verify_duration(output_path, expected_ms=12000)
```

## Success Metrics

- ✅ All 5 core test scenarios pass with real media
- ✅ Tests auto-skip when VIDEO_TEST_ASSETS not available
- ✅ ffprobe validates all output files
- ✅ Duration validation within ±300ms tolerance
- ✅ Tests run in isolation (no shared state)
- ✅ CI/CD ready with programmatic asset generation

## Related Documentation

- [JSON EDL v1 Schema](../../../backend/app/schemas/edit_request.py)
- [Render Task Implementation](../../app/tasks/render.py)
- [Timeline Generation](../../app/tasks/timeline.py)
