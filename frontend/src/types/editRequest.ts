/**
 * EditRequest v1 (EDL v1) TypeScript types for BeatStitch video editor.
 *
 * This module defines the user-authored JSON schema that fully defines a video edit
 * using only media assets, audio asset, and this JSON. Unlike the auto-generated EDL,
 * this is user input that drives the renderer.
 */

// =============================================================================
// Type Aliases and Literals
// =============================================================================

export type EffectPreset =
  | 'slow_zoom_in'
  | 'slow_zoom_out'
  | 'pan_left'
  | 'pan_right'
  | 'diagonal_push'
  | 'subtle_drift'
  | 'none';

export type TransitionType = 'cut' | 'crossfade';

export type RepeatMode = 'repeat_all' | 'repeat_last' | 'stop';

export type FillBehavior = 'black' | 'freeze_last';

// =============================================================================
// Duration Types (Discriminated Union)
// =============================================================================

/**
 * Duration specified in musical beats.
 * Actual duration = count × (60000/bpm) milliseconds.
 * Requires audio settings with BPM to be defined.
 */
export interface DurationBeats {
  mode: 'beats';
  /** Number of beats (1-64) */
  count: number;
}

/**
 * Duration specified in explicit milliseconds.
 */
export interface DurationMs {
  mode: 'ms';
  /** Duration in milliseconds (250-60000) */
  value: number;
}

/**
 * Natural duration based on asset type.
 * - Images: 4000ms default
 * - Videos: native duration of the source video
 */
export interface DurationNatural {
  mode: 'natural';
}

export type Duration = DurationBeats | DurationMs | DurationNatural;

// =============================================================================
// Component Types
// =============================================================================

/**
 * Video source trimming settings.
 * Defines in/out points for extracting a portion of a video asset.
 * Only applicable to video segments.
 */
export interface SourceTrim {
  /** Start time in source video (milliseconds) */
  in_ms?: number;
  /** End time in source video (milliseconds, undefined = end of video) */
  out_ms?: number;
}

/**
 * Transition settings between segments.
 */
export interface Transition {
  /** Transition type */
  type: TransitionType;
  /** Transition duration in milliseconds (0-2000) */
  duration_ms?: number;
}

/**
 * Output video settings.
 */
export interface OutputSettings {
  /** Output width in pixels (default: 1920) */
  width?: number;
  /** Output height in pixels (default: 1080) */
  height?: number;
  /** Frames per second (default: 30) */
  fps?: number;
}

/**
 * Audio track settings.
 */
export interface AudioSettings {
  /** UUID of the audio asset */
  asset_id: string;
  /** Override BPM (uses analyzed BPM if not set) */
  bpm?: number;
  /** Audio start offset in milliseconds */
  start_offset_ms?: number;
  /** End video when audio ends */
  end_at_audio_end?: boolean;
  /** Trim from end of audio in milliseconds */
  trim_end_ms?: number;
}

/**
 * Default settings applied to all segments unless overridden.
 */
export interface DefaultSettings {
  /** Default beats between cuts */
  beats_per_cut?: number;
  /** Default transition settings */
  transition?: Transition;
  /** Default motion effect preset */
  effect?: EffectPreset;
}

/**
 * Settings for handling timeline shorter than audio.
 */
export interface RepeatSettings {
  /** How to handle repeating timeline */
  mode?: RepeatMode;
  /** Fill behavior when mode=stop */
  fill_behavior?: FillBehavior;
}

// =============================================================================
// Timeline Segment Type
// =============================================================================

/**
 * Individual segment in the timeline.
 * Each segment represents a media asset (image or video) with its
 * duration, effects, and transition settings.
 */
export interface TimelineSegment {
  /** UUID of the media asset */
  asset_id: string;
  /** Type of media asset */
  type: 'image' | 'video';
  /** Segment duration (uses defaults if not set) */
  duration?: Duration;
  /** Motion effect preset */
  effect?: EffectPreset;
  /** Transition at start of segment */
  transition_in?: Transition;
  /** Video source trim settings (video only) */
  source?: SourceTrim;
}

// =============================================================================
// Main EditRequest Type
// =============================================================================

/**
 * EditRequest v1 - User-authored JSON schema for video editing.
 *
 * This schema fully defines a video edit using only media assets, audio asset,
 * and this JSON. It serves as user input that drives the video renderer.
 *
 * @example
 * ```typescript
 * const request: EditRequest = {
 *   version: '1.0',
 *   audio: { asset_id: 'audio_001', end_at_audio_end: true },
 *   defaults: { beats_per_cut: 8, effect: 'slow_zoom_in' },
 *   timeline: [
 *     { asset_id: 'img_001', type: 'image' },
 *     { asset_id: 'img_002', type: 'image' }
 *   ],
 *   repeat: { mode: 'repeat_all' }
 * };
 * ```
 */
export interface EditRequest {
  /** Schema version */
  version: '1.0';
  /** Optional project UUID to associate with */
  project_id?: string;
  /** Output video settings */
  output?: OutputSettings;
  /** Audio track settings */
  audio?: AudioSettings;
  /** Default segment settings */
  defaults?: DefaultSettings;
  /** List of timeline segments (required, at least 1) */
  timeline: TimelineSegment[];
  /** Timeline repeat settings */
  repeat?: RepeatSettings;
}

// =============================================================================
// Validation Result Types
// =============================================================================

/**
 * Details about a validation error or warning.
 */
export interface ValidationErrorDetail {
  /** Error code (e.g., 'asset_not_found', 'bpm_required') */
  code: string;
  /** Human-readable error message */
  message: string;
  /** JSON path to the problematic field */
  path?: string;
  /** Related asset ID if applicable */
  asset_id?: string;
}

/**
 * Computed information from a valid EditRequest.
 */
export interface ComputedInfo {
  /** Total timeline duration in milliseconds */
  total_duration_ms: number;
  /** Number of segments in timeline */
  segment_count: number;
  /** BPM used for beat calculations */
  effective_bpm?: number;
  /** Audio duration in milliseconds */
  audio_duration_ms?: number;
  /** Number of timeline loops needed */
  loop_count?: number;
}

/**
 * Result of validating an EditRequest.
 * Contains validation status, any errors/warnings, and computed metadata.
 */
export interface EditRequestValidationResult {
  /** Whether the EditRequest is valid */
  valid: boolean;
  /** Blocking errors that prevent processing */
  errors: ValidationErrorDetail[];
  /** Non-blocking warnings about potential issues */
  warnings: ValidationErrorDetail[];
  /** Computed metadata (only present if valid) */
  computed?: ComputedInfo;
}

/**
 * Response when saving an EditRequest.
 */
export interface EditRequestSaveResponse {
  /** Saved EditRequest UUID */
  id: string;
  /** SHA-256 hash of the EDL for cache validation */
  edl_hash: string;
  /** Validation result */
  validation: EditRequestValidationResult;
  /** ISO timestamp when saved */
  created_at: string;
}

// =============================================================================
// Helper Functions for Type Guards
// =============================================================================

/**
 * Type guard to check if a duration is beat-based.
 */
export function isDurationBeats(duration: Duration): duration is DurationBeats {
  return duration.mode === 'beats';
}

/**
 * Type guard to check if a duration is milliseconds-based.
 */
export function isDurationMs(duration: Duration): duration is DurationMs {
  return duration.mode === 'ms';
}

/**
 * Type guard to check if a duration is natural (asset-based).
 */
export function isDurationNatural(duration: Duration): duration is DurationNatural {
  return duration.mode === 'natural';
}

/**
 * Calculate duration in milliseconds from a Duration object.
 * @param duration - The duration specification
 * @param bpm - BPM for beat-based calculations (required for beats mode)
 * @param naturalDurationMs - Natural duration for the asset (required for natural mode)
 * @returns Duration in milliseconds
 * @throws Error if BPM is required but not provided
 */
export function calculateDurationMs(
  duration: Duration,
  bpm?: number,
  naturalDurationMs?: number
): number {
  switch (duration.mode) {
    case 'beats':
      if (!bpm) {
        throw new Error('BPM is required for beat-based duration calculation');
      }
      return Math.round(duration.count * (60000 / bpm));
    case 'ms':
      return duration.value;
    case 'natural':
      if (naturalDurationMs === undefined) {
        throw new Error('Natural duration is required for natural mode');
      }
      return naturalDurationMs;
  }
}
