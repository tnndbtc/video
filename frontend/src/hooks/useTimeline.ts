import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { Timeline, TimelineStatus, GenerateTimelineResponse } from '../types/timeline';
import type { ProjectSettings } from '../types';

/**
 * Fetch the full timeline with segments for a project
 */
export function useTimeline(projectId: string) {
  return useQuery<Timeline>({
    queryKey: ['project', projectId, 'timeline'],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/timeline`);
      return data;
    },
    enabled: !!projectId,
    retry: false, // Don't retry 404s when timeline doesn't exist
  });
}

/**
 * Lightweight status polling for timeline generation
 */
export function useTimelineStatus(projectId: string) {
  return useQuery<TimelineStatus>({
    queryKey: ['project', projectId, 'timeline-status'],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/timeline/status`);
      return data;
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Poll every 2 seconds while generating
      if (data?.generation_status === 'queued' || data?.generation_status === 'generating') {
        return 2000;
      }
      return false;
    },
  });
}

/**
 * Generate or regenerate timeline for a project
 */
export function useGenerateTimeline(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<GenerateTimelineResponse>({
    mutationFn: async () => {
      const { data } = await api.post(`/projects/${projectId}/timeline/generate`);
      return data;
    },
    onSuccess: () => {
      // Invalidate both timeline and status to trigger refetch
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'timeline'] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'timeline-status'] });
    },
  });
}

/**
 * Update project settings (affects timeline generation)
 */
export function useUpdateSettings(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, Partial<ProjectSettings>>({
    mutationFn: async (settings: Partial<ProjectSettings>) => {
      const { data } = await api.patch(`/projects/${projectId}/settings`, settings);
      return data;
    },
    onSuccess: () => {
      // Invalidate project and timeline status (settings change may make timeline stale)
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'timeline-status'] });
    },
  });
}
