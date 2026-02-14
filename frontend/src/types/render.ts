/**
 * Render-related TypeScript types for BeatStitch video editor
 */

export type RenderType = 'preview' | 'final';
export type RenderStatus = 'idle' | 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';

export interface RenderRequest {
  type: RenderType;
  rule_text?: string;  // Natural language rule (e.g., '8 beats', 'fast', '每4拍')
}

export interface RenderResponse {
  job_id: string;
  job_type: RenderType;
  status: string;
  edl_hash: string;
  created_at: string;
}

export interface RenderJobStatus {
  id?: string;
  project_id?: string;
  job_type?: RenderType;
  status: RenderStatus;
  edl_hash?: string;
  progress_percent: number;
  progress_message?: string;
  output_url?: string;
  file_size?: number;
  error?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}
