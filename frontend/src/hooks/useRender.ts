/**
 * React Query hooks for render operations in BeatStitch video editor
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { API_BASE_URL } from '../config';
import type { RenderType, RenderResponse, RenderJobStatus } from '../types/render';

/**
 * Hook to start a new render job
 */
export function useStartRender(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ type, edlHash }: { type: RenderType; edlHash: string }) => {
      const { data } = await api.post<RenderResponse>(`/projects/${projectId}/render`, {
        type,
        edl_hash: edlHash,
      });
      return data;
    },
    onSuccess: (data) => {
      // Invalidate the render status query for this type to trigger refetch
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'render', data.job_type],
      });
    },
  });
}

/**
 * Hook to get the latest render status by type (preview or final)
 */
export function useRenderStatus(projectId: string, renderType: RenderType) {
  return useQuery({
    queryKey: ['project', projectId, 'render', renderType],
    queryFn: async () => {
      const { data } = await api.get<RenderJobStatus>(
        `/projects/${projectId}/render/${renderType}/status`
      );
      return data;
    },
    refetchInterval: (query) => {
      // Poll while queued or running
      const data = query.state.data;
      return data?.status === 'queued' || data?.status === 'running' ? 2000 : false;
    },
  });
}

/**
 * Hook to get render status by specific job ID
 */
export function useRenderJobStatus(projectId: string, jobId: string | null) {
  return useQuery({
    queryKey: ['project', projectId, 'render', 'job', jobId],
    queryFn: async () => {
      if (!jobId) return null;
      const { data } = await api.get<RenderJobStatus>(
        `/projects/${projectId}/render/${jobId}/status`
      );
      return data;
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === 'queued' || data?.status === 'running' ? 2000 : false;
    },
  });
}

/**
 * Helper to get the download URL for a rendered video
 */
export function getDownloadUrl(projectId: string, renderType: RenderType): string {
  return `${API_BASE_URL}/projects/${projectId}/render/${renderType}/download`;
}

/**
 * Error types for render operations
 */
export interface RenderError {
  status: number;
  message: string;
  isEdlMismatch: boolean;
  isTimelineNotReady: boolean;
  isRenderInProgress: boolean;
}

/**
 * Parse API error into RenderError
 */
export function parseRenderError(error: unknown): RenderError {
  const axiosError = error as {
    response?: {
      status: number;
      data?: {
        detail?: string | { error?: string; message?: string };
        message?: string
      }
    };
    message?: string;
  };

  const status = axiosError.response?.status || 0;
  const detail = axiosError.response?.data?.detail;

  // Handle detail being either a string or an object with message field
  let message: string;
  if (typeof detail === 'string') {
    message = detail;
  } else if (detail && typeof detail === 'object' && 'message' in detail) {
    message = detail.message || 'An unknown error occurred';
  } else {
    message = axiosError.response?.data?.message || axiosError.message || 'An unknown error occurred';
  }

  // Check error type from detail object if available
  const errorType = typeof detail === 'object' && detail ? (detail as { error?: string }).error : '';

  return {
    status,
    message,
    isEdlMismatch: status === 409 && (errorType === 'edl_hash_mismatch' || message.toLowerCase().includes('edl')),
    isTimelineNotReady: status === 400 && message.toLowerCase().includes('timeline'),
    isRenderInProgress: status === 409 && (errorType === 'conflict' || message.toLowerCase().includes('progress')),
  };
}
