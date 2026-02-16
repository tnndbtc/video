#!/usr/bin/env python3
"""
Generate/update golden expected frame hashes.

This script renders an EDL and saves the frame hash to the expected/ directory.
Run this when:
- Creating a new golden test case
- Intentionally changing render behavior

Usage:
    python -m tests.golden.generate_golden_hash <edl_name>

Example:
    python -m tests.golden.generate_golden_hash simple_two_images
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


GOLDEN_DIR = Path(__file__).parent


def get_frame_hash(video_path: Path) -> str:
    """Extract frame hashes using ffmpeg framemd5."""
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-f", "framemd5", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Filter out comment lines (start with #)
    lines = [line for line in result.stdout.splitlines() if not line.startswith("#")]
    return "\n".join(lines)


def resolve_asset_path(asset_id: str) -> str:
    """Resolve asset_id to test asset path."""
    assets_dir = GOLDEN_DIR / "assets"
    for ext in [".png", ".jpg", ".jpeg"]:
        path = assets_dir / f"{asset_id}{ext}"
        if path.exists():
            return str(path)
    raise ValueError(f"Test asset not found: {asset_id}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tests.golden.generate_golden_hash <edl_name>")
        print("\nAvailable EDLs:")
        edl_dir = GOLDEN_DIR / "edl"
        for edl_file in edl_dir.glob("*.json"):
            print(f"  - {edl_file.stem}")
        sys.exit(1)

    edl_name = sys.argv[1]
    edl_path = GOLDEN_DIR / "edl" / f"{edl_name}.json"
    expected_path = GOLDEN_DIR / "expected" / f"{edl_name}.framemd5"

    if not edl_path.exists():
        print(f"Error: EDL not found: {edl_path}")
        sys.exit(1)

    print(f"Loading EDL: {edl_path}")
    with open(edl_path) as f:
        edl = json.load(f)

    # Import render components
    # Need to set up Python path if running as module
    sys.path.insert(0, str(GOLDEN_DIR.parent.parent))  # Add worker/ to path

    from app.tasks.render import FFmpegCommandBuilder, PreviewSettings

    # Create temp directory for output
    with tempfile.TemporaryDirectory(prefix="golden_hash_") as temp_dir:
        output_path = Path(temp_dir) / "output.mp4"
        audio_path = GOLDEN_DIR / "assets" / "test_audio.wav"

        if not audio_path.exists():
            print(f"Error: Test audio not found: {audio_path}")
            sys.exit(1)

        print(f"Building FFmpeg command...")
        settings = PreviewSettings()  # 640x360, 24fps, ultrafast

        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=resolve_asset_path,
            audio_path=str(audio_path),
        )
        cmd = builder.build()

        print(f"Rendering video...")
        print(f"  Command: {' '.join(cmd[:10])}...")  # Truncate for readability

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: FFmpeg render failed")
            print(f"stderr: {result.stderr}")
            sys.exit(1)

        if not output_path.exists():
            print(f"Error: Output file not created")
            sys.exit(1)

        file_size = output_path.stat().st_size
        print(f"  Output: {output_path} ({file_size:,} bytes)")

        print(f"Extracting frame hashes...")
        frame_hash = get_frame_hash(output_path)

        num_frames = len(frame_hash.strip().splitlines())
        print(f"  Frames: {num_frames}")

    # Save to expected file
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text(frame_hash)

    print(f"\nUpdated: {expected_path}")
    print(f"Hash preview (first 3 lines):")
    for line in frame_hash.splitlines()[:3]:
        print(f"  {line}")

    print(f"\nDone! Run tests to verify:")
    print(f"  pytest tests/golden/test_render_deterministic.py -v -k {edl_name}")


if __name__ == "__main__":
    main()
