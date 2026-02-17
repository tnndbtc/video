# BeatStitch - Beat-Synced Video Editor

A web-based video editor that automatically syncs media cuts to music beats. Upload your images, videos, and an audio track, and BeatStitch will create a perfectly beat-synced video montage.

## Final Goal: Prompt-to-Video API

BeatStitch's north-star capability is a fully automated **prompt-to-video** pipeline:
given a list of media assets and a natural-language description, the system produces a
rendered, edit-ready video with zero manual timeline work.

### Inputs

| Input | Description |
|-------|-------------|
| **Assets** | One or more images, video clips, and/or an audio track (already uploaded to a project) |
| **Prompt** | Natural-language description of the desired video (e.g. "energetic montage, cut every beat") |
| **Constraints** *(optional)* | Target duration, transition style, audio mode, max clips |

### Outputs

| Output | Description |
|--------|-------------|
| **EditPlan JSON** | Machine-validated timeline (EDL v1) describing every clip, duration, and transition |
| **Rendered video** | Final MP4 produced by the FFmpeg worker, accessible via a download URL |

### Pipeline

```
Ingest assets → AI Planner (OpenAI) → Validate EditPlan → Apply timeline → Render worker (FFmpeg) → Result
```

**Key design principle:** _The LLM decides the edit plan; the backend enforces correctness; the worker renders._

- The AI Planner calls OpenAI to produce an `EditPlan` JSON (EDL v1 format).
- The backend validator rejects any plan that references unknown media IDs, impossible durations, or invalid transitions.
- Only a valid plan is passed to the FFmpeg worker for rendering.
- The frontend `/ai-stitch` page exposes this full pipeline for manual testing.

### Try It

Visit **http://localhost:3001/ai-stitch** after starting the stack to use the interactive testing UI.
See [docs/manual_test_ai_stitch.md](docs/manual_test_ai_stitch.md) for a step-by-step guide.

## Features

- **Automatic Beat Detection** - Analyzes audio to detect beats using madmom/librosa
- **Media Management** - Upload and organize images and video clips
- **Timeline Generation** - Auto-generates edit timeline synced to detected beats
- **Video Rendering** - Render preview or final quality videos with FFmpeg
- **Transitions** - Crossfade and cut transitions between clips
- **Ken Burns Effect** - Automatic pan/zoom effects on images
- **Background Processing** - Long-running jobs processed in the background

## Quick Start

### Prerequisites

- Docker and Docker Compose v2+
- 4GB+ RAM recommended
- 100GB+ storage for projects

### Development Setup

```bash
# Clone repository
git clone <repo-url>
cd video

# Initialize environment configuration
make init-env

# Edit .env and set a secure SECRET_KEY
# Generate one with: openssl rand -hex 32

# Start development environment
make dev

# Access the app
open http://localhost:3001

# API documentation
open http://localhost:8080/docs
```

### Production Deployment

```bash
# Initialize and configure environment
make init-env
# Edit .env with production values (see docs/deployment.md)

# Start production environment (detached)
make prod

# View logs
make logs
```

## Architecture

```
+-----------+     +-----------+     +-----------+
|  Frontend |---->|  Backend  |---->|  Worker   |
|  (React)  |     | (FastAPI) |     |   (RQ)    |
+-----------+     +-----------+     +-----------+
                        |                 |
                        v                 v
                  +-----------+     +-----------+
                  |  SQLite   |     |   Redis   |
                  |  Database |     |   Queue   |
                  +-----------+     +-----------+
```

### Component Overview

| Component | Responsibility |
|-----------|---------------|
| **Frontend** | React-based UI for project management, media upload, and timeline viewing |
| **Backend** | FastAPI REST API for authentication, project state, and job management |
| **Worker** | RQ worker for CPU-intensive tasks (beat analysis, rendering, thumbnails) |
| **Redis** | Job queue and ephemeral cache |
| **SQLite** | Project metadata and user accounts |

## Documentation

- [API Documentation](docs/api.md) - REST API reference with examples
- [AI Prompt-to-Video](docs/ai_prompt_to_video.md) - Endpoint contract, EditPlan schema, pipeline design
- [Manual Testing: AI Stitch](docs/manual_test_ai_stitch.md) - Step-by-step testing guide
- [Deployment Guide](docs/deployment.md) - Production deployment and configuration
- [Development Guide](docs/development.md) - Local setup, testing, and contributing
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Architecture Design](docs/design/00-index.md) - Detailed technical design documents

## User Workflow

1. **Login** - Create account or sign in
2. **Create Project** - Name your video project
3. **Upload Media** - Add images, videos, and an audio track
4. **Configure Settings** - Set beats per cut, transition type, and effects
5. **Generate Timeline** - Auto-build timeline synced to detected beats
6. **Preview** - Render a quick low-quality preview
7. **Render Final** - Generate full-quality 1080p output
8. **Download** - Get your finished video

## Tech Stack

### Frontend
- React 18 with TypeScript
- Vite for development and building
- Tailwind CSS for styling
- Zustand for state management
- React Query for API communication

### Backend
- FastAPI (Python 3.11+)
- SQLAlchemy for database ORM
- Pydantic for validation
- JWT authentication with python-jose

### Worker
- RQ (Redis Queue) for job processing
- madmom / librosa for beat detection
- FFmpeg for video rendering

### Infrastructure
- Docker and Docker Compose
- Redis for message queue
- SQLite database (PostgreSQL in Phase 2)
- Nginx/Caddy reverse proxy (production)

## Project Structure

```
video/
|-- docker-compose.yml      # Main deployment configuration
|-- .env.example            # Environment template
|-- Makefile                # Development commands
|-- README.md               # This file
|
|-- frontend/               # React frontend application
|   |-- src/
|   |   |-- components/     # UI components
|   |   |-- pages/          # Route pages
|   |   |-- api/            # API client
|   |   |-- stores/         # Zustand stores
|   |   +-- hooks/          # Custom React hooks
|   +-- Dockerfile
|
|-- backend/                # FastAPI backend service
|   |-- app/
|   |   |-- api/            # Route handlers
|   |   |-- models/         # SQLAlchemy models
|   |   |-- schemas/        # Pydantic schemas
|   |   |-- repositories/   # Data access layer
|   |   +-- services/       # Business logic
|   +-- Dockerfile
|
|-- worker/                 # RQ worker service
|   |-- app/
|   |   |-- tasks/          # Job definitions
|   |   +-- engines/        # Processing logic
|   +-- Dockerfile
|
+-- docs/                   # Documentation
    |-- design/             # Architecture design docs
    |-- api.md              # API reference
    |-- deployment.md       # Deployment guide
    |-- development.md      # Developer guide
    +-- troubleshooting.md  # Common issues
```

## Make Commands

```bash
make dev           # Start development environment
make prod          # Start production environment (detached)
make build         # Build Docker images
make stop          # Stop all services
make clean         # Remove containers, volumes, and images
make logs          # Follow all service logs
make logs-worker   # Follow worker logs
make logs-backend  # Follow backend logs
make migrate       # Run database migrations
make shell-backend # Open shell in backend container
make shell-worker  # Open shell in worker container
make init-env      # Create .env from template
```

## Environment Variables

Key configuration options (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (32+ chars) | **Required** |
| `DATABASE_URL` | SQLite database path | `sqlite:////data/db/beatstitch.db` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `MAX_UPLOAD_SIZE` | Maximum file upload size | `524288000` (500MB) |
| `ACCESS_TOKEN_EXPIRE_HOURS` | JWT token expiration | `24` |

## MVP Limits

- 50 media items per project
- 500MB max upload size
- 30-minute max render time
- Single server deployment

## License

MIT

## Contributing

See [docs/development.md](docs/development.md) for development setup and contribution guidelines.
