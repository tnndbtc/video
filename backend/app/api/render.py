"""
Render API endpoints for BeatStitch.

Provides endpoints for starting render jobs, checking status, and downloading
rendered videos. All endpoints require authentication and verify project ownership.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_db
from app.core.queue import (
    enqueue_render_preview,
    enqueue_render_final,
    get_job_status,
    get_progress,
)
from app.core.rate_limit import ROUTE_CATEGORIES
from app.core.storage import get_storage_root
from app.models.job import RenderJob
from app.models.project import Project
from app.models.timeline import Timeline
from app.models.user import User
from app.models.media import MediaAsset
from app.rules import parse_user_rule
from app.schemas.render import (
    RenderConflictResponse,
    RenderJobStatus,
    RenderNotFoundResponse,
    RenderPreconditionFailedResponse,
    RenderRequest,
    RenderResponse,
)

router = APIRouter()

# Register route names for rate limiting
ROUTE_CATEGORIES["start_render"] = "render"


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


async def get_project_with_timeline(
    project_id: str,
    db: AsyncSession,
    user: User,
) -> Project:
    """
    Get a project with its timeline loaded.

    Args:
        project_id: The project UUID
        db: Database session
        user: Current authenticated user

    Returns:
        Project object with timeline relationship loaded

    Raises:
        HTTPException 404: If project not found or not owned by user
    """
    query = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.timeline))
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


async def get_in_progress_render_job(
    project_id: str,
    job_type: str,
    db: AsyncSession,
) -> RenderJob | None:
    """
    Check if there's an in-progress render job of the given type.

    Args:
        project_id: The project UUID
        job_type: Either "preview" or "final"
        db: Database session

    Returns:
        RenderJob if one is in progress, None otherwise
    """
    query = select(RenderJob).where(
        RenderJob.project_id == project_id,
        RenderJob.job_type == job_type,
        RenderJob.status.in_(["queued", "running"]),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_completed_render_job(
    project_id: str,
    job_type: str,
    db: AsyncSession,
) -> RenderJob | None:
    """
    Get the most recent completed render job of the given type.

    Args:
        project_id: The project UUID
        job_type: Either "preview" or "final"
        db: Database session

    Returns:
        Most recent completed RenderJob, or None if not found
    """
    query = (
        select(RenderJob)
        .where(
            RenderJob.project_id == project_id,
            RenderJob.job_type == job_type,
            RenderJob.status == "complete",
        )
        .order_by(RenderJob.completed_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


def get_render_settings_snapshot(project: Project) -> str:
    """
    Create a JSON snapshot of the current render settings.

    Args:
        project: Project to capture settings from

    Returns:
        JSON string of render settings
    """
    settings = {
        "beats_per_cut": project.beats_per_cut,
        "transition_type": project.transition_type,
        "transition_duration_ms": project.transition_duration_ms,
        "ken_burns_enabled": project.ken_burns_enabled,
        "output_width": project.output_width,
        "output_height": project.output_height,
        "output_fps": project.output_fps,
    }
    return json.dumps(settings)


# The actual render task is in the worker service:
# worker/app/tasks/render.py::render_video
# We pass the function path as a string to RQ
RENDER_VIDEO_TASK = "app.tasks.render.render_video"


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{project_id}/render",
    response_model=RenderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    name="start_render",
    summary="Start render job",
    description="Start a render job (preview or final). Timeline is auto-generated during render.",
    responses={
        400: {
            "model": RenderPreconditionFailedResponse,
            "description": "Project has no media for rendering",
        },
        409: {
            "description": "Render already in progress",
            "content": {
                "application/json": {
                    "examples": {
                        "render_in_progress": {
                            "summary": "Render already in progress",
                            "value": {
                                "error": "conflict",
                                "message": "Render job already in progress",
                                "existing_job_id": "job_abc123",
                            },
                        },
                    }
                }
            },
        },
    },
)
async def start_render(
    project_id: str,
    request: RenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RenderResponse:
    """
    Start a render job for a project.

    Timeline is now auto-generated as part of the render process,
    ensuring the render always uses the latest project state.

    Steps:
    1. Verify project exists and user owns it
    2. Verify project has media assets
    3. Check for existing in-progress render job of same type
    4. Create RenderJob record in database
    5. Enqueue render task (which will generate timeline + render)
    6. Return 202 with job details
    """
    # 1. Get project
    project = await get_project_or_404(project_id, db, current_user)

    # 2. Check if project has any processed media assets
    media_query = select(MediaAsset).where(
        MediaAsset.project_id == project_id,
        MediaAsset.processing_status == "ready",
    ).limit(1)
    media_result = await db.execute(media_query)
    has_media = media_result.scalar_one_or_none() is not None

    if not has_media:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "precondition_failed",
                "message": "No media available for rendering",
                "details": {"has_media": False},
            },
        )

    # 3. Check for existing in-progress render job of same type
    existing_job = await get_in_progress_render_job(project_id, request.type, db)
    if existing_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "message": "Render job already in progress",
                "existing_job_id": existing_job.id,
            },
        )

    # 4. Create RenderJob record (edl_hash will be set during render)
    render_settings = get_render_settings_snapshot(project)
    render_job = RenderJob(
        project_id=project_id,
        job_type=request.type,
        edl_hash="pending",  # Will be set by worker during timeline generation
        render_settings_json=render_settings,
        status="queued",
        progress_percent=0,
    )

    db.add(render_job)
    await db.flush()
    await db.refresh(render_job)

    # 4b. Build render_plan.json with timeline settings
    # Include timeline_media_ids from project, rule_text, and video_length_seconds
    try:
        if request.rule_text:
            render_plan = parse_user_rule(request.rule_text)
        else:
            render_plan = {}

        # Add video_length_seconds to render plan
        if request.video_length_seconds:
            render_plan["video_length_seconds"] = request.video_length_seconds

        # Add timeline_media_ids from project (the user's timeline preview order)
        # DEBUG: Log what we're reading from project
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"DEBUG: project.timeline_media_ids = {project.timeline_media_ids}")

        if project.timeline_media_ids:
            render_plan["timeline_media_ids"] = project.timeline_media_ids
            logger.warning(f"DEBUG: Added timeline_media_ids to render_plan: {project.timeline_media_ids}")
        else:
            logger.warning("DEBUG: No timeline_media_ids found on project!")

        # Save render_plan to filesystem
        storage_root = get_storage_root()
        derived_dir = storage_root / "derived" / project_id
        derived_dir.mkdir(parents=True, exist_ok=True)
        render_plan_path = derived_dir / "render_plan.json"
        with open(render_plan_path, "w") as f:
            json.dump(render_plan, f, indent=2)
        logger.warning(f"DEBUG: Saved render_plan.json: {render_plan}")
    except Exception as e:
        # If parsing fails, continue without render plan (will use natural duration)
        import logging
        logging.getLogger(__name__).warning(f"DEBUG: Exception in render_plan: {e}")
        pass

    # 5. Enqueue render task (no edl_hash needed - timeline generated during render)
    try:
        if request.type == "preview":
            rq_job = enqueue_render_preview(
                project_id=project_id,
                edl_hash="pending",  # Placeholder - worker will generate
                func=RENDER_VIDEO_TASK,
                job_id=f"render_preview_{render_job.id}",
            )
        else:  # final
            rq_job = enqueue_render_final(
                project_id=project_id,
                edl_hash="pending",  # Placeholder - worker will generate
                func=RENDER_VIDEO_TASK,
                job_id=f"render_final_{render_job.id}",
            )

        # Update render job with RQ job ID
        render_job.rq_job_id = rq_job.id
        await db.flush()

    except Exception as e:
        # If enqueueing fails, mark the job as failed
        render_job.status = "failed"
        render_job.error_message = f"Failed to enqueue render job: {str(e)}"
        await db.flush()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Failed to enqueue render job",
            },
        )

    # 6. Return response
    return RenderResponse(
        job_id=render_job.id,
        job_type=render_job.job_type,
        status="queued",
        created_at=render_job.created_at,
    )


@router.get(
    "/{project_id}/render/{render_type}/status",
    response_model=RenderJobStatus,
    summary="Get latest render status by type",
    description="Get the status of the most recent render job of the specified type (preview or final). Returns status='idle' if no render job exists.",
)
async def get_render_status_by_type(
    project_id: str,
    render_type: Literal["preview", "final"],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RenderJobStatus:
    """
    Get the status of the most recent render job of the specified type.

    This is useful for checking if a render is in progress or getting
    the result of the last render without knowing the job ID.

    Returns status='idle' if no render job of this type exists yet.

    NOTE: This route MUST be defined before /{job_id}/status to ensure
    'preview' and 'final' are matched as render_type, not job_id.
    """
    # Verify project ownership
    await get_project_or_404(project_id, db, current_user)

    # Get the most recent render job of this type (any status)
    query = (
        select(RenderJob)
        .where(
            RenderJob.project_id == project_id,
            RenderJob.job_type == render_type,
        )
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    render_job = result.scalar_one_or_none()

    if render_job is None:
        # No render job exists yet - return idle status
        return RenderJobStatus(
            status="idle",
            progress_percent=0,
        )

    # Get progress from Redis if job is running
    progress_message = render_job.progress_message
    progress_percent = render_job.progress_percent

    if render_job.rq_job_id and render_job.status == "running":
        progress = get_progress(render_job.rq_job_id)
        if progress:
            progress_percent = progress.get("percent", progress_percent)
            progress_message = progress.get("message", progress_message)

    # Build output URL if complete
    output_url = None
    if render_job.status == "complete" and render_job.output_path:
        output_url = f"/api/projects/{project_id}/render/{render_job.job_type}/download"

    return RenderJobStatus(
        id=render_job.id,
        project_id=render_job.project_id,
        job_type=render_job.job_type,
        status=render_job.status,
        edl_hash=render_job.edl_hash,
        progress_percent=progress_percent,
        progress_message=progress_message,
        output_url=output_url,
        file_size=render_job.file_size,
        error=render_job.error_message,
        created_at=render_job.created_at,
        started_at=render_job.started_at,
        completed_at=render_job.completed_at,
    )


@router.get(
    "/{project_id}/render/{job_id}/status",
    response_model=RenderJobStatus,
    summary="Get render job status by ID",
    description="Get the current status of a specific render job by its ID.",
    responses={
        404: {"model": RenderNotFoundResponse, "description": "Render job not found"},
    },
)
async def get_render_job_status(
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RenderJobStatus:
    """
    Get the status of a specific render job.

    Returns progress information for polling during rendering.
    """
    # Verify project ownership
    await get_project_or_404(project_id, db, current_user)

    # Get the render job
    query = select(RenderJob).where(
        RenderJob.id == job_id,
        RenderJob.project_id == project_id,
    )
    result = await db.execute(query)
    render_job = result.scalar_one_or_none()

    if render_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Render job not found",
                "details": {"job_id": job_id, "project_id": project_id},
            },
        )

    # Get progress from Redis if job is running
    progress_message = render_job.progress_message
    progress_percent = render_job.progress_percent

    if render_job.rq_job_id and render_job.status == "running":
        progress = get_progress(render_job.rq_job_id)
        if progress:
            progress_percent = progress.get("percent", progress_percent)
            progress_message = progress.get("message", progress_message)

    # Build output URL if complete
    output_url = None
    if render_job.status == "complete" and render_job.output_path:
        output_url = f"/api/projects/{project_id}/render/{render_job.job_type}/download"

    return RenderJobStatus(
        id=render_job.id,
        project_id=render_job.project_id,
        job_type=render_job.job_type,
        status=render_job.status,
        edl_hash=render_job.edl_hash,
        progress_percent=progress_percent,
        progress_message=progress_message,
        output_url=output_url,
        file_size=render_job.file_size,
        error=render_job.error_message,
        created_at=render_job.created_at,
        started_at=render_job.started_at,
        completed_at=render_job.completed_at,
    )


@router.get(
    "/{project_id}/render/{render_type}/download",
    summary="Download rendered video",
    description="Download the rendered video file (preview or final).",
    responses={
        200: {"content": {"video/mp4": {}}},
        404: {
            "model": RenderNotFoundResponse,
            "description": "Render not complete or not found",
        },
    },
)
async def download_render(
    project_id: str,
    render_type: Literal["preview", "final"],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FileResponse:
    """
    Download the rendered video.

    Returns the most recent completed render of the specified type.
    The file is returned with Content-Disposition: attachment.
    """
    # Verify project ownership
    project = await get_project_or_404(project_id, db, current_user)

    # Get the most recent completed render job of this type
    render_job = await get_completed_render_job(project_id, render_type, db)

    if render_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"No completed {render_type} render found",
                "details": {
                    "render_type": render_type,
                    "hint": f"POST /api/projects/{project_id}/render to start a render",
                },
            },
        )

    if not render_job.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Render output file path not found",
                "details": {"job_id": render_job.id},
            },
        )

    # Resolve the file path
    storage_root = get_storage_root()
    file_path = storage_root / render_job.output_path

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Render output file not found on filesystem",
                "details": {"job_id": render_job.id},
            },
        )

    # Generate download filename
    safe_project_name = "".join(
        c if c.isalnum() or c in "._- " else "_" for c in project.name
    )[:50]
    filename = f"{safe_project_name}_{render_type}.mp4"

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
