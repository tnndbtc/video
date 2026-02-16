"""
Unit tests for EditRequest validator.

Tests validation logic for EditRequest (EDL v1) schemas including:
- Asset existence validation
- Asset type matching
- BPM availability for beat-based durations
- Duration range validation
- Source trim validation for videos
- Transition duration warnings
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.schemas.edit_request import (
    EditRequest,
    EditRequestValidationResult,
    TimelineSegment,
    DurationBeats,
    DurationMs,
    DurationNatural,
    AudioSettings,
    DefaultSettings,
    SourceTrim,
    Transition,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_media_asset(
    asset_id: str,
    media_type: str = "image",
    duration_ms: int = None,
    processing_status: str = "ready",
):
    """Create a mock MediaAsset object."""
    mock = MagicMock()
    mock.id = asset_id
    mock.media_type = media_type
    mock.duration_ms = duration_ms
    mock.processing_status = processing_status
    return mock


def create_mock_audio_track(
    asset_id: str,
    bpm: float = None,
    duration_ms: int = 180000,
    analysis_status: str = "complete",
    analysis_error: str = None,
):
    """Create a mock AudioTrack object."""
    mock = MagicMock()
    mock.id = asset_id
    mock.bpm = bpm
    mock.duration_ms = duration_ms
    mock.analysis_status = analysis_status
    mock.analysis_error = analysis_error
    return mock


# =============================================================================
# Pydantic Model Tests
# =============================================================================


class TestEditRequestModel:
    """Test EditRequest Pydantic model validation."""

    def test_minimal_valid_request(self):
        """Test that minimal EditRequest is valid."""
        request = EditRequest(
            timeline=[
                TimelineSegment(asset_id="img_001", type="image")
            ]
        )
        assert request.version == "1.0"
        assert len(request.timeline) == 1
        assert request.defaults.beats_per_cut == 8

    def test_full_request(self):
        """Test EditRequest with all fields populated."""
        request = EditRequest(
            version="1.0",
            project_id="test-project",
            audio=AudioSettings(asset_id="audio_001", bpm=120.0),
            defaults=DefaultSettings(
                beats_per_cut=4,
                transition=Transition(type="crossfade", duration_ms=300),
                effect="slow_zoom_in"
            ),
            timeline=[
                TimelineSegment(
                    asset_id="img_001",
                    type="image",
                    duration=DurationBeats(count=8),
                    effect="pan_left",
                    transition_in=Transition(type="crossfade", duration_ms=300),
                ),
                TimelineSegment(
                    asset_id="vid_001",
                    type="video",
                    duration=DurationMs(value=5000),
                    source=SourceTrim(in_ms=1000, out_ms=6000),
                ),
            ],
        )
        assert request.audio.bpm == 120.0
        assert request.timeline[0].duration.count == 8
        assert request.timeline[1].source.in_ms == 1000

    def test_invalid_beats_count_too_low(self):
        """Test that beats count < 1 is rejected."""
        with pytest.raises(ValueError):
            DurationBeats(count=0)

    def test_invalid_beats_count_too_high(self):
        """Test that beats count > 64 is rejected."""
        with pytest.raises(ValueError):
            DurationBeats(count=65)

    def test_invalid_ms_duration_too_low(self):
        """Test that ms duration < 250 is rejected."""
        with pytest.raises(ValueError):
            DurationMs(value=100)

    def test_invalid_ms_duration_too_high(self):
        """Test that ms duration > 60000 is rejected."""
        with pytest.raises(ValueError):
            DurationMs(value=70000)

    def test_empty_timeline_rejected(self):
        """Test that empty timeline is rejected."""
        with pytest.raises(ValueError):
            EditRequest(timeline=[])

    def test_transition_duration_max(self):
        """Test that transition duration > 2000 is rejected."""
        with pytest.raises(ValueError):
            Transition(type="crossfade", duration_ms=3000)


# =============================================================================
# Validator Service Tests
# =============================================================================


class TestEditRequestValidator:
    """Test EditRequestValidator service."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_media_cache(self):
        """Create mock media assets cache."""
        return {
            "img_001": create_mock_media_asset("img_001", "image"),
            "img_002": create_mock_media_asset("img_002", "image"),
            "vid_001": create_mock_media_asset("vid_001", "video", duration_ms=30000),
        }

    @pytest.fixture
    def mock_audio_cache(self):
        """Create mock audio tracks cache."""
        return {
            "audio_001": create_mock_audio_track("audio_001", bpm=120.0),
        }

    @pytest.mark.asyncio
    async def test_valid_simple_request(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test validation of a simple valid request."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(asset_id="img_001", type="image"),
                TimelineSegment(asset_id="img_002", type="image"),
            ]
        )

        # Mock _prefetch_assets to use our caches
        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is True
        assert len(result.errors) == 0
        assert result.computed is not None
        assert result.computed.segment_count == 2
        assert result.computed.effective_bpm == 120.0

    @pytest.mark.asyncio
    async def test_asset_not_found_error(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that missing asset produces error."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache  # img_003 not in cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(asset_id="img_003", type="image"),  # Not found
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "asset_not_found"
        assert "img_003" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_asset_type_mismatch_error(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that asset type mismatch produces error."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(asset_id="img_001", type="video"),  # Wrong type
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "asset_type_mismatch"

    @pytest.mark.asyncio
    async def test_bpm_required_for_beats_duration(self, mock_db, mock_media_cache):
        """Test that BPM is required for beats-based duration."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = {}  # No audio

        request = EditRequest(
            timeline=[
                TimelineSegment(
                    asset_id="img_001",
                    type="image",
                    duration=DurationBeats(count=8),  # Needs BPM
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert any(e.code == "bpm_required" for e in result.errors)

    @pytest.mark.asyncio
    async def test_audio_not_found_error(self, mock_db, mock_media_cache):
        """Test that missing audio asset produces error."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = {}  # audio_001 not in cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),  # Not found
            timeline=[
                TimelineSegment(asset_id="img_001", type="image"),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert any(e.code == "asset_not_found" for e in result.errors)

    @pytest.mark.asyncio
    async def test_source_trim_invalid_out_less_than_in(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that source out_ms <= in_ms produces error."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(
                    asset_id="vid_001",
                    type="video",
                    source=SourceTrim(in_ms=5000, out_ms=3000),  # Invalid
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert any(e.code == "source_trim_invalid" for e in result.errors)

    @pytest.mark.asyncio
    async def test_source_trim_exceeds_video_duration(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that source trim exceeding video duration produces error."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(
                    asset_id="vid_001",
                    type="video",
                    source=SourceTrim(in_ms=0, out_ms=50000),  # Exceeds 30000
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is False
        assert any(e.code == "source_trim_invalid" for e in result.errors)

    @pytest.mark.asyncio
    async def test_transition_too_long_warning(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that long transition produces warning."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            defaults=DefaultSettings(beats_per_cut=1),  # Short segment (500ms at 120bpm)
            timeline=[
                TimelineSegment(
                    asset_id="img_001",
                    type="image",
                    duration=DurationBeats(count=1),  # 500ms at 120bpm
                    transition_in=Transition(type="crossfade", duration_ms=500),  # 100% of segment
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is True  # Warnings don't block
        assert any(w.code == "transition_too_long" for w in result.warnings)

    @pytest.mark.asyncio
    async def test_natural_duration_for_video(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test natural duration mode for videos."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001"),
            timeline=[
                TimelineSegment(
                    asset_id="vid_001",
                    type="video",
                    duration=DurationNatural(),
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is True
        # Video duration is 30000ms
        assert result.computed.total_duration_ms == 30000

    @pytest.mark.asyncio
    async def test_computed_info_calculation(self, mock_db, mock_media_cache, mock_audio_cache):
        """Test that computed info is correctly calculated."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)
        validator._media_cache = mock_media_cache
        validator._audio_cache = mock_audio_cache

        request = EditRequest(
            audio=AudioSettings(asset_id="audio_001", end_at_audio_end=True),
            timeline=[
                TimelineSegment(
                    asset_id="img_001",
                    type="image",
                    duration=DurationMs(value=5000),
                ),
                TimelineSegment(
                    asset_id="img_002",
                    type="image",
                    duration=DurationMs(value=5000),
                ),
            ]
        )

        with patch.object(validator, '_prefetch_assets', new_callable=AsyncMock):
            result = await validator.validate(request, "test-project")

        assert result.valid is True
        assert result.computed.total_duration_ms == 10000
        assert result.computed.segment_count == 2
        assert result.computed.effective_bpm == 120.0
        assert result.computed.audio_duration_ms == 180000
        # loop_count = ceil(180000 / 10000) = 18
        assert result.computed.loop_count == 18

    @pytest.mark.asyncio
    async def test_edl_hash_computation(self, mock_db):
        """Test EDL hash is computed correctly."""
        from app.services.edit_request_validator import EditRequestValidator

        validator = EditRequestValidator(mock_db)

        request = EditRequest(
            timeline=[
                TimelineSegment(asset_id="img_001", type="image"),
            ]
        )

        hash1 = await validator.compute_edl_hash(request)
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex digest

        # Same request should produce same hash
        hash2 = await validator.compute_edl_hash(request)
        assert hash1 == hash2

        # Different request should produce different hash
        request2 = EditRequest(
            timeline=[
                TimelineSegment(asset_id="img_002", type="image"),
            ]
        )
        hash3 = await validator.compute_edl_hash(request2)
        assert hash1 != hash3


# =============================================================================
# Duration Calculation Tests
# =============================================================================


class TestDurationCalculation:
    """Test duration calculation logic."""

    def test_beats_to_ms_calculation(self):
        """Test beats to milliseconds conversion."""
        # At 120 BPM: 1 beat = 500ms
        # 8 beats = 4000ms
        bpm = 120.0
        beats = 8
        expected_ms = int(beats * (60000 / bpm))
        assert expected_ms == 4000

    def test_beats_to_ms_at_different_bpm(self):
        """Test beats to ms at various BPM values."""
        test_cases = [
            (60, 4, 4000),    # 60 BPM, 4 beats = 4000ms
            (120, 8, 4000),  # 120 BPM, 8 beats = 4000ms
            (128, 8, 3750),  # 128 BPM, 8 beats = 3750ms
            (140, 4, 1714),  # 140 BPM, 4 beats ≈ 1714ms
        ]

        for bpm, beats, expected_ms in test_cases:
            actual_ms = int(beats * (60000 / bpm))
            assert actual_ms == expected_ms, f"BPM={bpm}, beats={beats}"
