"""
Unit tests for EditPlan v1 schema and validation.
"""

import pytest

from app.schemas.edit_plan import (
    EditPlanProjectSettings,
    EditPlanSegment,
    EditPlanSegmentEffects,
    EditPlanTimeline,
    EditPlanV1,
    validate_edit_plan,
)


def make_asset_map(ids):
    """Create a mock asset_map with all assets in 'ready' status."""
    return {
        id: type("Asset", (), {"processing_status": "ready"})() for id in ids
    }


def make_plan(segments, total_duration_ms=None, **kwargs):
    """Create an EditPlanV1 with given segments."""
    if total_duration_ms is None:
        total_duration_ms = sum(s["render_duration_ms"] for s in segments)
    return EditPlanV1(
        project_id="proj1",
        project_settings=EditPlanProjectSettings(**kwargs.get("project_settings", {})),
        timeline=EditPlanTimeline(
            total_duration_ms=total_duration_ms,
            segments=[EditPlanSegment(**s) for s in segments],
        ),
    )


class TestValidatePlanPasses:
    def test_valid_plan_two_images(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
            {
                "index": 1,
                "media_asset_id": "a2",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        plan = make_plan(segments)
        asset_map = make_asset_map(["a1", "a2"])
        validate_edit_plan(plan, asset_map)  # should not raise

    def test_valid_plan_crossfade(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
            {
                "index": 1,
                "media_asset_id": "a2",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        # crossfade: total = 4000 - (2-1)*500 = 3500
        plan = make_plan(
            segments,
            total_duration_ms=3500,
            project_settings={
                "transition_type": "crossfade",
                "transition_duration_ms": 500,
            },
        )
        asset_map = make_asset_map(["a1", "a2"])
        validate_edit_plan(plan, asset_map)

    def test_valid_plan_within_tolerance(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        # Off by 49ms, within +-50ms tolerance
        plan = make_plan(segments, total_duration_ms=2049)
        asset_map = make_asset_map(["a1"])
        validate_edit_plan(plan, asset_map)


class TestValidatePlanRaises:
    def test_non_contiguous_indices(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
            {
                "index": 2,  # gap: should be 1
                "media_asset_id": "a2",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        plan = make_plan(segments)
        asset_map = make_asset_map(["a1", "a2"])
        with pytest.raises(ValueError, match="contiguous"):
            validate_edit_plan(plan, asset_map)

    def test_unknown_asset(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "unknown_id",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        plan = make_plan(segments)
        asset_map = make_asset_map(["a1"])
        with pytest.raises(ValueError, match="not found"):
            validate_edit_plan(plan, asset_map)

    def test_asset_not_ready(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        plan = make_plan(segments)
        asset_map = {
            "a1": type("Asset", (), {"processing_status": "pending"})()
        }
        with pytest.raises(ValueError, match="processing_status"):
            validate_edit_plan(plan, asset_map)

    def test_total_duration_mismatch(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        plan = make_plan(segments, total_duration_ms=9999)
        asset_map = make_asset_map(["a1"])
        with pytest.raises(ValueError, match="total_duration_ms mismatch"):
            validate_edit_plan(plan, asset_map)

    def test_source_out_lte_source_in(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "video",
                "render_duration_ms": 2000,
                "source_in_ms": 1000,
                "source_out_ms": 500,  # out < in
            },
        ]
        plan = make_plan(segments)
        asset_map = make_asset_map(["a1"])
        with pytest.raises(ValueError, match="source_out_ms"):
            validate_edit_plan(plan, asset_map)

    def test_source_out_equals_source_in(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "video",
                "render_duration_ms": 2000,
                "source_in_ms": 1000,
                "source_out_ms": 1000,  # out == in
            },
        ]
        plan = make_plan(segments)
        asset_map = make_asset_map(["a1"])
        with pytest.raises(ValueError, match="source_out_ms"):
            validate_edit_plan(plan, asset_map)

    def test_crossfade_duration_mismatch(self):
        segments = [
            {
                "index": 0,
                "media_asset_id": "a1",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
            {
                "index": 1,
                "media_asset_id": "a2",
                "media_type": "image",
                "render_duration_ms": 2000,
                "source_in_ms": 0,
                "source_out_ms": 2000,
            },
        ]
        # Wrong total: should be 3500 for crossfade
        plan = make_plan(
            segments,
            total_duration_ms=4000,
            project_settings={
                "transition_type": "crossfade",
                "transition_duration_ms": 500,
            },
        )
        asset_map = make_asset_map(["a1", "a2"])
        with pytest.raises(ValueError, match="total_duration_ms mismatch"):
            validate_edit_plan(plan, asset_map)


class TestEditPlanV1Schema:
    """Tests for the EditPlanV1 schema contract guardrail."""

    def test_ai_output_validation_guardrail(self):
        """Raw LLM output missing required fields raises ValidationError."""
        from pydantic import ValidationError

        bad_outputs = [
            {},                                          # totally empty
            {"project_id": "abc"},                       # missing timeline
            {"project_id": "abc", "timeline": {}},       # timeline missing required fields
            {
                "project_id": "abc",
                "timeline": {
                    "total_duration_ms": 2000,
                    "segments": [
                        {
                            "index": 0,
                            "media_asset_id": "x",
                            "media_type": "image",
                            "render_duration_ms": 2000,
                            "source_out_ms": 0,  # violates gt=0 constraint
                        }
                    ],
                },
            },
        ]
        for bad in bad_outputs:
            with pytest.raises(ValidationError):
                EditPlanV1.model_validate(bad)
