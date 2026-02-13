"""
Timeline Generation Task for BeatStitch Worker

Generates the Edit Decision List (EDL) for a project by:
1. Loading media assets sorted by sort_order
2. Loading beat grid from /data/derived/{project_id}/beats.json
3. Snapping media segments to beat grid based on beats_per_cut setting
4. Calculating Ken Burns effect parameters for images
5. Assigning transitions between segments
6. Writing edl.json to /data/derived/{project_id}/edl.json
7. Computing edl_hash for race condition prevention
8. Updating Timeline record in database

Job timeout: 1 minute
"""

import hashlib
import json
import logging
import os
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

logger = logging.getLogger(__name__)

# Storage root from environment
STORAGE_ROOT = Path(os.environ.get("STORAGE_PATH", "/data"))

# Job timeout for timeline generation (1 minute)
TIMELINE_GENERATION_TIMEOUT = 60

# Ken Burns effect pan directions (cycle through these)
PAN_DIRECTIONS = [
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "center_zoom_in",
    "center_zoom_out",
]


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


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class EDLSegment:
    """Represents a single segment in the Edit Decision List."""

    segment_index: int
    media_asset_id: str
    media_type: str  # "image" or "video"
    timeline_in_ms: int
    timeline_out_ms: int
    render_duration_ms: int
    source_in_ms: int
    source_out_ms: int
    ken_burns: Optional[Dict[str, Any]] = None
    transition_in: Optional[Dict[str, Any]] = None
    transition_out: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "segment_index": self.segment_index,
            "media_asset_id": self.media_asset_id,
            "media_type": self.media_type,
            "timeline_in_ms": self.timeline_in_ms,
            "timeline_out_ms": self.timeline_out_ms,
            "render_duration_ms": self.render_duration_ms,
            "source_in_ms": self.source_in_ms,
            "source_out_ms": self.source_out_ms,
            "ken_burns": self.ken_burns,
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
        }


# ============================================================================
# Timeline Builder
# ============================================================================


class TimelineBuilder:
    """
    Builds the Edit Decision List (EDL) from media assets and beat grid.

    The timeline is built by stepping through beat indices, NOT by snapping
    arbitrary times to beats. This ensures no gaps or overlaps.
    """

    def __init__(
        self,
        project_id: str,
        media_assets: List[MediaAsset],
        beat_grid: dict,
        project_settings: dict,
        audio_duration_ms: int,
    ):
        """
        Initialize the timeline builder.

        Args:
            project_id: UUID of the project
            media_assets: List of MediaAsset records (sorted by sort_order)
            beat_grid: Beat grid loaded from beats.json
            project_settings: Project settings dict with beats_per_cut, transition_type, etc.
            audio_duration_ms: Duration of the audio track in milliseconds
        """
        self.project_id = project_id
        self.media_assets = sorted(media_assets, key=lambda a: a.sort_order)
        self.beat_grid = beat_grid
        self.settings = project_settings
        self.audio_duration_ms = audio_duration_ms

        # Extract settings with defaults
        self.beats_per_cut = project_settings.get("beats_per_cut", 4)
        self.transition_type = project_settings.get("transition_type", "cut")
        self.transition_duration_ms = project_settings.get("transition_duration_ms", 500)
        self.ken_burns_enabled = project_settings.get("ken_burns_enabled", True)
        self.ken_burns_zoom_range = project_settings.get("ken_burns_zoom_range", [1.0, 1.3])

        # Ken Burns effect state
        self._kb_zoom_direction = True  # True = zoom in, False = zoom out
        self._kb_pan_index = 0

    def build(self) -> dict:
        """
        Build the complete EDL.

        Returns:
            dict: Complete EDL structure ready for JSON serialization

        Raises:
            ValueError: If no media assets or beats available
        """
        if not self.media_assets:
            raise ValueError("No media assets available for timeline generation")

        # Step 1: Extract cut points from beat grid
        cut_points = self._extract_cut_points()

        if len(cut_points) < 2:
            raise ValueError("Not enough beats to create timeline (need at least 2 cut points)")

        # Step 2: Build media queue
        media_queue = self._build_media_queue(cut_points)

        # Step 3: Build segments
        segments = self._build_segments(cut_points, media_queue)

        # Step 4: Apply transition overlap adjustments
        if self.transition_type != "cut":
            segments = self._apply_transition_overlaps(segments)

        # Step 5: Compute EDL hash
        edl_hash = self._compute_edl_hash(segments)

        # Build final EDL structure
        total_duration_ms = segments[-1].timeline_out_ms if segments else 0

        edl = {
            "version": "1.0",
            "project_id": self.project_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "edl_hash": f"sha256:{edl_hash}",
            "beats_per_cut": self.beats_per_cut,
            "transition_type": self.transition_type,
            "transition_duration_ms": self.transition_duration_ms,
            "ken_burns_enabled": self.ken_burns_enabled,
            "total_duration_ms": total_duration_ms,
            "segment_count": len(segments),
            "audio": {
                "duration_ms": self.audio_duration_ms,
                "bpm": self.beat_grid.get("bpm", 120),
                "sample_rate": self.beat_grid.get("sample_rate", 44100),
            },
            "segments": [seg.to_dict() for seg in segments],
        }

        return edl

    def _extract_cut_points(self) -> List[int]:
        """
        Extract cut points by stepping through beat indices.

        cut_times = [beats[0], beats[N], beats[2N], ...]
        where N = beats_per_cut

        Returns:
            List of cut point timestamps in milliseconds
        """
        beats = self.beat_grid.get("beats", [])

        if not beats:
            # Fallback: generate evenly spaced cuts based on BPM
            logger.warning("No beats in beat grid, generating evenly spaced cuts")
            bpm = self.beat_grid.get("bpm", 120)
            beat_duration_ms = 60000 / bpm
            segment_duration_ms = int(self.beats_per_cut * beat_duration_ms)
            return list(range(0, self.audio_duration_ms, segment_duration_ms))

        cut_points = []
        for i in range(0, len(beats), self.beats_per_cut):
            cut_points.append(beats[i]["time_ms"])

        # Ensure we include the audio end as final cut point
        if cut_points and cut_points[-1] < self.audio_duration_ms:
            cut_points.append(self.audio_duration_ms)

        return cut_points

    def _build_media_queue(self, cut_points: List[int]) -> List[dict]:
        """
        Build a queue of media segments to fill the timeline.

        Videos are split into multiple segments if longer than cut duration.

        Args:
            cut_points: List of cut point timestamps

        Returns:
            List of media segment dictionaries
        """
        queue = []
        segment_count = len(cut_points) - 1

        if segment_count == 0:
            return queue

        for asset in self.media_assets:
            if asset.media_type == "image":
                queue.append({
                    "asset_id": asset.id,
                    "media_type": "image",
                    "source_in_ms": 0,
                    "source_out_ms": None,  # Images have no duration
                    "duration_ms": asset.duration_ms,
                })
            elif asset.media_type == "video":
                # Split video into chunks based on average segment duration
                avg_segment_ms = self.audio_duration_ms // max(1, segment_count)
                current_in = 0
                asset_duration = asset.duration_ms or 0

                while current_in < asset_duration:
                    chunk_duration = min(avg_segment_ms, asset_duration - current_in)
                    # Use if >= 30% of target duration
                    if chunk_duration >= avg_segment_ms * 0.3:
                        queue.append({
                            "asset_id": asset.id,
                            "media_type": "video",
                            "source_in_ms": current_in,
                            "source_out_ms": current_in + chunk_duration,
                            "duration_ms": chunk_duration,
                        })
                    current_in += chunk_duration

        return queue

    def _build_segments(
        self, cut_points: List[int], media_queue: List[dict]
    ) -> List[EDLSegment]:
        """
        Assign media from queue to timeline segments defined by cut points.

        Args:
            cut_points: List of cut point timestamps
            media_queue: Queue of media segments

        Returns:
            List of EDLSegment objects
        """
        if not media_queue:
            raise ValueError("No media assets available")

        segments = []
        original_queue = deepcopy(media_queue)
        queue = deepcopy(media_queue)

        for i in range(len(cut_points) - 1):
            if not queue:
                queue = deepcopy(original_queue)  # Loop media

            media = queue.pop(0)
            timeline_in_ms = cut_points[i]
            timeline_out_ms = cut_points[i + 1]
            render_duration_ms = timeline_out_ms - timeline_in_ms

            # For videos, adjust source_out based on actual render duration
            if media["media_type"] == "video":
                source_in_ms = media["source_in_ms"]
                source_out_ms = source_in_ms + render_duration_ms
            else:
                source_in_ms = 0
                source_out_ms = render_duration_ms

            # Calculate Ken Burns effect for images
            ken_burns = None
            if media["media_type"] == "image" and self.ken_burns_enabled:
                ken_burns = self._calculate_ken_burns(render_duration_ms)

            segment = EDLSegment(
                segment_index=i,
                media_asset_id=media["asset_id"],
                media_type=media["media_type"],
                timeline_in_ms=timeline_in_ms,
                timeline_out_ms=timeline_out_ms,
                render_duration_ms=render_duration_ms,
                source_in_ms=source_in_ms,
                source_out_ms=source_out_ms,
                ken_burns=ken_burns,
                transition_in=None,
                transition_out=None,
            )
            segments.append(segment)

        return segments

    def _calculate_ken_burns(self, duration_ms: int) -> dict:
        """
        Calculate Ken Burns effect parameters.

        Alternates zoom directions (in/out) and cycles through pan directions.

        Args:
            duration_ms: Duration of the segment in milliseconds

        Returns:
            dict with Ken Burns parameters
        """
        zoom_min, zoom_max = self.ken_burns_zoom_range

        # Alternate zoom direction
        if self._kb_zoom_direction:
            start_zoom = zoom_min
            end_zoom = zoom_max
        else:
            start_zoom = zoom_max
            end_zoom = zoom_min

        self._kb_zoom_direction = not self._kb_zoom_direction

        # Cycle through pan directions
        pan_direction = PAN_DIRECTIONS[self._kb_pan_index % len(PAN_DIRECTIONS)]
        self._kb_pan_index += 1

        return {
            "start_zoom": round(start_zoom, 2),
            "end_zoom": round(end_zoom, 2),
            "pan_direction": pan_direction,
        }

    def _apply_transition_overlaps(self, segments: List[EDLSegment]) -> List[EDLSegment]:
        """
        Apply transition overlap adjustments.

        For crossfades, segments overlap by transition_duration_ms.
        - Segment A: transition_out defines overlap with B
        - Segment B: timeline_in_ms is pulled back by overlap amount

        Args:
            segments: List of EDLSegment objects

        Returns:
            List of EDLSegment objects with transitions applied
        """
        if len(segments) <= 1:
            return segments

        overlap_ms = self.transition_duration_ms
        transition_def = {"type": self.transition_type, "duration_ms": overlap_ms}

        for i in range(len(segments)):
            # Cap transition at 50% of segment duration
            effective_overlap = min(overlap_ms, segments[i].render_duration_ms // 2)
            effective_transition = {"type": self.transition_type, "duration_ms": effective_overlap}

            # First segment has no transition_in
            if i == 0:
                segments[i].transition_in = None
            else:
                segments[i].transition_in = deepcopy(effective_transition)
                # Pull timeline_in back by overlap amount
                segments[i].timeline_in_ms -= effective_overlap

            # Last segment has no transition_out
            if i == len(segments) - 1:
                segments[i].transition_out = None
            else:
                segments[i].transition_out = deepcopy(effective_transition)

            # Recalculate render_duration after overlap adjustment
            segments[i].render_duration_ms = (
                segments[i].timeline_out_ms - segments[i].timeline_in_ms
            )

        return segments

    def _compute_edl_hash(self, segments: List[EDLSegment]) -> str:
        """
        Compute SHA-256 hash of EDL inputs for cache invalidation.

        Args:
            segments: List of EDLSegment objects

        Returns:
            SHA-256 hash string (without prefix)
        """
        payload = {
            "project_id": self.project_id,
            "settings": {
                "beats_per_cut": self.beats_per_cut,
                "transition_type": self.transition_type,
                "transition_duration_ms": self.transition_duration_ms,
                "ken_burns_enabled": self.ken_burns_enabled,
            },
            "media_order": [s.media_asset_id for s in segments],
            "audio_checksum": self.beat_grid.get("audio_file_checksum", ""),
            "beats_hash": hashlib.md5(
                json.dumps(self.beat_grid.get("beats", [])[:10]).encode()
            ).hexdigest(),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


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


def load_beat_grid(project_id: str) -> dict:
    """
    Load beat grid from filesystem.

    Args:
        project_id: UUID of the project

    Returns:
        dict: Beat grid data

    Raises:
        FileNotFoundError: If beats.json doesn't exist
    """
    beats_path = STORAGE_ROOT / "derived" / project_id / "beats.json"
    if not beats_path.exists():
        raise FileNotFoundError(f"Beat grid not found: {beats_path}")

    with open(beats_path, "r") as f:
        return json.load(f)


def save_edl(edl: dict, project_id: str) -> str:
    """
    Save EDL to filesystem.

    Args:
        edl: EDL dictionary
        project_id: UUID of the project

    Returns:
        str: Relative path to edl.json (relative to STORAGE_ROOT)
    """
    derived_dir = STORAGE_ROOT / "derived" / project_id
    derived_dir.mkdir(parents=True, exist_ok=True)

    edl_path = derived_dir / "edl.json"
    with open(edl_path, "w") as f:
        json.dump(edl, f, indent=2)

    logger.info(f"EDL saved to {edl_path}")
    return f"derived/{project_id}/edl.json"


def enqueue_timeline_generation(project_id: str):
    """
    Enqueue a timeline generation job with proper timeout.

    This helper ensures the 1-minute timeout is always applied.
    Use this instead of directly enqueueing the task.

    Args:
        project_id: UUID of the project

    Returns:
        RQ Job instance
    """
    from ..queues import timeline_queue

    return timeline_queue.enqueue(
        generate_timeline,
        project_id,
        job_timeout=TIMELINE_GENERATION_TIMEOUT,
    )


# ============================================================================
# Main Task Function
# ============================================================================


def generate_timeline(project_id: str) -> dict:
    """
    RQ task to generate timeline (EDL) for a project.

    Loads media assets and beat grid, generates EDL, writes to filesystem,
    and updates Timeline database record.

    Args:
        project_id: UUID of the project

    Returns:
        dict with edl_path, edl_hash, segment_count, and total_duration_ms

    Raises:
        ValueError: If project not found or no media/audio available
        FileNotFoundError: If beat grid doesn't exist
    """
    logger.info(f"Starting timeline generation for project={project_id}")
    update_job_progress(0, "Starting timeline generation")

    with get_db_session() as db:
        # Load project
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        update_job_progress(10, "Loading media assets")

        # Load media assets (sorted by sort_order)
        media_assets = (
            db.query(MediaAsset)
            .filter_by(project_id=project_id, processing_status="ready")
            .order_by(MediaAsset.sort_order)
            .all()
        )

        if not media_assets:
            raise ValueError(f"No processed media assets found for project {project_id}")

        update_job_progress(20, "Loading audio track")

        # Load audio track
        audio_track = db.query(AudioTrack).filter_by(project_id=project_id).first()
        if not audio_track:
            raise ValueError(f"No audio track found for project {project_id}")

        if audio_track.analysis_status != "complete":
            raise ValueError(f"Audio track analysis not complete: {audio_track.analysis_status}")

        update_job_progress(30, "Loading beat grid")

        # Load beat grid from filesystem
        try:
            beat_grid = load_beat_grid(project_id)
        except FileNotFoundError:
            raise ValueError(f"Beat grid not found for project {project_id}")

        update_job_progress(40, "Building timeline")

        # Extract project settings
        project_settings = {
            "beats_per_cut": project.beats_per_cut,
            "transition_type": project.transition_type,
            "transition_duration_ms": project.transition_duration_ms,
            "ken_burns_enabled": project.ken_burns_enabled,
            "output_width": project.output_width,
            "output_height": project.output_height,
            "output_fps": project.output_fps,
        }

        # Build timeline
        builder = TimelineBuilder(
            project_id=project_id,
            media_assets=media_assets,
            beat_grid=beat_grid,
            project_settings=project_settings,
            audio_duration_ms=audio_track.duration_ms,
        )

        edl = builder.build()

        update_job_progress(70, "Saving EDL")

        # Save EDL to filesystem
        edl_relative_path = save_edl(edl, project_id)

        update_job_progress(80, "Updating database")

        # Extract hash (remove 'sha256:' prefix for database storage)
        edl_hash = edl["edl_hash"]
        if edl_hash.startswith("sha256:"):
            edl_hash = edl_hash[7:]

        # Update or create Timeline record
        timeline = db.query(Timeline).filter_by(project_id=project_id).first()

        if timeline:
            # Update existing timeline
            timeline.edl_path = edl_relative_path
            timeline.total_duration_ms = edl["total_duration_ms"]
            timeline.segment_count = edl["segment_count"]
            timeline.edl_hash = edl_hash
            timeline.modified_at = datetime.utcnow()
        else:
            # Create new timeline
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

        # Update project status to ready
        project.status = "ready"
        project.status_message = "Timeline generated"

        db.commit()

        update_job_progress(100, "Timeline generation complete")

        logger.info(
            f"Timeline generation complete: segments={edl['segment_count']}, "
            f"duration_ms={edl['total_duration_ms']}, hash={edl_hash[:16]}..."
        )

        return {
            "edl_path": edl_relative_path,
            "edl_hash": edl_hash,
            "segment_count": edl["segment_count"],
            "total_duration_ms": edl["total_duration_ms"],
        }
