# BeatStitch - Processing: Beat Detection, Timeline & Rendering

[<- Back to Index](./00-index.md) | [<- Previous](./03-api-endpoints.md) | [Next ->](./05-infrastructure.md)

---

## 1. Beat Detection

### 1.1 Library Choice

| Library | Role | Strengths |
|---------|------|-----------|
| **madmom** | Primary | Academic-quality beat tracking via RNNBeatProcessor + DBNBeatTrackingProcessor |
| **librosa** | Fallback | General audio analysis, simpler beat tracking, always available |

> **Important**: We use madmom only for beat time detection, NOT for downbeat detection. The downbeat pipeline (`DBNDownBeatTrackingProcessor`) requires separate downbeat activations that are fragile and often produce incorrect results. For MVP, we derive `beat_number` in 4/4 time signature synthetically from the beat index.

### 1.2 Implementation

```python
from dataclasses import dataclass, asdict
from typing import List, Optional
from pathlib import Path
import hashlib
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Beat:
    time_ms: int
    beat_number: int      # 1-4 for 4/4 time
    is_downbeat: bool     # True if beat_number == 1
    confidence: float

@dataclass
class BeatGrid:
    version: str
    analyzer: str
    analyzed_at: str
    audio_file_checksum: str
    sample_rate: int
    duration_ms: int
    bpm: float
    bpm_confidence: float
    time_signature: str
    beats: List[dict]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BeatGrid":
        return cls(**data)


class BeatDetector:
    def __init__(self):
        self.madmom_available = self._check_madmom()
        logger.info(f"BeatDetector initialized. madmom available: {self.madmom_available}")

    def _check_madmom(self) -> bool:
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
            output_path: Path to save beats.json (e.g., /data/derived/{project_id}/beats.json)

        Returns:
            BeatGrid object
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

        # Load audio signal
        sig = madmom.audio.signal.Signal(audio_path, sample_rate=44100, num_channels=1)
        duration_ms = int(len(sig) / 44100 * 1000)

        # Beat tracking with neural network
        beat_proc = madmom.features.beats.RNNBeatProcessor()
        beat_act = beat_proc(sig)

        dbn_proc = madmom.features.beats.DBNBeatTrackingProcessor(fps=100)
        beat_times = dbn_proc(beat_act)  # Returns array of beat times in seconds

        # Tempo estimation
        tempo_proc = madmom.features.tempo.TempoEstimationProcessor(fps=100)
        tempo_result = tempo_proc(beat_act)
        bpm = float(tempo_result[0][0])
        bpm_confidence = float(tempo_result[0][1]) if len(tempo_result[0]) > 1 else 0.8

        # Build beat list with synthetic 4/4 beat numbers (no downbeat detection)
        beats = []
        for i, time_sec in enumerate(beat_times):
            beat_number = (i % 4) + 1  # Cycle 1, 2, 3, 4
            beats.append({
                "time_ms": int(time_sec * 1000),
                "beat_number": beat_number,
                "is_downbeat": beat_number == 1,
                "confidence": 0.9  # madmom generally high confidence
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
            beats=beats
        )

    def _analyze_with_librosa(self, audio_path: str, checksum: str) -> BeatGrid:
        """Fallback to librosa for beat detection."""
        import librosa

        y, sr = librosa.load(audio_path, sr=22050)
        duration_ms = int(len(y) / sr * 1000)

        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Handle numpy scalar for tempo
        bpm = float(tempo) if hasattr(tempo, 'item') else float(tempo)

        beats = []
        for i, time_sec in enumerate(beat_times):
            beat_number = (i % 4) + 1
            beats.append({
                "time_ms": int(time_sec * 1000),
                "beat_number": beat_number,
                "is_downbeat": beat_number == 1,
                "confidence": 0.7  # librosa generally lower confidence
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
            beats=beats
        )

    def _save_beat_grid(self, beat_grid: BeatGrid, output_path: str) -> None:
        """Save beat grid to filesystem (authoritative storage)."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(beat_grid.to_dict(), f, indent=2)
        logger.info(f"Beat grid saved to {output_path}")
```

### 1.3 Storage & Caching

| Aspect | Implementation |
|--------|----------------|
| **Authoritative Storage** | Filesystem: `/data/derived/{project_id}/beats.json` |
| **Database** | Stores metadata only: `bpm`, `beat_count`, `beat_grid_path` |
| **Redis** | May cache for quick access, but NOT authoritative |
| **Cache Invalidation** | Re-analyze if `audio_file_checksum` changes |

### 1.4 Performance & Edge Cases

| Factor | Handling |
|--------|----------|
| **Memory** | Process in chunks for files > 10 minutes |
| **Timeout** | 5-minute max; fail gracefully |
| **No beats (ambient)** | Return evenly spaced beats based on default 120 BPM |
| **Variable tempo** | Detect changes; warn user; use median tempo |
| **Long audio (>30 min)** | Analyze first 10 minutes for tempo estimation |

---

## 2. Timeline Generation

### 2.1 Algorithm Overview

The timeline is built by stepping through beat indices, NOT by snapping arbitrary times to beats. This ensures no gaps or overlaps.

```
INPUT:
  - media_assets: Ordered list of images/videos
  - beat_grid: From beats.json
  - settings: beats_per_cut, transition_type, transition_duration_ms, ken_burns_enabled

OUTPUT:
  - EDL JSON saved to /data/derived/{project_id}/edl.json

ALGORITHM:
  1. Extract cut points from beat grid: beats[0], beats[N], beats[2N], ...
     where N = beats_per_cut
  2. For each consecutive pair of cut points, create a segment
  3. Assign media assets to segments (loop if needed)
  4. Apply transition overlap adjustments to timeline_in_ms/timeline_out_ms
  5. Truncate final segment to audio duration
```

### 2.2 Implementation

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from copy import deepcopy
from pathlib import Path
import json
import random
import hashlib
from datetime import datetime


@dataclass
class EDLSegment:
    index: int
    media_asset_id: str
    media_type: str  # "image" or "video"
    timeline_in_ms: int
    timeline_out_ms: int
    render_duration_ms: int
    source_in_ms: int
    source_out_ms: int
    transition_in: Optional[Dict[str, Any]]
    transition_out: Optional[Dict[str, Any]]
    effects: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "media_asset_id": self.media_asset_id,
            "media_type": self.media_type,
            "timeline_in_ms": self.timeline_in_ms,
            "timeline_out_ms": self.timeline_out_ms,
            "render_duration_ms": self.render_duration_ms,
            "source_in_ms": self.source_in_ms,
            "source_out_ms": self.source_out_ms,
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
            "effects": self.effects,
        }


class TimelineBuilder:
    def __init__(
        self,
        media_assets: List,  # List of MediaAsset objects
        beat_grid: dict,      # Loaded from beats.json
        settings: dict,       # Project settings
        audio_duration_ms: int,
        project_id: str,
    ):
        self.media_assets = sorted(media_assets, key=lambda a: a.sort_order)
        self.beat_grid = beat_grid
        self.settings = settings
        self.audio_duration_ms = audio_duration_ms
        self.project_id = project_id

        self.beats_per_cut = settings.get("beats_per_cut", 4)
        self.transition_type = settings.get("transition_type", "cut")
        self.transition_duration_ms = settings.get("transition_duration_ms", 500)
        self.ken_burns_enabled = settings.get("ken_burns_enabled", True)

    def build(self) -> dict:
        """Build EDL from media assets and beat grid."""

        # Step 1: Extract cut points from beat grid
        cut_points = self._extract_cut_points()

        if len(cut_points) < 2:
            raise ValueError("Not enough beats to create timeline")

        # Step 2: Build media queue (split videos into segments)
        media_queue = self._build_media_queue(cut_points)

        # Step 3: Assign segments to cut points
        segments = self._build_segments(cut_points, media_queue)

        # Step 4: Apply transition overlap adjustments
        if self.transition_type != "cut":
            segments = self._apply_transition_overlaps(segments)

        # Step 5: Compute EDL hash
        edl_hash = self._compute_edl_hash(segments)

        # Build final EDL
        edl = {
            "version": "1.0",
            "project_id": self.project_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "edl_hash": edl_hash,
            "settings": {
                "output_width": self.settings.get("output_width", 1920),
                "output_height": self.settings.get("output_height", 1080),
                "output_fps": self.settings.get("output_fps", 30),
                "default_transition_type": self.transition_type,
                "default_transition_duration_ms": self.transition_duration_ms,
            },
            "audio": {
                "file_path": f"uploads/{self.project_id}/audio/track.mp3",  # Resolved at render
                "duration_ms": self.audio_duration_ms,
                "bpm": self.beat_grid.get("bpm", 120),
                "sample_rate": self.beat_grid.get("sample_rate", 44100),
                "start_offset_ms": 0,
            },
            "segments": [s.to_dict() for s in segments],
        }

        return edl

    def _extract_cut_points(self) -> List[int]:
        """
        Extract cut points by stepping through beat indices.
        cut_times = [beats[0], beats[N], beats[2N], ...]
        """
        beats = self.beat_grid.get("beats", [])
        if not beats:
            # Fallback: generate evenly spaced cuts based on BPM
            bpm = self.beat_grid.get("bpm", 120)
            beat_duration_ms = 60000 / bpm
            segment_duration_ms = int(self.beats_per_cut * beat_duration_ms)
            return list(range(0, self.audio_duration_ms, segment_duration_ms))

        cut_points = []
        for i in range(0, len(beats), self.beats_per_cut):
            cut_points.append(beats[i]["time_ms"])

        # Ensure we include the audio end as final cut point
        if cut_points[-1] < self.audio_duration_ms:
            cut_points.append(self.audio_duration_ms)

        return cut_points

    def _build_media_queue(self, cut_points: List[int]) -> List[dict]:
        """
        Build a queue of media segments to fill the timeline.
        Videos are split into multiple segments if longer than cut duration.
        """
        queue = []
        segment_count = len(cut_points) - 1

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
                while current_in < (asset.duration_ms or 0):
                    chunk_duration = min(avg_segment_ms, asset.duration_ms - current_in)
                    if chunk_duration >= avg_segment_ms * 0.3:  # Use if >= 30% of target
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

            segment = EDLSegment(
                index=i,
                media_asset_id=media["asset_id"],
                media_type=media["media_type"],
                timeline_in_ms=timeline_in_ms,
                timeline_out_ms=timeline_out_ms,
                render_duration_ms=render_duration_ms,
                source_in_ms=source_in_ms,
                source_out_ms=source_out_ms,
                transition_in=None,
                transition_out=None,
                effects=self._calculate_effects(media),
            )
            segments.append(segment)

        return segments

    def _apply_transition_overlaps(self, segments: List[EDLSegment]) -> List[EDLSegment]:
        """
        Apply transition overlap adjustments.

        For crossfades, segments overlap by transition_duration_ms.
        - Segment A: transition_out defines overlap with B
        - Segment B: timeline_in_ms is pulled back by overlap amount

        Timeline representation:
          Segment A: |================|
          Segment B:            |=====|================|
                                ^overlap^
        """
        if len(segments) <= 1:
            return segments

        overlap_ms = self.transition_duration_ms
        transition_def = {"type": self.transition_type, "duration_ms": overlap_ms}

        for i in range(len(segments)):
            # First segment has no transition_in
            if i == 0:
                segments[i].transition_in = None
            else:
                segments[i].transition_in = deepcopy(transition_def)
                # Pull timeline_in back by overlap amount
                segments[i].timeline_in_ms -= overlap_ms

            # Last segment has no transition_out
            if i == len(segments) - 1:
                segments[i].transition_out = None
            else:
                segments[i].transition_out = deepcopy(transition_def)

            # Recalculate render_duration after overlap adjustment
            segments[i].render_duration_ms = (
                segments[i].timeline_out_ms - segments[i].timeline_in_ms
            )

        return segments

    def _calculate_effects(self, media: dict) -> dict:
        """Generate Ken Burns effect for images."""
        if media["media_type"] == "image" and self.ken_burns_enabled:
            return {
                "ken_burns": {
                    "enabled": True,
                    "start_zoom": round(random.uniform(1.0, 1.1), 2),
                    "end_zoom": round(random.uniform(1.15, 1.3), 2),
                    "start_x": round(random.uniform(0.4, 0.6), 2),
                    "start_y": round(random.uniform(0.4, 0.6), 2),
                    "end_x": round(random.uniform(0.4, 0.6), 2),
                    "end_y": round(random.uniform(0.4, 0.6), 2),
                }
            }
        return {}

    def _compute_edl_hash(self, segments: List[EDLSegment]) -> str:
        """Compute hash of EDL inputs for cache invalidation."""
        payload = {
            "settings": self.settings,
            "media_order": [s.media_asset_id for s in segments],
            "audio_checksum": self.beat_grid.get("audio_file_checksum", ""),
            "beats_hash": hashlib.md5(
                json.dumps(self.beat_grid.get("beats", [])[:10]).encode()
            ).hexdigest(),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def save_edl(edl: dict, output_path: str) -> None:
    """Save EDL to filesystem (authoritative storage)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(edl, f, indent=2)
```

### 2.3 Transition Timing Model

```
WITHOUT TRANSITIONS (cut):
Segment 0: |---- 0ms ---- 2000ms ----|
Segment 1:                            |---- 2000ms ---- 4000ms ----|
Segment 2:                                                          |---- 4000ms ---- 6000ms ----|

WITH CROSSFADE (500ms overlap):
Segment 0: |---- 0ms ----------- 2000ms ----|
Segment 1:                   |---- 1500ms ----------- 4000ms ----|
                             ^overlap^
Segment 2:                                        |---- 3500ms ----------- 6000ms ----|

Key insight: timeline_in_ms of segment N+1 is pulled BACK by overlap amount,
causing overlap with segment N's ending.
```

### 2.4 Edge Cases

| Scenario | Handling |
|----------|----------|
| No media | Return error |
| Single image | Use for all segments (loop) |
| Not enough media | Loop through assets |
| Too much media | Use what fits, ignore rest |
| Very short video segment | Use entire remaining clip |
| Final segment shorter than overlap | Clamp overlap to segment duration |
| Transition > 50% of segment | Cap transition at 50% |

---

## 3. Rendering Strategy

### 3.1 Key Design Decisions

1. **One input per unique asset** - NOT one input per segment
2. **Use trim/setpts** to carve segments from asset streams
3. **Resolve source_path at render time** via `media_asset_id` lookup
4. **Track audio input index explicitly**
5. **Handle no-audio case** with `anullsrc`

### 3.2 FFmpeg Filter Graph Architecture

```
INPUTS (one per unique asset + audio):
  [0] image_a.jpg (with -loop 1)
  [1] video_b.mp4
  [2] image_c.jpg (with -loop 1)
  [3] audio.mp3

                                    +------------------+
                                    |     OUTPUT       |
                                    |   1920x1080      |
                                    +--------+---------+
                                             |
                                    +--------+---------+
                                    |    final mix     |
                                    | video + audio    |
                                    +--------+---------+
                                             |
                        +--------------------+--------------------+
                        |                                         |
               +--------+--------+                       +--------+--------+
               |   xfade chain   |                       |   audio trim    |
               |   or concat     |                       |   + asetpts     |
               +--------+--------+                       +-----------------+
                        |
        +---------------+---------------+---------------+
        |               |               |               |
   +----+----+     +----+----+     +----+----+     +----+----+
   | seg 0   |     | seg 1   |     | seg 2   |     | seg N   |
   | trim +  |     | trim +  |     | trim +  |     | trim +  |
   | scale   |     | scale   |     | scale   |     | scale   |
   +----+----+     +----+----+     +----+----+     +----+----+
        |               |               |               |
   [input 0]       [input 1]       [input 2]       [input N]
```

### 3.3 FFmpeg Command Builder

```python
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RenderSettings:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_bitrate: str = "8M"
    audio_bitrate: str = "192k"
    preset: str = "medium"
    crf: int = 23


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
        asset_path_resolver: callable,  # (asset_id) -> file_path
        audio_path: Optional[str] = None,
    ):
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
        """Build complete FFmpeg command."""
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
            seg_idx = seg["index"]
            input_idx = self.input_map[seg["media_asset_id"]]
            in_label = f"[{input_idx}:v]"
            out_label = f"[v{seg_idx}]"

            duration_sec = seg["render_duration_ms"] / 1000
            source_in_sec = seg["source_in_ms"] / 1000

            if seg["media_type"] == "image":
                # Image: trim by time, apply Ken Burns or scale
                kb = seg.get("effects", {}).get("ken_burns", {})
                if kb.get("enabled"):
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
            transition_type = self.edl["settings"].get("default_transition_type", "cut")
            if transition_type == "cut":
                concat_inputs = "".join(segment_labels)
                filters.append(
                    f"{concat_inputs}concat=n={len(segment_labels)}:v=1:a=0[outv]"
                )
            else:
                filters.extend(self._build_xfade_chain(segment_labels))
        else:
            # Single segment: just relabel
            filters.append(f"{segment_labels[0]}setpts=PTS-STARTPTS[outv]")

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
        """Build Ken Burns (zoompan) filter for an image."""
        duration_frames = int(duration_sec * fps)
        sz = kb.get("start_zoom", 1.0)
        ez = kb.get("end_zoom", 1.2)
        sx = kb.get("start_x", 0.5)
        sy = kb.get("start_y", 0.5)
        ex = kb.get("end_x", 0.5)
        ey = kb.get("end_y", 0.5)

        # Calculate zoom and pan expressions
        zoom_expr = f"if(eq(on,1),{sz},{sz}+(({ez}-{sz})/{duration_frames})*on)"
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

    def _build_xfade_chain(self, labels: List[str]) -> List[str]:
        """Build xfade chain for crossfade transitions."""
        filters = []
        trans_dur_sec = self.edl["settings"].get("default_transition_duration_ms", 500) / 1000
        current_label = labels[0]

        # Calculate xfade offsets based on segment durations
        cumulative_duration = 0

        for i in range(1, len(labels)):
            # Get previous segment's render duration
            prev_seg = self.edl["segments"][i - 1]
            seg_dur_sec = prev_seg["render_duration_ms"] / 1000

            # xfade offset = cumulative duration - transition overlap
            offset = cumulative_duration + seg_dur_sec - trans_dur_sec
            offset = max(0, offset)  # Ensure non-negative

            next_label = labels[i]
            out_label = f"[xf{i}]" if i < len(labels) - 1 else "[outv]"

            filters.append(
                f"{current_label}{next_label}"
                f"xfade=transition=fade:duration={trans_dur_sec}:offset={offset}"
                f"{out_label}"
            )

            current_label = out_label
            cumulative_duration = offset + trans_dur_sec

        return filters

    def _build_audio_filter(self) -> str:
        """Build audio filter chain."""
        # Calculate total timeline duration (last segment's timeline_out_ms)
        last_seg = self.edl["segments"][-1]
        total_duration_sec = last_seg["timeline_out_ms"] / 1000

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
```

### 3.4 Example FFmpeg Command

```bash
# Inputs: 2 images (used by 3 segments), 1 video, 1 audio
ffmpeg -y \
  -loop 1 -i image_a.jpg \
  -i video_b.mp4 \
  -loop 1 -i image_c.jpg \
  -i audio.mp3 \
  -filter_complex "
    [0:v]trim=duration=2,setpts=PTS-STARTPTS,scale=8000:-1,zoompan=z='1.0+((0.2)/60)*on':x='(iw-iw/zoom)*0.5':y='(ih-ih/zoom)*0.5':d=60:s=1920x1080:fps=30,setsar=1[v0];
    [1:v]trim=start=5:duration=2,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30[v1];
    [2:v]trim=duration=2,setpts=PTS-STARTPTS,scale=8000:-1,zoompan=z='1.1+((0.15)/60)*on':x='(iw-iw/zoom)*0.5':y='(ih-ih/zoom)*0.5':d=60:s=1920x1080:fps=30,setsar=1[v2];
    [v0][v1]xfade=transition=fade:duration=0.5:offset=1.5[xf1];
    [xf1][v2]xfade=transition=fade:duration=0.5:offset=3.0[outv];
    [3:a]atrim=0:5.5,asetpts=PTS-STARTPTS[outa]
  " \
  -map "[outv]" -map "[outa]" \
  -c:v libx264 -preset medium -crf 23 -b:v 8M \
  -c:a aac -b:a 192k -movflags +faststart -pix_fmt yuv420p \
  output.mp4
```

### 3.5 Asset Path Resolution

```python
def create_asset_path_resolver(db_session, project_id: str):
    """
    Factory to create asset path resolver.
    Resolves media_asset_id -> file_path via database lookup.
    """
    # Pre-load all assets for the project
    from app.models import MediaAsset

    assets = db_session.query(MediaAsset).filter(
        MediaAsset.project_id == project_id
    ).all()

    path_map = {asset.id: asset.file_path for asset in assets}

    def resolver(asset_id: str) -> str:
        if asset_id not in path_map:
            raise ValueError(f"Unknown asset_id: {asset_id}")
        return path_map[asset_id]

    return resolver
```

---

## 4. Preview Strategy

### 4.1 Preview vs Final Settings

| Setting | Preview | Final |
|---------|---------|-------|
| Resolution | 640x360 | 1920x1080 |
| Bitrate | 1M | 8M |
| Preset | ultrafast | medium |
| CRF | 32 | 23 |
| FPS | 24 | 30 |
| Ken Burns | Simplified (less zoom) | Full |
| Transitions | Same | Same |

### 4.2 Implementation

```python
@dataclass
class PreviewSettings(RenderSettings):
    width: int = 640
    height: int = 360
    fps: int = 24
    video_bitrate: str = "1M"
    preset: str = "ultrafast"
    crf: int = 32


def simplify_edl_for_preview(edl: dict) -> dict:
    """Create simplified EDL for preview rendering."""
    preview_edl = deepcopy(edl)

    # Simplify Ken Burns (reduce zoom range)
    for segment in preview_edl["segments"]:
        kb = segment.get("effects", {}).get("ken_burns", {})
        if kb.get("enabled"):
            # Reduce zoom range for faster processing
            kb["start_zoom"] = 1.0
            kb["end_zoom"] = min(kb.get("end_zoom", 1.2), 1.1)

    return preview_edl
```

---

## 5. Progress Tracking

### 5.1 FFmpeg Progress Output

FFmpeg's `-progress` option outputs key-value pairs. The most reliable fields are:

| Field | Description |
|-------|-------------|
| `out_time_us` | Output time in microseconds (preferred) |
| `out_time_ms` | Output time in milliseconds (may not always be present) |
| `out_time` | Output time as HH:MM:SS.microseconds string |
| `frame` | Number of frames encoded |
| `progress` | "continue" or "end" |

### 5.2 Robust Progress Parser

```python
import re
import subprocess
from typing import Callable, List, Optional
import logging

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    pass


def run_ffmpeg_with_progress(
    cmd: List[str],
    total_duration_ms: int,
    progress_callback: Callable[[int, str], None],
    timeout_seconds: int = 1800,  # 30 minutes
) -> None:
    """
    Run FFmpeg command with progress tracking.

    Args:
        cmd: FFmpeg command as list of arguments
        total_duration_ms: Expected total duration in milliseconds
        progress_callback: Function called with (percent, message)
        timeout_seconds: Maximum allowed runtime
    """
    # Add progress output to command
    cmd_with_progress = cmd + ["-progress", "pipe:1", "-stats_period", "0.5"]

    process = subprocess.Popen(
        cmd_with_progress,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    # Patterns for parsing progress output
    # Prefer out_time_us (microseconds) as it's most reliable
    time_us_pattern = re.compile(r"out_time_us=(\d+)")
    time_ms_pattern = re.compile(r"out_time_ms=(\d+)")
    time_str_pattern = re.compile(r"out_time=(\d+):(\d+):(\d+)\.(\d+)")
    progress_pattern = re.compile(r"progress=(\w+)")

    last_percent = 0

    try:
        for line in process.stdout:
            line = line.strip()

            # Check for completion
            progress_match = progress_pattern.search(line)
            if progress_match and progress_match.group(1) == "end":
                progress_callback(100, "Render complete")
                break

            # Try to extract current time (in order of preference)
            current_ms: Optional[int] = None

            # Method 1: out_time_us (microseconds -> milliseconds)
            match = time_us_pattern.search(line)
            if match:
                current_ms = int(match.group(1)) // 1000

            # Method 2: out_time_ms (already milliseconds)
            if current_ms is None:
                match = time_ms_pattern.search(line)
                if match:
                    current_ms = int(match.group(1))

            # Method 3: Parse out_time string HH:MM:SS.microseconds
            if current_ms is None:
                match = time_str_pattern.search(line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = int(match.group(3))
                    # Group 4 is microseconds (6 digits, but may be truncated)
                    micro_str = match.group(4).ljust(6, '0')[:6]
                    microseconds = int(micro_str)
                    current_ms = (
                        hours * 3600000
                        + minutes * 60000
                        + seconds * 1000
                        + microseconds // 1000
                    )

            # Calculate and report progress
            if current_ms is not None and total_duration_ms > 0:
                percent = min(99, int((current_ms / total_duration_ms) * 100))
                if percent > last_percent:
                    last_percent = percent
                    progress_callback(percent, f"Rendering: {percent}%")

        # Wait for process to complete
        return_code = process.wait(timeout=timeout_seconds)

        if return_code != 0:
            stderr_output = process.stderr.read()
            raise FFmpegError(f"FFmpeg failed with code {return_code}: {stderr_output}")

    except subprocess.TimeoutExpired:
        process.kill()
        raise FFmpegError(f"FFmpeg timed out after {timeout_seconds} seconds")

    except Exception as e:
        process.kill()
        raise FFmpegError(f"FFmpeg error: {str(e)}")
```

### 5.3 Integration with RQ Job

```python
from rq import get_current_job

def render_video_task(project_id: str, job_type: str, render_settings: dict):
    """RQ task for video rendering."""
    job = get_current_job()

    def update_progress(percent: int, message: str):
        if job:
            job.meta["progress_percent"] = percent
            job.meta["progress_message"] = message
            job.save_meta()

    # ... load EDL, build command ...

    run_ffmpeg_with_progress(
        cmd=ffmpeg_cmd,
        total_duration_ms=edl["segments"][-1]["timeline_out_ms"],
        progress_callback=update_progress,
    )
```

---

## 6. Error Handling & Recovery

### 6.1 Common FFmpeg Errors

| Error | Detection | Recovery |
|-------|-----------|----------|
| Invalid input file | Exit code + stderr | Mark job failed, notify user |
| Out of disk space | "No space left" in stderr | Clean temp files, retry |
| Corrupted video | Decode errors in stderr | Skip segment or use fallback |
| Memory exhaustion | OOM killer / exit 137 | Reduce resolution, retry |
| Timeout | Process exceeds limit | Kill process, mark failed |

### 6.2 Validation Before Render

```python
def validate_edl_for_render(edl: dict, asset_resolver: callable) -> List[str]:
    """
    Validate EDL before starting render.
    Returns list of error messages (empty if valid).
    """
    errors = []

    # Check segments exist
    if not edl.get("segments"):
        errors.append("EDL has no segments")
        return errors

    # Validate each segment
    for seg in edl["segments"]:
        asset_id = seg["media_asset_id"]

        # Check asset exists and is accessible
        try:
            path = asset_resolver(asset_id)
            if not Path(path).exists():
                errors.append(f"Asset file not found: {path}")
        except ValueError as e:
            errors.append(str(e))

        # Check timing is valid
        if seg["timeline_out_ms"] <= seg["timeline_in_ms"]:
            errors.append(f"Segment {seg['index']}: invalid timeline range")

        if seg["render_duration_ms"] <= 0:
            errors.append(f"Segment {seg['index']}: invalid render duration")

    return errors
```

---

[Next: Infrastructure (Jobs, Deployment, Security) ->](./05-infrastructure.md)
