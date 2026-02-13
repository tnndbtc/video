# BeatStitch - Infrastructure: Jobs, Deployment & Security

[← Back to Index](./00-index.md) | [← Previous](./04-processing.md) | [Next →](./06-roadmap.md)

---

## 1. Job Queue System

### 1.1 Choice: Redis + RQ

| Option | Verdict | Rationale |
|--------|---------|-----------|
| **Redis + RQ** | ✅ Chosen | Simple, Python-native, sufficient for MVP |
| Celery | ❌ | Overkill for single-server MVP |
| SQLite queue | ❌ | No pub/sub, harder progress tracking |

### 1.2 Queue Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        REDIS                                 │
│                                                              │
│  Queues:                                                     │
│  ├── beatstitch:render_preview  (high priority)             │
│  ├── beatstitch:beat_analysis   (medium priority)           │
│  ├── beatstitch:timeline        (medium priority)           │
│  ├── beatstitch:render_final    (low priority)              │
│  └── beatstitch:thumbnails      (low priority)              │
│                                                              │
│  Progress: beatstitch:progress:{job_id}                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      RQ WORKER                               │
│  (Single worker is fine for MVP)                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Worker Implementation

```python
# worker/main.py
from redis import Redis
from rq import Queue, Worker

redis_conn = Redis(host="redis", port=6379, db=0)

# All queues listed in priority order (highest first)
preview_queue = Queue("beatstitch:render_preview", connection=redis_conn)
beat_queue = Queue("beatstitch:beat_analysis", connection=redis_conn)
timeline_queue = Queue("beatstitch:timeline", connection=redis_conn)
final_queue = Queue("beatstitch:render_final", connection=redis_conn)
thumbnail_queue = Queue("beatstitch:thumbnails", connection=redis_conn)

def start_worker():
    queues = [preview_queue, beat_queue, timeline_queue, final_queue, thumbnail_queue]
    worker = Worker(queues, connection=redis_conn)
    worker.work()
```

### 1.4 Beat Analysis Task

The beat analysis worker loads audio from the filesystem and writes results to a derived file:

```python
# worker/tasks/beat_analysis.py
from pathlib import Path
import json

STORAGE_ROOT = Path("/data")

def analyze_beats(project_id: str, audio_id: str) -> dict:
    """
    Load audio from filesystem, run beat detection, write results to derived/beats.json.
    The API reads from this file rather than storing beats in the database.
    """
    job = get_current_job()
    update_progress(job.id, 0, "Loading audio")

    # Resolve audio path from database record
    audio_record = db.query(AudioTrack).filter_by(id=audio_id).first()
    audio_path = STORAGE_ROOT / audio_record.file_path  # e.g., uploads/{project}/audio/xyz.mp3

    update_progress(job.id, 10, "Detecting beats")
    detector = BeatDetector()
    beat_grid = detector.analyze(str(audio_path))

    # Write beat grid to derived location (filesystem, not DB blob)
    derived_dir = STORAGE_ROOT / "derived" / project_id
    derived_dir.mkdir(parents=True, exist_ok=True)
    beats_path = derived_dir / "beats.json"

    beats_data = {
        "bpm": beat_grid.bpm,
        "beats": beat_grid.beats,
        "time_signature": beat_grid.time_signature,
        "confidence": beat_grid.confidence,
        "analyzed_at": datetime.utcnow().isoformat()
    }
    beats_path.write_text(json.dumps(beats_data, indent=2))

    # Update database status (not the beat data itself)
    audio_record.analysis_status = "complete"
    audio_record.bpm = beat_grid.bpm
    db.commit()

    update_progress(job.id, 100, "Complete")
    return {"beats_path": str(beats_path), "bpm": beat_grid.bpm}
```

### 1.5 Render Task

The renderer resolves file paths via `media_asset_id` lookups. The EDL does **not** contain `source_path` directly—this prevents path injection and ensures paths are always resolved fresh from the database:

```python
# worker/tasks/render.py
import os
import signal
import subprocess
from pathlib import Path
from rq import get_current_job

STORAGE_ROOT = Path("/data")

def render_video(project_id: str, job_type: str, edl_hash: str) -> dict:
    job = get_current_job()
    update_progress(job.id, 0, "Starting render")

    project = load_project(project_id)
    timeline = project.timeline

    # Verify EDL hash hasn't changed (race condition prevention)
    if timeline.edl_hash != edl_hash:
        raise ValueError("Timeline changed during render request")

    edl = json.loads(timeline.edl_json)

    # Resolve all media paths from database (EDL contains only media_asset_ids)
    resolved_edl = resolve_media_paths(edl, project_id)

    if job_type == "preview":
        settings = PreviewSettings()
        resolved_edl = simplify_edl_for_preview(resolved_edl)
    else:
        settings = RenderSettings()

    output_dir = STORAGE_ROOT / "outputs" / project_id / job_type
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp()}.mp4"

    builder = FFmpegCommandBuilder(resolved_edl, settings, str(output_path))
    cmd = builder.build()

    # Run FFmpeg with timeout protection
    run_ffmpeg_with_timeout(
        cmd,
        timeout_seconds=JOB_TIMEOUTS[f"render_{job_type}"],
        total_duration_ms=edl["total_duration_ms"],
        progress_callback=lambda pct, msg: update_progress(job.id, pct, msg)
    )

    return {"output_path": str(output_path), "file_size": os.path.getsize(output_path)}


def resolve_media_paths(edl: dict, project_id: str) -> dict:
    """
    Resolve media_asset_ids to actual file paths.
    This ensures paths are never stored in EDL and are always validated at render time.
    """
    resolved = edl.copy()
    resolved["segments"] = []

    for segment in edl["segments"]:
        asset = db.query(MediaAsset).filter_by(
            id=segment["media_asset_id"],
            project_id=project_id  # Ensure asset belongs to this project
        ).first()

        if not asset:
            raise ValueError(f"Media asset {segment['media_asset_id']} not found")

        resolved_segment = segment.copy()
        resolved_segment["source_path"] = str(STORAGE_ROOT / asset.file_path)
        resolved["segments"].append(resolved_segment)

    # Also resolve audio path
    if edl.get("audio"):
        audio = db.query(AudioTrack).filter_by(project_id=project_id).first()
        resolved["audio"]["file_path"] = str(STORAGE_ROOT / audio.file_path)

    return resolved
```

### 1.6 FFmpeg Execution with Timeout

FFmpeg must be killed if it exceeds the job timeout. This is the primary protection against runaway processes:

```python
# worker/tasks/ffmpeg_runner.py
import os
import re
import signal
import subprocess
from typing import Callable, List

class FFmpegTimeout(Exception):
    pass

class FFmpegError(Exception):
    pass

def run_ffmpeg_with_timeout(
    cmd: List[str],
    timeout_seconds: int,
    total_duration_ms: int,
    progress_callback: Callable[[int, str], None]
) -> None:
    """
    Run FFmpeg with strict timeout enforcement.
    Kills the process if it exceeds the timeout.
    """
    cmd_with_progress = cmd + ["-progress", "pipe:1", "-stats_period", "0.5"]

    process = subprocess.Popen(
        cmd_with_progress,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        # Run FFmpeg in its own process group for clean termination
        preexec_fn=os.setsid
    )

    time_pattern = re.compile(r"out_time_ms=(\d+)")
    start_time = time.time()

    try:
        for line in process.stdout:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                # Kill entire process group
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                raise FFmpegTimeout(f"FFmpeg exceeded timeout of {timeout_seconds}s")

            match = time_pattern.search(line)
            if match:
                current_ms = int(match.group(1)) / 1000
                percent = min(99, int((current_ms / total_duration_ms) * 100))
                progress_callback(percent, f"Rendering: {percent}%")

        return_code = process.wait(timeout=30)  # Brief wait for cleanup
        if return_code != 0:
            stderr = process.stderr.read()
            raise FFmpegError(f"FFmpeg failed with code {return_code}: {stderr}")

        progress_callback(100, "Complete")

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        raise FFmpegTimeout("FFmpeg process cleanup timed out")

def update_progress(job_id: str, percent: int, message: str):
    redis_conn.hset(f"beatstitch:progress:{job_id}", mapping={
        "percent": percent, "message": message,
        "updated_at": datetime.utcnow().isoformat()
    })
    redis_conn.expire(f"beatstitch:progress:{job_id}", 3600)
```

### 1.7 Job Timeouts

Job timeouts are the **primary resource protection** mechanism. These are enforced at the RQ level and within FFmpeg execution:

```python
JOB_TIMEOUTS = {
    "beat_analysis": 300,      # 5 minutes
    "timeline_generation": 60, # 1 minute
    "media_processing": 120,   # 2 minutes
    "render_preview": 600,     # 10 minutes
    "render_final": 1800,      # 30 minutes
}

# RQ job enqueue with timeout
beat_queue.enqueue(
    analyze_beats,
    project_id,
    audio_id,
    job_timeout=JOB_TIMEOUTS["beat_analysis"]
)
```

---

## 2. Deployment

### 2.1 Docker Compose

**Note:** `deploy.resources.limits` only works in Docker Swarm mode. For standard `docker-compose up`, use `mem_limit` (Compose v2) or rely on job timeouts as the primary protection.

```yaml
# docker-compose.yml
version: "3.8"

services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      # For production: set to actual domain or use relative paths
      # Do NOT hardcode localhost for production deployments
      - VITE_API_URL=${API_URL:-}
    depends_on: [backend]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=sqlite:////data/db/beatstitch.db
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - STORAGE_PATH=/data
      - MAX_UPLOAD_SIZE=524288000
    volumes:
      - beatstitch-data:/data
    depends_on: [redis]
    # mem_limit works in Compose v2 (not Swarm)
    # Uncomment if needed: mem_limit: 2g

  worker:
    build: ./worker
    environment:
      - DATABASE_URL=sqlite:////data/db/beatstitch.db
      - REDIS_URL=redis://redis:6379/0
      - STORAGE_PATH=/data
    volumes:
      - beatstitch-data:/data
    depends_on: [redis, backend]
    # Memory limits in standard Compose (not Swarm):
    # mem_limit: 4g
    #
    # NOTE: Job timeouts (see 1.7) are the PRIMARY protection against
    # runaway FFmpeg processes. Memory limits are secondary.

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  beatstitch-data:
  redis-data:
```

### 2.2 Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.3 Worker Dockerfile

The worker runs as a non-root user for security (limits blast radius if FFmpeg is exploited):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running FFmpeg jobs
RUN useradd --create-home --shell /bin/bash worker

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

COPY . .

# Ensure data directories are accessible
RUN mkdir -p /data && chown -R worker:worker /data

# Switch to non-root user
USER worker

CMD ["python", "-m", "app.main"]
```

### 2.4 Reverse Proxy Configuration

When deploying behind Nginx or Caddy, you **must** configure large upload support:

#### Nginx

```nginx
# /etc/nginx/sites-available/beatstitch
server {
    listen 80;
    server_name beatstitch.example.com;

    # CRITICAL: Allow large file uploads (500MB)
    client_max_body_size 500M;

    # Increase timeouts for long uploads
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for upload progress
        proxy_request_buffering off;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Caddy

```caddyfile
beatstitch.example.com {
    # Large upload support
    request_body {
        max_size 500MB
    }

    handle /api/* {
        reverse_proxy localhost:8000
    }

    handle {
        reverse_proxy localhost:3000
    }
}
```

### 2.5 Frontend API URL Configuration

For production deployments behind a single domain:

```bash
# .env.production
# When frontend and API are served from the same domain via reverse proxy,
# use a relative path or leave empty:
VITE_API_URL=/api

# For separate domains (less common):
# VITE_API_URL=https://api.beatstitch.example.com
```

```typescript
// frontend/src/config.ts
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';
```

### 2.6 Deployment Commands

```makefile
# Makefile
dev:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

prod:
	docker-compose up -d --build

logs:
	docker-compose logs -f

logs-worker:
	docker-compose logs -f worker

migrate:
	docker-compose exec backend alembic upgrade head

backup:
	./scripts/backup.sh
```

### 2.7 Server Requirements (MVP)

- 4 CPU cores
- 8GB RAM
- 100GB SSD storage
- Ubuntu 22.04 or similar

---

## 3. Security

### 3.1 Authentication (JWT)

```python
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
```

### 3.2 Path Traversal Prevention

```python
import os
import re
import uuid
from pathlib import Path
from uuid import uuid4, UUID

STORAGE_ROOT = Path(config.STORAGE_PATH)
ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".m4a"}
}

def sanitize_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = filename.replace("\x00", "")
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    name, ext = os.path.splitext(filename)
    return f"{name[:100]}{ext}"

def generate_safe_path(project_id: str, category: str, filename: str) -> Path:
    # Validate project_id is a valid UUID
    try:
        UUID(project_id)
    except ValueError:
        raise ValueError("Invalid project ID")

    if category not in ["media", "audio"]:
        raise ValueError("Invalid category")

    safe_filename = f"{uuid4().hex[:8]}_{sanitize_filename(filename)}"
    path = STORAGE_ROOT / "uploads" / project_id / category / safe_filename

    # Verify path is within storage root
    if not str(path.resolve()).startswith(str(STORAGE_ROOT.resolve())):
        raise ValueError("Path traversal detected")

    return path

def validate_file_type(filename: str, expected_type: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS.get(expected_type, set())
```

### 3.3 Rate Limiting

Rate limits are keyed by **action category**, not by raw URL path. This prevents IDs in URLs from bypassing limits (e.g., `/projects/abc/render` and `/projects/xyz/render` should share the same limit).

```python
from fastapi import Request, HTTPException
from starlette.routing import Match

RATE_LIMITS = {
    "upload": (10, 60),     # 10 requests per minute
    "render": (5, 300),     # 5 requests per 5 minutes
    "analyze": (10, 60),    # 10 requests per minute
    "default": (100, 60),   # 100 requests per minute
}

# Map route names to rate limit categories
ROUTE_CATEGORIES = {
    "upload_media": "upload",
    "upload_audio": "upload",
    "start_render": "render",
    "analyze_audio": "analyze",
    "generate_timeline": "analyze",
}

def get_rate_limit_category(request: Request) -> str:
    """
    Determine rate limit category from route name, not URL path.
    This ensures /projects/abc/render and /projects/xyz/render share limits.
    """
    # Get the matched route name from FastAPI
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            route_name = getattr(route, "name", None)
            if route_name and route_name in ROUTE_CATEGORIES:
                return ROUTE_CATEGORIES[route_name]
    return "default"

async def rate_limit_middleware(request: Request, call_next):
    user_id = getattr(request.state, "user_id", "anonymous")
    category = get_rate_limit_category(request)
    limit, window = RATE_LIMITS[category]

    # Key by user + category (NOT by URL path)
    key = f"ratelimit:{user_id}:{category}"
    current = redis_conn.get(key)

    if current and int(current) >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded for {category}",
                "retry_after_seconds": redis_conn.ttl(key)
            }
        )

    pipe = redis_conn.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()

    return await call_next(request)
```

### 3.4 Resource Limits

```python
class Settings:
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_MEDIA_PER_PROJECT = 50
    MAX_PROJECTS_PER_USER = 20
    MAX_VIDEO_DURATION = 600    # 10 minutes per video

    # FFmpeg safety (see section 1.6 and 1.7)
    # Job timeouts are the primary protection mechanism
```

### 3.5 FFmpeg Safety Summary

| Protection | Mechanism | Notes |
|------------|-----------|-------|
| **Job Timeout** | RQ `job_timeout` + explicit kill | Primary protection |
| **Process Kill** | `os.killpg()` on timeout | Ensures cleanup |
| **Non-root User** | Worker Dockerfile `USER worker` | Limits blast radius |
| **Path Resolution** | Resolve at render time, not from EDL | Prevents path injection |
| **CPU Priority** | `nice` (future) | Optional, not MVP |

---

## 4. Observability

### 4.1 Structured Logging

```python
import logging
import json
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ["request_id", "user_id", "project_id", "job_id", "duration_ms"]:
            if hasattr(record, field):
                log[field] = getattr(record, field)
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)

# Usage
logger.info("Render started", extra={"project_id": "proj_123", "job_id": "job_456"})
```

### 4.2 Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram, Gauge

http_requests_total = Counter("http_requests_total", "Total requests", ["method", "endpoint", "status"])
render_jobs_total = Counter("render_jobs_total", "Total renders", ["type", "status"])
render_duration = Histogram("render_duration_seconds", "Render duration", ["type"])
active_render_jobs = Gauge("active_render_jobs", "Active renders")
```

### 4.3 Health Check

```python
@router.get("/health")
async def health_check():
    checks = {}
    healthy = True

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        healthy = False

    # Redis
    try:
        redis_conn.ping()
        checks["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        healthy = False

    # Storage
    try:
        stat = os.statvfs(config.STORAGE_PATH)
        free_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)
        checks["storage"] = {"status": "healthy" if free_gb > 1 else "warning", "free_gb": round(free_gb, 2)}
    except Exception as e:
        checks["storage"] = {"status": "unhealthy", "error": str(e)}
        healthy = False

    # FFmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        checks["ffmpeg"] = {"status": "healthy" if result.returncode == 0 else "unhealthy"}
    except Exception as e:
        checks["ffmpeg"] = {"status": "unhealthy", "error": str(e)}
        healthy = False

    return {"status": "healthy" if healthy else "unhealthy", "checks": checks}
```

---

## 5. Environment Variables

```bash
# .env.example

# App
SECRET_KEY=your-secret-key-min-32-chars
DEBUG=false
VERSION=1.0.0

# Database
DATABASE_URL=sqlite:////data/db/beatstitch.db

# Redis
REDIS_URL=redis://redis:6379/0

# Storage
STORAGE_PATH=/data
MAX_UPLOAD_SIZE=524288000

# API URL (for frontend)
# Production: use relative path or actual domain, NOT localhost
API_URL=/api

# CORS (adjust for your domain in production)
CORS_ORIGINS=https://beatstitch.example.com

# JWT
ACCESS_TOKEN_EXPIRE_HOURS=24
```

---

## 6. Deployment Checklist

### Pre-deployment

- [ ] Generate secure `SECRET_KEY` (32+ chars)
- [ ] Configure reverse proxy (Nginx/Caddy) with `client_max_body_size 500M`
- [ ] Set `API_URL` appropriately (not localhost)
- [ ] Set `CORS_ORIGINS` to production domain
- [ ] Verify worker Dockerfile runs as non-root

### Post-deployment

- [ ] Verify `/health` endpoint returns healthy
- [ ] Test file upload (small and large files)
- [ ] Test render job completes successfully
- [ ] Verify job timeout kills long-running FFmpeg processes
- [ ] Check logs for structured JSON output

---

[Next: Roadmap (Risks, Testing, Phase 2) →](./06-roadmap.md)
