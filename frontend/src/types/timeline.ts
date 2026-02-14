/**
 * Timeline-related TypeScript types for BeatStitch video editor
 */

export interface TimelineTransition {
  type: 'cut' | 'crossfade' | 'fade';
  duration_ms: number;
}

export interface KenBurnsEffect {
  start_zoom: number;
  end_zoom: number;
  pan_direction: string;
}

export interface TimelineEffects {
  ken_burns?: KenBurnsEffect;
}

export interface TimelineSegment {
  index: number;
  media_asset_id: string;
  media_type: 'image' | 'video';
  thumbnail_url?: string;
  timeline_in_ms: number;
  timeline_out_ms: number;
  render_duration_ms: number;
  source_in_ms: number;
  source_out_ms: number;
  effects: TimelineEffects;
  transition_in?: TimelineTransition | null;
  transition_out?: TimelineTransition | null;
}

export interface Timeline {
  id: string;
  edl_hash: string;
  segment_count: number;
  total_duration_ms: number;
  segments: TimelineSegment[];
  settings_used: {
    beats_per_cut: number;
    transition_type: string;
  };
  generated_at: string;
}

export interface TimelineStatus {
  project_id: string;
  generated: boolean;
  generation_status?: 'none' | 'queued' | 'generating' | 'ready' | 'failed';
  edl_hash?: string;
  segment_count?: number;
  total_duration_ms?: number;
  stale?: boolean;
  stale_reason?: string;
  progress_percent?: number;
  error_message?: string;
  generated_at?: string;
}

export interface GenerateTimelineResponse {
  job_id: string;
  message: string;
  status: string;
}

export interface SegmentDeleteResponse {
  success: boolean;
  deleted_index: number;
  new_segment_count: number;
  new_total_duration_ms: number;
  new_edl_hash: string;
}

/**
 * Preview segment for client-side beat-synced timeline preview.
 * Used before actual render to show calculated durations based on BPM.
 */
export interface PreviewSegment {
  media_id: string;
  thumbnail_url?: string;
  duration_ms: number;
  timeline_in_ms: number;
  timeline_out_ms: number;
}
