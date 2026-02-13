# BeatStitch - Architecture Design

> **Beat-Synced Video Stitching Web Application**
> Version: 1.0 (MVP)

---

## Document Index

| Document | Description | Size |
|----------|-------------|------|
| [01-overview.md](./01-overview.md) | Overview, architecture, tech stack, repo structure | ~18K |
| [02-data-models.md](./02-data-models.md) | Database schemas, EDL format, examples | ~15K |
| [03-api-endpoints.md](./03-api-endpoints.md) | REST API with request/response examples | ~18K |
| [04-processing.md](./04-processing.md) | Beat detection, timeline generation, rendering | ~20K |
| [05-infrastructure.md](./05-infrastructure.md) | Job queue, deployment, security, observability | ~20K |
| [06-roadmap.md](./06-roadmap.md) | Risks, mitigations, testing, Phase 2 roadmap | ~12K |

---

## Quick Reference

### Tech Stack Summary

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + Vite + TypeScript + Tailwind |
| Backend | FastAPI (Python 3.11+) |
| Database | SQLite (MVP) → PostgreSQL (Phase 2) |
| Queue | Redis + RQ |
| Beat Detection | madmom + librosa fallback |
| Rendering | ffmpeg CLI |
| Deployment | Docker Compose |

### Core User Workflow

```
Login → Create Project → Upload Media/Audio → Configure Settings
     → Auto-Build Timeline → Preview → Render Final → Download
```

### Key Design Principles

1. **Simplicity First** - iMovie-like ease of use
2. **Deterministic** - Same inputs = same outputs
3. **Self-Hosted** - Runs on user's Linux servers
4. **No AI Dependencies** - DSP-based beat detection, ffmpeg rendering
5. **Budget-Friendly** - All open-source, no paid APIs

### MVP Scope (~2 weeks)

- Single-user authentication
- Upload images, videos, audio
- Automatic beat detection (madmom/librosa)
- Auto-generate timeline synced to beats
- Ken Burns effect for images
- Cut/crossfade transitions
- Preview (fast, low-res) and Final (1080p) renders
- Background job queue for rendering
- Docker Compose deployment

### MVP Limits

- 50 media items per project
- 500MB max upload size
- 30-minute max render time
- Single server deployment
