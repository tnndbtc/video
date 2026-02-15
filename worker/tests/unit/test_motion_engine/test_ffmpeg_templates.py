"""
Unit tests for motion_engine.ffmpeg_templates module.
"""

import pytest

from worker.app.tasks.motion_engine.ffmpeg_templates import (
    RenderConfig,
    build_zoom_expression,
    build_pan_x_expression,
    build_pan_y_expression,
    build_motion_filter,
    build_render_command,
    build_simple_scale_command,
)
from worker.app.tasks.motion_engine.presets import MotionPreset, PRESET_LIBRARY


class TestRenderConfig:
    """Tests for RenderConfig dataclass."""

    def test_default_values(self):
        """Test RenderConfig default values."""
        config = RenderConfig()
        assert config.width == 1920
        assert config.height == 1080
        assert config.fps == 30
        assert config.crf == 20
        assert config.preset == "medium"
        assert config.pix_fmt == "yuv420p"

    def test_custom_values(self):
        """Test RenderConfig with custom values."""
        config = RenderConfig(
            width=640,
            height=360,
            fps=24,
            crf=32,
            preset="ultrafast",
        )
        assert config.width == 640
        assert config.fps == 24
        assert config.preset == "ultrafast"


class TestZoomExpression:
    """Tests for zoom expression building."""

    def test_linear_zoom_expression(self):
        """Test linear zoom expression format."""
        preset = MotionPreset(
            name="test",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=0.5,
            pan_start_y=0.5,
            pan_end_x=0.5,
            pan_end_y=0.5,
            easing="linear",
        )
        expr = build_zoom_expression(preset, total_frames=120)

        # Should contain if(eq(on,1)... for frame 0 check
        assert "if(eq(on,1)" in expr
        # Should contain start zoom value
        assert "1.0" in expr
        # Should contain end zoom value
        assert "1.2" in expr
        # Should contain frame count
        assert "120" in expr

    def test_ease_in_zoom_expression(self):
        """Test ease-in zoom expression format."""
        preset = MotionPreset(
            name="test",
            start_zoom=1.0,
            end_zoom=1.2,
            pan_start_x=0.5,
            pan_start_y=0.5,
            pan_end_x=0.5,
            pan_end_y=0.5,
            easing="ease_in",
        )
        expr = build_zoom_expression(preset, total_frames=120)

        # Ease-in uses quadratic formula
        assert "*" in expr  # Multiplication for quadratic

    def test_zoom_with_beat_sync(self):
        """Test zoom expression with beat sync overlay."""
        preset = PRESET_LIBRARY["slow_zoom_in"]
        beat_sync_expr = "0.05*sin(on/10)"

        expr = build_zoom_expression(preset, total_frames=120, beat_sync_expr=beat_sync_expr)

        # Should include beat sync expression
        assert "0.05*sin(on/10)" in expr


class TestPanExpressions:
    """Tests for pan expression building."""

    def test_pan_x_expression(self):
        """Test horizontal pan expression format."""
        preset = MotionPreset(
            name="test",
            start_zoom=1.1,
            end_zoom=1.1,
            pan_start_x=0.0,
            pan_start_y=0.5,
            pan_end_x=1.0,
            pan_end_y=0.5,
        )
        expr = build_pan_x_expression(preset, total_frames=120)

        # Should use iw (input width) and zoom
        assert "iw" in expr
        assert "zoom" in expr
        # Should contain start and end x values
        assert "0.0" in expr
        assert "1.0" in expr

    def test_pan_y_expression(self):
        """Test vertical pan expression format."""
        preset = MotionPreset(
            name="test",
            start_zoom=1.1,
            end_zoom=1.1,
            pan_start_x=0.5,
            pan_start_y=0.0,
            pan_end_x=0.5,
            pan_end_y=1.0,
        )
        expr = build_pan_y_expression(preset, total_frames=120)

        # Should use ih (input height) and zoom
        assert "ih" in expr
        assert "zoom" in expr


class TestMotionFilter:
    """Tests for complete motion filter building."""

    def test_motion_filter_structure(self):
        """Test motion filter contains expected components."""
        preset = PRESET_LIBRARY["slow_zoom_in"]
        config = RenderConfig(width=1920, height=1080, fps=30)

        filter_str = build_motion_filter(preset, duration_sec=4.0, config=config)

        # Should contain scale to 2x for quality
        assert "scale=3840" in filter_str
        # Should contain zoompan filter
        assert "zoompan=" in filter_str
        # Should contain zoom expression
        assert "z='" in filter_str
        # Should contain x and y expressions
        assert "x='" in filter_str
        assert "y='" in filter_str
        # Should contain output size
        assert "s=1920x1080" in filter_str
        # Should contain fps
        assert "fps=30" in filter_str
        # Should set SAR
        assert "setsar=1" in filter_str

    def test_motion_filter_with_reduced_strength(self):
        """Test motion filter with reduced motion strength."""
        preset = PRESET_LIBRARY["slow_zoom_in"]
        config = RenderConfig()

        filter_full = build_motion_filter(preset, duration_sec=4.0, config=config, motion_strength=1.0)
        filter_half = build_motion_filter(preset, duration_sec=4.0, config=config, motion_strength=0.5)

        # Different strength should produce different filter
        assert filter_full != filter_half


class TestRenderCommand:
    """Tests for render command building."""

    def test_render_command_structure(self):
        """Test render command contains expected arguments."""
        preset = PRESET_LIBRARY["slow_zoom_in"]
        config = RenderConfig(width=1920, height=1080, fps=30, crf=20, preset="medium")

        cmd = build_render_command(
            input_path="/path/to/image.jpg",
            output_path="/path/to/output.mp4",
            preset=preset,
            duration_sec=4.0,
            config=config,
        )

        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd  # Overwrite
        assert "-loop" in cmd
        assert "1" in cmd
        assert "-i" in cmd
        assert "/path/to/image.jpg" in cmd
        assert "-t" in cmd
        assert "4.0" in cmd
        assert "-vf" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-preset" in cmd
        assert "medium" in cmd
        assert "-crf" in cmd
        assert "20" in cmd
        assert "-an" in cmd  # No audio
        assert "/path/to/output.mp4" in cmd

    def test_render_command_includes_motion_filter(self):
        """Test render command includes the motion filter."""
        preset = PRESET_LIBRARY["pan_left"]
        config = RenderConfig()

        cmd = build_render_command(
            input_path="test.jpg",
            output_path="test.mp4",
            preset=preset,
            duration_sec=3.0,
            config=config,
        )

        # Find the -vf argument
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]

        # Should contain zoompan
        assert "zoompan=" in vf_value


class TestSimpleScaleCommand:
    """Tests for simple scale command building."""

    def test_simple_scale_command_structure(self):
        """Test simple scale command structure."""
        config = RenderConfig(width=1920, height=1080, fps=30)

        cmd = build_simple_scale_command(
            input_path="/path/to/image.jpg",
            output_path="/path/to/output.mp4",
            duration_sec=4.0,
            config=config,
        )

        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-loop" in cmd
        assert "-t" in cmd
        assert "-vf" in cmd
        assert "-an" in cmd

    def test_simple_scale_no_zoompan(self):
        """Test simple scale command doesn't include zoompan."""
        config = RenderConfig()

        cmd = build_simple_scale_command(
            input_path="test.jpg",
            output_path="test.mp4",
            duration_sec=3.0,
            config=config,
        )

        # Find the -vf argument
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]

        # Should NOT contain zoompan
        assert "zoompan" not in vf_value
        # Should contain scale
        assert "scale=" in vf_value
