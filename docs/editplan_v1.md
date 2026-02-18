# EditPlan v1 Schema Reference

The EditPlan v1 schema defines how an AI planner (or manual input) describes a video
edit. It is validated and then converted to an EditRequest for the renderer.

## Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `plan_version` | `"v1"` | Yes | `"v1"` | Schema version identifier |
| `mode` | `"no_audio"` \| `"with_audio"` | No | `"no_audio"` | Whether audio track is included |
| `project_id` | string | Yes | - | UUID of the target project |
| `project_settings` | EditPlanProjectSettings | No | defaults | Output and transition settings |
| `timeline` | EditPlanTimeline | Yes | - | Timeline with segments |
| `notes` | string \| null | No | null | Free-form notes from the planner |
| `warnings` | string[] \| null | No | null | Planner warnings |

## EditPlanProjectSettings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_width` | int | 1920 | Output video width in pixels |
| `output_height` | int | 1080 | Output video height in pixels |
| `output_fps` | int | 30 | Frames per second |
| `transition_type` | `"cut"` \| `"crossfade"` | `"cut"` | Default transition type |
| `transition_duration_ms` | int (0-2000) | 500 | Default transition duration |
| `ken_burns_enabled` | bool | false | Enable Ken Burns effect on images |

## EditPlanTimeline

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `total_duration_ms` | int (>0) | Yes | Declared total duration (validated against segments) |
| `segments` | EditPlanSegment[] | Yes | At least 1 segment |

## EditPlanSegment

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `index` | int (>=0) | Yes | - | Contiguous 0-based index |
| `media_asset_id` | string | Yes | - | UUID of the media asset |
| `media_type` | `"image"` \| `"video"` \| `"audio"` | Yes | - | Asset type |
| `render_duration_ms` | int (>0) | Yes | - | How long this segment renders |
| `source_in_ms` | int (>=0) | No | 0 | Source start point |
| `source_out_ms` | int (>0) | Yes | - | Source end point (must be > source_in_ms) |
| `effects` | EditPlanSegmentEffects | No | {} | Segment effects |
| `transition_out` | EditPlanTransition \| null | No | null | Transition to next segment |

## EditPlanTransition

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `"cut"` \| `"crossfade"` | `"cut"` | Transition type |
| `duration_ms` | int (0-2000) | 500 | Transition duration |

## EditPlanSegmentEffects

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ken_burns` | EditPlanKenBurns \| null | null | Ken Burns pan/zoom settings |

## EditPlanKenBurns

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | bool | Yes | Whether effect is active |
| `zoom` | float \| null | No | Zoom factor (1.0-1.5) |
| `pan` | string \| null | No | Pan direction: left, right, up, down |

## Validation Rules

1. **Contiguous indices**: Segment indices must be 0, 1, 2, ..., N-1.
2. **Asset existence**: Every `media_asset_id` must exist in the project and have `processing_status == "ready"`.
3. **Source trim**: `source_out_ms > source_in_ms` for every segment.
4. **Total duration**:
   - For `cut` transitions: `total_duration_ms == sum(render_duration_ms)` (non-audio segments)
   - For `crossfade`: `total_duration_ms == sum - (N-1) * transition_duration_ms`
   - Tolerance: +/- 50ms

## JSON Example

```json
{
  "plan_version": "v1",
  "mode": "no_audio",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_settings": {
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30,
    "transition_type": "cut",
    "transition_duration_ms": 0,
    "ken_burns_enabled": false
  },
  "timeline": {
    "total_duration_ms": 4000,
    "segments": [
      {
        "index": 0,
        "media_asset_id": "asset-uuid-1",
        "media_type": "image",
        "render_duration_ms": 2000,
        "source_in_ms": 0,
        "source_out_ms": 2000,
        "effects": {},
        "transition_out": null
      },
      {
        "index": 1,
        "media_asset_id": "asset-uuid-2",
        "media_type": "image",
        "render_duration_ms": 2000,
        "source_in_ms": 0,
        "source_out_ms": 2000,
        "effects": {},
        "transition_out": null
      }
    ]
  },
  "notes": null,
  "warnings": null
}
```
