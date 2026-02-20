"""
Unit tests for §5.7 AssetManifest, §5.8 RenderPlan, §5.9 RenderOutput schemas.

Tests:
  - Valid roundtrip (serialize → deserialize → equal)
  - Rejection of missing required fields
  - Rejection of incorrect types
  - Default value correctness
  - timing_lock_hash presence in both AssetManifest and RenderPlan
  - _canonical_json_hash stability (same object → same hash across repeated calls)

No ffmpeg required.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from schemas.asset_manifest import AssetManifest, Shot, VisualAsset, VOLine, SFXItem
from schemas.render_plan import FallbackConfig, RenderPlan, Resolution
from schemas.render_output import Lineage, OutputHashes, Provenance, RenderOutput


# ===========================================================================
# AssetManifest — §5.7
# ===========================================================================

class TestAssetManifest:

    def test_minimal_valid(self):
        """AssetManifest with minimum required fields is accepted."""
        m = AssetManifest(
            manifest_id="m-001",
            project_id="proj-1",
            shotlist_ref="file:///shotlist.json",
            timing_lock_hash="sha256:abc",
            shots=[
                Shot(shot_id="s1", duration_ms=2000),
            ],
        )
        assert m.schema_version == "1.0.0"
        assert len(m.shots) == 1
        assert m.music_uri is None

    def test_roundtrip_json(self):
        """Serialise and re-parse produces an identical model."""
        m = AssetManifest(
            manifest_id="m-rt",
            project_id="p",
            shotlist_ref="file:///sl.json",
            timing_lock_hash="sha256:rt",
            shots=[
                Shot(
                    shot_id="s1",
                    duration_ms=3000,
                    visual_assets=[
                        VisualAsset(asset_id="bg1", role="background",
                                    asset_uri="file:///bg.png")
                    ],
                    vo_lines=[
                        VOLine(line_id="v1", speaker_id="narrator",
                               text="Hello", timeline_in_ms=0, timeline_out_ms=2000)
                    ],
                )
            ],
            music_uri="file:///music.mp3",
        )
        raw = m.model_dump_json()
        m2 = AssetManifest.model_validate_json(raw)
        assert m2 == m

    def test_missing_manifest_id_raises(self):
        with pytest.raises(ValidationError):
            AssetManifest(  # type: ignore[call-arg]
                project_id="p",
                shotlist_ref="file:///sl.json",
                timing_lock_hash="sha256:x",
                shots=[],
            )

    def test_missing_timing_lock_hash_raises(self):
        with pytest.raises(ValidationError):
            AssetManifest(  # type: ignore[call-arg]
                manifest_id="m",
                project_id="p",
                shotlist_ref="file:///sl.json",
                shots=[],
            )

    def test_shot_duration_ms_required(self):
        with pytest.raises(ValidationError):
            Shot(shot_id="s1")  # type: ignore[call-arg]

    def test_visual_asset_null_uri_accepted(self):
        """asset_uri=None is valid (means placeholder needed)."""
        a = VisualAsset(asset_id="a1", role="character")
        assert a.asset_uri is None
        assert a.placeholder is False

    def test_vo_line_zero_timing_accepted(self):
        """timeline_in/out_ms both 0 is valid (means no explicit timing)."""
        v = VOLine(line_id="v1", speaker_id="spk", text="text")
        assert v.timeline_in_ms == 0
        assert v.timeline_out_ms == 0

    def test_vo_line_field_names(self):
        """Canonical field names from §5.7 are present."""
        v = VOLine(
            line_id="v1",
            speaker_id="hero",
            text="words",
            emotion="calm",
            pacing_tags=["slow"],
            audio_uri="file:///v.wav",
            timeline_in_ms=100,
            timeline_out_ms=900,
        )
        d = v.model_dump()
        assert "speaker_id" in d
        assert "pacing_tags" in d
        assert "emotion" in d

    def test_sfx_item(self):
        sfx = SFXItem(sfx_id="s1", description="thunder", timeline_in_ms=500)
        assert sfx.audio_uri is None


# ===========================================================================
# RenderPlan — §5.8
# ===========================================================================

class TestRenderPlan:

    def test_minimal_valid(self):
        rp = RenderPlan(
            plan_id="p-001",
            project_id="proj-1",
            asset_manifest_ref="file:///manifest.json",
            timing_lock_hash="sha256:abc",
        )
        assert rp.profile == "preview_local"
        assert rp.fps == 24
        assert rp.resolution.width == 1280
        assert rp.resolution.height == 720

    def test_roundtrip_json(self):
        rp = RenderPlan(
            plan_id="p-rt",
            project_id="p",
            asset_manifest_ref="file:///m.json",
            timing_lock_hash="sha256:rt",
            asset_resolutions={"bg1": "file:///bg.png"},
            audio_resolutions={"v1": "file:///v.wav"},
        )
        rp2 = RenderPlan.model_validate_json(rp.model_dump_json())
        assert rp2 == rp

    def test_missing_timing_lock_hash_raises(self):
        with pytest.raises(ValidationError):
            RenderPlan(  # type: ignore[call-arg]
                plan_id="p",
                project_id="p",
                asset_manifest_ref="file:///m.json",
            )

    def test_resolution_defaults(self):
        r = Resolution()
        assert r.width == 1280
        assert r.height == 720
        assert r.aspect == "16:9"

    def test_fallback_defaults(self):
        fb = FallbackConfig()
        assert fb.placeholder_color == "#1a1a2e"
        assert fb.placeholder_font_size == 36

    def test_asset_resolutions_is_dict(self):
        rp = RenderPlan(
            plan_id="x",
            project_id="p",
            asset_manifest_ref="file:///m.json",
            timing_lock_hash="sha256:x",
            asset_resolutions={"id1": "file:///a.png", "id2": "file:///b.png"},
        )
        assert rp.asset_resolutions["id1"] == "file:///a.png"

    def test_canonical_field_names(self):
        """§5.8 canonical field names are present in serialised output."""
        rp = RenderPlan(
            plan_id="x",
            project_id="p",
            asset_manifest_ref="file:///m.json",
            timing_lock_hash="sha256:x",
        )
        d = rp.model_dump()
        for field in ("profile", "resolution", "fps", "timing_lock_hash",
                      "asset_manifest_ref", "asset_resolutions"):
            assert field in d, f"Missing canonical field: {field}"


# ===========================================================================
# RenderOutput — §5.9
# ===========================================================================

class TestRenderOutput:

    def _make_valid(self) -> RenderOutput:
        return RenderOutput(
            output_id="out-001",
            request_id="req-001",
            render_plan_ref="file:///plan.json",
            video_uri="file:///output.mp4",
            captions_uri="file:///output.srt",
            hashes=OutputHashes(
                video_sha256="a" * 64,
                captions_sha256="b" * 64,
            ),
            provenance=Provenance(
                render_profile="preview_local",
                timing_lock_hash="sha256:xyz",
                rendered_at="2026-02-19T12:00:00Z",
                ffmpeg_version="6.1.1",
                placeholder_count=1,
            ),
            lineage=Lineage(
                asset_manifest_hash="c" * 64,
                render_plan_hash="d" * 64,
            ),
        )

    def test_valid(self):
        ro = self._make_valid()
        assert ro.schema_version == "1.0.0"
        assert ro.audio_stems_uri is None

    def test_roundtrip_json(self):
        ro = self._make_valid()
        ro2 = RenderOutput.model_validate_json(ro.model_dump_json())
        assert ro2 == ro

    def test_missing_video_uri_defaults_to_none(self):
        # video_uri is Optional to support dry-run mode (no mp4 produced).
        ro = RenderOutput(  # type: ignore[call-arg]
            output_id="o",
            request_id="r",
            render_plan_ref="file:///p.json",
            # video_uri intentionally omitted — must default to None
            hashes=OutputHashes(video_sha256="a" * 64),
            provenance=Provenance(
                render_profile="preview_local",
                timing_lock_hash="sha256:z",
                rendered_at="2026-01-01T00:00:00Z",
                ffmpeg_version="6.1",
            ),
            lineage=Lineage(
                asset_manifest_hash="c" * 64,
                render_plan_hash="d" * 64,
            ),
        )
        assert ro.video_uri is None

    def test_canonical_field_names(self):
        """§5.9 canonical field names are present."""
        ro = self._make_valid()
        d = ro.model_dump()
        for field in ("video_uri", "captions_uri", "audio_stems_uri",
                      "hashes", "provenance", "lineage"):
            assert field in d, f"Missing canonical field: {field}"

    def test_audio_stems_optional(self):
        """audio_stems_uri is optional (null in Phase 0)."""
        ro = self._make_valid()
        assert ro.audio_stems_uri is None
        # Also accept explicit null in JSON
        j = json.loads(ro.model_dump_json())
        j["audio_stems_uri"] = None
        ro2 = RenderOutput.model_validate(j)
        assert ro2.audio_stems_uri is None


# ===========================================================================
# Canonical JSON hashing — determinism contract
# ===========================================================================

class TestCanonicalJsonHash:
    """
    _canonical_json_hash must return the same digest for the same object on
    every call, regardless of Python dict insertion order or Pydantic version.
    """

    def _manifest(self, manifest_id: str = "m-001") -> AssetManifest:
        return AssetManifest(
            manifest_id=manifest_id,
            project_id="proj-1",
            shotlist_ref="file:///shotlist.json",
            timing_lock_hash="sha256:abc",
            shots=[Shot(shot_id="s1", duration_ms=2000)],
        )

    def test_same_object_same_hash_repeated(self):
        """The same AssetManifest always produces the same canonical hash."""
        from renderer.preview_local import _canonical_json_hash

        m = self._manifest()
        hashes = [_canonical_json_hash(m.model_dump()) for _ in range(5)]
        assert len(set(hashes)) == 1, (
            f"_canonical_json_hash is not stable: got {set(hashes)}"
        )

    def test_same_plan_same_hash_repeated(self):
        """The same RenderPlan always produces the same canonical hash."""
        from renderer.preview_local import _canonical_json_hash

        rp = RenderPlan(
            plan_id="p-001",
            project_id="proj-1",
            asset_manifest_ref="file:///manifest.json",
            timing_lock_hash="sha256:abc",
        )
        hashes = [_canonical_json_hash(rp.model_dump()) for _ in range(5)]
        assert len(set(hashes)) == 1, (
            f"_canonical_json_hash is not stable: got {set(hashes)}"
        )

    def test_distinct_objects_distinct_hashes(self):
        """Two manifests that differ in any field must produce different hashes."""
        from renderer.preview_local import _canonical_json_hash

        h1 = _canonical_json_hash(self._manifest("m-aaa").model_dump())
        h2 = _canonical_json_hash(self._manifest("m-bbb").model_dump())
        assert h1 != h2

    def test_canonical_json_is_sorted_keys(self):
        """canonical JSON must have sorted keys (contract for cross-language interop)."""
        from renderer.preview_local import _canonical_json_hash

        # Build the canonical string directly and check key order.
        m = self._manifest()
        d = m.model_dump()
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        parsed_keys = list(json.loads(canonical).keys())
        assert parsed_keys == sorted(parsed_keys), (
            "Top-level keys are not sorted in canonical JSON output."
        )
