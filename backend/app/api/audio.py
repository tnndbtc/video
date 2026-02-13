"""
Audio Upload API endpoints for BeatStitch.

Provides endpoints for uploading audio files and managing beat analysis.
All endpoints require authentication and verify project ownership.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.queue import enqueue_beat_analysis, get_progress, get_job_status
from app.core.rate_limit import ROUTE_CATEGORIES
from app.core.storage import (
    ALLOWED_EXTENSIONS,
    generate_safe_path,
    get_storage_root,
    sanitize_filename,
    validate_file_type,
    validate_project_id,
)
from app.models.audio import AudioTrack
from app.models.project import Project
from app.models.user import User
from app.schemas.audio import (
    AnalyzeConflictResponse,
    AnalyzeResponse,
    AudioUploadResponse,
    Beat,
    BeatsNotFoundError,
    BeatsResponse,
    BeatsStatusResponse,
)

router = APIRouter()

# Register route names for rate limiting
ROUTE_CATEGORIES["upload_audio"] = "upload"
ROUTE_CATEGORIES["analyze_audio"] = "analyze"

# Maximum file size for audio uploads (100MB)
MAX_AUDIO_SIZE = 100 * 1024 * 1024

# Allowed audio extensions (defined in storage.py but repeated here for clarity)
ALLOWED_AUDIO_EXTENSIONS = ALLOWED_EXTENSIONS["audio"]


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


async def get_audio_track_or_404(
    project_id: str,
    db: AsyncSession,
) -> AudioTrack:
    """
    Get an audio track for a project.

    Args:
        project_id: The project UUID
        db: Database session

    Returns:
        AudioTrack object if found

    Raises:
        HTTPException 404: If audio track not found
    """
    query = select(AudioTrack).where(AudioTrack.project_id == project_id)
    result = await db.execute(query)
    audio = result.scalar_one_or_none()

    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Audio track not found for this project",
                "resource_type": "audio_track",
                "project_id": project_id,
            },
        )

    return audio


def get_audio_duration_ms(file_path: str) -> int:
    """
    Get audio duration in milliseconds using mutagen.

    Falls back to a default value if detection fails.
    """
    try:
        from mutagen import File as MutagenFile
        audio_file = MutagenFile(file_path)
        if audio_file is not None and audio_file.info is not None:
            return int(audio_file.info.length * 1000)
    except Exception:
        pass
    # Default to 0 - will be updated by worker
    return 0


def get_audio_sample_rate(file_path: str) -> Optional[int]:
    """
    Get audio sample rate using mutagen.
    """
    try:
        from mutagen import File as MutagenFile
        audio_file = MutagenFile(file_path)
        if audio_file is not None and audio_file.info is not None:
            return getattr(audio_file.info, 'sample_rate', None)
    except Exception:
        pass
    return None


# The actual beat analysis task is in the worker service:
# worker/app/tasks/beat_analysis.py::analyze_beats
# We pass the function path as a string to RQ
BEAT_ANALYSIS_TASK = "app.tasks.beat_analysis.analyze_beats"


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{project_id}/audio",
    response_model=AudioUploadResponse,
    status_code=status.HTTP_201_CREATED,
    name="upload_audio",
    summary="Upload audio file",
    description="Upload an audio track for beat-synced editing. Replaces existing audio. Beat analysis starts automatically.",
)
async def upload_audio(
    project_id: str,
    file: UploadFile = File(..., description="Audio file (mp3, wav, flac, aac, ogg, m4a)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AudioUploadResponse:
    """
    Upload an audio file to a project.

    - Accepts audio files (mp3, wav, flac, aac, ogg, m4a)
    - Replaces any existing audio track for the project
    - Automatically triggers beat analysis job
    - Returns the audio track record with analysis_status: queued
    """
    # Validate project exists and user owns it
    project = await get_project_or_404(project_id, db, current_user)

    # Validate project_id format
    if not validate_project_id(project_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "Invalid project ID format",
            },
        )

    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "Filename is required",
            },
        )

    if not validate_file_type(file.filename, "audio"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": f"Invalid file type. Allowed audio formats: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
            },
        )

    # Check content type
    content_type = file.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "File must be an audio file",
            },
        )

    # Read file content and check size
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "message": f"File exceeds maximum size of {MAX_AUDIO_SIZE // (1024 * 1024)}MB",
                "max_size_bytes": MAX_AUDIO_SIZE,
            },
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "File is empty",
            },
        )

    # Generate safe storage path
    safe_path = generate_safe_path(project_id, "audio", file.filename)

    # Ensure directory exists
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file to disk
    async with aiofiles.open(safe_path, "wb") as f:
        await f.write(content)

    # Get audio metadata
    duration_ms = get_audio_duration_ms(str(safe_path))
    sample_rate = get_audio_sample_rate(str(safe_path))

    # Check if there's an existing audio track to replace
    existing_audio_result = await db.execute(
        select(AudioTrack).where(AudioTrack.project_id == project_id)
    )
    existing_audio = existing_audio_result.scalar_one_or_none()

    if existing_audio:
        # Delete old file if it exists
        old_file_path = Path(get_storage_root()) / existing_audio.file_path
        if old_file_path.exists():
            try:
                old_file_path.unlink()
            except OSError:
                pass  # Ignore errors deleting old file

        # Delete old beats.json if it exists
        if existing_audio.beat_grid_path:
            old_beats_path = Path(get_storage_root()) / existing_audio.beat_grid_path
            if old_beats_path.exists():
                try:
                    old_beats_path.unlink()
                except OSError:
                    pass

        # Delete existing audio record
        await db.delete(existing_audio)
        await db.flush()

    # Calculate relative path for storage
    storage_root = get_storage_root()
    relative_path = str(safe_path.relative_to(storage_root))

    # Create new audio track record
    audio_id = str(uuid.uuid4())
    audio_track = AudioTrack(
        id=audio_id,
        project_id=project_id,
        filename=safe_path.name,
        original_filename=sanitize_filename(file.filename),
        file_path=relative_path,
        file_size=file_size,
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        analysis_status="queued",
    )

    db.add(audio_track)
    await db.flush()
    await db.refresh(audio_track)

    # Update project timestamp
    project.updated_at = datetime.utcnow()
    await db.flush()

    # Enqueue beat analysis job
    job_id = f"beat_{audio_id}"
    try:
        enqueue_beat_analysis(
            project_id=project_id,
            audio_id=audio_id,
            func=BEAT_ANALYSIS_TASK,
            job_id=job_id,
        )
    except Exception:
        # Job enqueueing failed, but the file is uploaded
        # The user can manually trigger analysis later
        job_id = None

    return AudioUploadResponse(
        id=audio_track.id,
        filename=audio_track.original_filename,
        duration_ms=audio_track.duration_ms,
        sample_rate=audio_track.sample_rate,
        file_size=audio_track.file_size,
        analysis_status=audio_track.analysis_status,
        analysis_job_id=job_id,
    )


@router.get(
    "/{project_id}/audio/stream",
    summary="Stream audio file",
    description="Get the audio file for playback. Public endpoint (no auth required).",
    responses={
        200: {"content": {"audio/mpeg": {}}},
        404: {"description": "Audio not found"},
    },
)
async def stream_audio(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Stream the audio file for playback.

    Returns the audio file for HTML5 audio element playback.
    This endpoint is public to allow direct <audio src> usage.
    """
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Project not found"},
        )

    # Get audio track
    result = await db.execute(
        select(AudioTrack).where(AudioTrack.project_id == project_id)
    )
    audio = result.scalar_one_or_none()
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "No audio track for this project"},
        )

    # Resolve audio path
    audio_path = Path(get_storage_root()) / audio.file_path
    if not audio_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Audio file not found on disk"},
        )

    # Determine media type from file extension
    ext = audio_path.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(ext, "audio/mpeg")

    return FileResponse(
        path=str(audio_path),
        media_type=media_type,
        filename=audio.original_filename,
    )


@router.post(
    "/{project_id}/audio/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    name="analyze_audio",
    summary="Re-analyze audio",
    description="Manually re-trigger beat analysis for existing audio.",
    responses={
        409: {"model": AnalyzeConflictResponse, "description": "Analysis already in progress"},
    },
)
async def analyze_audio(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AnalyzeResponse:
    """
    Re-trigger beat analysis for existing audio.

    Use this to retry failed analysis or force re-analysis.
    Returns 409 if analysis is already in progress.
    """
    # Validate project exists and user owns it
    project = await get_project_or_404(project_id, db, current_user)

    # Get audio track
    audio = await get_audio_track_or_404(project_id, db)

    # Check if analysis is already in progress
    if audio.analysis_status == "processing":
        # Try to get the existing job ID
        existing_job_id = f"beat_{audio.id}"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "message": "Beat analysis already in progress",
                "existing_job_id": existing_job_id,
            },
        )

    # Update status to queued
    audio.analysis_status = "queued"
    audio.analysis_error = None
    audio.bpm = None
    audio.beat_count = None
    audio.beat_grid_path = None
    audio.analyzed_at = None

    await db.flush()

    # Enqueue beat analysis job
    job_id = f"beat_{audio.id}"
    try:
        enqueue_beat_analysis(
            project_id=project_id,
            audio_id=audio.id,
            func=BEAT_ANALYSIS_TASK,
            job_id=job_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Failed to enqueue beat analysis job",
            },
        )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message="Beat analysis queued",
    )


@router.get(
    "/{project_id}/audio/beats",
    response_model=BeatsResponse,
    summary="Get beat data",
    description="Get beat analysis results including the full beat grid.",
    responses={
        404: {"model": BeatsNotFoundError, "description": "Beats not found or not analyzed yet"},
    },
)
async def get_beats(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BeatsResponse:
    """
    Get beat analysis results.

    Returns the full beat grid data from derived/{project_id}/beats.json.
    Returns 404 if not analyzed yet, or 202 if analysis is in progress.
    """
    # Validate project exists and user owns it
    project = await get_project_or_404(project_id, db, current_user)

    # Get audio track
    audio = await get_audio_track_or_404(project_id, db)

    # Handle different analysis states
    if audio.analysis_status == "queued":
        job_id = f"beat_{audio.id}"
        return BeatsResponse(
            status="queued",
            job_id=job_id,
            message="Beat analysis queued, waiting to start...",
        )

    if audio.analysis_status == "processing":
        job_id = f"beat_{audio.id}"
        progress = get_progress(job_id)
        progress_percent = progress.get("percent", 0) if progress else 0
        message = progress.get("message", "Analyzing audio...") if progress else "Analyzing audio..."

        return BeatsResponse(
            status="processing",
            job_id=job_id,
            progress_percent=progress_percent,
            message=message,
        )

    if audio.analysis_status == "failed":
        return BeatsResponse(
            status="failed",
            message=audio.analysis_error or "Beat analysis failed",
        )

    # Analysis is complete - load beat grid from file
    if not audio.beat_grid_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Beat data not found",
                "hint": f"POST /api/projects/{project_id}/audio/analyze to trigger analysis",
            },
        )

    # Read beats.json from derived folder
    storage_root = get_storage_root()
    beats_file_path = storage_root / audio.beat_grid_path

    if not beats_file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Beat data file not found",
                "hint": f"POST /api/projects/{project_id}/audio/analyze to re-run analysis",
            },
        )

    try:
        with open(beats_file_path, "r") as f:
            beats_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Failed to read beat data",
            },
        )

    # Convert raw beat data to Beat objects
    beats = [
        Beat(
            time_ms=beat.get("time_ms", 0),
            beat_number=beat.get("beat_number", 1),
            is_downbeat=beat.get("is_downbeat", False),
        )
        for beat in beats_data.get("beats", [])
    ]

    return BeatsResponse(
        status="complete",
        bpm=audio.bpm,
        total_beats=audio.beat_count,
        time_signature=beats_data.get("time_signature", "4/4"),
        beats=beats,
        analyzed_at=audio.analyzed_at,
    )


@router.get(
    "/{project_id}/beats/status",
    response_model=BeatsStatusResponse,
    summary="Get beat analysis status",
    description="Lightweight status check for beat analysis (for polling).",
)
async def get_beats_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BeatsStatusResponse:
    """
    Get lightweight beat analysis status.

    Returns only the analysis status, useful for polling during analysis.
    """
    # Validate project exists and user owns it
    project = await get_project_or_404(project_id, db, current_user)

    # Get audio track (if exists)
    audio_result = await db.execute(
        select(AudioTrack).where(AudioTrack.project_id == project_id)
    )
    audio = audio_result.scalar_one_or_none()

    if audio is None:
        return BeatsStatusResponse(
            project_id=project_id,
            audio_uploaded=False,
            analysis_status=None,
        )

    return BeatsStatusResponse(
        project_id=project_id,
        audio_uploaded=True,
        analysis_status=audio.analysis_status,
        bpm=audio.bpm if audio.analysis_status == "complete" else None,
        total_beats=audio.beat_count if audio.analysis_status == "complete" else None,
        analyzed_at=audio.analyzed_at,
    )
