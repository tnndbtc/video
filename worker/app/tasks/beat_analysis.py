"""
Beat Analysis Task for BeatStitch Worker

Analyzes audio files for beat detection using:
- madmom (primary): Academic-quality beat tracking via RNN + DBN processors
- librosa (fallback): Simpler beat tracking if madmom fails

Writes beat grid to /data/derived/{project_id}/beats.json
Updates AudioTrack record with analysis results.

Job timeout: 5 minutes
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rq import get_current_job

from ..db import get_db_session

logger = logging.getLogger(__name__)

# Storage root from environment
STORAGE_ROOT = Path(os.environ.get("STORAGE_PATH", "/data"))

# Job timeout for beat analysis (5 minutes)
BEAT_ANALYSIS_TIMEOUT = 300


@dataclass
class Beat:
    """Represents a single beat in the beat grid."""

    time_ms: int
    beat_number: int  # 1-4 for 4/4 time
    is_downbeat: bool  # True if beat_number == 1


@dataclass
class BeatGrid:
    """
    Complete beat grid for an audio track.

    Stored as JSON at /data/derived/{project_id}/beats.json
    """

    bpm: float
    total_beats: int
    time_signature: str
    beats: List[Dict[str, Any]]
    # Additional metadata
    version: str = "1.0"
    analyzer: str = "unknown"
    analyzed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    audio_file_checksum: str = ""
    sample_rate: int = 44100
    duration_ms: int = 0
    bpm_confidence: float = 0.8

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class BeatDetector:
    """
    Beat detection using madmom (primary) with librosa fallback.

    Only uses madmom for beat time detection, NOT for downbeat detection.
    The downbeat pipeline is fragile and often produces incorrect results.
    For MVP, we derive beat_number in 4/4 time signature synthetically.
    """

    def __init__(self) -> None:
        self.madmom_available = self._check_madmom()
        logger.info(f"BeatDetector initialized. madmom available: {self.madmom_available}")

    def _check_madmom(self) -> bool:
        """Check if madmom is available."""
        try:
            import madmom

            return True
        except ImportError:
            logger.warning("madmom not available, will use librosa fallback")
            return False

    def analyze(self, audio_path: str, output_path: str) -> BeatGrid:
        """
        Analyze audio and return beat grid.
        Falls back to librosa if madmom fails or is unavailable.

        Args:
            audio_path: Path to audio file
            output_path: Path to save beats.json

        Returns:
            BeatGrid object with detected beats
        """
        # Compute checksum for cache validation
        audio_checksum = self._compute_checksum(audio_path)

        try:
            if self.madmom_available:
                beat_grid = self._analyze_with_madmom(audio_path, audio_checksum)
            else:
                beat_grid = self._analyze_with_librosa(audio_path, audio_checksum)
        except Exception as e:
            logger.warning(f"madmom failed: {e}, falling back to librosa")
            beat_grid = self._analyze_with_librosa(audio_path, audio_checksum)

        # Persist to filesystem (authoritative storage)
        self._save_beat_grid(beat_grid, output_path)

        return beat_grid

    def _compute_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum of audio file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def _analyze_with_madmom(self, audio_path: str, checksum: str) -> BeatGrid:
        """
        Use madmom for beat detection.
        Only uses RNNBeatProcessor + DBNBeatTrackingProcessor for beat times.
        Does NOT use downbeat detection (fragile pipeline).
        """
        import madmom

        logger.info(f"Analyzing with madmom: {audio_path}")

        # Load audio signal
        sig = madmom.audio.signal.Signal(audio_path, sample_rate=44100, num_channels=1)
        duration_ms = int(len(sig) / 44100 * 1000)

        # Beat tracking with neural network
        beat_proc = madmom.features.beats.RNNBeatProcessor()
        beat_act = beat_proc(sig)

        dbn_proc = madmom.features.beats.DBNBeatTrackingProcessor(fps=100)
        beat_times = dbn_proc(beat_act)  # Returns array of beat times in seconds

        # Handle edge case: no beats detected
        if len(beat_times) == 0:
            logger.warning("No beats detected by madmom, generating default beat grid")
            return self._generate_default_beat_grid(duration_ms, checksum, "madmom")

        # Tempo estimation
        try:
            tempo_proc = madmom.features.tempo.TempoEstimationProcessor(fps=100)
            tempo_result = tempo_proc(beat_act)
            bpm = float(tempo_result[0][0])
            bpm_confidence = float(tempo_result[0][1]) if len(tempo_result[0]) > 1 else 0.8
        except Exception as e:
            logger.warning(f"Tempo estimation failed: {e}, calculating from beat intervals")
            # Calculate BPM from beat intervals
            if len(beat_times) >= 2:
                intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
                avg_interval = sum(intervals) / len(intervals)
                bpm = 60.0 / avg_interval if avg_interval > 0 else 120.0
            else:
                bpm = 120.0
            bpm_confidence = 0.6

        # Build beat list with synthetic 4/4 beat numbers (no downbeat detection)
        beats = []
        for i, time_sec in enumerate(beat_times):
            beat_number = (i % 4) + 1  # Cycle 1, 2, 3, 4
            beats.append({
                "time_ms": int(time_sec * 1000),
                "beat_number": beat_number,
                "is_downbeat": beat_number == 1,
            })

        return BeatGrid(
            version="1.0",
            analyzer="madmom",
            analyzed_at=datetime.utcnow().isoformat() + "Z",
            audio_file_checksum=checksum,
            sample_rate=44100,
            duration_ms=duration_ms,
            bpm=bpm,
            bpm_confidence=bpm_confidence,
            time_signature="4/4",
            total_beats=len(beats),
            beats=beats,
        )

    def _analyze_with_librosa(self, audio_path: str, checksum: str) -> BeatGrid:
        """Fallback to librosa for beat detection."""
        import librosa

        logger.info(f"Analyzing with librosa: {audio_path}")

        y, sr = librosa.load(audio_path, sr=22050)
        duration_ms = int(len(y) / sr * 1000)

        # Handle edge case: very short audio
        if duration_ms < 1000:
            logger.warning("Audio too short for beat detection, generating default beat grid")
            return self._generate_default_beat_grid(duration_ms, checksum, "librosa")

        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Handle edge case: no beats detected
        if len(beat_times) == 0:
            logger.warning("No beats detected by librosa, generating default beat grid")
            return self._generate_default_beat_grid(duration_ms, checksum, "librosa")

        # Handle numpy scalar for tempo
        bpm = float(tempo) if hasattr(tempo, "item") else float(tempo)

        beats = []
        for i, time_sec in enumerate(beat_times):
            beat_number = (i % 4) + 1
            beats.append({
                "time_ms": int(time_sec * 1000),
                "beat_number": beat_number,
                "is_downbeat": beat_number == 1,
            })

        return BeatGrid(
            version="1.0",
            analyzer="librosa",
            analyzed_at=datetime.utcnow().isoformat() + "Z",
            audio_file_checksum=checksum,
            sample_rate=22050,
            duration_ms=duration_ms,
            bpm=bpm,
            bpm_confidence=0.7,
            time_signature="4/4",
            total_beats=len(beats),
            beats=beats,
        )

    def _generate_default_beat_grid(
        self, duration_ms: int, checksum: str, analyzer: str
    ) -> BeatGrid:
        """
        Generate a default beat grid when no beats are detected.
        Uses 120 BPM as the default tempo (standard for ambient/beatless music).
        """
        default_bpm = 120.0
        beat_interval_ms = int(60000 / default_bpm)  # 500ms at 120 BPM

        beats = []
        current_ms = 0
        beat_index = 0

        while current_ms < duration_ms:
            beat_number = (beat_index % 4) + 1
            beats.append({
                "time_ms": current_ms,
                "beat_number": beat_number,
                "is_downbeat": beat_number == 1,
            })
            current_ms += beat_interval_ms
            beat_index += 1

        return BeatGrid(
            version="1.0",
            analyzer=f"{analyzer}_default",
            analyzed_at=datetime.utcnow().isoformat() + "Z",
            audio_file_checksum=checksum,
            sample_rate=44100,
            duration_ms=duration_ms,
            bpm=default_bpm,
            bpm_confidence=0.0,  # No confidence for default grid
            time_signature="4/4",
            total_beats=len(beats),
            beats=beats,
        )

    def _save_beat_grid(self, beat_grid: BeatGrid, output_path: str) -> None:
        """Save beat grid to filesystem (authoritative storage)."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(beat_grid.to_dict(), f, indent=2)
        logger.info(f"Beat grid saved to {output_path}")


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


def enqueue_beat_analysis(project_id: str, audio_id: str):
    """
    Enqueue a beat analysis job with proper timeout.

    This helper ensures the 5-minute timeout is always applied.
    Use this instead of directly enqueueing the task.

    Args:
        project_id: UUID of the project
        audio_id: UUID of the AudioTrack record

    Returns:
        RQ Job instance
    """
    from ..queues import beat_queue

    return beat_queue.enqueue(
        analyze_beats,
        project_id,
        audio_id,
        job_timeout=BEAT_ANALYSIS_TIMEOUT,
    )


def analyze_beats(project_id: str, audio_id: str) -> dict:
    """
    RQ task to analyze audio for beat detection.

    Loads audio from filesystem, runs beat detection, writes results
    to derived/beats.json. The API reads from this file rather than
    storing beats in the database.

    Args:
        project_id: UUID of the project
        audio_id: UUID of the AudioTrack record

    Returns:
        dict with beats_path, bpm, and beat_count

    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If AudioTrack record not found
    """
    from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, BigInteger
    from sqlalchemy.orm import declarative_base

    # Define AudioTrack model locally to avoid circular imports
    # This matches the schema from backend/app/models/audio.py
    Base = declarative_base()

    class AudioTrack(Base):
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

    logger.info(f"Starting beat analysis for project={project_id}, audio={audio_id}")
    update_job_progress(0, "Starting beat analysis")

    with get_db_session() as db:
        # Get the audio track record
        audio_record = db.query(AudioTrack).filter_by(id=audio_id).first()

        if not audio_record:
            raise ValueError(f"AudioTrack not found: {audio_id}")

        # Verify project_id matches
        if audio_record.project_id != project_id:
            raise ValueError(f"AudioTrack {audio_id} does not belong to project {project_id}")

        # Update status to processing
        audio_record.analysis_status = "processing"
        audio_record.analysis_error = None
        db.commit()

        try:
            # Resolve audio path
            audio_path = STORAGE_ROOT / audio_record.file_path
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            update_job_progress(10, "Loading audio file")

            # Set up output path for beats.json
            derived_dir = STORAGE_ROOT / "derived" / project_id
            derived_dir.mkdir(parents=True, exist_ok=True)
            beats_path = derived_dir / "beats.json"

            update_job_progress(20, "Detecting beats")

            # Run beat detection
            detector = BeatDetector()
            beat_grid = detector.analyze(str(audio_path), str(beats_path))

            update_job_progress(90, "Saving results")

            # Update database with results
            # Store relative path (relative to /data)
            relative_beats_path = f"derived/{project_id}/beats.json"

            audio_record.bpm = beat_grid.bpm
            audio_record.beat_count = beat_grid.total_beats
            audio_record.beat_grid_path = relative_beats_path
            audio_record.analysis_status = "complete"
            audio_record.analysis_error = None
            audio_record.analyzed_at = datetime.utcnow()
            db.commit()

            update_job_progress(100, "Analysis complete")

            logger.info(
                f"Beat analysis complete: bpm={beat_grid.bpm}, "
                f"beats={beat_grid.total_beats}, path={relative_beats_path}"
            )

            return {
                "beats_path": relative_beats_path,
                "bpm": beat_grid.bpm,
                "beat_count": beat_grid.total_beats,
                "analyzer": beat_grid.analyzer,
            }

        except Exception as e:
            # Update status to failed
            error_message = str(e)[:500]  # Truncate to fit database column
            audio_record.analysis_status = "failed"
            audio_record.analysis_error = error_message
            db.commit()

            logger.error(f"Beat analysis failed: {e}")
            raise
