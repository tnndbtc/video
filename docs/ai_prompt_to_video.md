# AI Prompt-to-Video: Endpoint Contract & Design

This document describes the API contract for the AI-powered prompt-to-video pipeline,
the EditPlan v1 JSON schema, and the overall design rationale.

## Table of Contents

- [Pipeline Overview](#pipeline-overview)
- [Endpoint Contract](#endpoint-contract)
- [EditPlan v1 Schema](#editplan-v1-schema)
- [Audio Modes](#audio-modes)
- [Validation Rules](#validation-rules)
- [Error Handling](#error-handling)

---

## Pipeline Overview

```
POST /api/ai/plan   →   EditPlan JSON (validated)
         ↓
POST /api/ai/apply  →   Timeline saved to project
         ↓
POST /api/projects/{id}/render  →   Render job queued
         ↓
GET  /api/projects/{id}/render/final/status  →   Poll until complete
         ↓
GET  /api/projects/{id}/render/final/download  →   Download MP4
```

The AI Planner (OpenAI) is called **only** in `POST /api/ai/plan`. The result is a
validated EditPlan JSON. Subsequent steps are deterministic and do not call the LLM again.

---

## Endpoint Contract

### `POST /api/ai/plan`

Generate an EditPlan from a prompt and a project's media assets.

**Authentication:** Bearer token required.

**Request body:**

```json
{
  "project_id": "uuid-of-project",
  "prompt": "Energetic montage of the hike, cut every beat, crossfade transitions",
  "constraints": {
    "mode": "no_audio",
    "target_duration_seconds": 60,
    "transition_type": "crossfade",
    "max_clips": 20
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | string (UUID) | ✅ | Project whose media assets will be used |
| `prompt` | string | ✅ | Natural-language description of the desired video |
| `constraints.mode` | `"no_audio"` \| `"with_audio"` | — | Default: `"no_audio"` |
| `constraints.target_duration_seconds` | integer | — | Approximate target length |
| `constraints.transition_type` | `"cut"` \| `"crossfade"` | — | Default: `"cut"` |
| `constraints.max_clips` | integer | — | Maximum number of clips to include |

**Response `200 OK`:**

```json
{
  "edit_plan": { /* EditPlan v1 JSON - see schema below */ },
  "warnings": [],
  "model": "gpt-4o",
  "prompt_tokens": 312,
  "completion_tokens": 580
}
```

**Error `503`** — OpenAI API key not configured:

```json
{
  "error": "openai_not_configured",
  "message": "OPENAI_API_KEY is not set. Set it in .env to enable AI planning.",
  "stub_plan": { /* a sample EditPlan for UI testing */ }
}
```

**Error `422`** — Validation failed (plan produced by LLM is invalid):

```json
{
  "error": "edit_plan_invalid",
  "message": "AI-generated plan failed validation",
  "validation": {
    "valid": false,
    "errors": ["Segment 2 references unknown media_id abc123"]
  }
}
```

---

### `POST /api/ai/apply`

Save an EditPlan to a project, replacing the existing timeline.

**Authentication:** Bearer token required.

**Request body:**

```json
{
  "project_id": "uuid-of-project",
  "edit_plan": { /* EditPlan v1 JSON */ }
}
```

**Response `200 OK`:**

```json
{
  "saved": true,
  "edl_path": "derived/uuid/edit_request.json",
  "segment_count": 12,
  "total_duration_ms": 58400
}
```

This internally calls the existing `POST /api/projects/{id}/edl/save` endpoint and
validates the plan before writing it to disk.

---

### Render Endpoints (existing, unchanged)

Use the existing render endpoints after applying a plan:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/projects/{id}/render` | Start render job (`{"type": "final"}`) |
| `GET` | `/api/projects/{id}/render/final/status` | Poll render status |
| `GET` | `/api/projects/{id}/render/final/download` | Download rendered MP4 |

---

## EditPlan v1 Schema

The EditPlan follows the existing **EditRequest v1** format used by the backend EDL system.

### Top-Level Structure

```json
{
  "version": "1.0",
  "output": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "format": "mp4"
  },
  "audio": {
    "source": "project_audio",
    "mode": "no_audio"
  },
  "defaults": {
    "transition": { "type": "cut" },
    "effects": { "ken_burns": true }
  },
  "timeline": [
    {
      "media_id": "uuid-of-media-asset",
      "duration": { "seconds": 3.0 },
      "transition": { "type": "crossfade", "duration_ms": 500 },
      "trim": { "start_ms": 0, "end_ms": 3000 }
    }
  ]
}
```

### `output` object

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | integer | 1920 | Output width in pixels |
| `height` | integer | 1080 | Output height in pixels |
| `fps` | integer | 30 | Output frame rate |
| `format` | string | `"mp4"` | Container format |

### `audio` object

| Field | Type | Description |
|-------|------|-------------|
| `source` | `"project_audio"` \| `"none"` | Audio source |
| `mode` | `"no_audio"` \| `"with_audio"` | Whether to include audio in output |

### `defaults` object

Applied to all timeline segments unless overridden per-segment.

| Field | Type | Description |
|-------|------|-------------|
| `transition.type` | `"cut"` \| `"crossfade"` | Default transition between segments |
| `transition.duration_ms` | integer | Crossfade duration in ms (default: 500) |
| `effects.ken_burns` | boolean | Apply Ken Burns pan/zoom to images |

### `timeline` array

Each element is a **segment**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `media_id` | string (UUID) | ✅ | ID of a `MediaAsset` in the project |
| `duration` | Duration object | ✅ | How long to show this clip |
| `transition` | Transition object | — | Override default transition for this segment |
| `trim` | SourceTrim object | — | Trim source video to this range |
| `effects` | Effects object | — | Per-segment effect overrides |

### Duration variants

```json
{ "seconds": 3.0 }          // Fixed seconds
{ "ms": 3000 }               // Fixed milliseconds
{ "beats": 4, "bpm": 120 }  // Beat-relative (requires audio)
{ "natural": true }          // Use natural clip duration (videos only)
```

---

## Audio Modes

| Mode | Description |
|------|-------------|
| `no_audio` | (Default) Render video only, no audio track in output |
| `with_audio` | Mix project audio track into the rendered video |

When `mode = "with_audio"`, the project must have an analyzed audio track
(`POST /api/projects/{id}/audio` + beat analysis complete).

---

## Validation Rules

The backend validates every EditPlan before saving or rendering:

1. **All `media_id` values must exist** in the project and be in `processing_status = "ready"`.
2. **Duration must be positive** and non-zero for every segment.
3. **Beat-relative durations** require an analyzed audio track with known BPM.
4. **`trim.end_ms` must be <= source clip duration** for video assets.
5. **Crossfade transitions** require `duration_ms > 0`.
6. **Total timeline duration** must be > 0.

---

## Error Handling

| HTTP Status | `error` value | Meaning |
|-------------|---------------|---------|
| 400 | `edit_plan_invalid` | Plan failed backend validation |
| 404 | `project_not_found` | Project ID does not exist or not owned by caller |
| 422 | `validation_error` | Request body is malformed |
| 503 | `openai_not_configured` | `OPENAI_API_KEY` not set |
| 500 | `internal_error` | Unexpected server error |

---

## Contract & Validation

**EditPlanV1 is a strict contract.** All AI-generated and stub plans are validated against
the `EditPlanV1` Pydantic schema immediately after generation and again before apply.
Invalid plans are rejected (HTTP 422/400) before any timeline or EDL write occurs.
The backend API runs on port **8080**; the UI runs on port **3001**.

Run contract tests with:

```bash
bash scripts/validate_ai_contract.sh
```

### E2E Round-Trip Mode

When `OPENAI_API_KEY` is set (or `RUN_OPENAI_ROUNDTRIP=1`), the script also exercises the
full live pipeline against a running backend:

```bash
# Contract tests only (no server required):
./scripts/validate_ai_contract.sh

# Full E2E with real OpenAI (requires running backend + render worker):
OPENAI_API_KEY=sk-... ./scripts/validate_ai_contract.sh

# Full E2E with stub planner (no OpenAI key required):
RUN_OPENAI_ROUNDTRIP=1 ./scripts/validate_ai_contract.sh

# Override API base URL (default: http://localhost:8080):
API_BASE_URL=http://localhost:8080 PROMPT="Short montage" \
  OPENAI_API_KEY=sk-... ./scripts/validate_ai_contract.sh
```

Artifacts are saved to `/tmp/video_validate/` (plan.json, output.mp4).
