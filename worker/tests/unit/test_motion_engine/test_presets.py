"""
Unit tests for motion_engine.presets module.
"""

import pytest

from worker.app.tasks.motion_engine.presets import (
    MotionPreset,
    PRESET_LIBRARY,
    get_preset,
    get_preset_for_index,
    list_presets,
)


class TestMotionPreset:
    """Tests for MotionPreset dataclass."""

    def test_preset_creation(self):
        """Test creating a valid preset."""
        preset = MotionPreset(
            name="test_preset",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=0.3,
            pan_start_y=0.4,
            pan_end_x=0.7,
            pan_end_y=0.6,
        )
        assert preset.name == "test_preset"
        assert preset.start_zoom == 1.0
        assert preset.end_zoom == 1.2
        assert preset.easing == "linear"  # default

    def test_preset_validation_valid(self):
        """Test validation passes for valid preset."""
        preset = MotionPreset(
            name="valid",
            start_zoom=1.0,
            end_zoom=1.5,
            pan_start_x=0.0,
            pan_start_y=0.0,
            pan_end_x=1.0,
            pan_end_y=1.0,
            easing="ease_in",
        )
        assert preset.validate() is True

    def test_preset_validation_invalid_zoom(self):
        """Test validation fails for invalid zoom range."""
        preset = MotionPreset(
            name="invalid",
            start_zoom=0.3,  # Too low
            end_zoom=1.2,
            pan_start_x=0.5,
            pan_start_y=0.5,
            pan_end_x=0.5,
            pan_end_y=0.5,
        )
        assert preset.validate() is False

    def test_preset_validation_invalid_pan(self):
        """Test validation fails for out-of-range pan."""
        preset = MotionPreset(
            name="invalid",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=1.5,  # Out of range
            pan_start_y=0.5,
            pan_end_x=0.5,
            pan_end_y=0.5,
        )
        assert preset.validate() is False

    def test_preset_validation_invalid_easing(self):
        """Test validation fails for invalid easing."""
        preset = MotionPreset(
            name="invalid",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=0.5,
            pan_start_y=0.5,
            pan_end_x=0.5,
            pan_end_y=0.5,
            easing="bounce",  # Invalid
        )
        assert preset.validate() is False

    def test_preset_to_dict(self):
        """Test preset serialization to dict."""
        preset = MotionPreset(
            name="test",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=0.3,
            pan_start_y=0.4,
            pan_end_x=0.7,
            pan_end_y=0.6,
            easing="ease_out",
            description="Test description",
        )
        d = preset.to_dict()
        assert d["name"] == "test"
        assert d["start_zoom"] == 1.0
        assert d["easing"] == "ease_out"
        assert d["description"] == "Test description"


class TestPresetLibrary:
    """Tests for PRESET_LIBRARY and related functions."""

    def test_library_not_empty(self):
        """Test that PRESET_LIBRARY has presets."""
        assert len(PRESET_LIBRARY) > 0

    def test_all_presets_valid(self):
        """Test all library presets pass validation."""
        for name, preset in PRESET_LIBRARY.items():
            assert preset.validate(), f"Preset '{name}' failed validation"

    def test_expected_presets_exist(self):
        """Test expected preset names exist in library."""
        expected = [
            "slow_zoom_in",
            "slow_zoom_out",
            "pan_left",
            "pan_right",
            "diagonal_push",
            "subtle_drift",
        ]
        for name in expected:
            assert name in PRESET_LIBRARY, f"Missing preset: {name}"

    def test_get_preset_found(self):
        """Test get_preset returns preset when found."""
        preset = get_preset("slow_zoom_in")
        assert preset is not None
        assert preset.name == "slow_zoom_in"

    def test_get_preset_not_found(self):
        """Test get_preset returns None for unknown preset."""
        assert get_preset("nonexistent") is None

    def test_list_presets(self):
        """Test list_presets returns all preset names."""
        names = list_presets()
        assert len(names) == len(PRESET_LIBRARY)
        assert "slow_zoom_in" in names

    def test_get_preset_for_index_cycles(self):
        """Test get_preset_for_index cycles through presets."""
        num_presets = len(PRESET_LIBRARY)

        # Get presets for indices 0 through 2*num_presets
        presets = [get_preset_for_index(i) for i in range(num_presets * 2)]

        # First half should equal second half (cycling)
        for i in range(num_presets):
            assert presets[i].name == presets[i + num_presets].name


class TestPresetProperties:
    """Tests for specific preset properties."""

    def test_slow_zoom_in_zooms_in(self):
        """Test slow_zoom_in increases zoom."""
        preset = PRESET_LIBRARY["slow_zoom_in"]
        assert preset.end_zoom > preset.start_zoom

    def test_slow_zoom_out_zooms_out(self):
        """Test slow_zoom_out decreases zoom."""
        preset = PRESET_LIBRARY["slow_zoom_out"]
        assert preset.end_zoom < preset.start_zoom

    def test_pan_left_moves_left_to_right(self):
        """Test pan_left moves from left to right."""
        preset = PRESET_LIBRARY["pan_left"]
        # Start at left (0.0), end at right (1.0)
        assert preset.pan_start_x < preset.pan_end_x

    def test_pan_right_moves_right_to_left(self):
        """Test pan_right moves from right to left."""
        preset = PRESET_LIBRARY["pan_right"]
        # Start at right (1.0), end at left (0.0)
        assert preset.pan_start_x > preset.pan_end_x

    def test_diagonal_push_moves_diagonally(self):
        """Test diagonal_push moves both x and y."""
        preset = PRESET_LIBRARY["diagonal_push"]
        # Should move in both x and y directions
        assert preset.pan_start_x != preset.pan_end_x
        assert preset.pan_start_y != preset.pan_end_y
