export interface User {
  id: string;
  username: string;
}

export interface ProjectSettings {
  beats_per_cut: number;
  transition_type: 'cut' | 'crossfade' | 'fade';
  transition_duration_ms: number;
  ken_burns_enabled: boolean;
  output_width: number;
  output_height: number;
  output_fps: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  status: string;
  settings: ProjectSettings;
  media_count: number;
  has_audio: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  description?: string;
  status: string;
  media_count: number;
  has_audio: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectData {
  name: string;
  description?: string;
  timeline_media_ids?: string[];
  video_length_seconds?: number;
  rule_text?: string;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterCredentials {
  username: string;
  password: string;
}

// Re-export timeline types
export type {
  TimelineTransition,
  KenBurnsEffect,
  TimelineEffects,
  TimelineSegment,
  Timeline,
  TimelineStatus,
  GenerateTimelineResponse,
} from './timeline';

// Re-export EditRequest (EDL v1) types
export type {
  EffectPreset,
  TransitionType,
  RepeatMode,
  FillBehavior,
  DurationBeats,
  DurationMs,
  DurationNatural,
  Duration,
  SourceTrim,
  Transition,
  OutputSettings,
  AudioSettings,
  DefaultSettings,
  RepeatSettings,
  TimelineSegment as EditRequestTimelineSegment,
  EditRequest,
  ValidationErrorDetail,
  ComputedInfo,
  EditRequestValidationResult,
  EditRequestSaveResponse,
} from './editRequest';

export {
  isDurationBeats,
  isDurationMs,
  isDurationNatural,
  calculateDurationMs,
} from './editRequest';
