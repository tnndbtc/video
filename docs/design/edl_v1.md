# EditRequest v1 (EDL v1) Design Document

## Overview

EditRequest v1 is a user-authored JSON schema that fully defines a video edit using only media assets, audio asset, and this JSON. Unlike the auto-generated EDL, this is **user input** that drives the renderer directly.

### Goals

1. **User Control**: Allow users to define precise video edits through a structured JSON schema
2. **Flexibility**: Support both beat-synced and explicit timing modes
3. **Validation**: Provide comprehensive validation with clear error messages
4. **Compatibility**: Work alongside existing auto-generated timeline workflow

### Non-Goals

- Replace the existing auto-generated timeline (it remains available)
- Support real-time editing (this is a declarative specification)
- Include complex effects beyond motion presets

---

## JSON Schema

### Complete Example

```json
{
  "version": "1.0",
  "project_id": "uuid (optional)",
  "output": {
    "width": 1920,
    "height": 1080,
    "fps": 30
  },
  "audio": {
    "asset_id": "audio_001",
    "bpm": 120.0,
    "start_offset_ms": 0,
    "end_at_audio_end": true,
    "trim_end_ms": 0
  },
  "defaults": {
    "beats_per_cut": 8,
    "transition": { "type": "cut", "duration_ms": 0 },
    "effect": "slow_zoom_in"
  },
  "timeline": [
    {
      "asset_id": "img_001",
      "type": "image",
      "duration": { "mode": "beats", "count": 8 },
      "effect": "pan_left",
      "transition_in": { "type": "crossfade", "duration_ms": 300 }
    },
    {
      "asset_id": "vid_001",
      "type": "video",
      "duration": { "mode": "ms", "value": 16000 },
      "source": { "in_ms": 5000, "out_ms": 21000 }
    }
  ],
  "repeat": {
    "mode": "repeat_all",
    "fill_behavior": "black"
  }
}
```

---

## Schema Fields

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `"1.0"` | Yes | Schema version (always "1.0") |
| `project_id` | `string` | No | Optional project UUID to associate with |
| `output` | `OutputSettings` | No | Output video settings (defaults to 1920x1080@30fps) |
| `audio` | `AudioSettings` | No | Audio track settings |
| `defaults` | `DefaultSettings` | No | Default settings for all segments |
| `timeline` | `TimelineSegment[]` | Yes | List of timeline segments (min 1) |
| `repeat` | `RepeatSettings` | No | Timeline repeat settings |

### OutputSettings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | `int` | 1920 | Output width in pixels (320-7680) |
| `height` | `int` | 1080 | Output height in pixels (240-4320) |
| `fps` | `int` | 30 | Frames per second (15-120) |

### AudioSettings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | `string` | - | UUID of the audio asset (required) |
| `bpm` | `float` | null | Override BPM (uses analyzed BPM if not set) |
| `start_offset_ms` | `int` | 0 | Audio start offset in milliseconds |
| `end_at_audio_end` | `bool` | true | End video when audio ends |
| `trim_end_ms` | `int` | 0 | Trim from end of audio in milliseconds |

### DefaultSettings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `beats_per_cut` | `int` | 8 | Default beats between cuts (1-64) |
| `transition` | `Transition` | cut, 0ms | Default transition settings |
| `effect` | `EffectPreset` | null | Default motion effect preset |

### TimelineSegment

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_id` | `string` | Yes | UUID of the media asset |
| `type` | `"image" \| "video"` | Yes | Type of media asset |
| `duration` | `Duration` | No | Segment duration (uses defaults if not set) |
| `effect` | `EffectPreset` | No | Motion effect preset |
| `transition_in` | `Transition` | No | Transition at start of segment |
| `source` | `SourceTrim` | No | Video source trim settings (video only) |

### RepeatSettings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `RepeatMode` | "repeat_all" | How to handle repeating timeline |
| `fill_behavior` | `FillBehavior` | "black" | Fill behavior when mode=stop |

---

## Duration Modes

Duration is specified using a discriminated union based on the `mode` field:

| Mode | Fields | Description |
|------|--------|-------------|
| `beats` | `count: 1-64` | Duration = count × (60000/bpm) ms |
| `ms` | `value: 250-60000` | Explicit milliseconds |
| `natural` | (none) | Images: 4000ms, Videos: native duration |

### Examples

```json
// 8 beats at 120 BPM = 4000ms
{ "mode": "beats", "count": 8 }

// Explicit 3 seconds
{ "mode": "ms", "value": 3000 }

// Use natural duration
{ "mode": "natural" }
```

---

## Effect Presets

Available motion effect presets:

| Preset | Description |
|--------|-------------|
| `slow_zoom_in` | Slow zoom in effect |
| `slow_zoom_out` | Slow zoom out effect |
| `pan_left` | Pan from right to left |
| `pan_right` | Pan from left to right |
| `diagonal_push` | Diagonal push effect |
| `subtle_drift` | Subtle drift/movement |
| `none` | No motion effect |

---

## Transitions

| Type | Duration | Description |
|------|----------|-------------|
| `cut` | 0 (ignored) | Hard cut between segments |
| `crossfade` | 0-2000ms | Crossfade/dissolve transition |

---

## Repeat Modes

| Mode | Description |
|------|-------------|
| `repeat_all` | Loop entire timeline until audio ends |
| `repeat_last` | Play timeline once, then hold last frame |
| `stop` | Play timeline once, then use fill_behavior |

### Fill Behaviors (for mode=stop)

| Behavior | Description |
|----------|-------------|
| `black` | Show black screen after timeline ends |
| `freeze_last` | Freeze on last frame |

---

## Validation Rules

The validator checks the following rules:

| Rule | Error Code | Message |
|------|------------|---------|
| Asset exists | `asset_not_found` | Asset '{id}' not found |
| Asset type matches | `asset_type_mismatch` | Asset '{id}' is {actual}, not {expected} |
| BPM available for beats mode | `bpm_required` | Audio settings required for beats-based duration |
| Audio analyzed (if no bpm override) | `audio_not_analyzed` | BPM required. Set audio.bpm or wait for analysis |
| Beats count 1-64 | `duration_out_of_range` | Beats count must be 1-64 |
| Ms value 250-60000 | `duration_out_of_range` | Duration must be 250-60000ms |
| source.out > source.in | `source_trim_invalid` | out_ms must be > in_ms |
| source within video duration | `source_trim_invalid` | source.in_ms exceeds video duration |

### Warnings (Non-Blocking)

| Rule | Warning Code | Message |
|------|--------------|---------|
| Transition ≤ 50% segment | `transition_too_long` | Transition exceeds 50% of segment |
| Timeline vs audio alignment | `timeline_shorter_than_audio` | Timeline shorter than audio with mode=stop |
| Audio analysis in progress | `audio_analyzing` | Audio analysis in progress. BPM may change. |

---

## API Endpoints

### POST `/api/projects/{project_id}/edl/validate`

Validates EditRequest without saving. Returns validation result with errors, warnings, and computed metadata.

**Request Body**: `EditRequest`

**Response**: `EditRequestValidationResult`

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "computed": {
    "total_duration_ms": 24000,
    "segment_count": 3,
    "effective_bpm": 120.0,
    "audio_duration_ms": 180000,
    "loop_count": 8
  }
}
```

### POST `/api/projects/{project_id}/edl/save`

Validates and saves EditRequest. Returns saved EDL with computed hash.

**Request Body**: `EditRequest`

**Response** (201 Created): `EditRequestSaveResponse`

```json
{
  "id": "uuid",
  "edl_hash": "sha256...",
  "validation": { ... },
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Error** (400 Bad Request): When validation fails

```json
{
  "error": "validation_failed",
  "message": "EditRequest validation failed",
  "validation": { "valid": false, "errors": [...] }
}
```

### GET `/api/projects/{project_id}/edl`

Retrieve the currently saved EditRequest for a project.

**Response** (200 OK): `EditRequest` or `null` (204 No Content)

### DELETE `/api/projects/{project_id}/edl`

Delete the saved EditRequest for a project.

**Response**: 204 No Content

---

## File Locations

| File | Description |
|------|-------------|
| `backend/app/schemas/edit_request.py` | Pydantic models |
| `frontend/src/types/editRequest.ts` | TypeScript types |
| `backend/app/services/edit_request_validator.py` | Validation service |
| `backend/app/api/edit_request.py` | API endpoints |
| `backend/tests/fixtures/edit_request_*.json` | Example JSON fixtures |

---

## Usage Examples

### Example A: Simple Loop

A basic slideshow that loops with beat-synced cuts:

```json
{
  "version": "1.0",
  "audio": { "asset_id": "audio_001", "end_at_audio_end": true },
  "defaults": { "beats_per_cut": 8, "effect": "slow_zoom_in" },
  "timeline": [
    { "asset_id": "img_001", "type": "image" },
    { "asset_id": "img_002", "type": "image" },
    { "asset_id": "vid_001", "type": "video", "duration": { "mode": "beats", "count": 16 } }
  ],
  "repeat": { "mode": "repeat_all" }
}
```

### Example B: Per-Segment Overrides

Different durations and effects per segment:

```json
{
  "version": "1.0",
  "audio": { "asset_id": "audio_001", "bpm": 120.0 },
  "defaults": { "beats_per_cut": 8, "transition": { "type": "crossfade", "duration_ms": 300 } },
  "timeline": [
    { "asset_id": "img_001", "type": "image", "duration": { "mode": "beats", "count": 4 }, "effect": "pan_left" },
    { "asset_id": "img_002", "type": "image", "duration": { "mode": "beats", "count": 16 } },
    { "asset_id": "img_003", "type": "image", "duration": { "mode": "ms", "value": 3000 } }
  ],
  "repeat": { "mode": "repeat_last" }
}
```

### Example C: Mixed with Video Trimming

Using video clips with in/out points:

```json
{
  "version": "1.0",
  "audio": { "asset_id": "audio_001", "bpm": 128.0, "start_offset_ms": 500, "trim_end_ms": 1000 },
  "defaults": { "beats_per_cut": 8, "transition": { "type": "crossfade", "duration_ms": 500 } },
  "timeline": [
    { "asset_id": "img_001", "type": "image", "transition_in": { "type": "cut" } },
    { "asset_id": "vid_001", "type": "video", "duration": { "mode": "ms", "value": 16000 }, "source": { "in_ms": 5000, "out_ms": 21000 } },
    { "asset_id": "vid_002", "type": "video", "duration": { "mode": "natural" }, "source": { "in_ms": 0, "out_ms": 10000 } }
  ],
  "repeat": { "mode": "stop", "fill_behavior": "black" }
}
```

---

## Implementation Notes

### Validation Flow

1. Parse JSON into `EditRequest` model (Pydantic validation)
2. Prefetch all referenced assets from database
3. Determine effective BPM (override > analyzed > None)
4. Validate each segment:
   - Asset existence
   - Asset type matching
   - Source trim validity (videos only)
   - Duration calculation
5. Check timeline vs audio alignment
6. Compute metadata if valid

### EDL Hash

The EDL hash is a SHA-256 of the normalized JSON (excluding None values, sorted keys). This hash is used for:

- Cache validation
- Detecting when render needs to be re-run
- Deduplication

### Integration with Render

The render endpoint can accept an optional `edit_request` field. When provided:

1. The EditRequest is validated
2. The EditRequest is converted to internal EDL format
3. Rendering proceeds using the specified timeline

When not provided, the existing auto-generated timeline is used.

---

## Future Considerations

- Support for custom effects (not just presets)
- Support for keyframed motion
- Support for multiple audio tracks
- Support for text overlays
- Version migration (1.0 → 2.0)
