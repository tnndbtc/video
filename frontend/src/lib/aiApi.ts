import { api } from './api';

export interface EditPlanV1 {
  plan_version: "v1";
  mode: "no_audio" | "with_audio";
  project_id: string;
  project_settings: {
    output_width: number;
    output_height: number;
    output_fps: number;
    transition_type: "cut" | "crossfade";
    transition_duration_ms: number;
    ken_burns_enabled: boolean;
  };
  timeline: {
    total_duration_ms: number;
    segments: Array<{
      index: number;
      media_asset_id: string;
      media_type: "image" | "video" | "audio";
      render_duration_ms: number;
      source_in_ms: number;
      source_out_ms: number;
      effects?: {
        ken_burns?: { enabled: boolean; zoom?: number; pan?: string } | null;
      };
      transition_out?: { type: "cut" | "crossfade"; duration_ms: number } | null;
    }>;
  };
  notes?: string | null;
  warnings?: string[] | null;
}

export interface PlanResponse {
  edit_plan: EditPlanV1;
  warnings: string[];
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
}

export interface ApplyResponse {
  ok: boolean;
  edl_hash: string;
  segment_count: number;
  total_duration_ms: number;
}

export interface RenderJobStatus {
  status: "idle" | "queued" | "running" | "complete" | "failed" | "cancelled";
  progress_percent?: number;
  progress_message?: string;
  output_url?: string;
  id?: string;
  job_type?: string;
}

export const generatePlan = async (
  projectId: string,
  prompt: string,
  constraints?: {
    mode?: "no_audio" | "with_audio";
    transition_type?: "cut" | "crossfade";
    target_duration_ms?: number;
  }
): Promise<PlanResponse> => {
  const response = await api.post('/ai/plan', {
    project_id: projectId,
    prompt,
    mode: constraints?.mode ?? "no_audio",
    constraints,
  });
  return response.data;
};

export const applyPlan = async (
  projectId: string,
  editPlan: EditPlanV1
): Promise<ApplyResponse> => {
  const response = await api.post('/ai/apply', {
    project_id: projectId,
    edit_plan: editPlan,
  });
  return response.data;
};

export const startRender = async (
  projectId: string
): Promise<{ job_id: string; status: string }> => {
  const response = await api.post(`/projects/${projectId}/render`, {
    type: "final",
  });
  return response.data;
};

export const getRenderStatus = async (
  projectId: string,
  jobType: string = "final"
): Promise<RenderJobStatus> => {
  const response = await api.get(`/projects/${projectId}/render/${jobType}/status`);
  return response.data;
};

export const planAndApply = async (
  projectId: string,
  prompt: string,
  constraints?: {
    mode?: "no_audio" | "with_audio";
    transition_type?: "cut" | "crossfade";
    target_duration_ms?: number;
  }
): Promise<{
  ok: boolean;
  edit_plan: EditPlanV1;
  edl_hash: string;
  segment_count: number;
  total_duration_ms: number;
  warnings: string[];
}> => {
  const response = await api.post('/ai/plan_and_apply', {
    project_id: projectId,
    prompt,
    mode: constraints?.mode ?? "no_audio",
    constraints,
  });
  return response.data;
};

export const getRenderDownloadUrl = (projectId: string): string => {
  return `/api/projects/${projectId}/render/final/download`;
};
