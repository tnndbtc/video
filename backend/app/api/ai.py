"""
AI Planner API endpoints for BeatStitch.

Provides endpoints for generating, applying, and combining AI-generated edit plans.
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.storage import get_storage_root
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.user import User
from app.schemas.edit_plan import EditPlanV1, validate_edit_plan
from app.services.ai_planner import generate_plan
from app.services.edit_plan_converter import convert_edit_plan_to_edit_request
from app.services.edit_request_validator import EditRequestValidator

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class PlanRequest(BaseModel):
    project_id: str
    prompt: str
    mode: str = "no_audio"
    constraints: Optional[dict] = None


class ApplyRequest(BaseModel):
    project_id: str
    edit_plan: Any   # parsed manually below so we control the error format


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_project_or_404(
    project_id: str,
    db: AsyncSession,
    user: User,
) -> Project:
    """Get a project by ID, verifying ownership."""
    query = select(Project).where(Project.id == project_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()

    if project is None or project.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Project not found",
                "resource_type": "project",
                "resource_id": project_id,
            },
        )
    return project


async def _build_asset_map(
    project_id: str,
    db: AsyncSession,
) -> dict[str, MediaAsset]:
    """Build a map of asset_id -> MediaAsset for a project."""
    query = select(MediaAsset).where(MediaAsset.project_id == project_id)
    result = await db.execute(query)
    assets = result.scalars().all()
    return {asset.id: asset for asset in assets}


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/plan")
async def ai_plan(
    request: PlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate an EditPlan from a user prompt."""
    # Verify project ownership
    await _get_project_or_404(request.project_id, db, current_user)

    # Generate plan
    try:
        plan, metadata = await generate_plan(
            project_id=request.project_id,
            prompt=request.prompt,
            constraints=request.constraints,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "plan_generation_failed", "message": str(e)},
        )

    # Build asset_map for validation
    asset_map = await _build_asset_map(request.project_id, db)

    # Validate
    try:
        validate_edit_plan(plan, asset_map)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_edit_plan", "message": str(e), "details": []},
        )

    return {
        "edit_plan": plan.model_dump(),
        "warnings": metadata.get("warnings", []),
        "metadata": {
            "stub": metadata.get("stub", False),
            "model": metadata.get("model"),
            "prompt_tokens": metadata.get("prompt_tokens"),
            "completion_tokens": metadata.get("completion_tokens"),
        },
    }


@router.post("/apply")
async def ai_apply(
    request: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Apply an EditPlan to a project, saving it as an EditRequest."""
    # Verify project ownership
    await _get_project_or_404(request.project_id, db, current_user)

    # Parse and validate schema (explicit so we control the error format)
    try:
        plan = EditPlanV1.model_validate(request.edit_plan)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_edit_plan",
                "message": "Edit plan failed schema validation",
                "details": e.errors(),
            },
        )

    # Build asset_map
    asset_map = await _build_asset_map(request.project_id, db)

    # Validate
    try:
        validate_edit_plan(plan, asset_map)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_edit_plan", "message": str(e), "details": []},
        )

    # Convert to EditRequest
    edit_request = convert_edit_plan_to_edit_request(
        plan,
        asset_map=asset_map,
    )

    # Save edit_request.json (same pattern as edit_request.py save endpoint)
    storage_root = get_storage_root()
    derived_dir = storage_root / "derived" / request.project_id
    derived_dir.mkdir(parents=True, exist_ok=True)

    edit_request_path = derived_dir / "edit_request.json"
    with open(edit_request_path, "w") as f:
        json.dump(edit_request.model_dump(exclude_none=True), f, indent=2)

    # Compute edl_hash
    validator = EditRequestValidator(db)
    edl_hash = await validator.compute_edl_hash(edit_request)

    logger.info(
        f"Applied EditPlan for project {request.project_id}, hash={edl_hash[:16]}..."
    )

    return {
        "ok": True,
        "edl_hash": edl_hash,
        "segment_count": len(edit_request.timeline),
        "total_duration_ms": plan.timeline.total_duration_ms,
    }


@router.post("/plan_and_apply")
async def ai_plan_and_apply(
    request: PlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate an EditPlan and immediately apply it."""
    # Verify project ownership
    await _get_project_or_404(request.project_id, db, current_user)

    # Generate plan
    try:
        plan, metadata = await generate_plan(
            project_id=request.project_id,
            prompt=request.prompt,
            constraints=request.constraints,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "plan_generation_failed", "message": str(e)},
        )

    # Build asset_map
    asset_map = await _build_asset_map(request.project_id, db)

    # Validate
    try:
        validate_edit_plan(plan, asset_map)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_edit_plan", "message": str(e), "details": []},
        )

    # Convert and save
    edit_request = convert_edit_plan_to_edit_request(plan, asset_map=asset_map)

    storage_root = get_storage_root()
    derived_dir = storage_root / "derived" / request.project_id
    derived_dir.mkdir(parents=True, exist_ok=True)

    edit_request_path = derived_dir / "edit_request.json"
    with open(edit_request_path, "w") as f:
        json.dump(edit_request.model_dump(exclude_none=True), f, indent=2)

    validator = EditRequestValidator(db)
    edl_hash = await validator.compute_edl_hash(edit_request)

    logger.info(
        f"Plan+Apply for project {request.project_id}, hash={edl_hash[:16]}..."
    )

    return {
        "ok": True,
        "edit_plan": plan.model_dump(),
        "edl_hash": edl_hash,
        "segment_count": len(edit_request.timeline),
        "total_duration_ms": plan.timeline.total_duration_ms,
        "warnings": metadata.get("warnings", []),
        "metadata": {
            "stub": metadata.get("stub", False),
            "model": metadata.get("model"),
        },
    }
