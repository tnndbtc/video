"""
AI Planner service for BeatStitch.

Generates EditPlan v1 from a user prompt and project assets.
Uses OpenAI when OPENAI_API_KEY is set, otherwise falls back to a stub planner.
"""

import json
import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.media import MediaAsset
from ..models.project import Project
from ..schemas.edit_plan import (
    EditPlanProjectSettings,
    EditPlanSegment,
    EditPlanSegmentEffects,
    EditPlanTimeline,
    EditPlanV1,
)

logger = logging.getLogger(__name__)


async def generate_plan(
    project_id: str,
    prompt: str,
    constraints: Optional[dict],
    db: AsyncSession,
) -> tuple[EditPlanV1, dict]:
    """
    Generate an EditPlan for a project.

    Returns (edit_plan, metadata).
    metadata keys: stub (bool), warnings (list), model (str|None),
                   prompt_tokens (int|None), completion_tokens (int|None)
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        return await _stub_planner(project_id, constraints, db)
    else:
        return await _openai_planner(project_id, prompt, constraints, db, openai_key)


async def _stub_planner(
    project_id: str,
    constraints: Optional[dict],
    db: AsyncSession,
) -> tuple[EditPlanV1, dict]:
    """Generate a deterministic stub plan from project assets."""
    # Load media assets
    query = (
        select(MediaAsset)
        .where(
            MediaAsset.project_id == project_id,
            MediaAsset.processing_status == "ready",
        )
        .order_by(MediaAsset.sort_order)
    )
    result = await db.execute(query)
    assets = list(result.scalars().all())

    if not assets:
        raise ValueError("No ready media assets found for project")

    # Get constraints
    constraints = constraints or {}
    transition_type = constraints.get("transition_type", "cut")
    transition_duration_ms = constraints.get("transition_duration_ms", 500)

    # Build segments
    segments = []
    for idx, asset in enumerate(assets):
        if asset.media_type == "video":
            render_duration_ms = min(3000, asset.duration_ms or 3000)
        else:
            render_duration_ms = 2000

        segments.append(
            EditPlanSegment(
                index=idx,
                media_asset_id=asset.id,
                media_type=asset.media_type,
                render_duration_ms=render_duration_ms,
                source_in_ms=0,
                source_out_ms=render_duration_ms,
                effects=EditPlanSegmentEffects(),
                transition_out=None,
            )
        )

    # Compute total duration
    render_sum = sum(s.render_duration_ms for s in segments)
    n = len(segments)
    if transition_type == "crossfade" and n > 1:
        total_duration_ms = render_sum - (n - 1) * transition_duration_ms
    else:
        total_duration_ms = render_sum

    warnings = ["stub planner: OPENAI_API_KEY not set"]

    plan = EditPlanV1(
        project_id=project_id,
        project_settings=EditPlanProjectSettings(
            transition_type=transition_type,
            transition_duration_ms=transition_duration_ms,
        ),
        timeline=EditPlanTimeline(
            total_duration_ms=total_duration_ms,
            segments=segments,
        ),
        warnings=warnings,
    )

    metadata = {
        "stub": True,
        "warnings": warnings,
        "model": None,
        "prompt_tokens": None,
        "completion_tokens": None,
    }

    return plan, metadata


async def _openai_planner(
    project_id: str,
    prompt: str,
    constraints: Optional[dict],
    db: AsyncSession,
    openai_key: str,
) -> tuple[EditPlanV1, dict]:
    """Generate an EditPlan using OpenAI."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai library not installed, falling back to stub planner")
        plan, metadata = await _stub_planner(project_id, constraints, db)
        plan.warnings = (plan.warnings or []) + [
            "openai library not installed, used stub planner"
        ]
        metadata["warnings"] = plan.warnings
        return plan, metadata

    # Load assets for context
    query = (
        select(MediaAsset)
        .where(
            MediaAsset.project_id == project_id,
            MediaAsset.processing_status == "ready",
        )
        .order_by(MediaAsset.sort_order)
    )
    result = await db.execute(query)
    assets = list(result.scalars().all())

    if not assets:
        raise ValueError("No ready media assets found for project")

    # Build asset context
    asset_context = []
    for asset in assets:
        info = {
            "id": asset.id,
            "media_type": asset.media_type,
            "width": asset.width,
            "height": asset.height,
        }
        if asset.duration_ms:
            info["duration_ms"] = asset.duration_ms
        asset_context.append(info)

    constraints = constraints or {}

    system_prompt = (
        "You are a video editing AI. Given a list of media assets and a user prompt, "
        "produce a valid EditPlan v1 JSON object.\n\n"
        "The EditPlan must have:\n"
        '- plan_version: "v1"\n'
        '- mode: "no_audio" or "with_audio"\n'
        "- project_id: the given project ID\n"
        "- project_settings: {output_width, output_height, output_fps, "
        'transition_type ("cut"|"crossfade"), transition_duration_ms, ken_burns_enabled}\n'
        "- timeline: {total_duration_ms, segments: [...]}\n"
        "- Each segment: {index (0-based contiguous), media_asset_id, "
        'media_type ("image"|"video"), render_duration_ms (must be > 0), '
        "source_in_ms (>= 0, usually 0), "
        "source_out_ms (MUST be strictly greater than source_in_ms AND greater than 0; "
        "for images always set source_out_ms = render_duration_ms; "
        "for videos set source_out_ms = source_in_ms + render_duration_ms "
        "clamped to the asset's duration_ms if known)}\n\n"
        "CRITICAL: source_out_ms must NEVER be 0. "
        "It must always equal source_in_ms + render_duration_ms at minimum.\n\n"
        "total_duration_ms must equal sum of render_duration_ms for cut transitions, "
        "or sum - (N-1)*transition_duration_ms for crossfade.\n"
        "Return ONLY valid JSON, no markdown."
    )

    user_prompt = (
        f"Project ID: {project_id}\n"
        f"Assets: {json.dumps(asset_context)}\n"
        f"Constraints: {json.dumps(constraints)}\n"
        f"User prompt: {prompt}"
    )

    client = AsyncOpenAI(api_key=openai_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        plan_data = json.loads(content)

        # Sanitise segments: ensure source_out_ms is always > source_in_ms.
        # GPT-4o-mini occasionally emits source_out_ms=0 for image segments.
        for seg in plan_data.get("timeline", {}).get("segments", []):
            src_in = seg.get("source_in_ms", 0)
            src_out = seg.get("source_out_ms", 0)
            render_dur = seg.get("render_duration_ms", 1000)
            if src_out <= src_in or src_out <= 0:
                seg["source_out_ms"] = src_in + render_dur

        plan = EditPlanV1.model_validate(plan_data)
    except Exception as e:
        # Convert OpenAI API errors, JSON parse errors, and Pydantic
        # validation errors into ValueError so the endpoint returns 400
        # with a human-readable message instead of an unhandled 500.
        raise ValueError(f"AI planner error: {e}") from e

    metadata = {
        "stub": False,
        "warnings": plan.warnings or [],
        "model": "gpt-4o-mini",
        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
        "completion_tokens": (
            response.usage.completion_tokens if response.usage else None
        ),
    }

    return plan, metadata
