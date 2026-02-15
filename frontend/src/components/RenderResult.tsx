/**
 * RenderResult - Display completed render result with download option
 */

import { useState, useEffect, useCallback } from 'react';
import { formatFileSize, formatRelativeTime } from '../utils/formatSize';
import { getDownloadUrl } from '../hooks/useRender';
import type { RenderType, RenderJobStatus } from '../types/render';

export interface RenderResultProps {
  projectId: string;
  renderType: RenderType;
  status: RenderJobStatus;
  onRerender: () => void;
}

export function RenderResult({
  projectId,
  renderType,
  status,
  onRerender,
}: RenderResultProps) {
  const downloadUrl = getDownloadUrl(projectId, renderType);
  const [videoBlobUrl, setVideoBlobUrl] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [videoError, setVideoError] = useState<string | null>(null);

  // Fetch video with auth for playback (both preview and final)
  // Use completed_at as cache-buster to ensure we get the latest video
  useEffect(() => {
    if (!status.output_url) return;

    const token = localStorage.getItem('token');
    let cancelled = false;

    // Clear current video to show loading state
    setVideoBlobUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });

    const fetchVideo = async () => {
      try {
        setVideoError(null);
        // Add cache-busting timestamp to force fresh fetch
        const cacheBuster = status.completed_at ? `?t=${new Date(status.completed_at).getTime()}` : '';
        const response = await fetch(`${downloadUrl}${cacheBuster}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const blob = await response.blob();
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          setVideoBlobUrl(url);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to load video preview:', err);
          setVideoError('Failed to load video preview');
        }
      }
    };

    fetchVideo();

    // Cleanup on unmount or when deps change
    return () => {
      cancelled = true;
    };
  }, [status.output_url, status.completed_at, downloadUrl]);

  // Cleanup blob URL when it changes or component unmounts
  useEffect(() => {
    return () => {
      if (videoBlobUrl) {
        URL.revokeObjectURL(videoBlobUrl);
      }
    };
  }, [videoBlobUrl]);

  // Handle download with auth headers
  const handleDownload = useCallback(async () => {
    const token = localStorage.getItem('token');
    setIsDownloading(true);

    try {
      const response = await fetch(downloadUrl, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${renderType}_render.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Download failed: ' + err);
    } finally {
      setIsDownloading(false);
    }
  }, [downloadUrl, renderType]);

  return (
    <div className="space-y-3">
      {/* Success header */}
      <div className="flex items-center gap-2 text-green-400">
        <svg
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span className="font-medium">Render Complete</span>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-400">
        {status.file_size && (
          <span className="flex items-center gap-1">
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            {formatFileSize(status.file_size)}
          </span>
        )}
        {status.completed_at && (
          <span className="flex items-center gap-1">
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            {formatRelativeTime(status.completed_at)}
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        {/* Download button - uses fetch with auth headers */}
        <button
          type="button"
          onClick={handleDownload}
          disabled={isDownloading}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-green-600 to-green-500 hover:from-green-500 hover:to-green-400 disabled:from-green-600/50 disabled:to-green-500/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all duration-200 shadow-lg shadow-green-900/30"
        >
          {isDownloading ? (
            <svg
              className="animate-spin h-5 w-5"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          ) : (
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
          )}
          <span>
            {isDownloading ? 'Downloading...' : 'Download'}
            {status.file_size && !isDownloading && (
              <span className="ml-1 text-green-100/80">
                ({formatFileSize(status.file_size)})
              </span>
            )}
          </span>
        </button>

        {/* Re-render button */}
        <button
          type="button"
          onClick={onRerender}
          className="px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg transition-colors flex items-center gap-2"
          title="Re-render with current timeline"
        >
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          <span className="sr-only sm:not-sr-only">Re-render</span>
        </button>
      </div>

      {/* Video preview for both preview and final renders */}
      {status.output_url && (
        <div className="mt-3 rounded-lg overflow-hidden bg-black aspect-video">
          {videoError ? (
            <div className="w-full h-full flex items-center justify-center text-red-400 text-sm">
              {videoError}
            </div>
          ) : videoBlobUrl ? (
            <video
              src={videoBlobUrl}
              controls
              className="w-full h-full"
              preload="metadata"
            >
              Your browser does not support the video tag.
            </video>
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400">
              <svg
                className="animate-spin h-8 w-8"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
