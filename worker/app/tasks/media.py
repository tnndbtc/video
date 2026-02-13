"""
Media Processing Task

Processes uploaded media files (images and videos):
- Extracts metadata (dimensions, duration, fps)
- Generates thumbnails (256x256 JPEG)
- Updates processing_status in database

Uses PIL/Pillow for images and FFmpeg (via subprocess) for videos.

Job timeout: 2 minutes
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ExifTags
from rq import get_current_job
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

from ..db import get_db_session

logger = logging.getLogger(__name__)

# Storage root from environment
STORAGE_ROOT = Path(os.environ.get("STORAGE_PATH", "/data"))

# Job timeout in seconds (2 minutes as per spec)
MEDIA_PROCESSING_TIMEOUT = 120

# Thumbnail settings
THUMBNAIL_SIZE = (256, 256)
THUMBNAIL_FORMAT = "JPEG"
THUMBNAIL_QUALITY = 85

# SQLAlchemy base for worker models
WorkerBase = declarative_base()


class MediaAsset(WorkerBase):
    """
    Minimal MediaAsset model for worker database operations.

    This mirrors the backend's MediaAsset model but includes only
    the fields needed for media processing tasks.
    """

    __tablename__ = "media_assets"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)

    # File information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(50), nullable=False)

    # Media type
    media_type = Column(String(10), nullable=False, index=True)

    # Processing status
    processing_status = Column(String(20), default="pending", nullable=False, index=True)
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)

    # Dimensions (native/storage dimensions)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)

    # Display corrections
    rotation_deg = Column(Integer, default=0, nullable=False)
    display_aspect_ratio = Column(String(10), nullable=True)

    # Derived assets
    thumbnail_path = Column(String(500), nullable=True)
    proxy_path = Column(String(500), nullable=True)

    # Ordering and timestamps
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def update_job_progress(percent: int, message: str) -> None:
    """
    Update RQ job progress metadata.

    Args:
        percent: Progress percentage (0-100)
        message: Progress message
    """
    job = get_current_job()
    if job:
        job.meta["progress_percent"] = percent
        job.meta["progress_message"] = message
        job.save_meta()


def enqueue_media_processing(media_asset_id: str):
    """
    Enqueue a media processing job with proper timeout.

    This helper ensures the 2-minute timeout is always applied.
    Use this instead of directly enqueueing the task.

    Args:
        media_asset_id: UUID of the MediaAsset to process

    Returns:
        RQ Job instance
    """
    from ..queues import thumbnail_queue

    return thumbnail_queue.enqueue(
        process_media,
        media_asset_id,
        job_timeout=MEDIA_PROCESSING_TIMEOUT,
    )


def process_media(media_asset_id: str) -> dict:
    """
    RQ task to process an uploaded media asset.

    This task:
    1. Loads the MediaAsset record from the database
    2. Extracts metadata (dimensions, duration for videos, fps)
    3. Generates a 256x256 thumbnail
    4. Updates the database with metadata and processing status

    Args:
        media_asset_id: UUID string of the MediaAsset to process

    Returns:
        dict: Processing result with status, metadata, and thumbnail path

    Raises:
        ValueError: If media asset not found
        FileNotFoundError: If source file not found
        Exception: On processing errors (updates status to failed)
    """
    logger.info(f"Starting media processing for asset {media_asset_id}")
    update_job_progress(0, "Starting media processing")

    with get_db_session() as db:
        # Load the media asset
        asset = db.query(MediaAsset).filter(MediaAsset.id == media_asset_id).first()

        if not asset:
            raise ValueError(f"Media asset not found: {media_asset_id}")

        # Update status to processing
        asset.processing_status = "processing"
        asset.processing_error = None
        db.commit()

        try:
            source_path = STORAGE_ROOT / asset.file_path

            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            update_job_progress(10, "Extracting metadata")

            # Process based on media type
            if asset.media_type == "image":
                metadata = _process_image(source_path)
            elif asset.media_type == "video":
                metadata = _process_video(source_path)
            else:
                raise ValueError(f"Unknown media type: {asset.media_type}")

            update_job_progress(50, "Generating thumbnail")

            # Generate thumbnail
            thumbnail_path = _generate_thumbnail(
                source_path=source_path,
                media_type=asset.media_type,
                project_id=asset.project_id,
                asset_id=media_asset_id,
            )

            update_job_progress(90, "Saving results")

            # Update asset with metadata
            asset.width = metadata.get("width")
            asset.height = metadata.get("height")
            asset.duration_ms = metadata.get("duration_ms")
            asset.fps = metadata.get("fps")
            asset.rotation_deg = metadata.get("rotation", 0)

            if thumbnail_path:
                # Store relative path from storage root
                asset.thumbnail_path = str(thumbnail_path.relative_to(STORAGE_ROOT))

            asset.processing_status = "ready"
            asset.processed_at = datetime.utcnow()
            asset.processing_error = None
            db.commit()

            update_job_progress(100, "Processing complete")

            result = {
                "status": "ready",
                "media_asset_id": media_asset_id,
                "width": asset.width,
                "height": asset.height,
                "duration_ms": asset.duration_ms,
                "fps": asset.fps,
                "rotation_deg": asset.rotation_deg,
                "thumbnail_path": asset.thumbnail_path,
            }

            logger.info(f"Successfully processed media asset {media_asset_id}: {result}")
            return result

        except Exception as e:
            logger.error(f"Error processing media asset {media_asset_id}: {e}", exc_info=True)

            # Update status to failed
            error_message = str(e)[:1000]  # Limit error message length
            asset.processing_status = "failed"
            asset.processing_error = error_message
            asset.processed_at = datetime.utcnow()
            db.commit()

            raise


def _process_image(source_path: Path) -> dict:
    """
    Extract metadata from an image file.

    Handles EXIF orientation/rotation data.

    Args:
        source_path: Path to the image file

    Returns:
        dict: Metadata including width, height, rotation
    """
    with Image.open(source_path) as img:
        width, height = img.size
        rotation = 0

        # Extract EXIF orientation
        try:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "Orientation":
                        # EXIF orientation values:
                        # 1: Normal
                        # 3: Rotated 180
                        # 6: Rotated 90 CW
                        # 8: Rotated 90 CCW
                        orientation_to_rotation = {
                            1: 0,
                            3: 180,
                            6: 90,
                            8: 270,
                        }
                        rotation = orientation_to_rotation.get(value, 0)
                        break
        except (AttributeError, KeyError, TypeError):
            # No EXIF data or orientation tag
            pass

        return {
            "width": width,
            "height": height,
            "rotation": rotation,
            "duration_ms": None,
            "fps": None,
        }


def _process_video(source_path: Path) -> dict:
    """
    Extract metadata from a video file using ffprobe.

    Args:
        source_path: Path to the video file

    Returns:
        dict: Metadata including width, height, duration_ms, fps, rotation
    """
    try:
        # Run ffprobe to get video metadata
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(source_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        probe_data = json.loads(result.stdout)

        # Find video stream
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            raise ValueError("No video stream found in file")

        # Extract dimensions
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)

        # Extract duration (prefer format duration, fallback to stream)
        duration_sec = None
        if "format" in probe_data and "duration" in probe_data["format"]:
            duration_sec = float(probe_data["format"]["duration"])
        elif "duration" in video_stream:
            duration_sec = float(video_stream["duration"])

        duration_ms = int(duration_sec * 1000) if duration_sec else None

        # Extract frame rate
        fps = None
        if "r_frame_rate" in video_stream:
            fps_str = video_stream["r_frame_rate"]
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                if den > 0:
                    fps = round(num / den, 2)
            else:
                fps = float(fps_str)

        # Extract rotation from side_data_list or tags
        rotation = 0
        side_data = video_stream.get("side_data_list", [])
        for data in side_data:
            if data.get("side_data_type") == "Display Matrix":
                rotation = abs(int(data.get("rotation", 0)))
                break

        # Also check tags for rotation (older FFmpeg versions)
        if rotation == 0:
            tags = video_stream.get("tags", {})
            rotate_tag = tags.get("rotate", "0")
            rotation = abs(int(rotate_tag))

        # Normalize rotation to 0, 90, 180, 270
        rotation = rotation % 360
        if rotation not in (0, 90, 180, 270):
            rotation = 0

        return {
            "width": width,
            "height": height,
            "duration_ms": duration_ms,
            "fps": fps,
            "rotation": rotation,
        }

    except subprocess.TimeoutExpired:
        raise RuntimeError("ffprobe timed out")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}")


def _generate_thumbnail(
    source_path: Path,
    media_type: str,
    project_id: str,
    asset_id: str,
) -> Optional[Path]:
    """
    Generate a 256x256 JPEG thumbnail for the media asset.

    For images: Uses PIL to resize and convert.
    For videos: Extracts a keyframe using FFmpeg.

    Thumbnails are saved to:
        /data/derived/{project_id}/thumbnails/{asset_id}.jpg

    Args:
        source_path: Path to the source media file
        media_type: "image" or "video"
        project_id: UUID of the project
        asset_id: UUID of the media asset

    Returns:
        Path: Absolute path to the generated thumbnail, or None on failure
    """
    thumbnails_dir = STORAGE_ROOT / "derived" / project_id / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    thumbnail_path = thumbnails_dir / f"{asset_id}.jpg"

    try:
        if media_type == "image":
            _generate_image_thumbnail(source_path, thumbnail_path)
        elif media_type == "video":
            _generate_video_thumbnail(source_path, thumbnail_path)
        else:
            logger.warning(f"Unknown media type for thumbnail: {media_type}")
            return None

        if thumbnail_path.exists():
            logger.info(f"Generated thumbnail: {thumbnail_path}")
            return thumbnail_path
        else:
            logger.warning(f"Thumbnail not created: {thumbnail_path}")
            return None

    except Exception as e:
        logger.error(f"Failed to generate thumbnail: {e}", exc_info=True)
        return None


def _generate_image_thumbnail(source_path: Path, thumbnail_path: Path) -> None:
    """
    Generate thumbnail from an image file.

    Handles EXIF orientation by transposing the image if needed.

    Args:
        source_path: Path to source image
        thumbnail_path: Path to save thumbnail
    """
    with Image.open(source_path) as img:
        # Handle EXIF orientation
        try:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "Orientation":
                        # Apply rotation based on EXIF orientation
                        if value == 3:
                            img = img.rotate(180, expand=True)
                        elif value == 6:
                            img = img.rotate(270, expand=True)
                        elif value == 8:
                            img = img.rotate(90, expand=True)
                        break
        except (AttributeError, KeyError, TypeError):
            pass

        # Convert to RGB if necessary (for JPEG output)
        if img.mode in ("RGBA", "P", "LA"):
            # Create white background for transparent images
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Create thumbnail using LANCZOS resampling for quality
        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        # Save as JPEG
        img.save(thumbnail_path, THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY)


def _generate_video_thumbnail(source_path: Path, thumbnail_path: Path) -> None:
    """
    Generate thumbnail from a video file by extracting a keyframe.

    Extracts a frame from approximately 10% into the video (or first frame
    for very short videos).

    Args:
        source_path: Path to source video
        thumbnail_path: Path to save thumbnail
    """
    # First, get video duration to calculate seek position
    try:
        duration_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0
    except (subprocess.TimeoutExpired, ValueError):
        duration = 0

    # Seek to 10% of duration, but at least 0 and at most 5 seconds
    seek_time = min(max(duration * 0.1, 0), 5)

    # Extract frame using FFmpeg
    # -ss before -i for fast seeking
    # -vframes 1 to extract single frame
    # -vf scale to resize while maintaining aspect ratio
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-ss", str(seek_time),
        "-i", str(source_path),
        "-vframes", "1",
        "-vf", f"scale={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:force_original_aspect_ratio=decrease,pad={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:(ow-iw)/2:(oh-ih)/2:white",
        "-q:v", "2",  # High quality JPEG
        str(thumbnail_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning(f"FFmpeg thumbnail extraction failed: {result.stderr}")
            # Fallback: try extracting first frame without seeking
            fallback_cmd = [
                "ffmpeg",
                "-y",
                "-i", str(source_path),
                "-vframes", "1",
                "-vf", f"scale={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:force_original_aspect_ratio=decrease,pad={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:(ow-iw)/2:(oh-ih)/2:white",
                "-q:v", "2",
                str(thumbnail_path),
            ]
            subprocess.run(fallback_cmd, capture_output=True, timeout=30)

    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg thumbnail extraction timed out")
