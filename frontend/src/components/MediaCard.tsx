import { useState } from 'react';
import type { MediaAsset } from '../types/media';
import { ProcessingStatus } from './ProcessingStatus';
import { API_BASE_URL } from '../config';

interface MediaCardProps {
  asset: MediaAsset;
  onDelete?: (id: string) => void;
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function TrashIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ImagePlaceholder() {
  return (
    <div className="w-full h-full flex items-center justify-center bg-gray-700">
      <svg
        className="w-12 h-12 text-gray-500"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
        />
      </svg>
    </div>
  );
}

function VideoPlaceholder() {
  return (
    <div className="w-full h-full flex items-center justify-center bg-gray-700">
      <svg
        className="w-12 h-12 text-gray-500"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
        />
      </svg>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="w-full h-full bg-gray-700 animate-pulse flex items-center justify-center">
      <svg
        className="w-8 h-8 text-gray-600 animate-spin"
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
  );
}

export function MediaCard({ asset, onDelete }: MediaCardProps) {
  const [imageError, setImageError] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const isProcessing = asset.processing_status === 'pending' || asset.processing_status === 'processing';
  const isReady = asset.processing_status === 'ready';
  const hasThumbnail = isReady && asset.thumbnail_url && !imageError;

  const thumbnailUrl = hasThumbnail
    ? asset.thumbnail_url?.startsWith('http')
      ? asset.thumbnail_url
      : `${API_BASE_URL}/media/${asset.id}/thumbnail`
    : null;

  const handleDelete = async () => {
    if (!onDelete || isDeleting) return;

    if (window.confirm(`Delete "${asset.original_filename}"?`)) {
      setIsDeleting(true);
      try {
        await onDelete(asset.id);
      } catch {
        setIsDeleting(false);
      }
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700 hover:border-gray-600 transition-colors group relative">
      {/* Thumbnail Area */}
      <div className="aspect-video relative overflow-hidden bg-gray-900">
        {isProcessing && <LoadingSkeleton />}
        {!isProcessing && thumbnailUrl && (
          <img
            src={thumbnailUrl}
            alt={asset.original_filename}
            className="w-full h-full object-cover"
            onError={() => setImageError(true)}
          />
        )}
        {!isProcessing && !thumbnailUrl && asset.media_type === 'image' && <ImagePlaceholder />}
        {!isProcessing && !thumbnailUrl && asset.media_type === 'video' && <VideoPlaceholder />}

        {/* Video duration badge */}
        {asset.media_type === 'video' && asset.duration_ms && (
          <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
            {formatDuration(asset.duration_ms)}
          </div>
        )}

        {/* Media type badge */}
        <div className="absolute top-2 left-2">
          <span className="bg-black/70 text-white text-xs px-1.5 py-0.5 rounded uppercase">
            {asset.media_type}
          </span>
        </div>

        {/* Delete button */}
        {onDelete && (
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="absolute top-2 right-2 p-1.5 bg-red-600 hover:bg-red-500 text-white rounded opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50"
            title="Delete"
          >
            <TrashIcon className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Info Area */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-medium text-white truncate flex-1" title={asset.original_filename}>
            {asset.original_filename}
          </h3>
        </div>

        <div className="mt-2 flex items-center justify-between">
          <ProcessingStatus
            status={asset.processing_status}
            error={asset.processing_error}
          />
          <span className="text-xs text-gray-400">
            {formatFileSize(asset.file_size)}
          </span>
        </div>

        {/* Dimensions info */}
        {isReady && asset.width && asset.height && (
          <div className="mt-1 text-xs text-gray-500">
            {asset.width} x {asset.height}
            {asset.fps && ` @ ${asset.fps}fps`}
          </div>
        )}
      </div>
    </div>
  );
}

export default MediaCard;
