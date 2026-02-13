import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { MediaAsset, MediaUploadResponse, AudioTrack, BeatsStatus, Project } from '../types/media';

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const { data } = await api.get<Project>(`/projects/${projectId}`);
      return data;
    },
    enabled: !!projectId,
  });
}

export function useProjectMedia(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId, 'media'],
    queryFn: async () => {
      const { data } = await api.get<Project>(`/projects/${projectId}`);
      return data.media_assets as MediaAsset[];
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      // Poll if any media is still processing
      const data = query.state.data;
      const hasProcessing = data?.some(
        (m) => m.processing_status === 'pending' || m.processing_status === 'processing'
      );
      return hasProcessing ? 3000 : false;
    },
  });
}

export function useUploadMedia(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (files: File[]) => {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));
      const { data } = await api.post<MediaUploadResponse>(
        `/projects/${projectId}/media`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'media'] });
    },
  });
}

export function useDeleteMedia(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (mediaId: string) => {
      await api.delete(`/media/${mediaId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'media'] });
    },
  });
}

export function useReorderMedia(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (order: string[]) => {
      const { data } = await api.post(`/projects/${projectId}/media/reorder`, { order });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'media'] });
    },
  });
}

// Audio hooks
export function useUploadAudio(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await api.post<AudioTrack>(`/projects/${projectId}/audio`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'beats-status'] });
    },
  });
}

export function useBeatsStatus(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId, 'beats-status'],
    queryFn: async () => {
      const { data } = await api.get<BeatsStatus>(`/projects/${projectId}/beats/status`);
      return data;
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Poll while analyzing
      return data?.analysis_status === 'processing' || data?.analysis_status === 'queued'
        ? 2000
        : false;
    },
  });
}
