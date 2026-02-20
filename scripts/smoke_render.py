#!/usr/bin/env python3
"""Smoke render: produces out/output.mp4, out/output.srt, out/render_output.json."""
from __future__ import annotations
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))

from tests.golden.generate_golden import _make_test_assets, _build_manifest, _build_plan
from renderer.preview_local import PreviewRenderer

OUT_DIR = Path(__file__).resolve().parents[1] / "out"

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = OUT_DIR / "assets"
    _make_test_assets(assets_dir)
    manifest = _build_manifest(assets_dir)
    plan     = _build_plan()
    result   = PreviewRenderer(manifest, plan, output_dir=OUT_DIR).render()
    print(result.model_dump_json(indent=2))
    print(f"\nArtifacts in {OUT_DIR}")

if __name__ == "__main__":
    main()
