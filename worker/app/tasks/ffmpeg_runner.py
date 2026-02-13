"""
FFmpeg Runner with Timeout Enforcement

Runs FFmpeg commands with:
- Progress tracking via -progress pipe:1
- Strict timeout enforcement
- Process group management for clean termination
- Detailed error reporting

This is the primary protection against runaway FFmpeg processes.
"""

import logging
import os
import re
import signal
import subprocess
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class FFmpegTimeout(Exception):
    """Raised when FFmpeg exceeds the allowed timeout."""

    pass


class FFmpegError(Exception):
    """Raised when FFmpeg fails with a non-zero exit code."""

    pass


def run_ffmpeg_with_progress(
    cmd: List[str],
    total_duration_ms: int,
    progress_callback: Callable[[int, str], None],
    timeout_seconds: int = 1800,
) -> None:
    """
    Run FFmpeg command with progress tracking and timeout enforcement.

    This function:
    1. Adds -progress pipe:1 to capture progress output
    2. Runs FFmpeg in its own process group for clean termination
    3. Parses progress output (preferring out_time_us for accuracy)
    4. Calls progress_callback with percent and message
    5. Enforces timeout with SIGKILL to process group

    Args:
        cmd: FFmpeg command as list of arguments (without -progress)
        total_duration_ms: Expected total duration in milliseconds
        progress_callback: Function called with (percent, message)
        timeout_seconds: Maximum allowed runtime in seconds

    Raises:
        FFmpegTimeout: If FFmpeg exceeds the timeout
        FFmpegError: If FFmpeg fails with non-zero exit code

    Example:
        run_ffmpeg_with_progress(
            cmd=["ffmpeg", "-y", "-i", "input.mp4", "output.mp4"],
            total_duration_ms=10000,
            progress_callback=lambda p, m: print(f"{p}% - {m}"),
            timeout_seconds=300,
        )
    """
    # Add progress output options
    # -progress pipe:1 writes key=value progress to stdout
    # -stats_period 0.5 updates every 500ms
    cmd_with_progress = cmd + ["-progress", "pipe:1", "-stats_period", "0.5"]

    logger.info(f"Starting FFmpeg with timeout={timeout_seconds}s, duration={total_duration_ms}ms")
    logger.debug(f"FFmpeg command: {' '.join(cmd_with_progress)}")

    # Start process in its own process group for clean termination
    # preexec_fn=os.setsid creates a new session/process group
    process = subprocess.Popen(
        cmd_with_progress,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        preexec_fn=os.setsid,
    )

    # Patterns for parsing progress output
    # Prefer out_time_us (microseconds) as it's most reliable
    time_us_pattern = re.compile(r"out_time_us=(\d+)")
    time_ms_pattern = re.compile(r"out_time_ms=(\d+)")
    time_str_pattern = re.compile(r"out_time=(\d+):(\d+):(\d+)\.(\d+)")
    progress_pattern = re.compile(r"progress=(\w+)")

    start_time = time.time()
    last_percent = 0
    last_progress_time = start_time

    try:
        # Read progress from stdout line by line
        for line in process.stdout:
            line = line.strip()

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(f"FFmpeg timeout after {elapsed:.1f}s (limit: {timeout_seconds}s)")
                _kill_process_group(process)
                raise FFmpegTimeout(f"FFmpeg exceeded timeout of {timeout_seconds} seconds")

            # Check for completion
            progress_match = progress_pattern.search(line)
            if progress_match and progress_match.group(1) == "end":
                progress_callback(100, "Render complete")
                logger.info("FFmpeg signaled completion")
                break

            # Try to extract current time (in order of preference)
            current_ms = _parse_progress_time(
                line, time_us_pattern, time_ms_pattern, time_str_pattern
            )

            # Calculate and report progress
            if current_ms is not None and total_duration_ms > 0:
                percent = min(99, int((current_ms / total_duration_ms) * 100))
                if percent > last_percent:
                    last_percent = percent
                    last_progress_time = time.time()
                    progress_callback(percent, f"Rendering: {percent}%")

            # Check for stall (no progress for 60 seconds)
            if time.time() - last_progress_time > 60:
                logger.warning("FFmpeg appears stalled (no progress for 60s)")

        # Wait for process to complete with a brief timeout
        # This handles the case where we've read all stdout but process hasn't exited
        try:
            return_code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg cleanup timeout, killing process")
            _kill_process_group(process)
            raise FFmpegTimeout("FFmpeg process cleanup timed out")

        # Check return code
        if return_code != 0:
            stderr_output = process.stderr.read()
            error_msg = f"FFmpeg failed with code {return_code}"
            if stderr_output:
                # Truncate stderr to reasonable length
                stderr_truncated = stderr_output[-2000:] if len(stderr_output) > 2000 else stderr_output
                error_msg += f": {stderr_truncated}"
            logger.error(error_msg)
            raise FFmpegError(error_msg)

        # Final success
        elapsed = time.time() - start_time
        logger.info(f"FFmpeg completed successfully in {elapsed:.1f}s")
        progress_callback(100, "Complete")

    except (FFmpegTimeout, FFmpegError):
        # Re-raise our exceptions
        raise

    except Exception as e:
        # Catch any unexpected errors, ensure process is killed
        logger.error(f"Unexpected error during FFmpeg execution: {e}", exc_info=True)
        _kill_process_group(process)
        raise FFmpegError(f"FFmpeg error: {str(e)}")


def _parse_progress_time(
    line: str,
    time_us_pattern: re.Pattern,
    time_ms_pattern: re.Pattern,
    time_str_pattern: re.Pattern,
) -> Optional[int]:
    """
    Parse current output time from FFmpeg progress line.

    Tries multiple formats in order of preference:
    1. out_time_us (microseconds) - most accurate
    2. out_time_ms (milliseconds)
    3. out_time (HH:MM:SS.microseconds string)

    Args:
        line: Line of FFmpeg progress output
        time_us_pattern: Compiled regex for out_time_us
        time_ms_pattern: Compiled regex for out_time_ms
        time_str_pattern: Compiled regex for out_time string

    Returns:
        Current time in milliseconds, or None if not found
    """
    current_ms: Optional[int] = None

    # Method 1: out_time_us (microseconds -> milliseconds)
    match = time_us_pattern.search(line)
    if match:
        current_ms = int(match.group(1)) // 1000
        return current_ms

    # Method 2: out_time_ms (already milliseconds)
    match = time_ms_pattern.search(line)
    if match:
        current_ms = int(match.group(1))
        return current_ms

    # Method 3: Parse out_time string HH:MM:SS.microseconds
    match = time_str_pattern.search(line)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        # Group 4 is microseconds (6 digits, but may be truncated)
        micro_str = match.group(4).ljust(6, "0")[:6]
        microseconds = int(micro_str)
        current_ms = (
            hours * 3600000
            + minutes * 60000
            + seconds * 1000
            + microseconds // 1000
        )
        return current_ms

    return None


def _kill_process_group(process: subprocess.Popen) -> None:
    """
    Kill FFmpeg process and its entire process group.

    Uses SIGKILL to ensure immediate termination.
    Catches and logs any errors during termination.

    Args:
        process: The subprocess.Popen instance to kill
    """
    try:
        # Get process group ID and kill entire group
        pgid = os.getpgid(process.pid)
        logger.info(f"Killing FFmpeg process group {pgid}")
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        # Process already terminated
        logger.debug("Process already terminated")
    except Exception as e:
        logger.warning(f"Error killing process group: {e}")
        # Fallback: try to kill just the process
        try:
            process.kill()
        except Exception:
            pass


def validate_ffmpeg_available() -> bool:
    """
    Check if FFmpeg is available and working.

    Returns:
        True if FFmpeg is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"FFmpeg not available: {e}")
        return False
