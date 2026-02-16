"""
Golden render tests - verify deterministic frame output.

These tests ensure the same EDL JSON always produces identical visual output
using frame hash comparison (ffmpeg -f framemd5), which ignores container
metadata that can vary between renders.

Usage:
    # Run golden tests (requires FFmpeg - run in Docker container)
    pytest tests/golden/test_render_deterministic.py -v

    # Generate/update expected hashes
    python -m tests.golden.generate_golden_hash simple_two_images
"""
import json
import subprocess
from pathlib import Path
from typing import Callable

import pytest


GOLDEN_DIR = Path(__file__).parent


def get_frame_hash(video_path: Path) -> str:
    """
    Extract frame hashes using ffmpeg framemd5.

    This produces deterministic hashes of decoded frame data,
    ignoring container metadata that varies between renders.

    Args:
        video_path: Path to the video file

    Returns:
        Newline-separated string of frame hash lines (comments filtered out)
    """
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-f", "framemd5", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Filter out comment lines (start with #)
    lines = [line for line in result.stdout.splitlines() if not line.startswith("#")]
    return "\n".join(lines)


@pytest.mark.slow
class TestRenderDeterministic:
    """Golden tests comparing rendered output to expected frame hashes."""

    @pytest.mark.parametrize("edl_name", ["simple_two_images"])
    def test_golden_render(
        self,
        edl_name: str,
        temp_output_dir: Path,
        mock_asset_resolver: Callable[[str], str],
        test_audio_path: Path,
        require_ffmpeg,
    ):
        """
        Render EDL and compare frame hash to golden expected output.

        This test:
        1. Loads the EDL JSON file
        2. Renders video using FFmpegCommandBuilder (isolated, no DB)
        3. Extracts frame hashes from rendered video
        4. Compares against stored expected hashes

        Args:
            edl_name: Name of the EDL (matches files in edl/ and expected/)
            temp_output_dir: Fixture providing temp directory for output
            mock_asset_resolver: Fixture providing asset path resolver
            test_audio_path: Fixture providing path to test audio
            require_ffmpeg: Fixture that skips if FFmpeg unavailable
        """
        edl_path = GOLDEN_DIR / "edl" / f"{edl_name}.json"
        expected_path = GOLDEN_DIR / "expected" / f"{edl_name}.framemd5"

        # Load EDL
        with open(edl_path) as f:
            edl = json.load(f)

        # Import render components
        from app.tasks.render import FFmpegCommandBuilder, PreviewSettings

        output_path = temp_output_dir / "output.mp4"
        settings = PreviewSettings()  # 640x360, 24fps, ultrafast

        # Build FFmpeg command
        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=mock_asset_resolver,
            audio_path=str(test_audio_path),
        )
        cmd = builder.build()

        # Run FFmpeg render
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            pytest.fail(
                f"FFmpeg render failed:\n"
                f"Command: {' '.join(cmd)}\n"
                f"stderr: {result.stderr}"
            )

        # Verify output exists
        assert output_path.exists(), f"Output file not created: {output_path}"
        assert output_path.stat().st_size > 0, "Output file is empty"

        # Extract frame hashes
        actual_hash = get_frame_hash(output_path)

        # Compare against expected
        if not expected_path.exists():
            # No expected hash yet - save actual and fail with instructions
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            expected_path.write_text(actual_hash)
            pytest.fail(
                f"No expected hash found for {edl_name}. "
                f"Generated initial hash at {expected_path}. "
                f"Review and commit if correct."
            )

        expected_hash = expected_path.read_text().strip()

        assert actual_hash == expected_hash, (
            f"Frame hash mismatch for {edl_name}.\n"
            f"Expected ({len(expected_hash.splitlines())} frames):\n"
            f"{expected_hash[:500]}...\n\n"
            f"Actual ({len(actual_hash.splitlines())} frames):\n"
            f"{actual_hash[:500]}...\n\n"
            f"To regenerate expected hash:\n"
            f"  python -m tests.golden.generate_golden_hash {edl_name}"
        )

    def test_render_produces_correct_duration(
        self,
        temp_output_dir: Path,
        mock_asset_resolver: Callable[[str], str],
        test_audio_path: Path,
        require_ffmpeg,
    ):
        """Verify rendered video has correct duration from EDL."""
        edl_path = GOLDEN_DIR / "edl" / "simple_two_images.json"

        with open(edl_path) as f:
            edl = json.load(f)

        from app.tasks.render import FFmpegCommandBuilder, PreviewSettings

        output_path = temp_output_dir / "output.mp4"
        settings = PreviewSettings()

        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=mock_asset_resolver,
            audio_path=str(test_audio_path),
        )
        cmd = builder.build()

        subprocess.run(cmd, check=True, capture_output=True)

        # Get actual duration using ffprobe
        probe_result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        actual_duration_sec = float(probe_result.stdout.strip())
        expected_duration_sec = edl["total_duration_ms"] / 1000

        # Allow small tolerance for rounding
        assert abs(actual_duration_sec - expected_duration_sec) < 0.1, (
            f"Duration mismatch: expected {expected_duration_sec}s, "
            f"got {actual_duration_sec}s"
        )

    def test_render_produces_correct_resolution(
        self,
        temp_output_dir: Path,
        mock_asset_resolver: Callable[[str], str],
        test_audio_path: Path,
        require_ffmpeg,
    ):
        """Verify rendered video has correct resolution from settings."""
        edl_path = GOLDEN_DIR / "edl" / "simple_two_images.json"

        with open(edl_path) as f:
            edl = json.load(f)

        from app.tasks.render import FFmpegCommandBuilder, PreviewSettings

        output_path = temp_output_dir / "output.mp4"
        settings = PreviewSettings()  # 640x360

        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=mock_asset_resolver,
            audio_path=str(test_audio_path),
        )
        cmd = builder.build()

        subprocess.run(cmd, check=True, capture_output=True)

        # Get actual resolution using ffprobe
        probe_result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        width, height = map(int, probe_result.stdout.strip().split("x"))

        assert width == settings.width, f"Width mismatch: expected {settings.width}, got {width}"
        assert height == settings.height, f"Height mismatch: expected {settings.height}, got {height}"
