import { useParams, Link } from 'react-router-dom';
import { useProject, useProjectMedia, useDeleteMedia, useReorderMedia } from '../hooks/useMedia';
import { MediaUploader } from '../components/MediaUploader';
import { MediaGrid } from '../components/MediaGrid';
import { AudioUploader } from '../components/AudioUploader';

function ArrowLeftIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-900">
      <div className="text-center">
        <svg
          className="animate-spin h-10 w-10 text-blue-500 mx-auto mb-4"
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
        <p className="text-gray-400">Loading project...</p>
      </div>
    </div>
  );
}

function ErrorDisplay({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-900">
      <div className="text-center max-w-md p-6">
        <div className="w-16 h-16 bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-8 h-8 text-red-500"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-white mb-2">Error Loading Project</h2>
        <p className="text-gray-400 mb-4">{message}</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}

export function Editor() {
  const { projectId } = useParams<{ projectId: string }>();

  const { data: project, isLoading: isProjectLoading, error: projectError } = useProject(projectId || '');
  const { data: media = [], isLoading: isMediaLoading } = useProjectMedia(projectId || '');
  const { mutate: deleteMedia } = useDeleteMedia(projectId || '');
  const { mutate: reorderMedia } = useReorderMedia(projectId || '');

  if (!projectId) {
    return <ErrorDisplay message="No project ID provided" />;
  }

  if (isProjectLoading) {
    return <LoadingSpinner />;
  }

  if (projectError) {
    return <ErrorDisplay message={projectError instanceof Error ? projectError.message : 'Failed to load project'} />;
  }

  if (!project) {
    return <ErrorDisplay message="Project not found" />;
  }

  const handleDeleteMedia = (mediaId: string) => {
    deleteMedia(mediaId);
  };

  const handleReorderMedia = (newOrder: string[]) => {
    reorderMedia(newOrder);
  };

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
            >
              <ArrowLeftIcon className="w-5 h-5" />
              <span className="hidden sm:inline">Dashboard</span>
            </Link>
            <div className="h-6 w-px bg-gray-700" />
            <div>
              <h1 className="text-lg font-semibold text-white">{project.name}</h1>
              {project.description && (
                <p className="text-sm text-gray-400 truncate max-w-xs">{project.description}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Placeholder for future actions like export */}
            <span className="text-sm text-gray-500">
              {media.length} media file{media.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Panel - Media */}
        <div className="flex-1 overflow-y-auto p-4 lg:p-6">
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Media Uploader */}
            <section>
              <h2 className="text-lg font-medium text-white mb-3">Upload Media</h2>
              <MediaUploader projectId={projectId} />
            </section>

            {/* Media Grid */}
            <section>
              <h2 className="text-lg font-medium text-white mb-3">
                Media Library
                {isMediaLoading && (
                  <span className="ml-2 text-sm text-gray-500">(Loading...)</span>
                )}
              </h2>
              <MediaGrid
                projectId={projectId}
                media={media}
                onDelete={handleDeleteMedia}
                onReorder={handleReorderMedia}
              />
            </section>
          </div>
        </div>

        {/* Right Panel - Audio & Beat Status */}
        <div className="w-full lg:w-80 xl:w-96 bg-gray-800 border-t lg:border-t-0 lg:border-l border-gray-700 overflow-y-auto">
          <div className="p-4 lg:p-6 space-y-6">
            {/* Audio Section */}
            <section>
              <h2 className="text-lg font-medium text-white mb-3">Audio Track</h2>
              <AudioUploader
                projectId={projectId}
                currentAudio={project.audio_track}
              />
            </section>

            {/* Beat Status Section */}
            {project.audio_track && project.audio_track.analysis_status === 'complete' && (
              <section className="bg-gray-700/50 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-300 mb-2">Beat Analysis</h3>
                <div className="space-y-2 text-sm">
                  {project.audio_track.bpm && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">Tempo</span>
                      <span className="text-white font-medium">{project.audio_track.bpm} BPM</span>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Placeholder sections for future features */}
            <div className="border-t border-gray-700 pt-6 space-y-4">
              <div className="bg-gray-700/30 rounded-lg p-4 text-center">
                <svg
                  className="w-8 h-8 text-gray-600 mx-auto mb-2"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12"
                  />
                </svg>
                <p className="text-sm text-gray-500">Timeline</p>
                <p className="text-xs text-gray-600">Coming in S17</p>
              </div>

              <div className="bg-gray-700/30 rounded-lg p-4 text-center">
                <svg
                  className="w-8 h-8 text-gray-600 mx-auto mb-2"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
                  />
                </svg>
                <p className="text-sm text-gray-500">Render</p>
                <p className="text-xs text-gray-600">Coming in S18</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Editor;
