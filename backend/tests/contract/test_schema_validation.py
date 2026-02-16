"""Pytest contract tests for EDL v1 JSON Schema.

Tests validate good/bad EDL payloads against edl_schema.json using jsonschema.Draft7Validator.

Run these tests:
    cd backend
    pytest tests/contract/test_schema_validation.py -v --noconftest

The --noconftest flag is needed to avoid loading the parent conftest.py which
has heavy dependencies (FastAPI, SQLAlchemy) that aren't needed for schema validation.
"""
import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = Path(__file__).parent / "edl_schema.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    """Load the EDL v1 JSON schema."""
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def validator(schema) -> jsonschema.Draft7Validator:
    """Create a Draft7Validator instance for the schema."""
    return jsonschema.Draft7Validator(schema)


# =============================================================================
# GOOD PAYLOADS - These must pass validation
# =============================================================================


class TestGoodPayloads:
    """Test cases for valid EDL payloads that must pass schema validation."""

    def test_minimal_payload(self, schema):
        """Minimal valid EDL with just version and single timeline segment."""
        payload = {
            "version": "1.0",
            "timeline": [{"asset_id": "asset_001", "type": "image"}],
        }
        jsonschema.validate(payload, schema)

    def test_audio_beats_duration(self, schema):
        """Segment with beats-based duration."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "duration": {"mode": "beats", "count": 4},
                }
            ],
        }
        jsonschema.validate(payload, schema)

    def test_crossfade_300ms(self, schema):
        """Segment with valid crossfade transition (300ms)."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "transition_in": {"type": "crossfade", "duration_ms": 300},
                }
            ],
        }
        jsonschema.validate(payload, schema)

    def test_duration_null(self, schema):
        """Segment with explicit null duration (uses defaults)."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "duration": None,
                }
            ],
        }
        jsonschema.validate(payload, schema)

    def test_video_with_source_trim(self, schema):
        """Video segment with source trim settings."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "video_001",
                    "type": "video",
                    "source": {"in_ms": 0, "out_ms": 5000},
                }
            ],
        }
        jsonschema.validate(payload, schema)

    def test_cut_transition_zero_duration(self, schema):
        """Cut transition with explicit zero duration."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "transition_in": {"type": "cut", "duration_ms": 0},
                }
            ],
        }
        jsonschema.validate(payload, schema)

    def test_full_payload_with_all_sections(self, schema):
        """Complete payload with all optional sections."""
        payload = {
            "version": "1.0",
            "project_id": "project_123",
            "output": {"width": 1920, "height": 1080, "fps": 30},
            "audio": {"asset_id": "audio_001", "bpm": 120},
            "defaults": {"beats_per_cut": 4, "effect": "slow_zoom_in"},
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "duration": {"mode": "beats", "count": 4},
                    "effect": "pan_left",
                    "transition_in": {"type": "crossfade", "duration_ms": 200},
                },
                {
                    "asset_id": "video_001",
                    "type": "video",
                    "source": {"in_ms": 1000, "out_ms": 5000},
                },
            ],
            "repeat": {"mode": "repeat_all"},
        }
        jsonschema.validate(payload, schema)


# =============================================================================
# BAD PAYLOADS - These must fail validation
# =============================================================================


class TestBadPayloads:
    """Test cases for invalid EDL payloads that must fail schema validation."""

    def test_path_traversal_asset_id(self, schema):
        """Asset ID with path traversal should be rejected by pattern."""
        payload = {
            "version": "1.0",
            "timeline": [{"asset_id": "../../etc/passwd", "type": "image"}],
        }
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        # Verify the error is about the pattern match
        assert "does not match" in str(exc_info.value.message)

    def test_cut_with_nonzero_duration(self, schema):
        """Cut transition with non-zero duration_ms should fail."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "transition_in": {"type": "cut", "duration_ms": 100},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_crossfade_zero_ms(self, schema):
        """Crossfade transition with 0ms duration should fail (minimum 50ms)."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "transition_in": {"type": "crossfade", "duration_ms": 0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_beats_count_zero(self, schema):
        """Beats count of 0 should fail (minimum is 1)."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "duration": {"mode": "beats", "count": 0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_empty_timeline(self, schema):
        """Empty timeline array should fail (minItems: 1)."""
        payload = {"version": "1.0", "timeline": []}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        assert "minItems" in str(exc_info.value.schema) or len(
            exc_info.value.schema_path
        )

    def test_missing_version(self, schema):
        """Missing required 'version' field should fail."""
        payload = {"timeline": [{"asset_id": "asset_001", "type": "image"}]}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        assert "version" in str(exc_info.value.message)

    def test_missing_timeline(self, schema):
        """Missing required 'timeline' field should fail."""
        payload = {"version": "1.0"}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        assert "timeline" in str(exc_info.value.message)

    def test_invalid_version(self, schema):
        """Invalid version value should fail (must be '1.0')."""
        payload = {
            "version": "2.0",
            "timeline": [{"asset_id": "asset_001", "type": "image"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_missing_asset_id_in_segment(self, schema):
        """Segment without required asset_id should fail."""
        payload = {"version": "1.0", "timeline": [{"type": "image"}]}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        assert "asset_id" in str(exc_info.value.message)

    def test_missing_type_in_segment(self, schema):
        """Segment without required type should fail."""
        payload = {"version": "1.0", "timeline": [{"asset_id": "asset_001"}]}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(payload, schema)
        assert "type" in str(exc_info.value.message)

    def test_invalid_segment_type(self, schema):
        """Invalid segment type should fail (must be 'image' or 'video')."""
        payload = {
            "version": "1.0",
            "timeline": [{"asset_id": "asset_001", "type": "audio"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_beats_count_too_high(self, schema):
        """Beats count over maximum (64) should fail."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "duration": {"mode": "beats", "count": 100},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_crossfade_duration_too_long(self, schema):
        """Crossfade duration over maximum (2000ms) should fail."""
        payload = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "asset_001",
                    "type": "image",
                    "transition_in": {"type": "crossfade", "duration_ms": 3000},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_invalid_effect_preset(self, schema):
        """Invalid effect preset should fail."""
        payload = {
            "version": "1.0",
            "timeline": [
                {"asset_id": "asset_001", "type": "image", "effect": "invalid_effect"}
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_asset_id_too_long(self, schema):
        """Asset ID longer than 128 characters should fail."""
        payload = {
            "version": "1.0",
            "timeline": [{"asset_id": "a" * 200, "type": "image"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_asset_id_with_special_chars(self, schema):
        """Asset ID with disallowed special characters should fail."""
        payload = {
            "version": "1.0",
            "timeline": [{"asset_id": "asset@#$%", "type": "image"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)


# =============================================================================
# OPTIONAL: Image with source validation
# =============================================================================


class TestImageSourceValidation:
    """Test cases for image segments with source (optional validation).

    NOTE: These tests will only pass after the schema is updated to include
    the allOf constraint that rejects source on image segments.
    """

    def test_image_with_source_rejected(self, schema):
        """Image segment with source trim should be rejected.

        Images don't have temporal source trim - only videos do.
        This test requires adding the following to TimelineSegment in the schema:

        "allOf": [
          {
            "if": { "properties": { "type": { "const": "image" } } },
            "then": { "properties": { "source": { "type": "null" } } }
          }
        ]
        """
        bad = {
            "version": "1.0",
            "timeline": [
                {
                    "asset_id": "img1",
                    "type": "image",
                    "source": {"in_ms": 0, "out_ms": 1000},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


# =============================================================================
# Test Summary Plugin
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def summary(request):
    """Print a summary of test results after all tests complete."""
    yield
    # Access session stats after tests complete
    session = request.session
    failed = session.testsfailed
    total = session.testscollected
    # Note: pytest doesn't easily expose skipped count in session,
    # so we report total - failed as a conservative "non-failed" count
    non_failed = total - failed
    print(f"\n\n{'=' * 50}")
    print("EDL Schema Validation Summary")
    print(f"{'=' * 50}")
    print(f"PASSED/SKIPPED: {non_failed}")
    print(f"FAILED:         {failed}")
    print(f"TOTAL:          {total}")
    print(f"{'=' * 50}\n")
