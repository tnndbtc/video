#!/usr/bin/env python3
"""
Sole renderer CLI — accepts AssetManifest.json and RenderPlan.json, auto-detects
format (native Pydantic or orchestrator-adapter), then invokes PreviewRenderer.

Stdout: full RenderOutput JSON (parseable by callers).
Stderr: error message on failure (exit code 1).

Usage::

    python scripts/render_from_orchestrator.py \\
        --asset-manifest /path/to/AssetManifest.json \\
        --render-plan    /path/to/RenderPlan.json \\
        --out-dir        /tmp/smoke-out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))

from schemas.asset_manifest import AssetManifest, Shot, VisualAsset, VOLine
from schemas.render_plan import FallbackConfig, RenderPlan, Resolution
from renderer.preview_local import PreviewRenderer

# Fallback shot duration (ms) when orchestrator manifest carries no timing data.
_DEFAULT_SHOT_MS = 3_000


# ---------------------------------------------------------------------------
# Schema adapters
# ---------------------------------------------------------------------------

def _adapt_manifest(raw: dict, timing_lock_hash: str) -> AssetManifest:
    """
    Translate orchestrator AssetManifest JSON → renderer AssetManifest model.

    Orchestrator layout
    -------------------
    backgrounds[]        one entry per scene; carries scene_id and bg_id
    character_packs[]    flat list of character packs (not scene-bound)
    vo_items[]           each item_id encodes the scene_id it belongs to
                         (e.g. "vo-scene-001-commander-000")

    Renderer layout
    ---------------
    shots[]              one Shot per scene, each containing visual_assets and vo_lines
    timing_lock_hash     taken from the companion RenderPlan (absent in orchestrator manifest)
    """
    shots: list[Shot] = []

    for bg in raw.get("backgrounds", []):
        scene_id = bg["scene_id"]

        # Visual assets: background first, then all character packs.
        visual_assets: list[VisualAsset] = [
            VisualAsset(
                asset_id=bg["bg_id"],
                role="background",
                placeholder=bg.get("is_placeholder", False),
            )
        ]
        for cp in raw.get("character_packs", []):
            visual_assets.append(
                VisualAsset(
                    asset_id=cp["pack_id"],
                    role="character",
                    placeholder=cp.get("is_placeholder", False),
                )
            )

        # VO lines: match items whose item_id contains this scene_id.
        vo_lines: list[VOLine] = [
            VOLine(
                line_id=vo["item_id"],
                speaker_id=vo["speaker_id"],
                text=vo["text"],
            )
            for vo in raw.get("vo_items", [])
            if scene_id in vo["item_id"]
        ]

        shots.append(
            Shot(
                shot_id=scene_id,
                duration_ms=_DEFAULT_SHOT_MS,
                visual_assets=visual_assets,
                vo_lines=vo_lines,
            )
        )

    return AssetManifest(
        schema_version=raw.get("schema_version", "1.0.0"),
        manifest_id=raw["manifest_id"],
        project_id=raw["project_id"],
        shotlist_ref=raw["shotlist_ref"],
        timing_lock_hash=timing_lock_hash,
        shots=shots,
    )


def _adapt_plan(raw: dict, render_plan_path: Path) -> RenderPlan:
    """
    Translate orchestrator RenderPlan JSON → renderer RenderPlan model.

    Key adaptations
    ---------------
    resolution  "WxH" string  →  Resolution(width, height, aspect)
    asset_manifest_ref         set to file:// URI of the render-plan file itself
                               so that RenderOutput.render_plan_ref equals the
                               absolute path of the render plan (requirement #2).
    asset_resolutions          empty — all orchestrator URIs are placeholder://;
                               renderer falls back to generated placeholders.
    audio_resolutions          empty — no TTS audio in Phase 0 demo run.
    """
    width_str, height_str = raw["resolution"].split("x", 1)
    resolution = Resolution(
        width=int(width_str),
        height=int(height_str),
        aspect=raw["aspect_ratio"],
    )

    return RenderPlan(
        schema_version=raw.get("schema_version", "1.0.0"),
        plan_id=raw["plan_id"],
        project_id=raw["project_id"],
        profile=raw["profile"],
        resolution=resolution,
        fps=raw["fps"],
        # Setting asset_manifest_ref to the render-plan file URI causes
        # PreviewRenderer to write this value into RenderOutput.render_plan_ref
        # (see preview_local.py line 151: render_plan_ref=self.plan.asset_manifest_ref).
        asset_manifest_ref=f"file://{render_plan_path.resolve()}",
        timing_lock_hash=raw["timing_lock_hash"],
        asset_resolutions={},
        audio_resolutions={},
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sole renderer CLI: invoke PreviewRenderer and print RenderOutput JSON."
    )
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to AssetManifest.json (native Pydantic or orchestrator format)",
    )
    parser.add_argument(
        "--render-plan",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to RenderPlan.json (native Pydantic or orchestrator format)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        metavar="PATH",
        help="Output directory for output.mp4, output.srt, render_output.json",
    )
    args = parser.parse_args()

    try:
        raw_manifest = json.loads(args.asset_manifest.read_text(encoding="utf-8"))
        raw_plan = json.loads(args.render_plan.read_text(encoding="utf-8"))

        # Format auto-detect: native Pydantic format has a top-level "shots" key;
        # orchestrator format uses "backgrounds" / "character_packs" / "vo_items".
        if "shots" in raw_manifest:
            manifest = AssetManifest.model_validate(raw_manifest)
            plan = RenderPlan.model_validate(raw_plan)
        else:
            manifest = _adapt_manifest(raw_manifest, raw_plan["timing_lock_hash"])
            plan = _adapt_plan(raw_plan, args.render_plan)

        args.out_dir.mkdir(parents=True, exist_ok=True)

        asset_manifest_ref = f"file://{args.asset_manifest.resolve()}"
        result = PreviewRenderer(
            manifest, plan, output_dir=args.out_dir,
            asset_manifest_ref=asset_manifest_ref,
        ).render()
        # render() already writes render_output.json to out_dir.
        print(result.model_dump_json(indent=2))

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
