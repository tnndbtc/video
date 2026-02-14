import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useProject, useProjectMedia, useDeleteMedia, useReorderMedia } from '../hooks/useMedia';
import { useTimeline } from '../hooks/useTimeline';
import { MediaUploader } from '../components/MediaUploader';
import { MediaGrid } from '../components/MediaGrid';
import { AudioUploader } from '../components/AudioUploader';
import { Timeline } from '../components/Timeline';
import { RenderPanel } from '../components/RenderPanel';
import { parseRuleText } from '../utils/parseRuleText';
import type { PreviewSegment } from '../types/timeline';

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

  // Timeline hook (read-only preview)
  const { data: timeline } = useTimeline(projectId || '');

  // Video length state (in seconds, default 20)
  const [videoLengthSeconds, setVideoLengthSeconds] = useState(20);

  // Beat rule state (moved from RenderPanel)
  const [ruleText, setRuleText] = useState('');

  // Parse rule text for live preview
  const parsedRule = useMemo(() => parseRuleText(ruleText), [ruleText]);

  // Calculate preview segments based on beat rule, video length, and audio BPM
  const previewSegments = useMemo((): PreviewSegment[] | null => {
    // Need media to calculate preview
    if (!media.length) {
      return null;
    }

    // Use audio BPM if available, otherwise default to 120 BPM
    const bpm = project?.audio_track?.bpm ?? 120;
    const videoDurationMs = videoLengthSeconds * 1000;
    const beatsPerCut = parsedRule.beatsPerCut;

    // Formula: segment_duration_ms = (beats_per_cut / BPM) * 60000
    const segmentDurationMs = Math.floor((beatsPerCut / bpm) * 60000);

    // Build preview segments
    const segments: PreviewSegment[] = [];
    let currentTimeMs = 0;
    let mediaIndex = 0;

    while (currentTimeMs < videoDurationMs && mediaIndex < media.length) {
      const isLast = mediaIndex === media.length - 1;
      // Last item extends to fill remaining video duration
      const duration = isLast
        ? videoDurationMs - currentTimeMs
        : segmentDurationMs;

      segments.push({
        media_id: media[mediaIndex].id,
        thumbnail_url: media[mediaIndex].thumbnail_url,
        duration_ms: duration,
        timeline_in_ms: currentTimeMs,
        timeline_out_ms: currentTimeMs + duration,
      });

      currentTimeMs += duration;
      mediaIndex++;
    }

    return segments;
  }, [project?.audio_track, media, parsedRule.beatsPerCut, videoLengthSeconds]);

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

            {/* Timeline Visualization */}
            <section>
              <h2 className="text-lg font-medium text-white mb-3">Timeline Preview</h2>
              {timeline || previewSegments ? (
                <Timeline
                  timeline={timeline ?? null}
                  previewSegments={previewSegments}
                  bpm={project.audio_track?.bpm ?? 120}
                  beatsPerCut={parsedRule.beatsPerCut}
                />
              ) : (
                <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
                  {media.length === 0 ? (
                    <p className="text-gray-400 text-center">
                      Upload images and videos above to see them in the timeline.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-gray-400 text-sm">
                        {media.length} media file{media.length !== 1 ? 's' : ''} ready.
                      </p>
                      <div className="flex gap-2 overflow-x-auto pb-2">
                        {media.map((item, index) => (
                          <div
                            key={item.id}
                            className="flex-shrink-0 w-20 h-14 bg-gray-700 rounded overflow-hidden relative"
                          >
                            {item.thumbnail_url ? (
                              <img
                                src={item.thumbnail_url}
                                alt={`Media ${index + 1}`}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-gray-500 text-xs">
                                {index + 1}
                              </div>
                            )}
                            <span className="absolute bottom-0 right-0 bg-black/70 text-white text-xs px-1">
                              {index + 1}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* Video Length Section */}
            <section className="mt-4">
              <h3 className="text-sm font-medium text-gray-300 mb-2">Video Length</h3>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={videoLengthSeconds}
                  onChange={(e) => setVideoLengthSeconds(Math.max(1, parseInt(e.target.value) || 1))}
                  min="1"
                  className="w-24 px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <span className="text-gray-400 text-sm">seconds</span>
              </div>
            </section>

            {/* Beat Rule Section - under Timeline Preview */}
            <section className="mt-4">
              <h3 className="text-sm font-medium text-gray-300 mb-2">Beat Rule (optional)</h3>

              {/* Editable input */}
              <input
                type="text"
                value={ruleText}
                onChange={(e) => setRuleText(e.target.value)}
                placeholder="e.g., 8 beats, fast, 每4拍"
                className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white text-sm placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />

              {/* Live preview of parsed rule */}
              <div className="mt-2 flex items-center gap-2 text-sm">
                <span className="text-gray-500">→</span>
                <span className={parsedRule.isDefault ? 'text-gray-500' : 'text-green-400'}>
                  {parsedRule.beatsPerCut} beats per cut
                </span>
                {parsedRule.isDefault && (
                  <span className="text-gray-600 text-xs">(default)</span>
                )}
                {!parsedRule.isDefault && parsedRule.matchedPattern && (
                  <span className="text-gray-600 text-xs">
                    matched: "{parsedRule.matchedPattern}"
                  </span>
                )}
              </div>
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

            {/* Render Section */}
            <section className="border-t border-gray-700 pt-6">
              <h2 className="text-lg font-medium text-white mb-3">Export</h2>
              <RenderPanel
                projectId={projectId}
                hasMedia={media.length > 0}
                ruleText={ruleText}
                videoLengthSeconds={videoLengthSeconds}
              />
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Editor;
