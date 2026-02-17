# BeatStitch Development Guide

This guide covers setting up a development environment, running tests, and contributing to BeatStitch.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Code Style Guidelines](#code-style-guidelines)
- [Adding New Features](#adding-new-features)
- [Database Migrations](#database-migrations)
- [Debugging Tips](#debugging-tips)
- [Common Development Tasks](#common-development-tasks)

## Development Setup

### Prerequisites

- Docker and Docker Compose v2+
- Node.js 18+ (for frontend development outside Docker)
- Python 3.11+ (for backend development outside Docker)
- FFmpeg (for local testing)
- Git

### Quick Start with Docker

The fastest way to get started is using Docker:

```bash
# Clone the repository
git clone <repo-url>
cd video

# Initialize environment
make init-env

# Edit .env (default values work for development)
# For development, you can use any SECRET_KEY value

# Start development environment
make dev

# Access services:
# Frontend: http://localhost:3001
# Backend API: http://localhost:8080
# API Docs: http://localhost:8080/docs
```

### Local Development Without Docker

For faster iteration, you can run services locally.

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install poetry
poetry install

# Set environment variables
export DATABASE_URL=sqlite:///./beatstitch.db
export REDIS_URL=redis://localhost:6379/0
export SECRET_KEY=dev-secret-key-min-32-characters-long
export STORAGE_PATH=./data
export DEBUG=true

# Run database migrations
alembic upgrade head

# Start the backend
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Set environment variables
export VITE_API_URL=http://localhost:8080

# Start development server
npm run dev
```

#### Worker Setup

```bash
cd worker

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install poetry
poetry install

# Set environment variables
export DATABASE_URL=sqlite:///../backend/beatstitch.db
export REDIS_URL=redis://localhost:6379/0
export STORAGE_PATH=../backend/data

# Start the worker
python -m app.main
```

#### Redis Setup

```bash
# Using Docker (easiest)
docker run -d -p 6379:6379 redis:7-alpine

# Or install locally
# Ubuntu: sudo apt install redis-server
# Mac: brew install redis
```

### IDE Setup

#### VS Code

Recommended extensions:
- Python (Microsoft)
- Pylance
- ESLint
- Tailwind CSS IntelliSense
- Docker

Workspace settings (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": "./backend/venv/bin/python",
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter"
  }
}
```

#### PyCharm

1. Open the `video` directory as a project
2. Configure Python interpreter for backend (`backend/venv`)
3. Configure Python interpreter for worker (`worker/venv`)
4. Mark `backend/app` and `worker/app` as Sources Root

## Project Structure

```
video/
|-- docker-compose.yml       # Main Docker Compose config
|-- .env.example             # Environment template
|-- Makefile                 # Development commands
|-- README.md                # Project overview
|
|-- frontend/                # React frontend
|   |-- Dockerfile
|   |-- package.json
|   |-- vite.config.ts       # Vite configuration
|   |-- tailwind.config.js   # Tailwind CSS config
|   |-- src/
|   |   |-- main.tsx         # Application entry
|   |   |-- App.tsx          # Root component
|   |   |-- api/             # API client modules
|   |   |   |-- client.ts    # Axios client setup
|   |   |   |-- auth.ts      # Auth API calls
|   |   |   |-- projects.ts  # Project API calls
|   |   |   +-- media.ts     # Media API calls
|   |   |-- components/      # React components
|   |   |   |-- layout/      # Layout components
|   |   |   |-- auth/        # Auth components
|   |   |   |-- projects/    # Project components
|   |   |   |-- media/       # Media components
|   |   |   |-- timeline/    # Timeline components
|   |   |   +-- common/      # Shared components
|   |   |-- hooks/           # Custom React hooks
|   |   |-- stores/          # Zustand state stores
|   |   |-- pages/           # Route pages
|   |   |-- types/           # TypeScript types
|   |   +-- utils/           # Utility functions
|   +-- public/              # Static assets
|
|-- backend/                 # FastAPI backend
|   |-- Dockerfile
|   |-- pyproject.toml       # Python dependencies
|   |-- alembic/             # Database migrations
|   |   |-- versions/        # Migration files
|   |   +-- env.py           # Migration config
|   |-- app/
|   |   |-- main.py          # FastAPI entry point
|   |   |-- config.py        # Configuration (Pydantic)
|   |   |-- dependencies.py  # Dependency injection
|   |   |-- api/             # Route handlers
|   |   |   |-- auth.py      # Auth endpoints
|   |   |   |-- projects.py  # Project endpoints
|   |   |   |-- media.py     # Media endpoints
|   |   |   |-- audio.py     # Audio endpoints
|   |   |   |-- timeline.py  # Timeline endpoints
|   |   |   +-- jobs.py      # Job status endpoints
|   |   |-- models/          # SQLAlchemy models
|   |   |-- schemas/         # Pydantic schemas
|   |   |-- repositories/    # Data access layer
|   |   |-- services/        # Business logic
|   |   +-- utils/           # Utilities
|   +-- tests/               # Backend tests
|
|-- worker/                  # RQ worker
|   |-- Dockerfile
|   |-- pyproject.toml
|   |-- app/
|   |   |-- main.py          # Worker entry point
|   |   |-- tasks/           # Job definitions
|   |   |   |-- beat_analysis.py
|   |   |   |-- timeline_build.py
|   |   |   |-- render.py
|   |   |   +-- thumbnail.py
|   |   |-- engines/         # Processing engines
|   |   |   |-- beat_detector.py
|   |   |   |-- edl_builder.py
|   |   |   |-- ffmpeg.py
|   |   |   +-- ken_burns.py
|   |   +-- utils/
|   +-- tests/               # Worker tests
|
+-- docs/                    # Documentation
    |-- design/              # Architecture docs
    |-- api.md
    |-- deployment.md
    |-- development.md
    +-- troubleshooting.md
```

## Running Tests

### Backend Tests

```bash
# With Docker
docker-compose exec backend pytest

# Or locally
cd backend
source venv/bin/activate
pytest

# Run specific test file
pytest tests/test_auth.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

### Worker Tests

```bash
# With Docker
docker-compose exec worker pytest

# Or locally
cd worker
source venv/bin/activate
pytest

# Run beat detection tests
pytest tests/test_beat_detection.py

# Run timeline tests
pytest tests/test_timeline.py
```

### Frontend Tests

```bash
# With Docker
docker-compose exec frontend npm test

# Or locally
cd frontend
npm test

# Run with coverage
npm test -- --coverage

# Run in watch mode
npm test -- --watch
```

### End-to-End Tests

```bash
# Requires Playwright
cd frontend
npm run test:e2e
```

## Manual UI Validation

The quickest way to confirm the full stack is working is to walk through the
core workflow in a browser.

### Find your HOST_IP

Run `setup.sh` → option 3, or:

```bash
hostname -I | awk '{print $1}'
```

Two common cases:
- **Same machine as server:** use `localhost` — `http://localhost:3001`
- **Different machine on LAN (most common):** use the server's LAN IP —
  `http://<HOST_IP>:3001` (find it via `setup.sh` → option 3, or `hostname -I`)

### Health check (before opening browser)

```bash
curl http://<HOST_IP>:8080/health
# {"status": "healthy", ...}
```

### Steps

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Open `http://<HOST_IP>:3001` | Login page loads |
| 2 | Click Register, create account | Redirected to Dashboard |
| 3 | Click "New Project", give it a name | Project card appears |
| 4 | Open project, upload 2–3 images/videos | Assets show status "ready" |
| 5 | (Optional) Upload an audio track | Beat analysis completes |
| 6 | Click "Render" (Preview or Final) | Render job queued → running → complete |
| 7 | Download / play the rendered video | Video plays correctly |

If all steps pass, the frontend (`:3001`), backend (`:8080`), worker, Redis, and
Postgres are all functioning end-to-end.

### Test Fixtures

Test fixtures are located in `tests/fixtures/`:

| File | Description |
|------|-------------|
| `test_image.jpg` | 1920x1080 test image |
| `test_video.mp4` | 10 second test video |
| `test_audio.mp3` | 30 second audio file |
| `120bpm_track.mp3` | Known 120 BPM for beat tests |

## Code Style Guidelines

### Python (Backend/Worker)

- Use Black for formatting (line length 88)
- Use isort for import sorting
- Follow PEP 8 naming conventions
- Use type hints everywhere
- Use Pydantic for data validation

```bash
# Format code
black backend/app worker/app

# Sort imports
isort backend/app worker/app

# Type check
mypy backend/app worker/app
```

Example:

```python
from typing import Optional, List
from pydantic import BaseModel, Field

class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


async def create_project(
    project_data: ProjectCreate,
    user_id: str,
    db: Session,
) -> Project:
    """Create a new project for the given user."""
    project = Project(
        id=generate_uuid(),
        name=project_data.name,
        description=project_data.description,
        owner_id=user_id,
    )
    db.add(project)
    db.commit()
    return project
```

### TypeScript (Frontend)

- Use ESLint with recommended rules
- Use Prettier for formatting
- Use TypeScript strict mode
- Prefer functional components with hooks

```bash
# Lint code
cd frontend
npm run lint

# Fix lint issues
npm run lint:fix
```

Example:

```typescript
import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '@/api/projects';

interface Project {
  id: string;
  name: string;
  status: 'draft' | 'ready' | 'rendering';
}

export function useProjects() {
  const { data: projects, isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  });

  return { projects, isLoading, error };
}
```

## Adding New Features

### Adding a New API Endpoint

1. **Define schema** in `backend/app/schemas/`:

```python
# schemas/feature.py
from pydantic import BaseModel

class FeatureCreate(BaseModel):
    name: str

class FeatureResponse(BaseModel):
    id: str
    name: str
```

2. **Add repository** in `backend/app/repositories/`:

```python
# repositories/feature.py
from app.models import Feature

class FeatureRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> Feature:
        feature = Feature(**data)
        self.db.add(feature)
        self.db.commit()
        return feature
```

3. **Add service** in `backend/app/services/`:

```python
# services/feature.py
class FeatureService:
    def __init__(self, repo: FeatureRepository):
        self.repo = repo

    def create_feature(self, data: FeatureCreate) -> Feature:
        return self.repo.create(data.dict())
```

4. **Add route** in `backend/app/api/`:

```python
# api/feature.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/features", tags=["features"])

@router.post("/", response_model=FeatureResponse)
async def create_feature(
    data: FeatureCreate,
    current_user: User = Depends(get_current_user),
):
    service = FeatureService(FeatureRepository(db))
    return service.create_feature(data)
```

5. **Register router** in `backend/app/main.py`:

```python
from app.api import feature
app.include_router(feature.router, prefix="/api")
```

### Adding a New Worker Task

1. **Create task** in `worker/app/tasks/`:

```python
# tasks/new_task.py
from rq import get_current_job

def process_something(project_id: str, options: dict):
    """Process something in the background."""
    job = get_current_job()

    # Update progress
    job.meta['progress_percent'] = 0
    job.meta['progress_message'] = 'Starting...'
    job.save_meta()

    # Do work...

    job.meta['progress_percent'] = 100
    job.meta['progress_message'] = 'Complete'
    job.save_meta()

    return {'result': 'success'}
```

2. **Enqueue from backend**:

```python
from redis import Redis
from rq import Queue

redis_conn = Redis.from_url(settings.REDIS_URL)
queue = Queue('beatstitch:new_task', connection=redis_conn)

job = queue.enqueue(
    'app.tasks.new_task.process_something',
    project_id,
    options,
    job_timeout=300,  # 5 minutes
)
```

### Adding a New Frontend Component

1. **Create component** in `frontend/src/components/`:

```typescript
// components/feature/FeatureCard.tsx
import { FC } from 'react';

interface FeatureCardProps {
  id: string;
  name: string;
  onSelect: (id: string) => void;
}

export const FeatureCard: FC<FeatureCardProps> = ({ id, name, onSelect }) => {
  return (
    <div
      className="p-4 border rounded-lg cursor-pointer hover:bg-gray-50"
      onClick={() => onSelect(id)}
    >
      <h3 className="font-medium">{name}</h3>
    </div>
  );
};
```

2. **Add API client** in `frontend/src/api/`:

```typescript
// api/features.ts
import { apiClient } from './client';

export const featuresApi = {
  list: () => apiClient.get('/features'),
  create: (data: { name: string }) => apiClient.post('/features', data),
};
```

3. **Add hook** in `frontend/src/hooks/`:

```typescript
// hooks/useFeatures.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { featuresApi } from '@/api/features';

export function useFeatures() {
  return useQuery({
    queryKey: ['features'],
    queryFn: featuresApi.list,
  });
}

export function useCreateFeature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: featuresApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
    },
  });
}
```

## Database Migrations

### Creating a Migration

```bash
# Generate migration from model changes
docker-compose exec backend alembic revision --autogenerate -m "Add feature table"

# Or locally
cd backend
alembic revision --autogenerate -m "Add feature table"
```

### Running Migrations

```bash
# Apply all migrations
make migrate

# Or directly
docker-compose exec backend alembic upgrade head

# Rollback one migration
docker-compose exec backend alembic downgrade -1
```

### Migration Best Practices

- Always review auto-generated migrations
- Test migrations on a copy of production data
- Keep migrations backward-compatible when possible
- Add data migrations for schema changes that affect existing data

## Debugging Tips

### Backend Debugging

1. **Enable debug logging**:

```python
# In config.py or main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

2. **Use debugger**:

```python
# Insert breakpoint
import pdb; pdb.set_trace()

# Or with VS Code
import debugpy
debugpy.listen(5678)
debugpy.wait_for_client()
```

3. **Check request/response**:

```bash
# Watch backend logs
make logs-backend
```

### Worker Debugging

1. **Run worker in foreground**:

```bash
docker-compose exec worker python -m app.main
```

2. **Check job status in Redis**:

```bash
docker-compose exec redis redis-cli
> KEYS beatstitch:*
> HGETALL beatstitch:job:<job_id>
```

### Frontend Debugging

1. **Use React DevTools** (browser extension)

2. **Enable source maps** (already configured in Vite)

3. **Check network requests** in browser DevTools

### Common Issues

**"Connection refused" to Redis**:
- Check Redis is running: `docker-compose ps`
- Check Redis URL in environment

**"Database locked" error**:
- SQLite has single-writer limitation
- Consider using PostgreSQL for development if frequent

**FFmpeg errors**:
- Check FFmpeg is installed: `ffmpeg -version`
- Check file permissions on input files

## Common Development Tasks

### Resetting the Database

```bash
# Remove database and start fresh
docker-compose down -v
make dev
```

### Viewing Logs

```bash
# All logs
make logs

# Specific service
make logs-backend
make logs-worker
make logs-frontend
```

### Accessing Container Shell

```bash
# Backend
make shell-backend

# Worker
make shell-worker
```

### Rebuilding Containers

```bash
# Rebuild all
docker-compose build

# Rebuild specific service
docker-compose build backend
```

### Testing API with curl

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}' | jq -r '.access_token')

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/projects
```

### Testing API with httpie

```bash
# Install httpie
pip install httpie

# Login
http POST localhost:8080/api/auth/login username=test password=test123

# Make authenticated request
http GET localhost:8080/api/projects "Authorization: Bearer $TOKEN"
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `pytest` and `npm test`
5. Commit with clear message: `git commit -m "Add my feature"`
6. Push to your fork: `git push origin feature/my-feature`
7. Open a Pull Request

### Pull Request Guidelines

- Include tests for new functionality
- Update documentation as needed
- Follow code style guidelines
- Keep commits focused and atomic
- Write clear commit messages
