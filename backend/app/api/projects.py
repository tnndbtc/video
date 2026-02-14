"""
Project CRUD endpoints for BeatStitch.

Provides endpoints for creating, reading, updating, and deleting video projects.
All endpoints require authentication and verify project ownership.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_db
from app.models.audio import AudioTrack
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.timeline import Timeline
from app.models.user import User
from app.schemas.project import (
    AudioStatus,
    AudioTrackSummary,
    MediaAssetSummary,
    MediaStatusCounts,
    ProjectCreate,
    ProjectListItem,
    ProjectListResponse,
    ProjectResponse,
    ProjectSettings,
    ProjectSettingsResponse,
    ProjectSettingsUpdate,
    ProjectStatusResponse,
    ProjectUpdate,
    TimelineStatus,
    TimelineSummary,
)

router = APIRouter()


# =============================================================================
# Helper Functions
# =============================================================================


async def get_project_or_404(
    project_id: str,
    db: AsyncSession,
    user: User,
    load_relations: bool = False,
) -> Project:
    """
    Get a project by ID, verifying ownership.

    Args:
        project_id: The project UUID
        db: Database session
        user: Current authenticated user
        load_relations: Whether to eagerly load media_assets, audio_track, timeline

    Returns:
        Project object if found and owned by user

    Raises:
        HTTPException 404: If project not found or not owned by user
    """
    query = select(Project).where(Project.id == project_id)

    if load_relations:
        query = query.options(
            selectinload(Project.media_assets),
            selectinload(Project.audio_track),
            selectinload(Project.timeline),
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


def project_to_settings(project: Project) -> ProjectSettings:
    """Extract settings from a project model."""
    return ProjectSettings(
        beats_per_cut=project.beats_per_cut,
        transition_type=project.transition_type,
        transition_duration_ms=project.transition_duration_ms,
        ken_burns_enabled=project.ken_burns_enabled,
        output_width=project.output_width,
        output_height=project.output_height,
        output_fps=project.output_fps,
    )


def media_asset_to_summary(asset: MediaAsset) -> MediaAssetSummary:
    """Convert a MediaAsset to its summary representation."""
    thumbnail_url = None
    if asset.thumbnail_path:
        thumbnail_url = f"/api/media/{asset.id}/thumbnail"

    return MediaAssetSummary(
        id=asset.id,
        filename=asset.filename,
        original_filename=asset.original_filename,
        media_type=asset.media_type,
        processing_status=asset.processing_status,
        processing_error=asset.processing_error,
        width=asset.width,
        height=asset.height,
        duration_ms=asset.duration_ms,
        fps=asset.fps,
        file_size=asset.file_size,
        thumbnail_url=thumbnail_url,
        sort_order=asset.sort_order,
    )


def audio_track_to_summary(audio: AudioTrack) -> AudioTrackSummary:
    """Convert an AudioTrack to its summary representation."""
    return AudioTrackSummary(
        id=audio.id,
        filename=audio.original_filename,
        duration_ms=audio.duration_ms,
        bpm=audio.bpm,
        analysis_status=audio.analysis_status,
    )


def timeline_to_summary(timeline: Timeline) -> TimelineSummary:
    """Convert a Timeline to its summary representation."""
    return TimelineSummary(
        id=timeline.id,
        segment_count=timeline.segment_count,
        total_duration_ms=timeline.total_duration_ms,
        edl_hash=timeline.edl_hash,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List all projects",
    description="Get all projects for the current authenticated user.",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectListResponse:
    """
    List all projects for the current user.

    Returns project summaries with media count and audio status.
    """
    # Query projects with counts
    query = (
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.updated_at.desc().nullsfirst(), Project.created_at.desc())
    )
    result = await db.execute(query)
    projects = result.scalars().all()

    # Build response with media counts
    project_items = []
    for project in projects:
        # Count media assets for this project
        media_count_result = await db.execute(
            select(func.count(MediaAsset.id)).where(
                MediaAsset.project_id == project.id
            )
        )
        media_count = media_count_result.scalar() or 0

        # Check if audio exists
        audio_result = await db.execute(
            select(AudioTrack.id).where(AudioTrack.project_id == project.id)
        )
        has_audio = audio_result.scalar_one_or_none() is not None

        project_items.append(
            ProjectListItem(
                id=project.id,
                name=project.name,
                status=project.status,
                media_count=media_count,
                has_audio=has_audio,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )

    return ProjectListResponse(
        projects=project_items,
        total=len(project_items),
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new project",
    description="Create a new video editing project with default settings.",
)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectResponse:
    """
    Create a new project for the current user.

    The project is created with default settings which can be updated later.
    """
    project = Project(
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
        status="draft",
    )

    db.add(project)
    await db.flush()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        settings=project_to_settings(project),
        media_assets=[],
        audio_track=None,
        timeline=None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details",
    description="Get full project details including media, audio, and timeline summary.",
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectResponse:
    """
    Get a project by ID with all related data.

    Includes media assets, audio track summary, and timeline summary.
    """
    project = await get_project_or_404(
        project_id, db, current_user, load_relations=True
    )

    # Convert media assets
    media_summaries = [
        media_asset_to_summary(asset)
        for asset in sorted(project.media_assets, key=lambda a: a.sort_order)
    ]

    # Convert audio track if present
    audio_summary = None
    if project.audio_track:
        audio_summary = audio_track_to_summary(project.audio_track)

    # Convert timeline if present
    timeline_summary = None
    if project.timeline:
        timeline_summary = timeline_to_summary(project.timeline)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        settings=project_to_settings(project),
        media_assets=media_summaries,
        audio_track=audio_summary,
        timeline=timeline_summary,
        timeline_media_ids=project.timeline_media_ids,
        video_length_seconds=project.video_length_seconds,
        rule_text=project.rule_text,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project",
    description="Update project name, description, and timeline preview settings.",
)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectResponse:
    """
    Update project fields including timeline preview settings.
    """
    project = await get_project_or_404(project_id, db, current_user, load_relations=True)

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(project)

    # Build response with all relations
    media_summaries = [media_asset_to_summary(m) for m in project.media_assets]
    audio_summary = audio_track_to_summary(project.audio_track) if project.audio_track else None
    timeline_summary = timeline_to_summary(project.timeline) if project.timeline else None

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        settings=project_to_settings(project),
        media_assets=media_summaries,
        audio_track=audio_summary,
        timeline=timeline_summary,
        timeline_media_ids=project.timeline_media_ids,
        video_length_seconds=project.video_length_seconds,
        rule_text=project.rule_text,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.patch(
    "/{project_id}/settings",
    response_model=ProjectSettingsResponse,
    summary="Update project settings",
    description="Update project settings. Returns timeline_invalidated flag when settings change.",
)
async def update_project_settings(
    project_id: str,
    data: ProjectSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectSettingsResponse:
    """
    Update project settings.

    Only provided fields are updated. Timeline-affecting changes
    (beats_per_cut, transition_type, ken_burns_enabled) set
    timeline_invalidated=true in response.
    """
    project = await get_project_or_404(project_id, db, current_user)

    # Track if timeline-affecting settings changed
    timeline_invalidated = False
    timeline_affecting_fields = {
        "beats_per_cut",
        "transition_type",
        "transition_duration_ms",
        "ken_burns_enabled",
        "output_width",
        "output_height",
        "output_fps",
    }

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            current_value = getattr(project, field)
            if current_value != value:
                setattr(project, field, value)
                if field in timeline_affecting_fields:
                    timeline_invalidated = True

    # Update timestamp
    project.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(project)

    return ProjectSettingsResponse(
        id=project.id,
        settings=project_to_settings(project),
        timeline_invalidated=timeline_invalidated,
        updated_at=project.updated_at,
    )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    description="Delete a project and all associated data (media, audio, timeline).",
)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete a project and all associated data.

    This permanently deletes the project along with all media assets,
    audio tracks, timelines, and render jobs.
    """
    project = await get_project_or_404(project_id, db, current_user)

    await db.delete(project)
    await db.flush()

    # Return 204 No Content (no response body)
    return None


@router.get(
    "/{project_id}/status",
    response_model=ProjectStatusResponse,
    summary="Get project status",
    description="Lightweight status check for project processing state.",
)
async def get_project_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectStatusResponse:
    """
    Get lightweight project status.

    Returns media processing counts, audio analysis status,
    timeline generation status, and whether the project is ready to render.
    """
    project = await get_project_or_404(project_id, db, current_user)

    # Get media counts by status
    # Note: Since MediaAsset doesn't have processing_status field yet,
    # we count all media as "ready"
    media_count_result = await db.execute(
        select(func.count(MediaAsset.id)).where(MediaAsset.project_id == project_id)
    )
    total_media = media_count_result.scalar() or 0

    # For now, all media in DB is considered ready (no processing_status field)
    media_counts = MediaStatusCounts(
        total=total_media,
        pending=0,
        processing=0,
        ready=total_media,
        failed=0,
    )

    # Get audio status
    audio_result = await db.execute(
        select(AudioTrack).where(AudioTrack.project_id == project_id)
    )
    audio = audio_result.scalar_one_or_none()

    audio_status = AudioStatus(
        uploaded=audio is not None,
        analysis_status=audio.analysis_status if audio else None,
    )

    # Get timeline status
    timeline_result = await db.execute(
        select(Timeline).where(Timeline.project_id == project_id)
    )
    timeline = timeline_result.scalar_one_or_none()

    timeline_status = TimelineStatus(
        generated=timeline is not None,
        edl_hash=timeline.edl_hash if timeline else None,
        stale=False,  # TODO: Implement stale detection based on settings/media changes
    )

    # Determine if ready to render
    # Ready when: has media, audio analysis complete, timeline generated and not stale
    ready_to_render = (
        total_media > 0
        and audio is not None
        and audio.analysis_status == "complete"
        and timeline is not None
        and not timeline_status.stale
    )

    return ProjectStatusResponse(
        project_id=project_id,
        media=media_counts,
        audio=audio_status,
        timeline=timeline_status,
        ready_to_render=ready_to_render,
    )
