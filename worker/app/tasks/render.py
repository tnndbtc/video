"""
Render Task for BeatStitch Worker

Renders video output from EDL (Edit Decision List):
- Preview: 640x360, ultrafast preset, 24fps (timeout: 10 minutes)
- Final: 1920x1080, medium preset, 30fps (timeout: 30 minutes)

FFmpeg Filter Graph:
- One input per unique media asset (not per segment)
- Use trim/setpts to carve segments from inputs
- Images use -loop 1 for time-based trimming
- Ken Burns via zoompan filter
- Crossfade via xfade filter chain

Job timeouts:
- Preview: 10 minutes (RENDER_PREVIEW_TIMEOUT)
- Final: 30 minutes (RENDER_FINAL_TIMEOUT)
"""

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from rq import get_current_job
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

from ..db import get_db_session
from .ffmpeg_runner import FFmpegError, FFmpegTimeout, run_ffmpeg_with_progress

logger = logging.getLogger(__name__)

# Storage root from environment
STORAGE_ROOT = Path(os.environ.get("STORAGE_PATH", "/data"))

# Job timeouts
RENDER_PREVIEW_TIMEOUT = 600  # 10 minutes
RENDER_FINAL_TIMEOUT = 1800   # 30 minutes


# ============================================================================
# Render Settings Dataclasses
# ============================================================================


@dataclass
class RenderSettings:
    """
    Settings for final quality renders.

    Output: 1920x1080, 30fps, medium preset, H.264
    """

    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_bitrate: str = "8M"
    audio_bitrate: str = "192k"
    preset: str = "medium"
    crf: int = 23


@dataclass
class PreviewSettings:
    """
    Settings for fast preview renders.

    Output: 640x360, 24fps, ultrafast preset
    """

    width: int = 640
    height: int = 360
    fps: int = 24
    video_bitrate: str = "1M"
    audio_bitrate: str = "128k"
    preset: str = "ultrafast"
    crf: int = 32


# ============================================================================
# Local Model Definitions (to avoid circular imports)
# ============================================================================

Base = declarative_base()


class MediaAsset(Base):
    """Local model definition for MediaAsset."""

    __tablename__ = "media_assets"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(50), nullable=False)
    media_type = Column(String(10), nullable=False)
    processing_status = Column(String(20), default="pending", nullable=False)
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    rotation_deg = Column(Integer, default=0, nullable=False)
    display_aspect_ratio = Column(String(10), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    proxy_path = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, nullable=False)


class AudioTrack(Base):
    """Local model definition for AudioTrack."""

    __tablename__ = "audio_tracks"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    sample_rate = Column(Integer, nullable=True)
    bpm = Column(Float, nullable=True)
    beat_count = Column(Integer, nullable=True)
    beat_grid_path = Column(String(500), nullable=True)
    analysis_status = Column(String(20), default="pending", nullable=False)
    analysis_error = Column(String(500), nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)


class Project(Base):
    """Local model definition for Project."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    beats_per_cut = Column(Integer, default=4, nullable=False)
    transition_type = Column(String(20), default="cut", nullable=False)
    transition_duration_ms = Column(Integer, default=500, nullable=False)
    ken_burns_enabled = Column(Boolean, default=True, nullable=False)
    output_width = Column(Integer, default=1920, nullable=False)
    output_height = Column(Integer, default=1080, nullable=False)
    output_fps = Column(Integer, default=30, nullable=False)
    status = Column(String(20), default="draft", nullable=False)
    status_message = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)


class Timeline(Base):
    """Local model definition for Timeline."""

    __tablename__ = "timelines"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    edl_path = Column(String(500), nullable=False)
    total_duration_ms = Column(Integer, nullable=False, default=0)
    segment_count = Column(Integer, nullable=False, default=0)
    edl_hash = Column(String(64), nullable=False)
    generated_at = Column(DateTime, nullable=False)
    modified_at = Column(DateTime, nullable=False)


# ============================================================================
# FFmpeg Command Builder
# ============================================================================


class FFmpegCommandBuilder:
    """
    Builds FFmpeg command from EDL.

    Key design:
    - One input per unique media asset (not per segment)
    - Use trim + setpts to carve segments from inputs
    - Images use -loop 1 + trim by time
    - Audio input tracked explicitly
    """

    def __init__(
        self,
        edl: dict,
        settings: RenderSettings,
        output_path: str,
        asset_path_resolver: Callable[[str], str],
        audio_path: Optional[str] = None,
    ):
        """
        Initialize the FFmpeg command builder.

        Args:
            edl: Edit Decision List dictionary
            settings: RenderSettings or PreviewSettings instance
            output_path: Path for output video file
            asset_path_resolver: Function that resolves asset_id to file path
            audio_path: Optional path to audio file (resolved at initialization)
        """
        self.edl = edl
        self.settings = settings
        self.output_path = output_path
        self.resolve_asset_path = asset_path_resolver
        self.audio_path = audio_path

        # Track input indices
        self.input_map: Dict[str, int] = {}  # asset_id -> input_index
        self.next_input_idx = 0
        self.audio_input_idx: Optional[int] = None

    def build(self) -> List[str]:
        """
        Build complete FFmpeg command.

        Returns:
            List of command arguments for subprocess
        """
        cmd = ["ffmpeg", "-y"]

        # Build inputs (one per unique asset)
        cmd.extend(self._build_inputs())

        # Build filter complex
        filter_complex = self._build_filter_complex()
        cmd.extend(["-filter_complex", filter_complex])

        # Build output options
        cmd.extend(self._build_output_options())
        cmd.append(self.output_path)

        return cmd

    def _build_inputs(self) -> List[str]:
        """
        Build input arguments.

        - One input per unique media asset
        - Images get -loop 1 to allow trim by time
        - Audio input added last
        """
        inputs = []
        seen_assets: Set[str] = set()

        # Add media inputs (deduplicated by asset_id)
        for segment in self.edl["segments"]:
            asset_id = segment["media_asset_id"]
            if asset_id in seen_assets:
                continue
            seen_assets.add(asset_id)

            file_path = self.resolve_asset_path(asset_id)
            media_type = segment["media_type"]

            if media_type == "image":
                # -loop 1 allows trimming image stream by time
                inputs.extend(["-loop", "1", "-i", file_path])
            else:
                inputs.extend(["-i", file_path])

            self.input_map[asset_id] = self.next_input_idx
            self.next_input_idx += 1

        # Add audio input
        if self.audio_path:
            inputs.extend(["-i", self.audio_path])
            self.audio_input_idx = self.next_input_idx
            self.next_input_idx += 1

        return inputs

    def _build_filter_complex(self) -> str:
        """Build the filter_complex string."""
        filters = []
        segment_labels = []

        w = self.settings.width
        h = self.settings.height
        fps = self.settings.fps

        # Process each segment
        for seg in self.edl["segments"]:
            seg_idx = seg["segment_index"]
            input_idx = self.input_map[seg["media_asset_id"]]
            in_label = f"[{input_idx}:v]"
            out_label = f"[v{seg_idx}]"

            duration_sec = seg["render_duration_ms"] / 1000
            source_in_sec = seg["source_in_ms"] / 1000

            if seg["media_type"] == "image":
                # Image: trim by time, apply Ken Burns or scale
                kb = seg.get("ken_burns")
                if kb and kb.get("start_zoom") is not None:
                    filter_chain = self._build_ken_burns_filter(
                        in_label, out_label, kb, duration_sec, w, h, fps
                    )
                else:
                    # Simple scale + pad + trim for image
                    filter_chain = (
                        f"{in_label}"
                        f"trim=duration={duration_sec},"
                        f"setpts=PTS-STARTPTS,"
                        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                        f"setsar=1,fps={fps}{out_label}"
                    )
            else:
                # Video: trim from source_in to source_in + duration
                filter_chain = (
                    f"{in_label}"
                    f"trim=start={source_in_sec}:duration={duration_sec},"
                    f"setpts=PTS-STARTPTS,"
                    f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"setsar=1,fps={fps}{out_label}"
                )

            filters.append(filter_chain)
            segment_labels.append(out_label)

        # Concatenate or crossfade segments
        if len(segment_labels) > 1:
            transition_type = self.edl.get("transition_type", "cut")
            if transition_type == "cut":
                concat_inputs = "".join(segment_labels)
                filters.append(
                    f"{concat_inputs}concat=n={len(segment_labels)}:v=1:a=0[outv]"
                )
            else:
                filters.extend(self._build_xfade_chain(segment_labels))
        else:
            # Single segment: just relabel
            filters.append(f"{segment_labels[0]}copy[outv]")

        # Audio handling
        filters.append(self._build_audio_filter())

        return ";".join(filters)

    def _build_ken_burns_filter(
        self,
        in_label: str,
        out_label: str,
        kb: dict,
        duration_sec: float,
        w: int,
        h: int,
        fps: int,
    ) -> str:
        """
        Build Ken Burns (zoompan) filter for an image.

        Uses zoompan filter with interpolated zoom/pan values.
        Scales input to 8000:-1 for high quality zoom.

        Args:
            in_label: Input stream label (e.g., "[0:v]")
            out_label: Output stream label (e.g., "[v0]")
            kb: Ken Burns parameters dict
            duration_sec: Duration in seconds
            w: Output width
            h: Output height
            fps: Output frame rate

        Returns:
            Filter chain string
        """
        duration_frames = int(duration_sec * fps)
        sz = kb.get("start_zoom", 1.0)
        ez = kb.get("end_zoom", 1.2)

        # Pan direction determines start/end x,y positions
        pan_direction = kb.get("pan_direction", "center_zoom_in")
        sx, sy, ex, ey = self._get_pan_positions(pan_direction)

        # Calculate zoom and pan expressions
        # zoom interpolates from start_zoom to end_zoom over duration_frames
        zoom_expr = f"if(eq(on,1),{sz},{sz}+(({ez}-{sz})/{duration_frames})*on)"

        # x and y interpolate based on current zoom level
        x_expr = f"(iw-iw/zoom)*({sx}+({ex}-{sx})*on/{duration_frames})"
        y_expr = f"(ih-ih/zoom)*({sy}+({ey}-{sy})*on/{duration_frames})"

        return (
            f"{in_label}"
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d={duration_frames}:s={w}x{h}:fps={fps},"
            f"setsar=1{out_label}"
        )

    def _get_pan_positions(self, direction: str) -> tuple:
        """
        Get start/end x,y positions based on pan direction.

        Positions are relative (0.0 to 1.0) representing percentage
        of the available pan range.

        Args:
            direction: Pan direction string

        Returns:
            Tuple of (start_x, start_y, end_x, end_y)
        """
        # Define pan positions for each direction
        positions = {
            "left_to_right": (0.0, 0.5, 1.0, 0.5),
            "right_to_left": (1.0, 0.5, 0.0, 0.5),
            "top_to_bottom": (0.5, 0.0, 0.5, 1.0),
            "bottom_to_top": (0.5, 1.0, 0.5, 0.0),
            "center_zoom_in": (0.5, 0.5, 0.5, 0.5),
            "center_zoom_out": (0.5, 0.5, 0.5, 0.5),
        }
        return positions.get(direction, (0.5, 0.5, 0.5, 0.5))

    def _build_xfade_chain(self, labels: List[str]) -> List[str]:
        """
        Build xfade chain for crossfade transitions.

        Chains segments with xfade filter, calculating offsets based
        on segment durations.

        Args:
            labels: List of segment output labels

        Returns:
            List of filter strings
        """
        filters = []
        trans_dur_sec = self.edl.get("transition_duration_ms", 500) / 1000
        current_label = labels[0]

        # Calculate xfade offsets based on segment durations
        cumulative_duration = 0

        for i in range(1, len(labels)):
            # Get previous segment's render duration
            prev_seg = self.edl["segments"][i - 1]
            seg_dur_sec = prev_seg["render_duration_ms"] / 1000

            # xfade offset = cumulative duration + segment duration - transition overlap
            offset = cumulative_duration + seg_dur_sec - trans_dur_sec
            offset = max(0, offset)  # Ensure non-negative

            next_label = labels[i]
            out_label = f"[xf{i}]" if i < len(labels) - 1 else "[outv]"

            filters.append(
                f"{current_label}{next_label}"
                f"xfade=transition=fade:duration={trans_dur_sec}:offset={offset:.3f}"
                f"{out_label}"
            )

            current_label = out_label
            cumulative_duration = offset + trans_dur_sec

        return filters

    def _build_audio_filter(self) -> str:
        """Build audio filter chain."""
        # Calculate total timeline duration
        segments = self.edl.get("segments", [])
        if segments:
            # Find the maximum timeline_out_ms across all segments
            total_duration_sec = max(seg["timeline_out_ms"] for seg in segments) / 1000
        else:
            total_duration_sec = 0

        if self.audio_input_idx is not None:
            # Trim audio to match video duration
            return (
                f"[{self.audio_input_idx}:a]"
                f"atrim=0:{total_duration_sec},"
                f"asetpts=PTS-STARTPTS[outa]"
            )
        else:
            # No audio: generate silent audio track
            return (
                f"anullsrc=r=44100:cl=stereo,"
                f"atrim=0:{total_duration_sec}[outa]"
            )

    def _build_output_options(self) -> List[str]:
        """Build output encoding options."""
        return [
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-preset", self.settings.preset,
            "-crf", str(self.settings.crf),
            "-b:v", self.settings.video_bitrate,
            "-c:a", "aac",
            "-b:a", self.settings.audio_bitrate,
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
        ]


# ============================================================================
# Helper Functions
# ============================================================================


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


def create_asset_path_resolver(db, project_id: str) -> Callable[[str], str]:
    """
    Factory to create asset path resolver.

    Resolves media_asset_id -> file_path via database lookup.
    Pre-loads all assets for the project to minimize queries.

    Args:
        db: Database session
        project_id: UUID of the project

    Returns:
        Callable that takes asset_id and returns absolute file path

    Raises:
        ValueError: If asset_id not found
    """
    # Pre-load all assets for the project
    assets = db.query(MediaAsset).filter(
        MediaAsset.project_id == project_id
    ).all()

    path_map = {asset.id: asset.file_path for asset in assets}

    def resolver(asset_id: str) -> str:
        if asset_id not in path_map:
            raise ValueError(f"Unknown asset_id: {asset_id}")
        return str(STORAGE_ROOT / path_map[asset_id])

    return resolver


def resolve_media_paths(edl: dict, project_id: str, db) -> dict:
    """
    Resolve media_asset_ids to actual file paths.

    This ensures paths are never stored in EDL and are always
    validated at render time.

    Args:
        edl: Edit Decision List dictionary
        project_id: UUID of the project
        db: Database session

    Returns:
        EDL dictionary with source_path added to each segment

    Raises:
        ValueError: If asset not found or doesn't belong to project
    """
    resolved = deepcopy(edl)

    for segment in resolved["segments"]:
        asset = db.query(MediaAsset).filter_by(
            id=segment["media_asset_id"],
            project_id=project_id,  # Ensure asset belongs to this project
        ).first()

        if not asset:
            raise ValueError(f"Media asset {segment['media_asset_id']} not found")

        segment["source_path"] = str(STORAGE_ROOT / asset.file_path)

    return resolved


def simplify_edl_for_preview(edl: dict) -> dict:
    """
    Create simplified EDL for preview rendering.

    Reduces Ken Burns zoom range for faster processing.

    Args:
        edl: Original EDL dictionary

    Returns:
        Simplified EDL copy
    """
    preview_edl = deepcopy(edl)

    # Simplify Ken Burns (reduce zoom range)
    for segment in preview_edl["segments"]:
        kb = segment.get("ken_burns")
        if kb:
            # Reduce zoom range for faster processing
            kb["start_zoom"] = 1.0
            kb["end_zoom"] = min(kb.get("end_zoom", 1.1), 1.1)

    return preview_edl


def validate_edl_for_render(edl: dict, resolver: Callable[[str], str]) -> List[str]:
    """
    Validate EDL before starting render.

    Checks:
    - Segments exist
    - All assets are accessible
    - Timeline ranges are valid
    - Render durations are positive

    Args:
        edl: Edit Decision List dictionary
        resolver: Asset path resolver function

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Check segments exist
    segments = edl.get("segments", [])
    if not segments:
        errors.append("EDL has no segments")
        return errors

    # Validate each segment
    for seg in segments:
        asset_id = seg.get("media_asset_id")
        if not asset_id:
            errors.append(f"Segment {seg.get('segment_index', '?')}: missing media_asset_id")
            continue

        # Check asset exists and is accessible
        try:
            path = resolver(asset_id)
            if not Path(path).exists():
                errors.append(f"Asset file not found: {path}")
        except ValueError as e:
            errors.append(str(e))

        # Check timing is valid
        timeline_in = seg.get("timeline_in_ms", 0)
        timeline_out = seg.get("timeline_out_ms", 0)
        if timeline_out <= timeline_in:
            errors.append(
                f"Segment {seg.get('segment_index', '?')}: invalid timeline range "
                f"({timeline_in}ms - {timeline_out}ms)"
            )

        render_duration = seg.get("render_duration_ms", 0)
        if render_duration <= 0:
            errors.append(
                f"Segment {seg.get('segment_index', '?')}: invalid render duration "
                f"({render_duration}ms)"
            )

    return errors


def load_edl_from_path(edl_path: str) -> dict:
    """
    Load EDL from filesystem.

    Args:
        edl_path: Relative path to edl.json (relative to STORAGE_ROOT)

    Returns:
        EDL dictionary

    Raises:
        FileNotFoundError: If EDL file doesn't exist
        json.JSONDecodeError: If EDL is not valid JSON
    """
    full_path = STORAGE_ROOT / edl_path
    if not full_path.exists():
        raise FileNotFoundError(f"EDL not found: {full_path}")

    with open(full_path, "r") as f:
        return json.load(f)


def enqueue_render(project_id: str, job_type: str, edl_hash: str):
    """
    Enqueue a render job with proper timeout.

    This helper ensures the correct timeout is applied based on job_type.
    Use this instead of directly enqueueing the task.

    Args:
        project_id: UUID of the project
        job_type: "preview" or "final"
        edl_hash: Expected EDL hash for race condition prevention

    Returns:
        RQ Job instance

    Raises:
        ValueError: If job_type is invalid
    """
    from ..queues import preview_queue, final_queue

    if job_type == "preview":
        queue = preview_queue
        timeout = RENDER_PREVIEW_TIMEOUT
    elif job_type == "final":
        queue = final_queue
        timeout = RENDER_FINAL_TIMEOUT
    else:
        raise ValueError(f"Invalid job_type: {job_type}")

    return queue.enqueue(
        render_video,
        project_id,
        job_type,
        edl_hash,
        job_timeout=timeout,
    )


# ============================================================================
# Main Task Function
# ============================================================================


def render_video(project_id: str, job_type: str, edl_hash: str) -> dict:
    """
    RQ task to render video output from EDL.

    This task:
    1. Loads project and timeline from database
    2. Verifies edl_hash matches (race condition prevention)
    3. Loads EDL from filesystem
    4. Resolves media paths via database lookup
    5. Creates output directory
    6. Builds FFmpeg command
    7. Runs FFmpeg with timeout enforcement
    8. Updates progress via RQ job metadata
    9. Returns output information

    Args:
        project_id: UUID of the project
        job_type: "preview" or "final"
        edl_hash: Expected EDL hash (raises ValueError if mismatch)

    Returns:
        dict with output_path, file_size, duration_ms

    Raises:
        ValueError: If project/timeline not found, or edl_hash mismatch
        FileNotFoundError: If EDL or media files not found
        FFmpegTimeout: If render exceeds timeout
        FFmpegError: If FFmpeg fails
    """
    logger.info(f"Starting {job_type} render for project={project_id}, edl_hash={edl_hash[:16]}...")
    update_job_progress(0, f"Starting {job_type} render")

    with get_db_session() as db:
        # Load project
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        update_job_progress(5, "Loading timeline")

        # Load timeline
        timeline = db.query(Timeline).filter_by(project_id=project_id).first()
        if not timeline:
            raise ValueError(f"Timeline not found for project: {project_id}")

        # Verify edl_hash matches (race condition prevention)
        if timeline.edl_hash != edl_hash:
            raise ValueError(
                f"EDL hash mismatch - timeline has changed. "
                f"Expected: {edl_hash[:16]}..., Got: {timeline.edl_hash[:16]}..."
            )

        update_job_progress(10, "Loading EDL")

        # Load EDL from filesystem
        edl = load_edl_from_path(timeline.edl_path)

        # Load audio track for path resolution
        audio_track = db.query(AudioTrack).filter_by(project_id=project_id).first()
        audio_path = None
        if audio_track:
            audio_path = str(STORAGE_ROOT / audio_track.file_path)

        update_job_progress(15, "Resolving media paths")

        # Create asset path resolver
        resolver = create_asset_path_resolver(db, project_id)

        # Validate EDL before render
        validation_errors = validate_edl_for_render(edl, resolver)
        if validation_errors:
            raise ValueError(f"EDL validation failed: {'; '.join(validation_errors)}")

        update_job_progress(20, "Building FFmpeg command")

        # Determine settings based on job type
        if job_type == "preview":
            settings = PreviewSettings()
            edl = simplify_edl_for_preview(edl)
            timeout = RENDER_PREVIEW_TIMEOUT
        else:
            settings = RenderSettings()
            timeout = RENDER_FINAL_TIMEOUT

        # Create output directory and path
        output_dir = STORAGE_ROOT / "outputs" / project_id / job_type
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_filename = f"render_{timestamp}.mp4"
        output_path = output_dir / output_filename

        # Build FFmpeg command
        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=resolver,
            audio_path=audio_path,
        )
        cmd = builder.build()

        logger.info(f"FFmpeg command: {' '.join(cmd[:20])}...")  # Log first 20 args

        update_job_progress(25, "Starting FFmpeg render")

        # Calculate total duration for progress tracking
        total_duration_ms = edl.get("total_duration_ms", 0)
        if not total_duration_ms and edl.get("segments"):
            total_duration_ms = max(seg["timeline_out_ms"] for seg in edl["segments"])

        # Progress callback that updates RQ job
        def progress_callback(percent: int, message: str) -> None:
            # Scale FFmpeg progress (0-100) to our range (25-95)
            scaled_percent = 25 + int(percent * 0.7)
            update_job_progress(scaled_percent, message)

        # Run FFmpeg with timeout enforcement
        try:
            run_ffmpeg_with_progress(
                cmd=cmd,
                total_duration_ms=total_duration_ms,
                progress_callback=progress_callback,
                timeout_seconds=timeout,
            )
        except (FFmpegTimeout, FFmpegError) as e:
            # Update project status to failed
            project.status = "render_failed"
            project.status_message = str(e)[:200]
            db.commit()
            raise

        update_job_progress(95, "Finalizing output")

        # Verify output file exists and get stats
        if not output_path.exists():
            raise FFmpegError("Output file was not created")

        file_size = output_path.stat().st_size
        if file_size == 0:
            raise FFmpegError("Output file is empty")

        # Calculate relative path for storage
        relative_output_path = f"outputs/{project_id}/{job_type}/{output_filename}"

        update_job_progress(100, f"{job_type.capitalize()} render complete")

        logger.info(
            f"Render complete: {relative_output_path}, "
            f"size={file_size}, duration_ms={total_duration_ms}"
        )

        return {
            "output_path": relative_output_path,
            "file_size": file_size,
            "duration_ms": total_duration_ms,
        }
