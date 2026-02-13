# BeatStitch - Overview & Architecture

[<- Back to Index](./00-index.md)

---

## 1. Product Summary

BeatStitch is a self-hosted web application for creating videos by stitching images and video clips together, synchronized to an audio track's beats. It's a deterministic editing and rendering system—not an AI generation tool.

---

## 2. User Workflow

```
+---------------------------------------------------------------------+
|                        USER WORKFLOW                                |
+---------------------------------------------------------------------+
|                                                                     |
|  1. LOGIN          2. CREATE PROJECT    3. UPLOAD MEDIA             |
|  ------------->    ---------------->    -------------->             |
|  Simple auth       Name project         Images, videos,             |
|                                         audio track                 |
|                                                                     |
|  4. CONFIGURE      5. AUTO-BUILD        6. PREVIEW                  |
|  ------------->    ---------------->    -------------->             |
|  - Beats per cut   Generate timeline    Quick low-res               |
|  - Transition type from beats + media   render                      |
|  - Ken Burns                                                        |
|  - Resolution                                                       |
|                                                                     |
|  7. RENDER         8. DOWNLOAD                                      |
|  ------------->    ---------------->                                |
|  Full quality      Get final MP4                                    |
|  background job                                                     |
|                                                                     |
+---------------------------------------------------------------------+
```

---

## 3. Component Architecture

### 3.1 High-Level Diagram

```
+----------------------------------------------------------------------------+
|                              NGINX (Reverse Proxy)                         |
|                              Ports 80/443 ONLY                             |
+------------------------------------+---------------------------------------+
                                     |
                       +-------------+-------------+
                       |                           |
                       v                           v
+---------------------------+     +-------------------------------------------+
|      FRONTEND (React)     |     |           BACKEND (FastAPI)               |
|      Port 3000            |     |           Port 8000                       |
|                           |     |                                           |
|  - Project Dashboard      |---->|  - REST API                               |
|  - Media Upload           |     |  - Auth (JWT)                             |
|  - Timeline View          |     |  - Input Validation                       |
|    (ordered segments)     |     |  - Project State Persistence              |
|  - Render Controls        |     |  - Job Enqueueing                         |
|  - Job Status Display     |     |  - File Serving (authenticated)           |
|                           |     |  - NO CPU-intensive processing            |
+---------------------------+     +---------------------+---------------------+
                                                        |
                                                        | Job Queue
                                                        v
+----------------------------------------------------------------------------+
|                              REDIS                                         |
|                              Port 6379                                     |
|  - Job Queue (RQ)                                                          |
|  - Job Status Cache                                                        |
|  - Ephemeral Cache (NOT authoritative storage)                             |
+------------------------------------+---------------------------------------+
                                     |
                                     v
+----------------------------------------------------------------------------+
|                         WORKER PROCESS (Python + RQ)                       |
|                                                                            |
|  ALL CPU-intensive processing happens here:                                |
|  +---------------------+  +---------------------+  +--------------------+  |
|  |  Beat Analyzer      |  |  Timeline Builder   |  |  Render Engine     |  |
|  |  (madmom/librosa)   |  |  (auto-build EDL)   |  |  (ffmpeg)          |  |
|  +---------------------+  +---------------------+  +--------------------+  |
+------------------------------------+---------------------------------------+
                                     |
                                     v
+----------------------------------------------------------------------------+
|                           FILE STORAGE                                     |
|  /data/                                                                    |
|  +-- uploads/{project_id}/                                                 |
|  |   +-- media/                     # Original images and videos           |
|  |   +-- audio/                     # Original audio tracks                |
|  |                                                                         |
|  +-- derived/{project_id}/                                                 |
|  |   +-- thumbnails/                # Generated thumbnails                 |
|  |   +-- proxies/                   # Low-res proxy files                  |
|  |   +-- beats.json                 # Beat analysis results (authoritative)|
|  |   +-- edl.json                   # Timeline/EDL (canonical source)      |
|  |                                                                         |
|  +-- outputs/{project_id}/                                                 |
|  |   +-- preview/                   # Low-res preview renders              |
|  |   +-- final/                     # Full-res final exports               |
|  |                                                                         |
|  +-- temp/                          # In-progress renders (ephemeral)      |
|                                                                            |
|  /db/beatstitch.db                  # SQLite database                      |
+----------------------------------------------------------------------------+
```

### 3.2 Component Responsibilities

| Component | Responsibility | Technology | Notes |
|-----------|---------------|------------|-------|
| **Frontend** | UI, user interactions, state management, EDL editing | React + Vite | Edits EDL JSON via API |
| **Backend API** | REST endpoints, auth, validation, job enqueueing, file serving | FastAPI (Python) | **NO CPU-intensive work** |
| **Worker** | Beat analysis, timeline auto-build, rendering, thumbnail generation | Python + RQ | **ALL heavy processing** |
| **Redis** | Job queue, job status, ephemeral caching | Redis | **Cache only, not authoritative** |
| **SQLite** | Project metadata, user accounts | SQLite | Via repository abstraction |
| **File Storage** | Media files, derived assets, renders | Local filesystem | Authoritative for beats/EDL |

#### Backend vs Worker Separation (Critical)

| Task | Backend API | Worker |
|------|-------------|--------|
| Input validation | :white_check_mark: | |
| Store/retrieve project state | :white_check_mark: | |
| Enqueue jobs | :white_check_mark: | |
| Serve files (authenticated) | :white_check_mark: | |
| Beat detection | | :white_check_mark: |
| Timeline auto-build | | :white_check_mark: |
| Thumbnail generation | | :white_check_mark: |
| Preview rendering | | :white_check_mark: |
| Final rendering | | :white_check_mark: |

---

## 4. EDL as Canonical Source of Truth

### 4.1 Overview

Each project has a **Timeline/EDL (Edit Decision List)** stored as JSON. This is the canonical representation of the video edit and the single source of truth for rendering.

```
+-------------------+       +-------------------+       +-------------------+
|   Auto-Build      |       |   UI (Frontend)   |       |   Renderer        |
|   (Worker)        |       |                   |       |   (Worker)        |
+--------+----------+       +--------+----------+       +--------+----------+
         |                           |                           |
         | generates                 | edits                     | consumes
         v                           v                           v
+------------------------------------------------------------------------+
|                         EDL JSON                                       |
|                   /data/derived/{project_id}/edl.json                  |
|                                                                        |
|  {                                                                     |
|    "version": "1.0",                                                   |
|    "project_id": "uuid",                                               |
|    "audio_track": "audio/track.mp3",                                   |
|    "resolution": { "width": 1920, "height": 1080 },                    |
|    "fps": 30,                                                          |
|    "segments": [                                                       |
|      {                                                                 |
|        "id": "seg-001",                                                |
|        "media_ref": "media/image1.jpg",                                |
|        "start_beat": 0,                                                |
|        "end_beat": 4,                                                  |
|        "start_time_ms": 0,                                             |
|        "end_time_ms": 2000,                                            |
|        "transition": "cut",                                            |
|        "ken_burns": { "enabled": true, "start_zoom": 1.0, ... }        |
|      },                                                                |
|      ...                                                               |
|    ]                                                                   |
|  }                                                                     |
+------------------------------------------------------------------------+
```

### 4.2 EDL Lifecycle

1. **Auto-build generates it**: Worker analyzes beats + media, creates initial EDL
2. **UI edits it**: Frontend modifies segment order, transitions, timing via API
3. **Renderer consumes it**: Worker reads EDL to produce video output

### 4.3 Critical Rule

> **Rendering MUST NEVER depend on UI state directly.**
>
> The renderer reads only from the persisted EDL JSON. If the UI has unsaved changes, they are not rendered. This ensures deterministic, reproducible renders.

---

## 5. Tech Stack

### 5.1 Final Recommendations

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | React 18 + Vite + TypeScript | Fast dev, good ecosystem, type safety |
| **UI Components** | Tailwind CSS + shadcn/ui | Rapid styling, consistent design |
| **State** | Zustand | Simpler than Redux, good for medium complexity |
| **Backend** | FastAPI (Python 3.11+) | Async, auto-docs, great for media processing |
| **Database** | SQLite + SQLAlchemy | Zero config, sufficient for single-server MVP |
| **Job Queue** | Redis + RQ | Simple, Python-native, good for MVP |
| **Beat Detection** | madmom (primary) + librosa (fallback) | Accurate, open-source |
| **Rendering** | ffmpeg CLI | Industry standard |
| **Auth** | JWT (python-jose) + bcrypt | Simple, stateless, secure |
| **Deployment** | Docker Compose | Single-command deployment |

### 5.2 Key Dependencies

```toml
# Backend (pyproject.toml)
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
sqlalchemy = "^2.0.0"
rq = "^1.15.0"
redis = "^5.0.0"
python-jose = "^3.3.0"
bcrypt = "^4.1.0"

# Worker (pyproject.toml) - separate from backend
python = "^3.11"
rq = "^1.15.0"
redis = "^5.0.0"
madmom = "^0.16.1"    # Optional, see note below
librosa = "^0.10.0"   # Required fallback
ffmpeg-python = "^0.2.0"

# Frontend (package.json)
react = "^18.2.0"
vite = "^5.0.0"
typescript = "^5.3.0"
tailwindcss = "^3.4.0"
zustand = "^4.5.0"
```

### 5.3 madmom Installation Risk

> **Warning**: `madmom` has complex native dependencies (Cython, numpy) and may fail to build in certain container environments (especially Alpine-based images or ARM architectures).
>
> **Mitigation**:
> - `librosa` MUST be a fully supported fallback for beat detection
> - The system MUST function correctly without `madmom` installed
> - Worker should detect `madmom` availability at startup and log which detector is active
> - Use Debian-based container images for better compatibility

---

## 6. File Serving Design

### 6.1 Principle

> **No direct public filesystem exposure.**
>
> All file access goes through authenticated backend endpoints. The filesystem is never mounted or exposed directly to the web.

### 6.2 Endpoints

```
# Download outputs
GET /projects/{id}/outputs/{type}
    type: "preview" | "final"
    Returns: Streaming file response with Content-Disposition header
    Auth: Required (JWT)

# Download/stream media
GET /projects/{id}/media/{filename}
    Returns: File response
    Auth: Required (JWT)

# Thumbnails (may be cached)
GET /projects/{id}/thumbnails/{filename}
    Returns: Image response
    Auth: Required (JWT)
```

### 6.3 Implementation Notes

- Backend validates user owns the project before serving
- Use `FileResponse` or streaming responses for large files
- Set appropriate `Content-Type` headers
- For downloads, set `Content-Disposition: attachment`
- For previews/thumbnails, set `Content-Disposition: inline`

---

## 7. Security Assumptions

### 7.1 Input Validation

| Control | Implementation |
|---------|---------------|
| **File type validation** | Allowlist: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.mp4`, `.mov`, `.webm`, `.mp3`, `.wav`, `.ogg`, `.flac` |
| **Upload size limits** | Images: 50MB, Videos: 2GB, Audio: 500MB (configurable) |
| **Path traversal prevention** | Sanitize all filenames; reject `..`, absolute paths; use UUID-based storage paths |
| **MIME type verification** | Verify magic bytes match declared file extension |

### 7.2 Resource Constraints

| Control | Implementation |
|---------|---------------|
| **Render job rate limiting** | Max 2 concurrent render jobs per user; queue additional |
| **ffmpeg timeout** | Hard timeout: 30 minutes per render job |
| **ffmpeg CPU limit** | Container CPU limits via Docker (e.g., `cpus: 2`) |
| **ffmpeg memory limit** | Container memory limits via Docker (e.g., `mem_limit: 4g`) |
| **Beat analysis timeout** | 5 minutes max per audio file |

### 7.3 Network Exposure

| Port | Exposure | Notes |
|------|----------|-------|
| **80/443** | Public (via NGINX) | Only ports exposed externally |
| **3000** | Internal only | Frontend dev server |
| **8000** | Internal only | Backend API |
| **6379** | Internal only | Redis |

### 7.4 Additional Controls

- All API endpoints require authentication except `/auth/login` and `/auth/register`
- JWT tokens expire after 24 hours (configurable)
- Passwords hashed with bcrypt (cost factor 12)
- CORS restricted to known origins
- Rate limiting on auth endpoints (10 requests/minute)

---

## 8. Persistence Abstraction

> **Note**: The backend uses a **repository abstraction layer** for all database operations.
>
> This means:
> - All SQLAlchemy queries are encapsulated in repository classes
> - Business logic depends on repository interfaces, not SQLAlchemy directly
> - SQLite can be replaced with PostgreSQL (or other databases) by implementing new repository backends
> - No raw SQL or direct session access in API route handlers

Example structure:
```
backend/app/
+-- repositories/
|   +-- base.py           # Abstract base repository
|   +-- project.py        # ProjectRepository
|   +-- user.py           # UserRepository
|   +-- media.py          # MediaRepository
+-- services/
|   +-- project.py        # Uses ProjectRepository (injected)
```

---

## 9. Repository Structure

```
beatstitch/
+-- docker-compose.yml          # Main deployment config
+-- docker-compose.dev.yml      # Development overrides
+-- .env.example                # Environment template
+-- Makefile                    # Common commands
+-- README.md
|
+-- frontend/
|   +-- Dockerfile
|   +-- package.json
|   +-- vite.config.ts
|   +-- tailwind.config.js
|   +-- src/
|       +-- main.tsx
|       +-- App.tsx
|       +-- api/                # API client modules
|       |   +-- client.ts
|       |   +-- auth.ts
|       |   +-- projects.ts
|       |   +-- media.ts
|       |   +-- edl.ts          # EDL/timeline operations
|       |   +-- jobs.ts
|       +-- components/
|       |   +-- layout/         # Header, Sidebar, Layout
|       |   +-- auth/           # LoginForm, ProtectedRoute
|       |   +-- projects/       # ProjectList, ProjectCard
|       |   +-- media/          # MediaUploader, MediaBin
|       |   +-- timeline/       # TimelineView, SegmentList, BeatMarkers
|       |   +-- editor/         # EditorPanel, SettingsPanel
|       |   +-- common/         # Button, Modal, Progress
|       +-- hooks/              # useAuth, useProject, useMedia, useEDL
|       +-- stores/             # Zustand stores
|       +-- pages/              # Login, Dashboard, Editor
|       +-- types/              # TypeScript interfaces
|       +-- utils/              # Formatters, validators
|
+-- backend/
|   +-- Dockerfile
|   +-- pyproject.toml
|   +-- alembic/                # Database migrations
|   +-- app/
|       +-- main.py             # FastAPI entry
|       +-- config.py           # Settings (pydantic)
|       +-- dependencies.py
|       +-- api/                # Route handlers
|       |   +-- auth.py
|       |   +-- projects.py
|       |   +-- media.py
|       |   +-- edl.py          # EDL read/write endpoints
|       |   +-- jobs.py
|       +-- models/             # SQLAlchemy models
|       +-- schemas/            # Pydantic schemas
|       +-- repositories/       # Data access abstraction
|       +-- services/           # Business logic
|       +-- utils/              # Security, file helpers
|
+-- worker/
|   +-- Dockerfile
|   +-- pyproject.toml
|   +-- app/
|       +-- main.py             # RQ worker entry
|       +-- tasks/              # Job definitions
|       |   +-- beat_analysis.py
|       |   +-- timeline_build.py   # Auto-build EDL
|       |   +-- render.py
|       |   +-- thumbnail.py
|       +-- engines/            # Processing logic
|       |   +-- beat_detector.py    # madmom/librosa abstraction
|       |   +-- edl_builder.py      # Generates EDL from beats + media
|       |   +-- ffmpeg.py
|       |   +-- ken_burns.py
|       +-- utils/
|
+-- scripts/
|   +-- setup.sh
|   +-- dev.sh
|   +-- migrate.sh
|   +-- backup.sh
|
+-- tests/
|   +-- backend/
|   +-- worker/
|   +-- integration/
|
+-- docs/
    +-- design/                 # This documentation
```

---

## 10. Data Flow

```
+-----------------------------------------------------------------------------+
|                              DATA FLOW                                      |
+-----------------------------------------------------------------------------+

UPLOAD FLOW:
+---------+      +---------+      +-----------+      +----------+
| Browser |----->| Backend |----->| Validate  |----->| Store to |
| Upload  |      | API     |      | File Type |      | /uploads |
+---------+      +---------+      +-----------+      +-----+----+
                      |                                    |
                      v                                    v
                 +---------+                         +---------+
                 | SQLite  |<--- Store metadata ---->| Enqueue |
                 |   DB    |                         | Job     |
                 +---------+                         +----+----+
                                                          |
                                                          v
                                                     +---------+
                                                     | Redis   |
                                                     | Queue   |
                                                     +----+----+
                                                          |
PROCESSING FLOW (Worker):                                 v
                                                     +---------+
                                                     | Worker  |
                                                     +----+----+
                                                          |
            +-------------------+-------------------+-----+
            |                   |                   |
            v                   v                   v
      +-----------+       +-----------+       +-----------+
      | Beat      |       | Generate  |       | Generate  |
      | Analysis  |       | Thumbnails|       | Proxies   |
      +-----------+       +-----------+       +-----------+
            |                   |                   |
            v                   v                   v
      +-----------+       +-----------------------------+
      | /derived/ |       |        /derived/            |
      | beats.json|       |   thumbnails/ + proxies/    |
      +-----------+       +-----------------------------+

AUTO-BUILD FLOW:
+-----------+      +-----------+      +-----------+
| beats.json|----->| Worker:   |----->| edl.json  |
| + media   |      | EDL Build |      | (saved)   |
+-----------+      +-----------+      +-----------+

RENDER FLOW:
+-----------+      +-----------+      +-----------+      +-----------+
| edl.json  |----->| Worker:   |----->| ffmpeg    |----->| /outputs/ |
| (read)    |      | Render    |      | process   |      | final/    |
+-----------+      +-----------+      +-----------+      +-----------+
       ^
       |
  (NOT from UI state - always from persisted EDL)

DOWNLOAD FLOW:
+-----------+      +-----------+      +-----------+      +-----------+
| Browser   |----->| Backend   |----->| Validate  |----->| Stream    |
| Request   |      | API       |      | Auth +    |      | File      |
+-----------+      +-----------+      | Ownership |      +-----------+
                                      +-----------+
```

---

[Next: Data Models ->](./02-data-models.md)
