"""
Timeline API endpoints for BeatStitch.

Provides endpoints for generating and retrieving timelines (EDLs).
All endpoints require authentication and verify project ownership.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_db
from app.core.queue import enqueue_timeline_generation, get_progress, get_job_status
from app.core.rate_limit import ROUTE_CATEGORIES
from app.core.storage import get_storage_root
from app.models.audio import AudioTrack
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.timeline import Timeline
from app.models.user import User
from app.schemas.timeline import (
    TimelineGenerateConflictResponse,
    TimelineGeneratePreconditionResponse,
    TimelineGenerateResponse,
    TimelineNotFoundResponse,
    TimelineResponse,
    TimelineSegment,
    TimelineSettingsUsed,
    TimelineStatusResponse,
    TimelineEffects,
    TimelineTransition,
)

router = APIRouter()

# Register route names for rate limiting
ROUTE_CATEGORIES["generate_timeline"] = "analyze"


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


async def get_project_with_relations(
    project_id: str,
    db: AsyncSession,
    user: User,
) -> Project:
    """
    Get a project with its related data (media_assets, audio_track, timeline).

    Args:
        project_id: The project UUID
        db: Database session
        user: Current authenticated user

    Returns:
        Project object with related data loaded

    Raises:
        HTTPException 404: If project not found or not owned by user
    """
    query = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.media_assets),
            selectinload(Project.audio_track),
            selectinload(Project.timeline),
        )
    )
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


# The actual timeline generation task is in the worker service:
# worker/app/tasks/timeline.py::generate_timeline
# We pass the function path as a string to RQ
TIMELINE_GENERATION_TASK = "app.tasks.timeline.generate_timeline"


def load_edl_segments(edl_path: str) -> List[Dict[str, Any]]:
    """
    Load segments from an EDL JSON file.

    Args:
        edl_path: Path to the edl.json file (relative to storage root)

    Returns:
        List of segment dictionaries from the EDL

    Raises:
        HTTPException 500: If EDL file cannot be read or parsed
    """
    storage_root = get_storage_root()
    full_path = storage_root / edl_path

    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "EDL file not found on filesystem",
            },
        )

    try:
        with open(full_path, "r") as f:
            edl_data = json.load(f)
        return edl_data.get("segments", [])
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Failed to read EDL file",
            },
        )


def get_generation_job_id(project_id: str) -> str:
    """Generate a consistent job ID for timeline generation."""
    return f"timeline_{project_id}"


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{project_id}/timeline/generate",
    response_model=TimelineGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    name="generate_timeline",
    summary="Generate timeline",
    description="Trigger timeline generation from media and beats. This is an async operation.",
    responses={
        400: {"model": TimelineGeneratePreconditionResponse, "description": "Prerequisites not met"},
        409: {"model": TimelineGenerateConflictResponse, "description": "Generation already in progress"},
    },
)
async def generate_timeline(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TimelineGenerateResponse:
    """
    Trigger timeline generation for a project.

    Prerequisites:
    - Project must have audio uploaded with beat analysis complete
    - Project must have at least one media asset that is ready

    Returns 202 Accepted with job_id on success.
    Returns 400 if prerequisites are not met.
    Returns 409 if generation is already in progress.
    """
    # Get project with related data
    project = await get_project_with_relations(project_id, db, current_user)

    # Check if there's already a generation in progress
    job_id = get_generation_job_id(project_id)
    job_status = get_job_status(job_id)

    if job_status is not None:
        status_value = job_status.get("status", "")
        if status_value in ("queued", "started"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "conflict",
                    "message": "Timeline generation already in progress",
                    "existing_job_id": job_id,
                },
            )

    # Check prerequisites: audio uploaded and analyzed
    audio = project.audio_track
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "precondition_failed",
                "message": "Cannot generate timeline",
                "details": {
                    "audio_uploaded": False,
                    "beats_complete": False,
                },
            },
        )

    if audio.analysis_status != "complete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "precondition_failed",
                "message": "Cannot generate timeline",
                "details": {
                    "audio_uploaded": True,
                    "beats_complete": False,
                    "analysis_status": audio.analysis_status,
                },
            },
        )

    # Check prerequisites: at least one ready media asset
    media_assets = project.media_assets or []
    ready_assets = [m for m in media_assets if m.processing_status == "ready"]
    pending_assets = [m for m in media_assets if m.processing_status in ("pending", "processing")]

    if len(ready_assets) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "precondition_failed",
                "message": "Cannot generate timeline",
                "details": {
                    "audio_uploaded": True,
                    "beats_complete": True,
                    "media_ready": False,
                    "media_pending": len(pending_assets),
                    "media_total": len(media_assets),
                },
            },
        )

    # All prerequisites met - enqueue the job
    try:
        enqueue_timeline_generation(
            project_id=project_id,
            func=TIMELINE_GENERATION_TASK,
            job_id=job_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Failed to enqueue timeline generation job",
            },
        )

    return TimelineGenerateResponse(
        job_id=job_id,
        status="queued",
        message="Timeline generation queued",
    )


@router.get(
    "/{project_id}/timeline",
    response_model=TimelineResponse,
    summary="Get timeline with EDL",
    description="Get the full timeline with all segments. Only available after generation completes.",
    responses={
        404: {"model": TimelineNotFoundResponse, "description": "Timeline not generated"},
    },
)
async def get_timeline(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TimelineResponse:
    """
    Get the full timeline with segments.

    Returns the complete timeline including all segment data from the EDL.
    The edl_hash is included and required for rendering operations.
    """
    # Get project with timeline
    project = await get_project_with_relations(project_id, db, current_user)

    # Check if timeline exists
    timeline = project.timeline
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Timeline not generated",
                "hint": f"POST /api/projects/{project_id}/timeline/generate to create timeline",
            },
        )

    # Load segments from EDL file
    raw_segments = load_edl_segments(timeline.edl_path)

    # Build segment response objects
    segments: List[TimelineSegment] = []
    for seg in raw_segments:
        # Build effects object
        effects = None
        if seg.get("effects"):
            effects = TimelineEffects(
                ken_burns=seg["effects"].get("ken_burns")
            )

        # Build transition object
        transition_in = None
        if seg.get("transition_in"):
            transition_in = TimelineTransition(
                type=seg["transition_in"].get("type", "cut"),
                duration_ms=seg["transition_in"].get("duration_ms", 0),
            )

        segment = TimelineSegment(
            index=seg.get("index", 0),
            media_asset_id=seg.get("media_asset_id", ""),
            media_type=seg.get("media_type", "image"),
            thumbnail_url=f"/api/media/{seg.get('media_asset_id', '')}/thumbnail",
            timeline_in_ms=seg.get("timeline_in_ms", 0),
            timeline_out_ms=seg.get("timeline_out_ms", 0),
            render_duration_ms=seg.get("render_duration_ms", 0),
            source_in_ms=seg.get("source_in_ms", 0),
            source_out_ms=seg.get("source_out_ms", 0),
            effects=effects,
            transition_in=transition_in,
        )
        segments.append(segment)

    # Build settings used object
    settings_used = TimelineSettingsUsed(
        beats_per_cut=project.beats_per_cut,
        transition_type=project.transition_type,
    )

    return TimelineResponse(
        id=timeline.id,
        edl_hash=timeline.edl_hash,
        segment_count=timeline.segment_count,
        total_duration_ms=timeline.total_duration_ms,
        segments=segments,
        settings_used=settings_used,
        generated_at=timeline.generated_at,
    )


@router.get(
    "/{project_id}/timeline/status",
    response_model=TimelineStatusResponse,
    summary="Get timeline status",
    description="Lightweight status check for timeline generation (for polling).",
)
async def get_timeline_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TimelineStatusResponse:
    """
    Get lightweight timeline generation status.

    Returns only the generation status and basic info, useful for polling
    during timeline generation.

    Generation status values:
    - "none": No timeline and no generation in progress
    - "queued": Generation job queued but not started
    - "generating": Generation in progress
    - "ready": Timeline is generated and ready
    - "failed": Generation failed
    """
    # Get project with timeline
    project = await get_project_with_relations(project_id, db, current_user)

    timeline = project.timeline
    job_id = get_generation_job_id(project_id)

    # Check for active job
    job_status = get_job_status(job_id)

    # Case 1: Timeline exists and is ready
    if timeline is not None:
        # Check if there's a new job running (regeneration)
        if job_status is not None:
            status_value = job_status.get("status", "")
            if status_value == "queued":
                return TimelineStatusResponse(
                    project_id=project_id,
                    generated=True,
                    generation_status="queued",
                    generation_job_id=job_id,
                    # Include existing timeline info
                    edl_hash=timeline.edl_hash,
                    segment_count=timeline.segment_count,
                    total_duration_ms=timeline.total_duration_ms,
                    generated_at=timeline.generated_at,
                )
            elif status_value == "started":
                progress = job_status.get("progress")
                progress_percent = progress.get("percent", 0) if progress else None
                return TimelineStatusResponse(
                    project_id=project_id,
                    generated=True,
                    generation_status="generating",
                    generation_job_id=job_id,
                    progress_percent=progress_percent,
                    # Include existing timeline info
                    edl_hash=timeline.edl_hash,
                    segment_count=timeline.segment_count,
                    total_duration_ms=timeline.total_duration_ms,
                    generated_at=timeline.generated_at,
                )
            elif status_value == "failed":
                error_msg = job_status.get("error", "Timeline generation failed")
                return TimelineStatusResponse(
                    project_id=project_id,
                    generated=True,
                    generation_status="failed",
                    generation_job_id=job_id,
                    error_message=error_msg,
                    # Include existing timeline info (from before failure)
                    edl_hash=timeline.edl_hash,
                    segment_count=timeline.segment_count,
                    total_duration_ms=timeline.total_duration_ms,
                    generated_at=timeline.generated_at,
                )

        # No active job - timeline is ready
        # Check if timeline is stale (settings changed since generation)
        stale = False
        stale_reason = None

        # Compare modification times
        if project.updated_at and timeline.generated_at:
            if project.updated_at > timeline.generated_at:
                stale = True
                stale_reason = "Project settings changed since generation"

        return TimelineStatusResponse(
            project_id=project_id,
            generated=True,
            generation_status="ready",
            edl_hash=timeline.edl_hash,
            segment_count=timeline.segment_count,
            total_duration_ms=timeline.total_duration_ms,
            stale=stale,
            stale_reason=stale_reason,
            generated_at=timeline.generated_at,
        )

    # Case 2: No timeline - check for active job
    if job_status is not None:
        status_value = job_status.get("status", "")

        if status_value == "queued":
            return TimelineStatusResponse(
                project_id=project_id,
                generated=False,
                generation_status="queued",
                generation_job_id=job_id,
            )
        elif status_value == "started":
            progress = job_status.get("progress")
            progress_percent = progress.get("percent", 0) if progress else None
            return TimelineStatusResponse(
                project_id=project_id,
                generated=False,
                generation_status="generating",
                generation_job_id=job_id,
                progress_percent=progress_percent,
            )
        elif status_value == "failed":
            error_msg = job_status.get("error", "Timeline generation failed")
            return TimelineStatusResponse(
                project_id=project_id,
                generated=False,
                generation_status="failed",
                generation_job_id=job_id,
                error_message=error_msg,
            )

    # Case 3: No timeline and no active job
    return TimelineStatusResponse(
        project_id=project_id,
        generated=False,
        generation_status="none",
    )
