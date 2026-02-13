/**
 * Render-related TypeScript types for BeatStitch video editor
 */

export type RenderType = 'preview' | 'final';
export type RenderStatus = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';

export interface RenderRequest {
  type: RenderType;
  edl_hash: string;
}

export interface RenderResponse {
  job_id: string;
  job_type: RenderType;
  status: string;
  edl_hash: string;
  created_at: string;
}

export interface RenderJobStatus {
  id: string;
  project_id: string;
  job_type: RenderType;
  status: RenderStatus;
  edl_hash: string;
  progress_percent: number;
  progress_message?: string;
  output_url?: string;
  file_size?: number;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}
