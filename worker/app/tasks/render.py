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

import hashlib
import json
import logging
import os
import uuid
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
    # ForeignKey not needed - just reading from existing DB
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

from ..db import get_db_session
from .ffmpeg_runner import FFmpegError, FFmpegTimeout, run_ffmpeg_with_progress
from .motion_engine import (
    MotionClipCache,
    RenderConfig as MotionRenderConfig,
    prerender_segment_clips,
)

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
    project_id = Column(String(36), nullable=False)  # FK to projects.id
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
    project_id = Column(String(36), nullable=False)  # FK to projects.id
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
    owner_id = Column(String(36), nullable=False)  # FK to users.id
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
    project_id = Column(String(36), nullable=False)  # FK to projects.id
    edl_path = Column(String(500), nullable=False)
    total_duration_ms = Column(Integer, nullable=False, default=0)
    segment_count = Column(Integer, nullable=False, default=0)
    edl_hash = Column(String(64), nullable=False)
    generated_at = Column(DateTime, nullable=False)
    modified_at = Column(DateTime, nullable=False)


class RenderJob(Base):
    """Local model definition for RenderJob."""

    __tablename__ = "render_jobs"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False)
    job_type = Column(String(10), nullable=False)  # 'preview' or 'final'
    edl_hash = Column(String(64), nullable=False)
    rq_job_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False)  # queued, running, complete, failed
    progress_percent = Column(Integer, default=0)
    progress_message = Column(String(200), nullable=True)
    output_path = Column(String(500), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    error_message = Column(Text, nullable=True)
    render_settings_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ============================================================================
# FFmpeg Command Builder
# ============================================================================


class FFmpegCommandBuilder:
    """
    Builds FFmpeg command from EDL.

    Key design:
    - One input per unique media asset (not per segment)
    - Use trim + setpts to carve segments from inputs
    - Images use -loop 1 + trim by time (or pre-rendered motion clips)
    - Audio input tracked explicitly
    """

    def __init__(
        self,
        edl: dict,
        settings: RenderSettings,
        output_path: str,
        asset_path_resolver: Callable[[str], str],
        audio_path: Optional[str] = None,
        motion_clip_resolver: Optional[Callable[[int], Optional[str]]] = None,
    ):
        """
        Initialize the FFmpeg command builder.

        Args:
            edl: Edit Decision List dictionary
            settings: RenderSettings or PreviewSettings instance
            output_path: Path for output video file
            asset_path_resolver: Function that resolves asset_id to file path
            audio_path: Optional path to audio file (resolved at initialization)
            motion_clip_resolver: Function that resolves segment_index to pre-rendered clip path
        """
        self.edl = edl
        self.settings = settings
        self.output_path = output_path
        self.resolve_asset_path = asset_path_resolver
        self.audio_path = audio_path
        self.motion_clip_resolver = motion_clip_resolver

        # Track input indices
        self.input_map: Dict[str, int] = {}  # asset_id -> input_index
        self.segment_input_map: Dict[int, int] = {}  # segment_index -> input_index (for motion clips)
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

        - Uses pre-rendered motion clips when available (one per segment)
        - Otherwise: one input per unique media asset
        - Images get -loop 1 to allow trim by time
        - Audio input added last
        """
        inputs = []
        seen_assets: Set[str] = set()

        # Add media inputs
        for segment in self.edl["segments"]:
            seg_idx = segment["segment_index"]
            asset_id = segment["media_asset_id"]
            media_type = segment["media_type"]

            # Check for pre-rendered motion clip first
            motion_clip_path = None
            if self.motion_clip_resolver and media_type == "image":
                motion_clip_path = self.motion_clip_resolver(seg_idx)

            if motion_clip_path:
                # Use pre-rendered motion clip (each segment gets its own input)
                inputs.extend(["-i", motion_clip_path])
                self.segment_input_map[seg_idx] = self.next_input_idx
                self.next_input_idx += 1
            else:
                # Traditional handling: deduplicate by asset_id
                if asset_id not in seen_assets:
                    seen_assets.add(asset_id)
                    file_path = self.resolve_asset_path(asset_id)

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
            out_label = f"[v{seg_idx}]"

            duration_sec = seg["render_duration_ms"] / 1000
            source_in_sec = seg["source_in_ms"] / 1000

            # Check if this segment has a pre-rendered motion clip
            if seg_idx in self.segment_input_map:
                # Pre-rendered motion clip: just copy with frame rate normalization
                input_idx = self.segment_input_map[seg_idx]
                in_label = f"[{input_idx}:v]"
                filter_chain = (
                    f"{in_label}"
                    f"setpts=PTS-STARTPTS,"
                    f"fps={fps},"
                    f"setsar=1{out_label}"
                )
            elif seg["media_type"] == "image":
                # Traditional image handling
                input_idx = self.input_map[seg["media_asset_id"]]
                in_label = f"[{input_idx}:v]"

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
                input_idx = self.input_map[seg["media_asset_id"]]
                in_label = f"[{input_idx}:v]"
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
        Scales input to 2x output width for quality zoom (not 8000 which is too slow).

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

        # Scale to 2x output width for quality, not 8000 which is extremely slow
        # For preview (640x360) -> 1280px, for final (1920x1080) -> 3840px
        intermediate_width = w * 2

        return (
            f"{in_label}"
            f"scale={intermediate_width}:-1,"
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

    DISABLES Ken Burns entirely for fast preview renders.
    Zoompan filter is too slow even with small input sizes.

    Args:
        edl: Original EDL dictionary

    Returns:
        Simplified EDL copy with Ken Burns disabled
    """
    preview_edl = deepcopy(edl)

    # DISABLE Ken Burns entirely for preview - zoompan is too slow
    for segment in preview_edl["segments"]:
        if "ken_burns" in segment:
            del segment["ken_burns"]

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


def enqueue_render(project_id: str, job_type: str):
    """
    Enqueue a render job with proper timeout.

    This helper ensures the correct timeout is applied based on job_type.
    Use this instead of directly enqueueing the task.

    Timeline generation is now integrated into the render task itself,
    so edl_hash is no longer required.

    Args:
        project_id: UUID of the project
        job_type: "preview" or "final"

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
        job_timeout=timeout,
    )


# ============================================================================
# Main Task Function
# ============================================================================


def update_render_job_status(
    db,
    project_id: str,
    job_type: str,
    status: str,
    progress_percent: int = None,
    progress_message: str = None,
    output_path: str = None,
    file_size: int = None,
    error_message: str = None,
    started_at: datetime = None,
    completed_at: datetime = None,
) -> None:
    """Update the render_jobs table with current status."""
    # Find the most recent render job for this project/type that's queued or running
    render_job = db.query(RenderJob).filter(
        RenderJob.project_id == project_id,
        RenderJob.job_type == job_type,
        RenderJob.status.in_(["queued", "running"]),
    ).order_by(RenderJob.created_at.desc()).first()

    if render_job:
        render_job.status = status
        if progress_percent is not None:
            render_job.progress_percent = progress_percent
        if progress_message is not None:
            render_job.progress_message = progress_message
        if output_path is not None:
            render_job.output_path = output_path
        if file_size is not None:
            render_job.file_size = file_size
        if error_message is not None:
            render_job.error_message = error_message
        if started_at is not None:
            render_job.started_at = started_at
        if completed_at is not None:
            render_job.completed_at = completed_at
        db.commit()
        logger.debug(f"Updated render job {render_job.id} status to {status}")


def render_video(project_id: str, job_type: str) -> dict:
    """
    RQ task to render video output from EDL.

    This task:
    1. Loads project from database
    2. Generates timeline (EDL) - always regenerates for fresh data
    3. Loads EDL from filesystem
    4. Resolves media paths via database lookup
    5. Creates output directory
    6. Builds FFmpeg command
    7. Runs FFmpeg with timeout enforcement
    8. Updates progress via RQ job metadata
    9. Updates render_jobs table with status
    10. Returns output information

    Args:
        project_id: UUID of the project
        job_type: "preview" or "final"

    Returns:
        dict with output_path, file_size, duration_ms

    Raises:
        ValueError: If project/media not found
        FileNotFoundError: If EDL or media files not found
        FFmpegTimeout: If render exceeds timeout
        FFmpegError: If FFmpeg fails
    """
    logger.info(f"Starting {job_type} render for project={project_id}...")
    update_job_progress(0, f"Starting {job_type} render")

    with get_db_session() as db:
        # Mark job as running
        update_render_job_status(
            db, project_id, job_type,
            status="running",
            started_at=datetime.utcnow(),
            progress_percent=0,
            progress_message="Starting render",
        )
        # Load project
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # =====================================================================
        # Phase 1: Generate Timeline (0-15%)
        # =====================================================================
        update_job_progress(2, "Generating timeline...")

        # Load render_plan.json first (to get timeline_media_ids if present)
        render_plan = None
        render_plan_path = STORAGE_ROOT / "derived" / project_id / "render_plan.json"
        if render_plan_path.exists():
            try:
                with open(render_plan_path) as f:
                    render_plan = json.load(f)
                logger.info(f"Loaded render_plan: {render_plan}")
            except Exception as e:
                logger.warning(f"Failed to load render_plan.json: {e}")

        # Load media assets - use timeline_media_ids if provided in render_plan
        timeline_media_ids = render_plan.get("timeline_media_ids") if render_plan else None

        if timeline_media_ids:
            # Load only the specified media in the specified order
            all_media = (
                db.query(MediaAsset)
                .filter_by(project_id=project_id, processing_status="ready")
                .all()
            )
            media_by_id = {m.id: m for m in all_media}
            media_assets = [media_by_id[mid] for mid in timeline_media_ids if mid in media_by_id]
            logger.info(f"Using timeline_media_ids: {len(media_assets)} media items")
        else:
            # Fall back to all media sorted by sort_order
            media_assets = (
                db.query(MediaAsset)
                .filter_by(project_id=project_id, processing_status="ready")
                .order_by(MediaAsset.sort_order)
                .all()
            )

        if not media_assets:
            raise ValueError(f"No processed media assets found for project {project_id}")

        update_job_progress(5, "Building timeline...")

        # Import timeline builder from timeline module
        from .timeline import TimelineBuilder, save_edl, PAN_DIRECTIONS

        # Extract project settings
        project_settings = {
            "transition_type": project.transition_type,
            "transition_duration_ms": project.transition_duration_ms,
            "ken_burns_enabled": project.ken_burns_enabled,
            "output_width": project.output_width,
            "output_height": project.output_height,
            "output_fps": project.output_fps,
        }

        # Build beat_config from audio track + render_plan
        beat_config = None
        audio_track = db.query(AudioTrack).filter_by(project_id=project_id).first()

        # Get target duration from render_plan (works with or without audio)
        target_duration_ms = None
        if render_plan and render_plan.get("video_length_seconds"):
            target_duration_ms = render_plan["video_length_seconds"] * 1000
            logger.info(f"Target duration from render_plan: {target_duration_ms}ms")

        if audio_track and audio_track.bpm and render_plan:
            # Beat-synced mode with audio
            if not target_duration_ms:
                target_duration_ms = audio_track.duration_ms

            beat_config = {
                "bpm": audio_track.bpm,
                "beats_per_cut": render_plan.get("beats_per_cut", 8),
                "audio_duration_ms": target_duration_ms,
                "loop_media": render_plan.get("loop_media", True),
            }
            logger.info(f"Beat-synced mode: bpm={audio_track.bpm}, "
                       f"beats_per_cut={beat_config['beats_per_cut']}, "
                       f"target_duration_ms={target_duration_ms}")
        elif target_duration_ms:
            # No audio but have target duration - use simple duration mode
            beat_config = {
                "target_duration_ms": target_duration_ms,
                "loop_media": False,
            }
            logger.info(f"Fixed duration mode (no audio): target_duration_ms={target_duration_ms}")

        # Build timeline
        builder = TimelineBuilder(
            project_id=project_id,
            media_assets=media_assets,
            project_settings=project_settings,
            beat_config=beat_config,
        )
        edl = builder.build()

        update_job_progress(10, "Saving timeline...")

        # Save EDL to filesystem
        edl_relative_path = save_edl(edl, project_id)

        # Extract hash (remove 'sha256:' prefix for database storage)
        edl_hash = edl["edl_hash"]
        if edl_hash.startswith("sha256:"):
            edl_hash = edl_hash[7:]

        # Update or create Timeline record
        timeline = db.query(Timeline).filter_by(project_id=project_id).first()

        if timeline:
            timeline.edl_path = edl_relative_path
            timeline.total_duration_ms = edl["total_duration_ms"]
            timeline.segment_count = edl["segment_count"]
            timeline.edl_hash = edl_hash
            timeline.modified_at = datetime.utcnow()
        else:
            timeline = Timeline(
                id=str(uuid.uuid4()),
                project_id=project_id,
                edl_path=edl_relative_path,
                total_duration_ms=edl["total_duration_ms"],
                segment_count=edl["segment_count"],
                edl_hash=edl_hash,
                generated_at=datetime.utcnow(),
                modified_at=datetime.utcnow(),
            )
            db.add(timeline)

        # Update render job with new edl_hash
        render_job = db.query(RenderJob).filter(
            RenderJob.project_id == project_id,
            RenderJob.job_type == job_type,
            RenderJob.status == "running",
        ).order_by(RenderJob.created_at.desc()).first()
        if render_job:
            render_job.edl_hash = edl_hash

        db.commit()

        update_job_progress(15, "Timeline ready, starting render...")
        logger.info(f"Timeline generated: segments={edl['segment_count']}, hash={edl_hash[:16]}...")

        # =====================================================================
        # Phase 2: Render (15-100%)
        # =====================================================================

        # Use audio track loaded earlier for path resolution
        audio_path = None
        if audio_track:
            audio_path = str(STORAGE_ROOT / audio_track.file_path)

        update_job_progress(17, "Resolving media paths...")

        # Create asset path resolver
        resolver = create_asset_path_resolver(db, project_id)

        # Validate EDL before render
        validation_errors = validate_edl_for_render(edl, resolver)
        if validation_errors:
            raise ValueError(f"EDL validation failed: {'; '.join(validation_errors)}")

        update_job_progress(20, "Preparing render...")

        # Determine settings based on job type
        motion_clip_paths = {}  # segment_index -> pre-rendered clip path

        if job_type == "preview":
            settings = PreviewSettings()
            timeout = RENDER_PREVIEW_TIMEOUT
        else:
            settings = RenderSettings()
            timeout = RENDER_FINAL_TIMEOUT

        # Pre-render motion clips for both preview and final renders
        update_job_progress(22, "Pre-rendering motion clips...")

        # Check if any image segments have effects
        image_segments = [s for s in edl["segments"] if s.get("media_type") == "image"]
        if image_segments and any(s.get("effects") for s in image_segments):
            motion_config = MotionRenderConfig(
                width=settings.width,
                height=settings.height,
                fps=settings.fps,
                crf=settings.crf,
                preset=settings.preset,
            )

            # Get beat grid path if audio analysis exists
            beat_grid_path = None
            if audio_track and audio_track.beat_grid_path:
                beat_grid_path = str(STORAGE_ROOT / audio_track.beat_grid_path)

            cache = MotionClipCache()

            def prerender_progress(current: int, total: int) -> None:
                # Map prerender progress to 22-40% range
                percent = 22 + int((current / total) * 18) if total > 0 else 22
                update_job_progress(percent, f"Pre-rendering clips: {current}/{total}")

            try:
                motion_clip_paths = prerender_segment_clips(
                    segments=edl["segments"],
                    asset_path_resolver=resolver,
                    config=motion_config,
                    cache=cache,
                    beat_grid_path=beat_grid_path,
                    progress_callback=prerender_progress,
                )
                logger.info(f"Pre-rendered {len(motion_clip_paths)} motion clips")
            except Exception as e:
                logger.warning(f"Motion clip pre-rendering failed, falling back: {e}")
                motion_clip_paths = {}

        # If no pre-rendered clips, simplify EDL (removes effects that need pre-rendering)
        if not motion_clip_paths:
            edl = simplify_edl_for_preview(edl)

        update_job_progress(40, "Building FFmpeg command...")

        # Create output directory and path
        output_dir = STORAGE_ROOT / "outputs" / project_id / job_type
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_filename = f"render_{timestamp}.mp4"
        output_path = output_dir / output_filename

        # Create motion clip resolver if we have pre-rendered clips
        motion_clip_resolver = None
        if motion_clip_paths:
            def motion_clip_resolver(seg_idx: int) -> Optional[str]:
                return motion_clip_paths.get(seg_idx)

        # Build FFmpeg command
        builder = FFmpegCommandBuilder(
            edl=edl,
            settings=settings,
            output_path=str(output_path),
            asset_path_resolver=resolver,
            audio_path=audio_path,
            motion_clip_resolver=motion_clip_resolver,
        )
        cmd = builder.build()

        # Log full command for debugging FFmpeg issues
        logger.info(f"Full FFmpeg command: {' '.join(cmd)}")

        update_job_progress(42, "Starting FFmpeg render...")

        # Calculate total duration for progress tracking
        total_duration_ms = edl.get("total_duration_ms", 0)
        if not total_duration_ms and edl.get("segments"):
            total_duration_ms = max(seg["timeline_out_ms"] for seg in edl["segments"])

        # Progress callback that updates RQ job
        # Scale FFmpeg progress (0-100) to render phase range (42-95)
        def progress_callback(percent: int, message: str) -> None:
            # 42% + (percent * 0.53) gives us 42-95% range
            scaled_percent = 42 + int(percent * 0.53)
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
            # Update render job status to failed
            update_render_job_status(
                db, project_id, job_type,
                status="failed",
                error_message=str(e)[:500],
                completed_at=datetime.utcnow(),
            )
            db.commit()
            raise

        update_job_progress(95, "Finalizing output")

        # Verify output file exists and get stats
        if not output_path.exists():
            update_render_job_status(
                db, project_id, job_type,
                status="failed",
                error_message="Output file was not created",
                completed_at=datetime.utcnow(),
            )
            raise FFmpegError("Output file was not created")

        file_size = output_path.stat().st_size
        if file_size == 0:
            update_render_job_status(
                db, project_id, job_type,
                status="failed",
                error_message="Output file is empty",
                completed_at=datetime.utcnow(),
            )
            raise FFmpegError("Output file is empty")

        # Calculate relative path for storage
        relative_output_path = f"outputs/{project_id}/{job_type}/{output_filename}"

        # Update render job status to complete
        update_render_job_status(
            db, project_id, job_type,
            status="complete",
            progress_percent=100,
            progress_message="Render complete",
            output_path=relative_output_path,
            file_size=file_size,
            completed_at=datetime.utcnow(),
        )

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
