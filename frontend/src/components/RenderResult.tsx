/**
 * RenderResult - Display completed render result with download option
 */

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
        {/* Download button */}
        <a
          href={downloadUrl}
          download
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-green-600 to-green-500 hover:from-green-500 hover:to-green-400 text-white font-medium rounded-lg transition-all duration-200 shadow-lg shadow-green-900/30"
        >
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
          <span>
            Download
            {status.file_size && (
              <span className="ml-1 text-green-100/80">
                ({formatFileSize(status.file_size)})
              </span>
            )}
          </span>
        </a>

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

      {/* Optional video preview for preview renders */}
      {renderType === 'preview' && status.output_url && (
        <div className="mt-3 rounded-lg overflow-hidden bg-black aspect-video">
          <video
            src={status.output_url}
            controls
            className="w-full h-full"
            preload="metadata"
          >
            Your browser does not support the video tag.
          </video>
        </div>
      )}
    </div>
  );
}
