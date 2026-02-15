"""
Beat-Synchronized Motion Effects

Generates FFmpeg expressions for beat-synced zoom pulses
that add rhythmic emphasis to motion clips.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def load_beat_grid(beat_grid_path: str) -> Optional[dict]:
    """
    Load beat grid from JSON file.

    The beat grid contains detected beat positions from audio analysis.

    Expected format:
    {
        "bpm": 120.0,
        "beats": [0.5, 1.0, 1.5, ...],  // Beat times in seconds
        "downbeats": [0.5, 2.5, ...],   // Beat 1 of each bar
        "bars": [
            {"start": 0.5, "beats": [0.5, 1.0, 1.5, 2.0]},
            ...
        ]
    }

    Args:
        beat_grid_path: Path to beat_grid.json

    Returns:
        Beat grid dict if loaded successfully, None otherwise
    """
    try:
        path = Path(beat_grid_path)
        if not path.exists():
            logger.warning(f"Beat grid not found: {beat_grid_path}")
            return None

        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load beat grid: {e}")
        return None


def get_beat_frames(
    beat_times_sec: List[float],
    clip_start_sec: float,
    clip_duration_sec: float,
    fps: int,
) -> List[int]:
    """
    Convert beat times to frame numbers within a clip.

    Args:
        beat_times_sec: List of beat times in seconds (relative to audio start)
        clip_start_sec: When this clip starts in the timeline (seconds)
        clip_duration_sec: Duration of this clip (seconds)
        fps: Frame rate for conversion

    Returns:
        List of frame numbers where beats occur within the clip
    """
    clip_end_sec = clip_start_sec + clip_duration_sec
    beat_frames = []

    for beat_time in beat_times_sec:
        # Check if beat falls within this clip's time range
        if clip_start_sec <= beat_time < clip_end_sec:
            # Convert to frame number relative to clip start
            relative_time = beat_time - clip_start_sec
            frame = int(relative_time * fps)
            beat_frames.append(frame)

    return beat_frames


def build_beat_pulse_expression(
    beat_frames: List[int],
    pulse_amplitude: float = 0.05,
    decay_frames: int = 6,
) -> str:
    """
    Build FFmpeg expression for beat-synced zoom pulses.

    Creates additive zoom pulses that decay exponentially at each beat.
    The pulse function: amplitude * exp(-3 * (frame - beat_frame) / decay)

    Args:
        beat_frames: List of frame numbers where pulses occur
        pulse_amplitude: Maximum zoom increase (0.05 = 5% zoom bump)
        decay_frames: Number of frames for pulse to decay (default 6 = 200ms at 30fps)

    Returns:
        FFmpeg expression string to add to zoom value
    """
    if not beat_frames:
        return "0"

    pulse_expressions = []
    for bf in beat_frames:
        # Exponential decay pulse starting at beat frame
        # between(on, start, end) returns 1 if on is in range
        # exp(-3 * t/decay) gives nice exponential decay from 1 to ~0.05 over decay_frames
        pulse = (
            f"if(between(on,{bf},{bf + decay_frames}),"
            f"{pulse_amplitude}*exp(-3*(on-{bf})/{decay_frames}),0)"
        )
        pulse_expressions.append(pulse)

    # Sum all pulses (they shouldn't overlap if beats are spaced normally)
    return "(" + "+".join(pulse_expressions) + ")"


def build_beat_sync_zoom_expr(
    beat_grid_path: str,
    clip_start_sec: float,
    clip_duration_sec: float,
    fps: int,
    mode: str = "downbeat",
    beat_n: int = 4,
    pulse_amplitude: float = 0.05,
    decay_frames: int = 6,
) -> Optional[str]:
    """
    Build complete beat-synced zoom expression for a clip.

    Modes:
    - "none": No beat sync (returns None)
    - "downbeat": Pulse on beat 1 of each bar
    - "every_n_beats": Pulse every N beats

    Args:
        beat_grid_path: Path to beat_grid.json
        clip_start_sec: When this clip starts in timeline (seconds)
        clip_duration_sec: Duration of this clip (seconds)
        fps: Output frame rate
        mode: Beat sync mode
        beat_n: For "every_n_beats" mode, pulse every N beats
        pulse_amplitude: Zoom bump amount (0.05 = 5%)
        decay_frames: Pulse decay duration in frames

    Returns:
        FFmpeg expression string, or None if no beat sync
    """
    if mode == "none":
        return None

    beat_grid = load_beat_grid(beat_grid_path)
    if not beat_grid:
        logger.warning("No beat grid available, skipping beat sync")
        return None

    # Select which beats to use based on mode
    if mode == "downbeat":
        # Use only downbeats (beat 1 of each bar)
        beat_times = beat_grid.get("downbeats", [])
        if not beat_times:
            # Fall back to first beat of each bar
            bars = beat_grid.get("bars", [])
            beat_times = [bar["start"] for bar in bars if "start" in bar]
    elif mode == "every_n_beats":
        # Use every Nth beat from the full beat list
        all_beats = beat_grid.get("beats", [])
        beat_times = all_beats[::beat_n] if all_beats else []
    else:
        logger.warning(f"Unknown beat sync mode: {mode}")
        return None

    if not beat_times:
        logger.warning("No beats found for sync")
        return None

    # Convert to frame numbers within this clip
    beat_frames = get_beat_frames(
        beat_times_sec=beat_times,
        clip_start_sec=clip_start_sec,
        clip_duration_sec=clip_duration_sec,
        fps=fps,
    )

    if not beat_frames:
        logger.debug(f"No beats fall within clip ({clip_start_sec}s - {clip_start_sec + clip_duration_sec}s)")
        return None

    logger.debug(f"Beat sync: {len(beat_frames)} pulses for clip at {clip_start_sec}s")

    return build_beat_pulse_expression(
        beat_frames=beat_frames,
        pulse_amplitude=pulse_amplitude,
        decay_frames=decay_frames,
    )


def calculate_bpm_from_beats(beat_times: List[float]) -> Optional[float]:
    """
    Calculate BPM from a list of beat times.

    Args:
        beat_times: List of beat times in seconds

    Returns:
        BPM as float, or None if not enough beats
    """
    if len(beat_times) < 2:
        return None

    # Calculate intervals between consecutive beats
    intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]

    # Average interval in seconds
    avg_interval = sum(intervals) / len(intervals)

    # Convert to BPM
    if avg_interval > 0:
        return 60.0 / avg_interval

    return None
