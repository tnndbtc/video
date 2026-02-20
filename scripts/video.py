#!/usr/bin/env python3
"""
video — top-level renderer CLI.

Usage:
    python scripts/video.py verify
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))

from tests._fixture_builders import build_minimal_verify_fixture
from renderer.preview_local import PreviewRenderer

_PINNED_MP4_SHA256 = "b4a44e354dc6e8808a94a59b7bd402e0496e3d1489223a20a92132a7c8ecd6a9"
_PINNED_SRT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _fingerprint_bytes(out_dir: Path) -> bytes:
    """Run verify() on the minimal fixture; return render_fingerprint.json bytes."""
    manifest, plan = build_minimal_verify_fixture()
    PreviewRenderer(
        manifest, plan,
        output_dir=out_dir,
        asset_manifest_ref="file:///asset_manifest.json",
        dry_run=False,
    ).verify()
    return (out_dir / "render_fingerprint.json").read_bytes()


def cmd_verify(strict: bool = False) -> int:
    """
    System verification export.
    Runs verify() twice on the minimal fixture, compares fingerprint bytes,
    and checks pinned mp4/srt hashes.
    Returns 0 on success, 1 on failure.
    """
    errors: list[str] = []
    try:
        with (tempfile.TemporaryDirectory() as d1,
              tempfile.TemporaryDirectory() as d2):
            b1 = _fingerprint_bytes(Path(d1))
            b2 = _fingerprint_bytes(Path(d2))

            if b1 != b2:
                errors.append("fingerprint JSON bytes differ between runs")

            fp = json.loads(b1)

            # mp4 check — warn only unless --strict
            if fp.get("mp4_sha256") != _PINNED_MP4_SHA256:
                msg = (
                    f"mp4_sha256 mismatch: expected {_PINNED_MP4_SHA256}, "
                    f"got {fp.get('mp4_sha256')}"
                )
                if strict:
                    errors.append(msg)
                else:
                    print(f"  WARNING: {msg}", file=sys.stderr)

            # srt check — always hard fail
            if fp.get("srt_sha256") != _PINNED_SRT_SHA256:
                errors.append(
                    f"srt_sha256 mismatch: expected {_PINNED_SRT_SHA256}, "
                    f"got {fp.get('srt_sha256')}"
                )
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("ERROR: video verification failed")
        return 1

    print("OK: video verified")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="video — renderer CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify", help="Run system verification export")
    verify_parser.add_argument(
        "--strict", action="store_true",
        help="Fail (exit 1) on mp4_sha256 mismatch instead of warning",
    )
    args = parser.parse_args()
    if args.command == "verify":
        sys.exit(cmd_verify(strict=args.strict))


if __name__ == "__main__":
    main()
