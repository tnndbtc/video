export type ProcessingStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type MediaType = 'image' | 'video';

export interface MediaAsset {
  id: string;
  project_id: string;
  filename: string;
  original_filename: string;
  media_type: MediaType;
  processing_status: ProcessingStatus;
  processing_error?: string;
  width?: number;
  height?: number;
  duration_ms?: number;
  fps?: number;
  file_size: number;
  thumbnail_url?: string;
  sort_order: number;
  created_at: string;
  processed_at?: string;
}

export interface AudioTrack {
  id: string;
  filename: string;
  duration_ms: number;
  sample_rate?: number;
  bpm?: number;
  analysis_status: 'queued' | 'processing' | 'complete' | 'failed';
  analysis_error?: string;
}

export interface MediaUploadResponse {
  uploaded: MediaAsset[];
  failed: { filename: string; error: string }[];
  total_uploaded: number;
}

export interface BeatsStatus {
  has_audio: boolean;
  analysis_status?: 'queued' | 'processing' | 'complete' | 'failed';
  analysis_error?: string;
  beat_count?: number;
  bpm?: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  media_assets: MediaAsset[];
  audio_track?: AudioTrack | null;
  created_at: string;
  updated_at: string;
}
