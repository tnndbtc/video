import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ProjectListItem } from '../types';

interface ProjectCardProps {
  project: ProjectListItem;
  onDelete: (projectId: string) => void;
  isDeleting?: boolean;
  onAiStitch?: () => void;
}

function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'ready':
      return 'bg-green-500';
    case 'rendering':
      return 'bg-yellow-500';
    case 'error':
      return 'bg-red-500';
    case 'draft':
    default:
      return 'bg-gray-500';
  }
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function ProjectCard({ project, onDelete, isDeleting, onAiStitch }: ProjectCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const navigate = useNavigate();

  const handleDelete = () => {
    onDelete(project.id);
    setShowDeleteConfirm(false);
  };

  const handleOpen = () => {
    navigate(`/project/${project.id}`);
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-gray-600 transition-colors">
      {/* Thumbnail area */}
      <div className="aspect-video bg-gray-900 flex items-center justify-center">
        <svg
          className="w-16 h-16 text-gray-700"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
          />
        </svg>
      </div>

      {/* Content area */}
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <h3 className="text-lg font-semibold text-white truncate flex-1 mr-2">
            {project.name}
          </h3>
          <span
            className={`${getStatusColor(project.status)} text-white text-xs px-2 py-1 rounded-full capitalize`}
          >
            {project.status}
          </span>
        </div>

        {project.description && (
          <p className="text-gray-400 text-sm mb-3 line-clamp-2">
            {project.description}
          </p>
        )}

        <div className="flex items-center text-gray-500 text-sm mb-4 space-x-4">
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            {project.media_count} media
          </span>
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
              />
            </svg>
            {project.has_audio ? 'Audio' : 'No audio'}
          </span>
        </div>

        <div className="text-gray-500 text-xs mb-4">
          <div>Created: {formatDate(project.created_at)}</div>
          <div>Updated: {formatDate(project.updated_at)}</div>
        </div>

        {/* Action buttons */}
        {showDeleteConfirm ? (
          <div className="flex space-x-2">
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-800 disabled:cursor-not-allowed text-white px-3 py-2 rounded-md text-sm font-medium transition-colors"
            >
              {isDeleting ? 'Deleting...' : 'Confirm Delete'}
            </button>
            <button
              onClick={() => setShowDeleteConfirm(false)}
              disabled={isDeleting}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-white px-3 py-2 rounded-md text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex space-x-2">
            <button
              onClick={handleOpen}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-md text-sm font-medium transition-colors"
            >
              Open
            </button>
            {onAiStitch && (
              <button
                onClick={onAiStitch}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-2 rounded-md text-sm font-medium transition-colors"
              >
                AI Stitch
              </button>
            )}
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="bg-gray-700 hover:bg-red-600 text-white px-3 py-2 rounded-md text-sm font-medium transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
