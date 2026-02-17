"""FFprobe validation utilities for integration tests.

Provides utilities to:
- Extract video metadata using ffprobe
- Verify video duration within tolerance
- Verify video files are readable and valid
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class VideoInfo:
    """Container for video file metadata extracted via ffprobe."""

    duration_sec: float
    width: int
    height: int
    fps: float
    has_video: bool
    has_audio: bool
    audio_sample_rate: Optional[int]
    file_size: int

    @property
    def duration_ms(self) -> int:
        """Duration in milliseconds."""
        return int(self.duration_sec * 1000)


def probe_video(path: Path) -> VideoInfo:
    """Extract metadata from a video file using ffprobe.

    Args:
        path: Path to video file

    Returns:
        VideoInfo object with extracted metadata

    Raises:
        FileNotFoundError: If video file doesn't exist
        subprocess.CalledProcessError: If ffprobe fails
        ValueError: If ffprobe output cannot be parsed
    """
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    # Run ffprobe to get JSON metadata
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise subprocess.CalledProcessError(
            e.returncode,
            e.cmd,
            output=e.output,
            stderr=f"ffprobe failed for {path}: {e.stderr}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse ffprobe output: {e}")

    # Extract format information
    format_info = data.get("format", {})
    duration_sec = float(format_info.get("duration", 0))
    file_size = int(format_info.get("size", 0))

    # Extract stream information
    streams = data.get("streams", [])

    # Find video stream
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"),
        None
    )

    # Find audio stream
    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"),
        None
    )

    # Extract video properties
    if video_stream:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # Calculate FPS from r_frame_rate (format: "num/den")
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, r_frame_rate.split("/"))
            fps = num / den if den > 0 else 0
        except (ValueError, ZeroDivisionError):
            fps = 0.0
    else:
        width = 0
        height = 0
        fps = 0.0

    # Extract audio properties
    audio_sample_rate = None
    if audio_stream:
        audio_sample_rate = int(audio_stream.get("sample_rate", 0))

    return VideoInfo(
        duration_sec=duration_sec,
        width=width,
        height=height,
        fps=fps,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
        audio_sample_rate=audio_sample_rate,
        file_size=file_size,
    )


def verify_duration(
    path: Path,
    expected_ms: int,
    tolerance_ms: int = 300
) -> bool:
    """Verify that a video file's duration matches expected within tolerance.

    Args:
        path: Path to video file
        expected_ms: Expected duration in milliseconds
        tolerance_ms: Acceptable deviation in milliseconds (default: 300ms)

    Returns:
        True if duration is within tolerance, False otherwise

    Raises:
        FileNotFoundError: If video file doesn't exist
        subprocess.CalledProcessError: If ffprobe fails
    """
    info = probe_video(path)
    actual_ms = info.duration_ms

    deviation = abs(actual_ms - expected_ms)
    return deviation <= tolerance_ms


def verify_readable(path: Path) -> bool:
    """Verify that ffprobe can successfully read and parse a video file.

    This is a simple sanity check that the file is a valid video/audio file.

    Args:
        path: Path to video file

    Returns:
        True if file is readable by ffprobe, False otherwise
    """
    try:
        probe_video(path)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return False


def get_duration_ms(path: Path) -> int:
    """Quick helper to get duration in milliseconds.

    Args:
        path: Path to video file

    Returns:
        Duration in milliseconds

    Raises:
        FileNotFoundError: If video file doesn't exist
        subprocess.CalledProcessError: If ffprobe fails
    """
    info = probe_video(path)
    return info.duration_ms
