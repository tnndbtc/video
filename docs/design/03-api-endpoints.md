# BeatStitch - API Endpoints

[← Back to Index](./00-index.md) | [← Previous](./02-data-models.md) | [Next →](./04-processing.md)

---

## 1. Authentication

### POST /api/auth/register
```http
POST /api/auth/register
Content-Type: application/json

{"username": "newuser", "password": "securepassword123"}
```

**Response (201):**
```json
{
  "id": "usr_xyz789",
  "username": "newuser",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### POST /api/auth/login
```http
POST /api/auth/login
Content-Type: application/json

{"username": "user1", "password": "secretpassword"}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {"id": "usr_abc123", "username": "user1"}
}
```

---

## 2. Projects

### GET /api/projects
List all projects for current user.

```http
GET /api/projects
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "projects": [
    {
      "id": "proj_001",
      "name": "Summer Vacation Video",
      "status": "draft",
      "media_count": 12,
      "has_audio": true,
      "created_at": "2024-01-10T08:00:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1
}
```

### POST /api/projects
Create new project.

```http
POST /api/projects
Authorization: Bearer {token}
Content-Type: application/json

{"name": "My New Project", "description": "A test video project"}
```

**Response (201):**
```json
{
  "id": "proj_002",
  "name": "My New Project",
  "description": "A test video project",
  "status": "draft",
  "settings": {
    "beats_per_cut": 4,
    "transition_type": "cut",
    "transition_duration_ms": 500,
    "ken_burns_enabled": true,
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30
  },
  "created_at": "2024-01-15T11:00:00Z"
}
```

### GET /api/projects/{project_id}
Get project details with media, audio, and timeline.

```http
GET /api/projects/proj_001
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "proj_001",
  "name": "Summer Vacation Video",
  "status": "ready",
  "settings": {
    "beats_per_cut": 4,
    "transition_type": "crossfade",
    "transition_duration_ms": 500,
    "ken_burns_enabled": true,
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30
  },
  "media_assets": [
    {
      "id": "asset_001",
      "filename": "photo1.jpg",
      "media_type": "image",
      "processing_status": "ready",
      "thumbnail_url": "/api/media/asset_001/thumbnail",
      "sort_order": 0
    }
  ],
  "audio_track": {
    "id": "audio_001",
    "filename": "background.mp3",
    "duration_ms": 180000,
    "bpm": 120.5,
    "analysis_status": "complete"
  },
  "timeline": {
    "id": "tl_001",
    "segment_count": 45,
    "total_duration_ms": 180000,
    "edl_hash": "sha256_abc123def456"
  }
}
```

### GET /api/projects/{project_id}/status
Lightweight status check for project processing state.

```http
GET /api/projects/proj_001/status
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "project_id": "proj_001",
  "media": {
    "total": 12,
    "pending": 0,
    "processing": 0,
    "ready": 12,
    "failed": 0
  },
  "audio": {
    "uploaded": true,
    "analysis_status": "complete"
  },
  "timeline": {
    "generated": true,
    "edl_hash": "sha256_abc123def456",
    "stale": false
  },
  "ready_to_render": true
}
```

### PATCH /api/projects/{project_id}/settings
Update project settings.

```http
PATCH /api/projects/proj_001/settings
Authorization: Bearer {token}
Content-Type: application/json

{
  "beats_per_cut": 8,
  "transition_type": "crossfade",
  "ken_burns_enabled": false
}
```

**Response (200):**
```json
{
  "id": "proj_001",
  "settings": {
    "beats_per_cut": 8,
    "transition_type": "crossfade",
    "transition_duration_ms": 500,
    "ken_burns_enabled": false,
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30
  },
  "timeline_invalidated": true,
  "updated_at": "2024-01-15T11:30:00Z"
}
```

### DELETE /api/projects/{project_id}
Delete project and all associated data.

```http
DELETE /api/projects/proj_001
Authorization: Bearer {token}
```

**Response (204):** No content

---

## 3. Media

### POST /api/projects/{project_id}/media
Upload media files (images/videos). Processing starts automatically.

```http
POST /api/projects/proj_001/media
Authorization: Bearer {token}
Content-Type: multipart/form-data

files: [photo1.jpg, photo2.png, clip1.mp4]
```

**Response (201):**
```json
{
  "uploaded": [
    {
      "id": "asset_001",
      "filename": "photo1.jpg",
      "media_type": "image",
      "processing_status": "pending",
      "width": null,
      "height": null,
      "file_size": 2500000
    },
    {
      "id": "asset_002",
      "filename": "clip1.mp4",
      "media_type": "video",
      "processing_status": "pending",
      "width": null,
      "height": null,
      "duration_ms": null,
      "fps": null,
      "file_size": 45000000
    }
  ],
  "failed": [],
  "total_uploaded": 2
}
```

**Note:** Media metadata (width, height, duration, fps, thumbnail) is populated after processing completes. Poll `GET /api/media/{asset_id}` or use the status endpoint to check processing state.

### GET /api/media/{asset_id}
Get media asset details and processing status.

```http
GET /api/media/asset_001
Authorization: Bearer {token}
```

**Response (200) - Processing:**
```json
{
  "id": "asset_001",
  "project_id": "proj_001",
  "filename": "photo1.jpg",
  "media_type": "image",
  "processing_status": "processing",
  "width": null,
  "height": null,
  "file_size": 2500000,
  "thumbnail_url": null,
  "sort_order": 0,
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Response (200) - Ready:**
```json
{
  "id": "asset_001",
  "project_id": "proj_001",
  "filename": "photo1.jpg",
  "media_type": "image",
  "processing_status": "ready",
  "width": 4000,
  "height": 3000,
  "file_size": 2500000,
  "thumbnail_url": "/api/media/asset_001/thumbnail",
  "sort_order": 0,
  "created_at": "2024-01-15T10:00:00Z",
  "processed_at": "2024-01-15T10:00:05Z"
}
```

**Response (200) - Failed:**
```json
{
  "id": "asset_003",
  "project_id": "proj_001",
  "filename": "corrupt.jpg",
  "media_type": "image",
  "processing_status": "failed",
  "processing_error": "Unable to decode image: invalid JPEG header",
  "file_size": 1500000,
  "created_at": "2024-01-15T10:00:00Z"
}
```

### GET /api/media/{asset_id}/thumbnail
Get media thumbnail.

```http
GET /api/media/asset_001/thumbnail
Authorization: Bearer {token}
```

**Response:** Binary image (JPEG, 256x256)

**Response (404):** If processing not yet complete or failed.

### DELETE /api/media/{asset_id}
Delete media asset.

```http
DELETE /api/media/asset_001
Authorization: Bearer {token}
```

**Response (204):** No content

### POST /api/projects/{project_id}/media/reorder
Reorder media assets.

```http
POST /api/projects/proj_001/media/reorder
Authorization: Bearer {token}
Content-Type: application/json

{"order": ["asset_003", "asset_001", "asset_002"]}
```

**Response (200):**
```json
{
  "success": true,
  "new_order": [
    {"id": "asset_003", "sort_order": 0},
    {"id": "asset_001", "sort_order": 1},
    {"id": "asset_002", "sort_order": 2}
  ],
  "timeline_invalidated": true
}
```

---

## 4. Audio

### POST /api/projects/{project_id}/audio
Upload audio track (replaces existing). Beat analysis is automatically queued.

```http
POST /api/projects/proj_001/audio
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: background_music.mp3
```

**Response (201):**
```json
{
  "id": "audio_001",
  "filename": "background_music.mp3",
  "duration_ms": 195000,
  "sample_rate": 44100,
  "file_size": 4500000,
  "analysis_status": "queued",
  "analysis_job_id": "beat_job_001"
}
```

**Note:** Beat analysis starts automatically upon upload. The `analysis_job_id` can be used to track progress via `GET /api/jobs/{job_id}`.

### POST /api/projects/{project_id}/audio/analyze
Re-run beat analysis (optional). Use this to retry failed analysis or force re-analysis.

```http
POST /api/projects/proj_001/audio/analyze
Authorization: Bearer {token}
```

**Response (202):**
```json
{
  "job_id": "beat_job_002",
  "status": "queued",
  "message": "Beat analysis queued"
}
```

**Response (409) - Analysis already in progress:**
```json
{
  "error": "conflict",
  "message": "Beat analysis already in progress",
  "existing_job_id": "beat_job_001"
}
```

### GET /api/projects/{project_id}/audio/beats
Get beat analysis results.

```http
GET /api/projects/proj_001/audio/beats
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "status": "complete",
  "bpm": 120.5,
  "total_beats": 390,
  "time_signature": "4/4",
  "beats": [
    {"time_ms": 0, "beat_number": 1, "is_downbeat": true},
    {"time_ms": 498, "beat_number": 2, "is_downbeat": false},
    {"time_ms": 996, "beat_number": 3, "is_downbeat": false}
  ],
  "analyzed_at": "2024-01-15T10:15:00Z"
}
```

**Response (202) - Analysis in progress:**
```json
{
  "status": "processing",
  "job_id": "beat_job_001",
  "progress_percent": 45,
  "message": "Analyzing audio..."
}
```

### GET /api/projects/{project_id}/beats/status
Lightweight status check for beat analysis.

```http
GET /api/projects/proj_001/beats/status
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "project_id": "proj_001",
  "audio_uploaded": true,
  "analysis_status": "complete",
  "bpm": 120.5,
  "total_beats": 390,
  "analyzed_at": "2024-01-15T10:15:00Z"
}
```

**Response (200) - No audio:**
```json
{
  "project_id": "proj_001",
  "audio_uploaded": false,
  "analysis_status": null
}
```

---

## 5. Timeline

### POST /api/projects/{project_id}/timeline/generate
Generate timeline from media and beats. This is an async operation.

```http
POST /api/projects/proj_001/timeline/generate
Authorization: Bearer {token}
```

**Response (202):**
```json
{
  "job_id": "timeline_job_001",
  "status": "queued",
  "message": "Timeline generation queued"
}
```

**Response (400) - Prerequisites not met:**
```json
{
  "error": "precondition_failed",
  "message": "Cannot generate timeline",
  "details": {
    "media_ready": false,
    "media_pending": 2,
    "beats_complete": true
  }
}
```

**Response (409) - Generation already in progress:**
```json
{
  "error": "conflict",
  "message": "Timeline generation already in progress",
  "existing_job_id": "timeline_job_001"
}
```

### GET /api/projects/{project_id}/timeline
Get full timeline with segments. Only available after generation completes.

```http
GET /api/projects/proj_001/timeline
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "tl_001",
  "edl_hash": "sha256_abc123def456",
  "segment_count": 45,
  "total_duration_ms": 180000,
  "segments": [
    {
      "index": 0,
      "media_asset_id": "asset_001",
      "media_type": "image",
      "thumbnail_url": "/api/media/asset_001/thumbnail",
      "timeline_in_ms": 0,
      "timeline_out_ms": 2000,
      "render_duration_ms": 2000,
      "source_in_ms": 0,
      "source_out_ms": 2000,
      "effects": {"ken_burns": {"enabled": true}},
      "transition_in": null
    },
    {
      "index": 1,
      "media_asset_id": "asset_002",
      "media_type": "video",
      "thumbnail_url": "/api/media/asset_002/thumbnail",
      "timeline_in_ms": 2000,
      "timeline_out_ms": 4000,
      "render_duration_ms": 2000,
      "source_in_ms": 5000,
      "source_out_ms": 7000,
      "effects": {},
      "transition_in": {"type": "crossfade", "duration_ms": 500}
    }
  ],
  "settings_used": {
    "beats_per_cut": 4,
    "transition_type": "crossfade"
  },
  "generated_at": "2024-01-15T11:00:00Z"
}
```

**Response (404) - Timeline not yet generated:**
```json
{
  "error": "not_found",
  "message": "Timeline not generated",
  "hint": "POST /api/projects/proj_001/timeline/generate to create timeline"
}
```

### GET /api/projects/{project_id}/timeline/status
Lightweight status check for timeline.

```http
GET /api/projects/proj_001/timeline/status
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "project_id": "proj_001",
  "generated": true,
  "edl_hash": "sha256_abc123def456",
  "segment_count": 45,
  "total_duration_ms": 180000,
  "stale": false,
  "generated_at": "2024-01-15T11:00:00Z"
}
```

**Response (200) - Stale timeline (settings or media changed):**
```json
{
  "project_id": "proj_001",
  "generated": true,
  "edl_hash": "sha256_abc123def456",
  "segment_count": 45,
  "total_duration_ms": 180000,
  "stale": true,
  "stale_reason": "Project settings changed since generation",
  "generated_at": "2024-01-15T11:00:00Z"
}
```

**Response (200) - Not generated:**
```json
{
  "project_id": "proj_001",
  "generated": false,
  "generation_job_id": null
}
```

**Response (200) - Generation in progress:**
```json
{
  "project_id": "proj_001",
  "generated": false,
  "generation_job_id": "timeline_job_001",
  "generation_status": "running",
  "progress_percent": 60
}
```

---

## 6. Rendering

### POST /api/projects/{project_id}/render
Start render job. Requires `edl_hash` to prevent race conditions with timeline changes.

```http
POST /api/projects/proj_001/render
Authorization: Bearer {token}
Content-Type: application/json

{
  "type": "preview",
  "edl_hash": "sha256_abc123def456"
}
```

**Response (202):**
```json
{
  "job_id": "render_001",
  "job_type": "preview",
  "status": "queued",
  "edl_hash": "sha256_abc123def456",
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Response (400) - Missing edl_hash:**
```json
{
  "error": "validation_error",
  "message": "edl_hash is required",
  "details": {
    "field": "edl_hash",
    "hint": "Fetch current edl_hash from GET /api/projects/{id}/timeline"
  }
}
```

**Response (409) - EDL hash mismatch (timeline changed):**
```json
{
  "error": "edl_hash_mismatch",
  "message": "Timeline has changed since request was initiated",
  "details": {
    "provided_hash": "sha256_abc123def456",
    "current_hash": "sha256_xyz789ghi012"
  },
  "hint": "Fetch updated timeline and retry with current edl_hash"
}
```

**Response (400) - Timeline not ready:**
```json
{
  "error": "precondition_failed",
  "message": "Timeline not available for rendering",
  "details": {
    "timeline_generated": false
  }
}
```

### GET /api/projects/{project_id}/render/{type}/download
Download rendered video.

```http
GET /api/projects/proj_001/render/preview/download
Authorization: Bearer {token}
```

**Response:** Binary MP4 file with `Content-Disposition: attachment`

---

## 7. Jobs

### GET /api/jobs/{job_id}
Get job status and progress.

```http
GET /api/jobs/render_001
Authorization: Bearer {token}
```

**Response (200) - Queued:**
```json
{
  "id": "render_001",
  "project_id": "proj_001",
  "job_type": "render_preview",
  "status": "queued",
  "progress_percent": 0,
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Response (200) - Running:**
```json
{
  "id": "render_001",
  "project_id": "proj_001",
  "job_type": "render_preview",
  "status": "running",
  "progress_percent": 45,
  "progress_message": "Rendering segment 20/45",
  "started_at": "2024-01-15T12:00:05Z"
}
```

**Response (200) - Complete:**
```json
{
  "id": "render_001",
  "project_id": "proj_001",
  "job_type": "render_preview",
  "status": "complete",
  "progress_percent": 100,
  "output_url": "/api/projects/proj_001/render/preview/download",
  "file_size": 15000000,
  "completed_at": "2024-01-15T12:02:30Z"
}
```

**Response (200) - Failed:**
```json
{
  "id": "render_001",
  "project_id": "proj_001",
  "job_type": "render_preview",
  "status": "failed",
  "error": "FFmpeg encoding failed: out of memory",
  "failed_at": "2024-01-15T12:01:15Z"
}
```

**Response (200) - Cancelled:**
```json
{
  "id": "render_001",
  "project_id": "proj_001",
  "job_type": "render_preview",
  "status": "cancelled",
  "cancelled_at": "2024-01-15T12:00:45Z"
}
```

### POST /api/jobs/{job_id}/cancel
Cancel a running or queued job.

```http
POST /api/jobs/render_001/cancel
Authorization: Bearer {token}
```

**Response (200):**
```json
{
  "id": "render_001",
  "status": "cancelled",
  "message": "Job cancellation initiated"
}
```

**Response (409) - Job cannot be cancelled:**
```json
{
  "error": "conflict",
  "message": "Job cannot be cancelled",
  "details": {
    "current_status": "complete",
    "cancellable_statuses": ["queued", "running"]
  }
}
```

---

## 8. Health Check

### GET /health
System health check.

```http
GET /health
```

**Response (200):**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"},
    "storage": {"status": "healthy", "free_gb": 45.2},
    "ffmpeg": {"status": "healthy"}
  },
  "version": "1.0.0"
}
```

---

## 9. Error Responses

### 400 Bad Request
```json
{
  "error": "validation_error",
  "message": "Invalid beats_per_cut value",
  "details": {"field": "beats_per_cut", "constraint": "must be 1, 2, 4, 8, or 16"}
}
```

### 401 Unauthorized
```json
{"error": "unauthorized", "message": "Invalid or expired token"}
```

### 404 Not Found
```json
{
  "error": "not_found",
  "message": "Project not found",
  "resource_type": "project",
  "resource_id": "proj_999"
}
```

### 409 Conflict
```json
{
  "error": "conflict",
  "message": "Resource state conflict",
  "details": {"reason": "Operation cannot be performed in current state"}
}
```

### 413 Payload Too Large
```json
{
  "error": "file_too_large",
  "message": "File exceeds maximum size of 500MB",
  "max_size_bytes": 524288000
}
```

### 429 Too Many Requests
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after_seconds": 60
}
```

### 500 Internal Server Error
```json
{
  "error": "internal_error",
  "message": "An unexpected error occurred",
  "request_id": "req_abc123"
}
```

---

## 10. Job Types Reference

| Job Type | Triggered By | Cancellable | Typical Duration |
|----------|--------------|-------------|------------------|
| `beat_analysis` | Audio upload (auto) or `/audio/analyze` | Yes | 10-60 seconds |
| `timeline_generation` | `POST /timeline/generate` | Yes | 1-10 seconds |
| `media_processing` | Media upload (auto) | No | 2-30 seconds |
| `render_preview` | `POST /render` with `type: preview` | Yes | 30-120 seconds |
| `render_final` | `POST /render` with `type: final` | Yes | 2-15 minutes |

---

## 11. Processing Status Reference

### Media Processing Status

| Status | Description |
|--------|-------------|
| `pending` | Upload complete, processing not yet started |
| `processing` | Thumbnail generation and metadata extraction in progress |
| `ready` | Processing complete, asset ready for use |
| `failed` | Processing failed, see `processing_error` for details |

### Audio Analysis Status

| Status | Description |
|--------|-------------|
| `queued` | Analysis job queued (auto-triggered on upload) |
| `processing` | Beat detection algorithm running |
| `complete` | Beats extracted successfully |
| `failed` | Analysis failed, manual retry available |

---

[Next: Processing (Beat Detection, Timeline, Rendering) →](./04-processing.md)
