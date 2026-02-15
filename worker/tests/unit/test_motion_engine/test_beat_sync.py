"""
Unit tests for motion_engine.beat_sync module.
"""

import json
import os
import tempfile

import pytest

from worker.app.tasks.motion_engine.beat_sync import (
    load_beat_grid,
    get_beat_frames,
    build_beat_pulse_expression,
    build_beat_sync_zoom_expr,
    calculate_bpm_from_beats,
)


class TestLoadBeatGrid:
    """Tests for beat grid loading."""

    def test_load_valid_beat_grid(self):
        """Test loading a valid beat grid file."""
        beat_grid = {
            "bpm": 120.0,
            "beats": [0.5, 1.0, 1.5, 2.0],
            "downbeats": [0.5, 2.5],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(beat_grid, f)
            temp_path = f.name

        try:
            loaded = load_beat_grid(temp_path)
            assert loaded is not None
            assert loaded["bpm"] == 120.0
            assert len(loaded["beats"]) == 4
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file returns None."""
        result = load_beat_grid("/nonexistent/path/beats.json")
        assert result is None

    def test_load_invalid_json(self):
        """Test loading invalid JSON returns None."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {")
            temp_path = f.name

        try:
            result = load_beat_grid(temp_path)
            assert result is None
        finally:
            os.unlink(temp_path)


class TestGetBeatFrames:
    """Tests for beat time to frame conversion."""

    def test_beats_within_clip(self):
        """Test converting beats that fall within clip range."""
        beat_times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        clip_start = 1.0
        clip_duration = 1.5
        fps = 30

        frames = get_beat_frames(beat_times, clip_start, clip_duration, fps)

        # Beats at 1.0, 1.5, 2.0 should be in range [1.0, 2.5)
        assert len(frames) == 3
        # 1.0 - 1.0 = 0.0 -> frame 0
        assert 0 in frames
        # 1.5 - 1.0 = 0.5 -> frame 15
        assert 15 in frames
        # 2.0 - 1.0 = 1.0 -> frame 30
        assert 30 in frames

    def test_no_beats_in_clip(self):
        """Test when no beats fall within clip range."""
        beat_times = [0.0, 0.5]
        clip_start = 5.0
        clip_duration = 2.0
        fps = 30

        frames = get_beat_frames(beat_times, clip_start, clip_duration, fps)
        assert len(frames) == 0

    def test_beat_at_clip_boundary(self):
        """Test beat exactly at clip start is included."""
        beat_times = [1.0, 2.0]
        clip_start = 1.0
        clip_duration = 0.5
        fps = 30

        frames = get_beat_frames(beat_times, clip_start, clip_duration, fps)
        # Beat at 1.0 should be included (frame 0)
        assert 0 in frames
        # Beat at 2.0 should not be included (outside range)
        assert 30 not in frames

    def test_beat_at_clip_end_excluded(self):
        """Test beat exactly at clip end is excluded."""
        beat_times = [1.0, 1.5]
        clip_start = 0.0
        clip_duration = 1.0
        fps = 30

        frames = get_beat_frames(beat_times, clip_start, clip_duration, fps)
        # Beat at 1.0 should be excluded (end of range)
        assert len(frames) == 0


class TestBuildBeatPulseExpression:
    """Tests for beat pulse expression building."""

    def test_empty_beats(self):
        """Test empty beat list returns '0'."""
        expr = build_beat_pulse_expression([])
        assert expr == "0"

    def test_single_beat(self):
        """Test single beat expression."""
        expr = build_beat_pulse_expression([30], pulse_amplitude=0.05, decay_frames=6)

        # Should contain between() check
        assert "between(on,30,36)" in expr
        # Should contain amplitude
        assert "0.05" in expr
        # Should contain exponential decay
        assert "exp(" in expr

    def test_multiple_beats(self):
        """Test multiple beat expression has all beats."""
        beats = [0, 30, 60]
        expr = build_beat_pulse_expression(beats, pulse_amplitude=0.05, decay_frames=6)

        # Should contain all beats
        assert "between(on,0,6)" in expr
        assert "between(on,30,36)" in expr
        assert "between(on,60,66)" in expr
        # Should be summed with +
        assert "+" in expr

    def test_custom_amplitude(self):
        """Test custom pulse amplitude."""
        expr = build_beat_pulse_expression([30], pulse_amplitude=0.1, decay_frames=6)
        assert "0.1" in expr

    def test_custom_decay(self):
        """Test custom decay frames."""
        expr = build_beat_pulse_expression([30], pulse_amplitude=0.05, decay_frames=10)
        assert "between(on,30,40)" in expr


class TestBuildBeatSyncZoomExpr:
    """Tests for complete beat sync zoom expression building."""

    def create_beat_grid_file(self, beat_grid):
        """Helper to create a temporary beat grid file."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(beat_grid, f)
        f.close()
        return f.name

    def test_mode_none_returns_none(self):
        """Test mode='none' returns None."""
        expr = build_beat_sync_zoom_expr(
            beat_grid_path="/fake/path.json",
            clip_start_sec=0.0,
            clip_duration_sec=4.0,
            fps=30,
            mode="none",
        )
        assert expr is None

    def test_missing_beat_grid_returns_none(self):
        """Test missing beat grid returns None."""
        expr = build_beat_sync_zoom_expr(
            beat_grid_path="/nonexistent/beats.json",
            clip_start_sec=0.0,
            clip_duration_sec=4.0,
            fps=30,
            mode="downbeat",
        )
        assert expr is None

    def test_downbeat_mode(self):
        """Test downbeat mode uses downbeats."""
        beat_grid = {
            "bpm": 120.0,
            "beats": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            "downbeats": [0.0, 2.0],
        }
        temp_path = self.create_beat_grid_file(beat_grid)

        try:
            expr = build_beat_sync_zoom_expr(
                beat_grid_path=temp_path,
                clip_start_sec=0.0,
                clip_duration_sec=4.0,
                fps=30,
                mode="downbeat",
            )

            assert expr is not None
            # Should have pulses for beats at 0.0 and 2.0
            # Frame 0 (beat at 0.0)
            assert "between(on,0," in expr
            # Frame 60 (beat at 2.0)
            assert "between(on,60," in expr
        finally:
            os.unlink(temp_path)

    def test_every_n_beats_mode(self):
        """Test every_n_beats mode selects every Nth beat."""
        beat_grid = {
            "bpm": 120.0,
            "beats": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            "downbeats": [0.0, 2.0],
        }
        temp_path = self.create_beat_grid_file(beat_grid)

        try:
            expr = build_beat_sync_zoom_expr(
                beat_grid_path=temp_path,
                clip_start_sec=0.0,
                clip_duration_sec=4.0,
                fps=30,
                mode="every_n_beats",
                beat_n=2,  # Every 2nd beat: 0.0, 1.0, 2.0, 3.0
            )

            assert expr is not None
        finally:
            os.unlink(temp_path)

    def test_no_beats_in_clip_returns_none(self):
        """Test returns None when no beats fall in clip range."""
        beat_grid = {
            "bpm": 120.0,
            "beats": [0.0, 0.5, 1.0],
            "downbeats": [0.0],
        }
        temp_path = self.create_beat_grid_file(beat_grid)

        try:
            expr = build_beat_sync_zoom_expr(
                beat_grid_path=temp_path,
                clip_start_sec=10.0,  # Far beyond beat times
                clip_duration_sec=4.0,
                fps=30,
                mode="downbeat",
            )

            assert expr is None
        finally:
            os.unlink(temp_path)


class TestCalculateBpmFromBeats:
    """Tests for BPM calculation from beat times."""

    def test_calculate_bpm(self):
        """Test BPM calculation from evenly spaced beats."""
        # Beats at 0.5 second intervals = 120 BPM
        beat_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        bpm = calculate_bpm_from_beats(beat_times)
        assert bpm is not None
        assert abs(bpm - 120.0) < 0.01

    def test_not_enough_beats(self):
        """Test returns None with less than 2 beats."""
        assert calculate_bpm_from_beats([]) is None
        assert calculate_bpm_from_beats([1.0]) is None

    def test_two_beats(self):
        """Test BPM from exactly 2 beats."""
        beat_times = [0.0, 0.6]  # 0.6 second interval = 100 BPM
        bpm = calculate_bpm_from_beats(beat_times)
        assert bpm is not None
        assert abs(bpm - 100.0) < 0.01
