"""
EditRequest API endpoints for BeatStitch.

Provides endpoints for validating and saving EditRequest (EDL v1) specifications.
These endpoints allow users to define video edits through a structured JSON schema.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.storage import get_storage_root
from app.models.project import Project
from app.models.user import User
from app.schemas.edit_request import (
    EditRequest,
    EditRequestSaveResponse,
    EditRequestValidationResult,
)
from app.services.edit_request_validator import EditRequestValidator

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Helper Functions
# =============================================================================


async def get_project_or_404(
    project_id: str,
    db: AsyncSession,
    user: User,
) -> Project:
    """
    Get a project by ID, verifying ownership.

    Args:
        project_id: The project UUID
        db: Database session
        user: Current authenticated user

    Returns:
        Project object if found and owned by user

    Raises:
        HTTPException 404: If project not found or not owned by user
    """
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


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{project_id}/edl/validate",
    response_model=EditRequestValidationResult,
    summary="Validate EditRequest",
    description=(
        "Validates an EditRequest (EDL v1) without saving. "
        "Checks asset existence, type matching, BPM availability, and other rules. "
        "Returns validation result with errors, warnings, and computed metadata."
    ),
    responses={
        200: {
            "description": "Validation completed (check 'valid' field for result)",
            "content": {
                "application/json": {
                    "examples": {
                        "valid": {
                            "summary": "Valid EditRequest",
                            "value": {
                                "valid": True,
                                "errors": [],
                                "warnings": [],
                                "computed": {
                                    "total_duration_ms": 24000,
                                    "segment_count": 3,
                                    "effective_bpm": 120.0,
                                    "audio_duration_ms": 180000,
                                    "loop_count": 8,
                                },
                            },
                        },
                        "invalid": {
                            "summary": "Invalid EditRequest",
                            "value": {
                                "valid": False,
                                "errors": [
                                    {
                                        "code": "asset_not_found",
                                        "message": "Asset 'img_001' not found",
                                        "path": "timeline[0].asset_id",
                                        "asset_id": "img_001",
                                    }
                                ],
                                "warnings": [],
                                "computed": None,
                            },
                        },
                    }
                }
            },
        },
        422: {
            "description": "Invalid JSON structure (Pydantic validation failed)",
        },
    },
)
async def validate_edit_request(
    project_id: str,
    edit_request: EditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EditRequestValidationResult:
    """
    Validate an EditRequest against the project's assets and business rules.

    This endpoint performs the following validations:
    - Asset existence: All referenced asset IDs must exist in the project
    - Asset type matching: Asset types must match their declared types
    - BPM availability: Beat-based durations require BPM from audio or override
    - Duration ranges: Duration values must be within valid ranges
    - Source trim validity: Video trim points must be valid
    - Transition duration warnings: Warns if transition exceeds 50% of segment

    The validation result includes computed metadata if the request is valid,
    such as total duration, effective BPM, and loop count.
    """
    # Verify project ownership
    await get_project_or_404(project_id, db, current_user)

    # Create validator and run validation
    validator = EditRequestValidator(db)
    result = await validator.validate(edit_request, project_id)

    return result


@router.post(
    "/{project_id}/edl/save",
    response_model=EditRequestSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save EditRequest",
    description=(
        "Validates and saves an EditRequest (EDL v1) to the project. "
        "The saved EDL is stored as JSON and assigned a hash for cache validation."
    ),
    responses={
        201: {
            "description": "EditRequest saved successfully",
        },
        400: {
            "description": "Validation failed - EditRequest has errors",
            "content": {
                "application/json": {
                    "example": {
                        "error": "validation_failed",
                        "message": "EditRequest validation failed",
                        "validation": {
                            "valid": False,
                            "errors": [
                                {
                                    "code": "asset_not_found",
                                    "message": "Asset 'img_001' not found",
                                    "path": "timeline[0].asset_id",
                                    "asset_id": "img_001",
                                }
                            ],
                            "warnings": [],
                            "computed": None,
                        },
                    }
                }
            },
        },
        422: {
            "description": "Invalid JSON structure (Pydantic validation failed)",
        },
    },
)
async def save_edit_request(
    project_id: str,
    edit_request: EditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EditRequestSaveResponse:
    """
    Validate and save an EditRequest to the project.

    This endpoint:
    1. Validates the EditRequest against project assets
    2. If valid, saves the JSON to the project's derived directory
    3. Computes and returns an EDL hash for cache validation

    The saved EditRequest can be used directly for rendering without
    auto-generating the timeline.
    """
    # Verify project ownership
    project = await get_project_or_404(project_id, db, current_user)

    # Create validator and run validation
    validator = EditRequestValidator(db)
    result = await validator.validate(edit_request, project_id)

    # If validation failed, return 400 with details
    if not result.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_failed",
                "message": "EditRequest validation failed",
                "validation": result.model_dump(),
            },
        )

    # Compute EDL hash
    edl_hash = await validator.compute_edl_hash(edit_request)

    # Save to filesystem
    storage_root = get_storage_root()
    derived_dir = storage_root / "derived" / project_id
    derived_dir.mkdir(parents=True, exist_ok=True)

    # Save EditRequest JSON
    edit_request_path = derived_dir / "edit_request.json"
    with open(edit_request_path, "w") as f:
        json.dump(edit_request.model_dump(exclude_none=True), f, indent=2)

    logger.info(
        f"Saved EditRequest for project {project_id}, hash={edl_hash[:16]}..."
    )

    # Generate unique ID for the saved EDL
    edl_id = str(uuid.uuid4())

    return EditRequestSaveResponse(
        id=edl_id,
        edl_hash=edl_hash,
        validation=result,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get(
    "/{project_id}/edl",
    response_model=Optional[EditRequest],
    summary="Get saved EditRequest",
    description="Retrieve the currently saved EditRequest (EDL v1) for a project.",
    responses={
        200: {
            "description": "EditRequest found",
        },
        204: {
            "description": "No EditRequest saved for this project",
        },
    },
)
async def get_edit_request(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Optional[EditRequest]:
    """
    Get the currently saved EditRequest for a project.

    Returns None (204) if no EditRequest has been saved yet.
    """
    # Verify project ownership
    await get_project_or_404(project_id, db, current_user)

    # Check if edit_request.json exists
    storage_root = get_storage_root()
    edit_request_path = storage_root / "derived" / project_id / "edit_request.json"

    if not edit_request_path.exists():
        return None

    # Load and parse
    try:
        with open(edit_request_path, "r") as f:
            data = json.load(f)
        return EditRequest.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(f"Failed to load EditRequest for project {project_id}: {e}")
        return None


@router.delete(
    "/{project_id}/edl",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete saved EditRequest",
    description="Delete the saved EditRequest (EDL v1) for a project.",
)
async def delete_edit_request(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete the saved EditRequest for a project.

    This allows the project to return to auto-generated timeline mode.
    """
    # Verify project ownership
    await get_project_or_404(project_id, db, current_user)

    # Delete if exists
    storage_root = get_storage_root()
    edit_request_path = storage_root / "derived" / project_id / "edit_request.json"

    if edit_request_path.exists():
        edit_request_path.unlink()
        logger.info(f"Deleted EditRequest for project {project_id}")
