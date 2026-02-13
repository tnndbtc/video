# BeatStitch API Documentation

This document describes the REST API endpoints for BeatStitch.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Projects](#projects)
- [Media](#media)
- [Audio](#audio)
- [Timeline](#timeline)
- [Rendering](#rendering)
- [Jobs](#jobs)
- [Error Responses](#error-responses)

## Overview

### Base URL

```
http://localhost:8000/api
```

### Authentication

Most endpoints require authentication via JWT bearer token. Include the token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Content Types

- Request bodies: `application/json` (except file uploads)
- File uploads: `multipart/form-data`
- Responses: `application/json`

### Interactive Documentation

FastAPI provides interactive documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Authentication

### Register

Create a new user account.

```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "newuser",
  "password": "securepassword123"
}
```

**Response (201 Created):**

```json
{
  "id": "usr_abc123",
  "username": "newuser",
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Errors:**
- `409 Conflict`: Username already exists

### Login

Authenticate and receive an access token.

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "user1",
  "password": "secretpassword"
}
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "usr_abc123",
    "username": "user1"
  }
}
```

**Errors:**
- `401 Unauthorized`: Invalid credentials

### Get Current User

```http
GET /api/auth/me
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "id": "usr_abc123",
  "username": "user1",
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

## Projects

### List Projects

Get all projects for the current user.

```http
GET /api/projects
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "projects": [
    {
      "id": "proj_001",
      "name": "Summer Vacation Video",
      "status": "ready",
      "media_count": 12,
      "has_audio": true,
      "created_at": "2024-01-10T08:00:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1
}
```

### Create Project

```http
POST /api/projects
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My New Project",
  "description": "A test video project"
}
```

**Response (201 Created):**

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

### Get Project

Get detailed project information including media, audio, and timeline.

```http
GET /api/projects/{project_id}
Authorization: Bearer <token>
```

**Response (200 OK):**

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

### Get Project Status

Lightweight status check for processing state.

```http
GET /api/projects/{project_id}/status
Authorization: Bearer <token>
```

**Response (200 OK):**

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

### Update Project Settings

```http
PATCH /api/projects/{project_id}/settings
Authorization: Bearer <token>
Content-Type: application/json

{
  "beats_per_cut": 8,
  "transition_type": "crossfade",
  "ken_burns_enabled": false
}
```

**Response (200 OK):**

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

### Delete Project

Delete project and all associated data.

```http
DELETE /api/projects/{project_id}
Authorization: Bearer <token>
```

**Response (204 No Content)**

---

## Media

### Upload Media

Upload images and/or video files. Processing starts automatically.

```http
POST /api/projects/{project_id}/media
Authorization: Bearer <token>
Content-Type: multipart/form-data

files: [photo1.jpg, photo2.png, clip1.mp4]
```

**Response (201 Created):**

```json
{
  "uploaded": [
    {
      "id": "asset_001",
      "filename": "photo1.jpg",
      "media_type": "image",
      "processing_status": "pending",
      "file_size": 2500000
    },
    {
      "id": "asset_002",
      "filename": "clip1.mp4",
      "media_type": "video",
      "processing_status": "pending",
      "file_size": 45000000
    }
  ],
  "failed": [],
  "total_uploaded": 2
}
```

**Notes:**
- Media metadata (width, height, duration) is populated after processing
- Poll the status endpoint or individual media endpoints to check progress

### Get Media Asset

```http
GET /api/media/{asset_id}
Authorization: Bearer <token>
```

**Response (200 OK) - Processing:**

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

**Response (200 OK) - Ready:**

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

**Response (200 OK) - Failed:**

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

### Get Thumbnail

```http
GET /api/media/{asset_id}/thumbnail
Authorization: Bearer <token>
```

**Response:** Binary image (JPEG, 256x256)

**Errors:**
- `404 Not Found`: Processing not complete or failed

### Delete Media

```http
DELETE /api/media/{asset_id}
Authorization: Bearer <token>
```

**Response (204 No Content)**

### Reorder Media

Update the sort order of media assets.

```http
POST /api/projects/{project_id}/media/reorder
Authorization: Bearer <token>
Content-Type: application/json

{
  "order": ["asset_003", "asset_001", "asset_002"]
}
```

**Response (200 OK):**

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

## Audio

### Upload Audio

Upload audio track. Replaces existing audio. Beat analysis starts automatically.

```http
POST /api/projects/{project_id}/audio
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: background_music.mp3
```

**Response (202 Accepted):**

```json
{
  "id": "audio_001",
  "filename": "background_music.mp3",
  "duration_ms": 195000,
  "sample_rate": 44100,
  "file_size": 4500000,
  "analysis_status": "queued",
  "analysis_job_id": "beat_job_001",
  "message": "Audio uploaded, beat analysis started"
}
```

### Re-analyze Audio

Re-run beat analysis (retry failed or force re-analysis).

```http
POST /api/projects/{project_id}/audio/analyze
Authorization: Bearer <token>
```

**Response (202 Accepted):**

```json
{
  "job_id": "beat_job_002",
  "status": "queued",
  "message": "Beat analysis queued"
}
```

**Response (409 Conflict) - Already in progress:**

```json
{
  "error": "conflict",
  "message": "Beat analysis already in progress",
  "existing_job_id": "beat_job_001"
}
```

### Get Beat Analysis Results

```http
GET /api/projects/{project_id}/audio/beats
Authorization: Bearer <token>
```

**Response (200 OK) - Complete:**

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

**Response (202 Accepted) - In progress:**

```json
{
  "status": "processing",
  "job_id": "beat_job_001",
  "progress_percent": 45,
  "message": "Analyzing audio..."
}
```

### Get Beat Analysis Status

```http
GET /api/projects/{project_id}/beats/status
Authorization: Bearer <token>
```

**Response (200 OK):**

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

---

## Timeline

### Generate Timeline

Generate timeline from media and detected beats. This is an async operation.

```http
POST /api/projects/{project_id}/timeline/generate
Authorization: Bearer <token>
```

**Response (202 Accepted):**

```json
{
  "job_id": "timeline_job_001",
  "status": "queued",
  "message": "Timeline generation queued"
}
```

**Response (400 Bad Request) - Prerequisites not met:**

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

**Response (409 Conflict) - Already in progress:**

```json
{
  "error": "conflict",
  "message": "Timeline generation already in progress",
  "existing_job_id": "timeline_job_001"
}
```

### Get Timeline

Get full timeline with segments.

```http
GET /api/projects/{project_id}/timeline
Authorization: Bearer <token>
```

**Response (200 OK):**

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
      "transition_in": null,
      "transition_out": {"type": "crossfade", "duration_ms": 500}
    },
    {
      "index": 1,
      "media_asset_id": "asset_002",
      "media_type": "video",
      "thumbnail_url": "/api/media/asset_002/thumbnail",
      "timeline_in_ms": 1500,
      "timeline_out_ms": 4000,
      "render_duration_ms": 2500,
      "source_in_ms": 5000,
      "source_out_ms": 7500,
      "effects": {},
      "transition_in": {"type": "crossfade", "duration_ms": 500},
      "transition_out": null
    }
  ],
  "settings_used": {
    "beats_per_cut": 4,
    "transition_type": "crossfade"
  },
  "generated_at": "2024-01-15T11:00:00Z"
}
```

**Response (404 Not Found) - Not generated:**

```json
{
  "error": "not_found",
  "message": "Timeline not generated",
  "hint": "POST /api/projects/proj_001/timeline/generate to create timeline"
}
```

### Get Timeline Status

```http
GET /api/projects/{project_id}/timeline/status
Authorization: Bearer <token>
```

**Response (200 OK) - Generated:**

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

**Response (200 OK) - Stale (settings changed):**

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

**Response (200 OK) - In progress:**

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

## Rendering

### Start Render

Start a render job. Requires `edl_hash` to prevent race conditions.

```http
POST /api/projects/{project_id}/render
Authorization: Bearer <token>
Content-Type: application/json

{
  "type": "preview",
  "edl_hash": "sha256_abc123def456"
}
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | `"preview"` or `"final"` |
| `edl_hash` | string | Yes | EDL hash from timeline endpoint |

**Response (202 Accepted):**

```json
{
  "job_id": "render_001",
  "job_type": "preview",
  "status": "queued",
  "edl_hash": "sha256_abc123def456",
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Response (409 Conflict) - EDL hash mismatch:**

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

### Download Rendered Video

```http
GET /api/projects/{project_id}/render/{type}/download
Authorization: Bearer <token>
```

**Parameters:**
- `type`: `preview` or `final`

**Response:** Binary MP4 file with `Content-Disposition: attachment`

**Headers:**
```
Content-Type: video/mp4
Content-Disposition: attachment; filename="project_preview.mp4"
```

---

## Jobs

### Get Job Status

```http
GET /api/jobs/{job_id}
Authorization: Bearer <token>
```

**Response (200 OK) - Queued:**

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

**Response (200 OK) - Running:**

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

**Response (200 OK) - Complete:**

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

**Response (200 OK) - Failed:**

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

### Cancel Job

```http
POST /api/jobs/{job_id}/cancel
Authorization: Bearer <token>
```

**Response (200 OK):**

```json
{
  "id": "render_001",
  "status": "cancelled",
  "message": "Job cancellation initiated"
}
```

**Response (409 Conflict) - Cannot cancel:**

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

## Health Check

### System Health

```http
GET /health
```

**Response (200 OK):**

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

## Error Responses

All error responses follow a consistent format:

### 400 Bad Request

Validation error or invalid input.

```json
{
  "error": "validation_error",
  "message": "Invalid beats_per_cut value",
  "details": {
    "field": "beats_per_cut",
    "constraint": "must be 1, 2, 4, 8, or 16"
  }
}
```

### 401 Unauthorized

Missing or invalid authentication.

```json
{
  "error": "unauthorized",
  "message": "Invalid or expired token"
}
```

### 403 Forbidden

Access denied to resource.

```json
{
  "error": "forbidden",
  "message": "You do not have permission to access this resource"
}
```

### 404 Not Found

Resource not found.

```json
{
  "error": "not_found",
  "message": "Project not found",
  "resource_type": "project",
  "resource_id": "proj_999"
}
```

### 409 Conflict

Resource state conflict.

```json
{
  "error": "conflict",
  "message": "Resource state conflict",
  "details": {
    "reason": "Operation cannot be performed in current state"
  }
}
```

### 413 Payload Too Large

File exceeds size limit.

```json
{
  "error": "file_too_large",
  "message": "File exceeds maximum size of 500MB",
  "max_size_bytes": 524288000
}
```

### 429 Too Many Requests

Rate limit exceeded.

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after_seconds": 60
}
```

### 500 Internal Server Error

Unexpected server error.

```json
{
  "error": "internal_error",
  "message": "An unexpected error occurred",
  "request_id": "req_abc123"
}
```

---

## Reference Tables

### Job Types

| Job Type | Triggered By | Cancellable | Duration |
|----------|--------------|-------------|----------|
| `beat_analysis` | Audio upload (auto) | Yes | 10-60s |
| `timeline_generation` | POST /timeline/generate | Yes | 1-10s |
| `media_processing` | Media upload (auto) | No | 2-30s |
| `render_preview` | POST /render (preview) | Yes | 30s-5min |
| `render_final` | POST /render (final) | Yes | 2-30min |

### Project Status Values

| Status | Description |
|--------|-------------|
| `draft` | Project created, media upload in progress |
| `analyzing` | Beat analysis in progress |
| `ready` | All analysis complete, ready for timeline/render |
| `rendering` | Render job in progress |
| `complete` | At least one successful render exists |
| `error` | Analysis or processing failed |

### Media Processing Status

| Status | Description |
|--------|-------------|
| `pending` | Upload complete, processing not started |
| `processing` | Thumbnail/metadata extraction in progress |
| `ready` | Processing complete, ready for use |
| `failed` | Processing failed (see `processing_error`) |

### Audio Analysis Status

| Status | Description |
|--------|-------------|
| `queued` | Analysis job queued |
| `processing` | Beat detection running |
| `complete` | Beats extracted successfully |
| `failed` | Analysis failed (retry available) |

### Supported File Types

| Category | Extensions |
|----------|------------|
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Audio | `.mp3`, `.wav`, `.flac`, `.aac`, `.m4a`, `.ogg` |

### Settings Constraints

| Setting | Type | Range | Default |
|---------|------|-------|---------|
| `beats_per_cut` | int | 1, 2, 4, 8, 16 | 4 |
| `transition_type` | string | cut, crossfade, fade_black | cut |
| `transition_duration_ms` | int | 100-2000 | 500 |
| `ken_burns_enabled` | bool | true/false | true |
| `output_width` | int | 320-3840 | 1920 |
| `output_height` | int | 240-2160 | 1080 |
| `output_fps` | int | 15-60 | 30 |
