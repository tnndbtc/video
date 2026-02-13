"""
Media Upload API endpoints for BeatStitch.

Provides endpoints for uploading, retrieving, and managing media assets.
All endpoints require authentication and verify project ownership.
"""

import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.config import get_settings
from app.core.storage import (
    ALLOWED_EXTENSIONS,
    ensure_project_directories,
    generate_safe_path,
    get_file_category,
    get_storage_root,
    validate_file_type,
)
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.user import User
from app.schemas.media import (
    MediaAssetResponse,
    MediaReorderItem,
    MediaReorderRequest,
    MediaReorderResponse,
    MediaUploadItem,
    MediaUploadResponse,
)

router = APIRouter()


# =============================================================================
# Constants
# =============================================================================

# Valid media MIME types
ALLOWED_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

ALLOWED_VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",  # .mov
    "video/webm",
    "video/x-msvideo",  # .avi (not in spec but common)
}

ALLOWED_MEDIA_MIMES = ALLOWED_IMAGE_MIMES | ALLOWED_VIDEO_MIMES


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
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
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


async def get_media_or_404(
    media_id: str,
    db: AsyncSession,
    user: User,
) -> MediaAsset:
    """
    Get a media asset by ID, verifying ownership through project.

    Args:
        media_id: The media asset UUID
        db: Database session
        user: Current authenticated user

    Returns:
        MediaAsset object if found and owned by user

    Raises:
        HTTPException 404: If media not found or not owned by user
    """
    result = await db.execute(
        select(MediaAsset)
        .join(Project, MediaAsset.project_id == Project.id)
        .where(MediaAsset.id == media_id)
        .where(Project.owner_id == user.id)
    )
    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Media asset not found",
                "resource_type": "media",
                "resource_id": media_id,
            },
        )

    return media


def get_media_type_from_mime(mime_type: str) -> str | None:
    """
    Determine media type (image/video) from MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        "image" or "video" if valid, None otherwise
    """
    if mime_type in ALLOWED_IMAGE_MIMES:
        return "image"
    if mime_type in ALLOWED_VIDEO_MIMES:
        return "video"
    return None


def get_thumbnail_url(media: MediaAsset) -> str | None:
    """Generate thumbnail URL if thumbnail exists."""
    if media.thumbnail_path:
        return f"/api/media/{media.id}/thumbnail"
    return None


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/projects/{project_id}/media",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload media files",
    description="Upload images or videos to a project. Processing starts automatically.",
    name="upload_media",  # Used for rate limiting category
)
async def upload_media(
    project_id: str,
    files: List[UploadFile] = File(..., description="Media files to upload"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MediaUploadResponse:
    """
    Upload media files (images/videos) to a project.

    Accepts multiple files via multipart/form-data.
    Each file is validated for type and size, then saved to storage.
    A MediaAsset record is created with processing_status: pending.

    The worker will process the files to extract metadata and generate thumbnails.
    """
    # Verify project exists and is owned by user
    project = await get_project_or_404(project_id, db, current_user)

    settings = get_settings()

    # Check media count limit
    media_count_result = await db.execute(
        select(func.count(MediaAsset.id)).where(MediaAsset.project_id == project_id)
    )
    current_count = media_count_result.scalar() or 0

    if current_count + len(files) > settings.max_media_per_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": f"Project would exceed maximum of {settings.max_media_per_project} media files",
                "details": {
                    "current_count": current_count,
                    "attempted_upload": len(files),
                    "max_allowed": settings.max_media_per_project,
                },
            },
        )

    # Ensure project directories exist
    ensure_project_directories(project_id)

    uploaded: List[MediaUploadItem] = []
    failed: List[dict] = []

    # Get the next sort_order value
    max_sort_result = await db.execute(
        select(func.max(MediaAsset.sort_order)).where(MediaAsset.project_id == project_id)
    )
    next_sort_order = (max_sort_result.scalar() or -1) + 1

    for file in files:
        try:
            # Validate file has a name
            if not file.filename:
                failed.append({
                    "filename": "unknown",
                    "error": "File has no name",
                })
                continue

            # Validate MIME type
            content_type = file.content_type or mimetypes.guess_type(file.filename)[0]
            if not content_type or content_type not in ALLOWED_MEDIA_MIMES:
                # Also check by extension as fallback
                file_category = get_file_category(file.filename)
                if file_category not in ("image", "video"):
                    failed.append({
                        "filename": file.filename,
                        "error": f"Invalid file type: {content_type or 'unknown'}. Allowed: images (jpg, png, gif, webp) and videos (mp4, mov, webm)",
                    })
                    continue
                media_type = file_category
            else:
                media_type = get_media_type_from_mime(content_type)

            if not media_type:
                failed.append({
                    "filename": file.filename,
                    "error": "Could not determine media type",
                })
                continue

            # Read file content to check size
            content = await file.read()
            file_size = len(content)

            if file_size > settings.max_upload_size:
                failed.append({
                    "filename": file.filename,
                    "error": f"File too large: {file_size / (1024*1024):.1f}MB. Maximum: {settings.max_upload_size / (1024*1024):.0f}MB",
                })
                continue

            if file_size == 0:
                failed.append({
                    "filename": file.filename,
                    "error": "File is empty",
                })
                continue

            # Generate safe storage path
            safe_path = generate_safe_path(project_id, "media", file.filename)

            # Ensure parent directory exists
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file to storage
            with open(safe_path, "wb") as f:
                f.write(content)

            # Compute relative path for database storage
            storage_root = get_storage_root()
            relative_path = str(safe_path.relative_to(storage_root))

            # Create MediaAsset record
            asset = MediaAsset(
                project_id=project_id,
                filename=safe_path.name,
                original_filename=file.filename,
                file_path=relative_path,
                file_size=file_size,
                mime_type=content_type or f"{media_type}/unknown",
                media_type=media_type,
                processing_status="pending",
                sort_order=next_sort_order,
                # width, height, duration_ms, fps will be populated by worker
            )

            db.add(asset)
            await db.flush()
            await db.refresh(asset)

            uploaded.append(MediaUploadItem(
                id=asset.id,
                filename=asset.original_filename,
                media_type=asset.media_type,
                processing_status=asset.processing_status,
                width=asset.width,
                height=asset.height,
                duration_ms=asset.duration_ms,
                fps=asset.fps,
                file_size=asset.file_size,
            ))

            next_sort_order += 1

        except ValueError as e:
            # Catch storage validation errors
            failed.append({
                "filename": file.filename if file.filename else "unknown",
                "error": str(e),
            })
        except Exception as e:
            # Catch unexpected errors
            failed.append({
                "filename": file.filename if file.filename else "unknown",
                "error": f"Upload failed: {str(e)}",
            })

    # Update project timestamp
    project.updated_at = datetime.utcnow()
    await db.flush()

    return MediaUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total_uploaded=len(uploaded),
    )


@router.get(
    "/media/{media_id}",
    response_model=MediaAssetResponse,
    summary="Get media details",
    description="Get media asset details and processing status.",
)
async def get_media(
    media_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MediaAssetResponse:
    """
    Get a media asset by ID with full details.

    Returns processing_status, metadata (when available), and thumbnail URL.
    """
    media = await get_media_or_404(media_id, db, current_user)

    return MediaAssetResponse(
        id=media.id,
        project_id=media.project_id,
        filename=media.original_filename,
        media_type=media.media_type,
        processing_status=media.processing_status,
        width=media.width,
        height=media.height,
        duration_ms=media.duration_ms,
        fps=media.fps,
        file_size=media.file_size,
        thumbnail_url=get_thumbnail_url(media),
        sort_order=media.sort_order,
        created_at=media.created_at,
        processed_at=media.processed_at,
        processing_error=media.processing_error,
    )


@router.get(
    "/media/{media_id}/thumbnail",
    summary="Get media thumbnail",
    description="Get the thumbnail image for a media asset.",
    responses={
        200: {"content": {"image/jpeg": {}}},
        404: {"description": "Thumbnail not found or not yet generated"},
    },
)
async def get_media_thumbnail(
    media_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FileResponse:
    """
    Get the thumbnail for a media asset.

    Returns a JPEG image (256x256) if available.
    Returns 404 if processing not yet complete or failed.
    """
    media = await get_media_or_404(media_id, db, current_user)

    if not media.thumbnail_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Thumbnail not available",
                "details": {
                    "processing_status": media.processing_status,
                    "hint": "Thumbnail is generated after processing completes"
                    if media.processing_status in ("pending", "processing")
                    else "Processing may have failed",
                },
            },
        )

    # Resolve thumbnail path
    storage_root = get_storage_root()
    thumbnail_path = storage_root / media.thumbnail_path

    if not thumbnail_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": "Thumbnail file not found",
            },
        )

    return FileResponse(
        path=str(thumbnail_path),
        media_type="image/jpeg",
        filename=f"{media.id}_thumbnail.jpg",
    )


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete media asset",
    description="Delete a media asset and its associated files.",
)
async def delete_media(
    media_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete a media asset.

    Removes the file from storage and deletes the database record.
    """
    media = await get_media_or_404(media_id, db, current_user)
    storage_root = get_storage_root()

    # Delete main file
    if media.file_path:
        file_path = storage_root / media.file_path
        if file_path.exists():
            try:
                os.remove(file_path)
            except OSError:
                pass  # File may already be deleted

    # Delete thumbnail
    if media.thumbnail_path:
        thumbnail_path = storage_root / media.thumbnail_path
        if thumbnail_path.exists():
            try:
                os.remove(thumbnail_path)
            except OSError:
                pass

    # Delete proxy if exists
    if media.proxy_path:
        proxy_path = storage_root / media.proxy_path
        if proxy_path.exists():
            try:
                os.remove(proxy_path)
            except OSError:
                pass

    # Update project timestamp
    project_result = await db.execute(
        select(Project).where(Project.id == media.project_id)
    )
    project = project_result.scalar_one_or_none()
    if project:
        project.updated_at = datetime.utcnow()

    # Delete database record
    await db.delete(media)
    await db.flush()

    return None


@router.post(
    "/projects/{project_id}/media/reorder",
    response_model=MediaReorderResponse,
    summary="Reorder media assets",
    description="Reorder media assets within a project.",
)
async def reorder_media(
    project_id: str,
    data: MediaReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MediaReorderResponse:
    """
    Reorder media assets in a project.

    Accepts an array of media IDs in the new desired order.
    Updates the sort_order field for each asset.
    """
    # Verify project exists and is owned by user
    project = await get_project_or_404(project_id, db, current_user)

    # Get all media assets for this project
    result = await db.execute(
        select(MediaAsset).where(MediaAsset.project_id == project_id)
    )
    media_assets = {asset.id: asset for asset in result.scalars().all()}

    # Validate all IDs in the request exist and belong to this project
    for media_id in data.order:
        if media_id not in media_assets:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": f"Media asset not found in project: {media_id}",
                    "details": {
                        "invalid_id": media_id,
                        "project_id": project_id,
                    },
                },
            )

    # Update sort_order for each asset
    new_order: List[MediaReorderItem] = []
    for index, media_id in enumerate(data.order):
        asset = media_assets[media_id]
        asset.sort_order = index
        new_order.append(MediaReorderItem(
            id=asset.id,
            sort_order=index,
        ))

    # Any assets not in the new order keep their position at the end
    max_order = len(data.order)
    for media_id, asset in media_assets.items():
        if media_id not in data.order:
            asset.sort_order = max_order
            max_order += 1

    # Update project timestamp
    project.updated_at = datetime.utcnow()
    await db.flush()

    return MediaReorderResponse(
        success=True,
        new_order=new_order,
        timeline_invalidated=True,  # Reordering media invalidates the timeline
    )
