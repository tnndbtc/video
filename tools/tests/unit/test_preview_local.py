"""Unit tests for PreviewRenderer dry-run mode."""
from __future__ import annotations
import pytest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[2]
import sys; sys.path.insert(0, str(TOOLS_ROOT))

from schemas.asset_manifest import AssetManifest, Shot
from schemas.render_plan import FallbackConfig, RenderPlan, Resolution
from renderer.preview_local import PreviewRenderer

_TIMING = "sha256:test-timing-lock-abc123"


def _make_manifest() -> AssetManifest:
    return AssetManifest(
        manifest_id="dry-m",
        project_id="dry-p",
        shotlist_ref="file:///sl.json",
        timing_lock_hash=_TIMING,
        shots=[Shot(shot_id="s1", duration_ms=2_000)],
    )


def _make_plan() -> RenderPlan:
    return RenderPlan(
        plan_id="dry-pl",
        project_id="dry-p",
        profile="preview_local",
        resolution=Resolution(width=1280, height=720, aspect="16:9"),
        fps=24,
        asset_manifest_ref="file:///render_plan.json",   # becomes render_plan_ref
        timing_lock_hash=_TIMING,
        fallback=FallbackConfig(),
    )


class TestDryRun:

    _ASSET_MANIFEST_REF = "file:///asset_manifest.json"

    @pytest.fixture()
    def dry_result(self, tmp_path):
        return PreviewRenderer(
            _make_manifest(),
            _make_plan(),
            output_dir=tmp_path / "out",
            asset_manifest_ref=self._ASSET_MANIFEST_REF,
            dry_run=True,
        ).render()

    def test_render_plan_ref(self, dry_result):
        assert dry_result.render_plan_ref == "file:///render_plan.json"

    def test_asset_manifest_ref(self, dry_result):
        assert dry_result.asset_manifest_ref == self._ASSET_MANIFEST_REF

    def test_video_uri_is_none(self, dry_result):
        assert dry_result.video_uri is None

    def test_outputs_empty(self, dry_result):
        assert dry_result.outputs == []

    def test_effective_settings_present(self, dry_result):
        assert dry_result.effective_settings is not None
        assert dry_result.effective_settings.encoder == "libx264"

    def test_only_json_written(self, tmp_path):
        out = tmp_path / "out2"
        PreviewRenderer(
            _make_manifest(), _make_plan(),
            output_dir=out,
            asset_manifest_ref=self._ASSET_MANIFEST_REF,
            dry_run=True,
        ).render()
        assert {f.name for f in out.iterdir()} == {"render_output.json"}
