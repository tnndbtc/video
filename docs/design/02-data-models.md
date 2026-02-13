# BeatStitch - Data Models & Schemas

[<- Back to Index](./00-index.md) | [<- Previous](./01-overview.md) | [Next ->](./03-api-endpoints.md)

---

## 1. Database Schema (SQLAlchemy)

### 1.1 User Model

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[List["Project"]] = relationship(back_populates="owner")
```

### 1.2 Project Model

```python
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Settings
    beats_per_cut: Mapped[int] = mapped_column(Integer, default=4)
    transition_type: Mapped[str] = mapped_column(String(20), default="cut")
    transition_duration_ms: Mapped[int] = mapped_column(Integer, default=500)
    ken_burns_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    output_width: Mapped[int] = mapped_column(Integer, default=1920)
    output_height: Mapped[int] = mapped_column(Integer, default=1080)
    output_fps: Mapped[int] = mapped_column(Integer, default=30)

    # Status: draft, analyzing, ready, rendering, complete, error
    status: Mapped[str] = mapped_column(String(20), default="draft")
    status_message: Mapped[Optional[str]] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="projects")
    media_assets: Mapped[List["MediaAsset"]] = relationship(back_populates="project")
    audio_track: Mapped[Optional["AudioTrack"]] = relationship(back_populates="project")
    timeline: Mapped[Optional["Timeline"]] = relationship(back_populates="project")
    render_jobs: Mapped[List["RenderJob"]] = relationship(back_populates="project")
```

#### Project Status Values

| Status | Description |
|--------|-------------|
| `draft` | Project created, media upload in progress |
| `analyzing` | Beat analysis or other background processing in progress |
| `ready` | All analysis complete, timeline can be built or edited |
| `rendering` | Render job currently in progress |
| `complete` | At least one successful render exists |
| `error` | Analysis or processing failed (see `status_message`) |

### 1.3 MediaAsset Model

```python
class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # File info
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Media type: image, video
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # Dimensions (native/storage dimensions)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)  # Videos only
    fps: Mapped[Optional[float]] = mapped_column(Float)          # Videos only

    # Display corrections
    rotation_deg: Mapped[int] = mapped_column(Integer, default=0)  # 0, 90, 180, 270
    display_aspect_ratio: Mapped[Optional[str]] = mapped_column(String(10))  # e.g., "16:9", "4:3"

    # Derived assets
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500))
    proxy_path: Mapped[Optional[str]] = mapped_column(String(500))

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="media_assets")
```

#### Display Dimension Calculation

The renderer must compute effective display dimensions:

```python
def get_display_dimensions(asset: MediaAsset) -> tuple[int, int]:
    """Returns (width, height) accounting for rotation and DAR."""
    w, h = asset.width, asset.height

    # Apply rotation
    if asset.rotation_deg in (90, 270):
        w, h = h, w

    # Apply display aspect ratio override if present
    if asset.display_aspect_ratio:
        # Parse "16:9" format and adjust width to match
        dar_w, dar_h = map(int, asset.display_aspect_ratio.split(":"))
        w = int(h * dar_w / dar_h)

    return w, h
```

### 1.4 AudioTrack Model

```python
class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)

    # File info (original upload)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Audio metadata
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer)  # e.g., 44100, 48000

    # Beat analysis results (metadata only - payload on filesystem)
    bpm: Mapped[Optional[float]] = mapped_column(Float)
    beat_count: Mapped[Optional[int]] = mapped_column(Integer)
    beat_grid_path: Mapped[Optional[str]] = mapped_column(String(500))
    # Path to: /data/derived/{project_id}/beats.json

    # Analysis status: pending, analyzing, complete, failed
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending")
    analysis_error: Mapped[Optional[str]] = mapped_column(String(500))
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project: Mapped["Project"] = relationship(back_populates="audio_track")
```

> **Design Note**: The `beat_grid_json` payload is NOT stored in the database. Beat analysis results are persisted to the filesystem at `beat_grid_path`. The database stores only metadata (bpm, beat_count) for display purposes. This keeps the database lightweight and allows efficient streaming of large beat grids.

### 1.5 Timeline Model

```python
class Timeline(Base):
    __tablename__ = "timelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)

    # EDL is stored on filesystem, path is predictable:
    # /data/derived/{project_id}/edl.json
    edl_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Summary metadata (for display without parsing EDL)
    total_duration_ms: Mapped[int] = mapped_column(Integer)
    segment_count: Mapped[int] = mapped_column(Integer)

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    modified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Hash of inputs: settings + media order + audio file + beat grid checksum
    # Used to detect if timeline needs regeneration
    edl_hash: Mapped[str] = mapped_column(String(64))

    project: Mapped["Project"] = relationship(back_populates="timeline")
```

#### EDL Hash Computation

The `edl_hash` enables cache invalidation and render reproducibility:

```python
import hashlib
import json

def compute_edl_hash(
    project_settings: dict,
    media_asset_ids: list[str],  # Ordered list
    audio_file_checksum: str,
    beat_grid_checksum: str
) -> str:
    """
    Compute deterministic hash of all inputs that affect EDL generation.
    If any input changes, the hash changes, signaling stale timeline.
    """
    payload = {
        "settings": project_settings,
        "media_order": media_asset_ids,
        "audio_checksum": audio_file_checksum,
        "beats_checksum": beat_grid_checksum,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

### 1.6 RenderJob Model

```python
class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # Type: preview, final
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Snapshot of inputs at render time (for reproducibility)
    edl_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    render_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Contains: resolution, fps, codec, quality preset, etc.

    # Status: queued, running, complete, failed, cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[Optional[str]] = mapped_column(String(200))

    output_path: Mapped[Optional[str]] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    rq_job_id: Mapped[Optional[str]] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship(back_populates="render_jobs")
```

#### Render Reproducibility

> **Critical Design Rule**: A render job captures `edl_hash` and `render_settings_json` at creation time. This ensures:
>
> 1. The render output is reproducible regardless of subsequent project changes
> 2. Re-running a failed job uses the same inputs as the original attempt
> 3. Comparing `edl_hash` values identifies which renders are equivalent
>
> The renderer reads the EDL from the filesystem path, NOT from project state. If the user modifies the project after queueing a render, those changes do not affect the in-progress render.

#### Render Settings Schema

```python
class RenderSettings(BaseModel):
    """Captured at render job creation time."""
    output_width: int
    output_height: int
    output_fps: int
    codec: str = "h264"           # h264, h265, prores
    quality_preset: str = "medium"  # preview, medium, high
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
```

---

## 2. EDL (Edit Decision List) Schema

The EDL is stored as JSON on the filesystem (`/data/derived/{project_id}/edl.json`) and is the canonical source of truth for rendering.

### 2.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EditDecisionList",
  "type": "object",
  "required": ["version", "project_id", "settings", "audio", "segments"],
  "properties": {
    "version": { "const": "1.0" },
    "project_id": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "edl_hash": { "type": "string", "description": "SHA-256 hash of inputs" },
    "settings": {
      "type": "object",
      "required": ["output_width", "output_height", "output_fps"],
      "properties": {
        "output_width": { "type": "integer" },
        "output_height": { "type": "integer" },
        "output_fps": { "type": "integer" },
        "default_transition_type": { "enum": ["cut", "crossfade", "fade"] },
        "default_transition_duration_ms": { "type": "integer" }
      }
    },
    "audio": {
      "type": "object",
      "required": ["file_path", "duration_ms"],
      "properties": {
        "file_path": { "type": "string" },
        "duration_ms": { "type": "integer" },
        "bpm": { "type": "number" },
        "sample_rate": { "type": "integer" },
        "start_offset_ms": { "type": "integer", "default": 0 }
      }
    },
    "segments": {
      "type": "array",
      "items": { "$ref": "#/definitions/segment" }
    }
  },
  "definitions": {
    "segment": {
      "type": "object",
      "required": ["index", "media_asset_id", "media_type", "timeline_in_ms", "timeline_out_ms", "render_duration_ms"],
      "properties": {
        "index": {
          "type": "integer",
          "description": "Zero-based segment position in timeline"
        },
        "media_asset_id": {
          "type": "string",
          "description": "References MediaAsset.id - renderer resolves file path"
        },
        "media_type": { "enum": ["image", "video"] },

        "timeline_in_ms": {
          "type": "integer",
          "description": "Start position on output timeline (ms)"
        },
        "timeline_out_ms": {
          "type": "integer",
          "description": "End position on output timeline (ms)"
        },
        "render_duration_ms": {
          "type": "integer",
          "description": "Actual rendered duration (timeline_out - timeline_in)"
        },

        "source_in_ms": {
          "type": "integer",
          "default": 0,
          "description": "For videos: start point in source file"
        },
        "source_out_ms": {
          "type": "integer",
          "description": "For videos: end point in source file"
        },

        "transition_in": { "$ref": "#/definitions/transition" },
        "transition_out": { "$ref": "#/definitions/transition" },

        "effects": { "$ref": "#/definitions/effects" }
      }
    },
    "effects": {
      "type": "object",
      "properties": {
        "ken_burns": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "start_zoom": { "type": "number", "minimum": 1.0, "maximum": 2.0 },
            "end_zoom": { "type": "number", "minimum": 1.0, "maximum": 2.0 },
            "start_x": { "type": "number", "minimum": 0, "maximum": 1 },
            "start_y": { "type": "number", "minimum": 0, "maximum": 1 },
            "end_x": { "type": "number", "minimum": 0, "maximum": 1 },
            "end_y": { "type": "number", "minimum": 0, "maximum": 1 }
          }
        }
      }
    },
    "transition": {
      "type": "object",
      "required": ["type", "duration_ms"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["cut", "crossfade", "fade_black", "fade_white"]
        },
        "duration_ms": { "type": "integer", "minimum": 0, "maximum": 2000 }
      }
    }
  }
}
```

### 2.2 Segment Timing Model

```
Timeline:     |-------- Segment A --------|-------- Segment B --------|
              ^                           ^                           ^
              timeline_in_ms              timeline_out_ms             timeline_out_ms
              (A)                         (A) = timeline_in_ms(B)     (B)

With Crossfade:
              |-------- Segment A --------|
                                   |======|-------- Segment B --------|
                                   ^ overlap = transition_out(A).duration_ms
```

- `timeline_in_ms`: Where segment starts on final output timeline
- `timeline_out_ms`: Where segment ends on final output timeline
- `render_duration_ms`: Computed as `timeline_out_ms - timeline_in_ms`
- `transition_in`: Applied at start of this segment (overlap with previous)
- `transition_out`: Applied at end of this segment (overlap with next)

### 2.3 Example EDL

```json
{
  "version": "1.0",
  "project_id": "proj_abc123",
  "generated_at": "2024-01-15T10:30:00Z",
  "edl_hash": "a1b2c3d4e5f6...",
  "settings": {
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30,
    "default_transition_type": "crossfade",
    "default_transition_duration_ms": 500
  },
  "audio": {
    "file_path": "uploads/proj_abc123/audio/track.mp3",
    "duration_ms": 180000,
    "bpm": 120.0,
    "sample_rate": 44100,
    "start_offset_ms": 0
  },
  "segments": [
    {
      "index": 0,
      "media_asset_id": "asset_001",
      "media_type": "image",
      "timeline_in_ms": 0,
      "timeline_out_ms": 2000,
      "render_duration_ms": 2000,
      "source_in_ms": 0,
      "source_out_ms": 2000,
      "effects": {
        "ken_burns": {
          "enabled": true,
          "start_zoom": 1.0,
          "end_zoom": 1.2,
          "start_x": 0.5,
          "start_y": 0.5,
          "end_x": 0.6,
          "end_y": 0.4
        }
      },
      "transition_in": null,
      "transition_out": {
        "type": "crossfade",
        "duration_ms": 500
      }
    },
    {
      "index": 1,
      "media_asset_id": "asset_002",
      "media_type": "video",
      "timeline_in_ms": 1500,
      "timeline_out_ms": 5500,
      "render_duration_ms": 4000,
      "source_in_ms": 5000,
      "source_out_ms": 9000,
      "effects": {},
      "transition_in": {
        "type": "crossfade",
        "duration_ms": 500
      },
      "transition_out": {
        "type": "cut",
        "duration_ms": 0
      }
    }
  ]
}
```

> **Note**: `source_path` is NOT stored in the EDL. The renderer resolves the file path by looking up `media_asset_id` in the database. This ensures the EDL remains valid even if files are reorganized, and prevents path inconsistencies.

---

## 3. Beat Grid Schema

### 3.1 File Location

Beat grid JSON is stored at: `/data/derived/{project_id}/beats.json`

This path is referenced by `AudioTrack.beat_grid_path`.

### 3.2 Structure

```json
{
  "version": "1.0",
  "analyzer": "librosa",
  "analyzed_at": "2024-01-15T10:25:00Z",
  "audio_file_checksum": "sha256:abc123...",
  "sample_rate": 44100,
  "duration_ms": 180000,
  "bpm": 120.5,
  "bpm_confidence": 0.92,
  "time_signature": "4/4",
  "beats": [
    {"time_ms": 0, "beat_number": 1, "is_downbeat": true, "confidence": 0.95},
    {"time_ms": 498, "beat_number": 2, "is_downbeat": false, "confidence": 0.91},
    {"time_ms": 996, "beat_number": 3, "is_downbeat": false, "confidence": 0.89},
    {"time_ms": 1494, "beat_number": 4, "is_downbeat": false, "confidence": 0.90},
    {"time_ms": 1992, "beat_number": 1, "is_downbeat": true, "confidence": 0.94}
  ],
  "measures": [
    {"index": 0, "start_ms": 0, "end_ms": 1992, "beat_count": 4}
  ]
}
```

### 3.3 Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version |
| `analyzer` | string | Which library produced this: `madmom` or `librosa` |
| `analyzed_at` | string | ISO timestamp of analysis |
| `audio_file_checksum` | string | SHA-256 of source audio (for cache validation) |
| `sample_rate` | int | Audio sample rate in Hz (e.g., 44100, 48000) |
| `duration_ms` | int | Total audio duration in milliseconds |
| `bpm` | float | Detected tempo in beats per minute |
| `bpm_confidence` | float | Confidence score 0.0-1.0 |
| `time_signature` | string | Time signature (4/4 assumed for MVP) |
| `beats[].time_ms` | int | Beat position in milliseconds |
| `beats[].beat_number` | int | Position within measure (1-4 for 4/4) |
| `beats[].is_downbeat` | bool | True if beat 1 of measure |
| `beats[].confidence` | float | Per-beat confidence score |
| `measures[]` | array | Measure boundaries (optional, derived from beats) |

---

## 4. Entity Relationships

```
+----------+
|   User   |
+----+-----+
     | 1:N
     v
+----------+       1:N      +-------------+
| Project  |--------------->| MediaAsset  |
+----+-----+                +-------------+
     |                            |
     |                            | (resolved at render time)
     |                            v
     +-- 1:1 --> AudioTrack --> beats.json (filesystem)
     |
     +-- 1:1 --> Timeline ----> edl.json (filesystem)
     |
     +-- 1:N --> RenderJob
                    |
                    +-- captures edl_hash + render_settings_json
                    |   (immutable snapshot for reproducibility)
                    v
                /outputs/{project_id}/
```

### Key Relationships

| Relationship | Cardinality | Notes |
|--------------|-------------|-------|
| User -> Project | 1:N | User owns multiple projects |
| Project -> MediaAsset | 1:N | Project contains multiple images/videos |
| Project -> AudioTrack | 1:1 | One audio track per project (MVP) |
| Project -> Timeline | 1:1 | One active timeline/EDL per project |
| Project -> RenderJob | 1:N | Multiple render attempts allowed |
| RenderJob -> EDL | snapshot | RenderJob captures `edl_hash`, not live reference |

---

## 5. Pydantic Schemas (API)

### 5.1 Project Schemas

```python
from enum import Enum

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    READY = "ready"
    RENDERING = "rendering"
    COMPLETE = "complete"
    ERROR = "error"

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class ProjectSettings(BaseModel):
    beats_per_cut: int = Field(4, ge=1, le=16)
    transition_type: Literal["cut", "crossfade", "fade_black"] = "cut"
    transition_duration_ms: int = Field(500, ge=100, le=2000)
    ken_burns_enabled: bool = True
    output_width: int = Field(1920, ge=320, le=3840)
    output_height: int = Field(1080, ge=240, le=2160)
    output_fps: int = Field(30, ge=15, le=60)

    @validator("beats_per_cut")
    def validate_beats(cls, v):
        if v not in [1, 2, 4, 8, 16]:
            raise ValueError("Must be 1, 2, 4, 8, or 16")
        return v

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: ProjectStatus
    status_message: Optional[str]
    settings: ProjectSettings
    media_count: int
    has_audio: bool
    has_timeline: bool
    created_at: datetime
    updated_at: datetime
```

### 5.2 Media Schemas

```python
class MediaAssetResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    media_type: Literal["image", "video"]
    width: int
    height: int
    rotation_deg: int = 0
    display_aspect_ratio: Optional[str]
    duration_ms: Optional[int]
    file_size: int
    thumbnail_url: str
    sort_order: int

class AudioTrackResponse(BaseModel):
    id: str
    filename: str
    duration_ms: int
    sample_rate: Optional[int]
    bpm: Optional[float]
    beat_count: Optional[int]
    analysis_status: Literal["pending", "analyzing", "complete", "failed"]
    analysis_error: Optional[str]
```

### 5.3 Timeline/EDL Schemas

```python
class SegmentTransition(BaseModel):
    type: Literal["cut", "crossfade", "fade_black", "fade_white"]
    duration_ms: int = Field(ge=0, le=2000)

class KenBurnsEffect(BaseModel):
    enabled: bool = False
    start_zoom: float = Field(1.0, ge=1.0, le=2.0)
    end_zoom: float = Field(1.2, ge=1.0, le=2.0)
    start_x: float = Field(0.5, ge=0, le=1)
    start_y: float = Field(0.5, ge=0, le=1)
    end_x: float = Field(0.5, ge=0, le=1)
    end_y: float = Field(0.5, ge=0, le=1)

class SegmentEffects(BaseModel):
    ken_burns: Optional[KenBurnsEffect]

class EDLSegment(BaseModel):
    index: int
    media_asset_id: str
    media_type: Literal["image", "video"]
    timeline_in_ms: int = Field(ge=0)
    timeline_out_ms: int = Field(ge=0)
    render_duration_ms: int = Field(ge=0)
    source_in_ms: int = Field(default=0, ge=0)
    source_out_ms: Optional[int]
    transition_in: Optional[SegmentTransition]
    transition_out: Optional[SegmentTransition]
    effects: SegmentEffects = SegmentEffects()

class EDLResponse(BaseModel):
    version: str
    project_id: str
    generated_at: datetime
    edl_hash: str
    total_duration_ms: int
    segment_count: int
    segments: List[EDLSegment]

class EDLUpdateRequest(BaseModel):
    """For UI edits to segment order, timing, effects."""
    segments: List[EDLSegment]
```

### 5.4 Job Schemas

```python
class RenderSettingsRequest(BaseModel):
    output_width: int = Field(1920, ge=320, le=3840)
    output_height: int = Field(1080, ge=240, le=2160)
    output_fps: int = Field(30, ge=15, le=60)
    quality_preset: Literal["preview", "medium", "high"] = "medium"

class RenderJobCreate(BaseModel):
    job_type: Literal["preview", "final"]
    settings: Optional[RenderSettingsRequest]

class RenderJobResponse(BaseModel):
    id: str
    project_id: str
    job_type: Literal["preview", "final"]
    status: Literal["queued", "running", "complete", "failed", "cancelled"]
    progress_percent: int
    progress_message: Optional[str]
    edl_hash: str
    output_url: Optional[str]
    file_size: Optional[int]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

---

## 6. File Storage Layout

```
/data/
+-- uploads/{project_id}/
|   +-- media/
|   |   +-- {uuid}.jpg           # Original uploaded image
|   |   +-- {uuid}.mp4           # Original uploaded video
|   +-- audio/
|       +-- {uuid}.mp3           # Original uploaded audio
|
+-- derived/{project_id}/
|   +-- thumbnails/
|   |   +-- {asset_id}_thumb.jpg
|   +-- proxies/
|   |   +-- {asset_id}_proxy.mp4
|   +-- beats.json               # Beat analysis (authoritative)
|   +-- edl.json                 # Timeline EDL (authoritative)
|
+-- outputs/{project_id}/
|   +-- preview/
|   |   +-- {job_id}.mp4
|   +-- final/
|       +-- {job_id}.mp4
|
+-- temp/
    +-- render_{job_id}/         # Intermediate render files
```

---

[Next: API Endpoints ->](./03-api-endpoints.md)
