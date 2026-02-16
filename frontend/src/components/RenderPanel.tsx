/**
 * RenderPanel - Main render controls panel for BeatStitch video editor
 * Contains Preview and Final render sections with status, progress, and download controls
 */

import { useCallback } from 'react';
import { clsx } from 'clsx';
import { useStartRender, useRenderStatus, parseRenderError } from '../hooks/useRender';
import { RenderButton } from './RenderButton';
import { RenderProgress } from './RenderProgress';
import { RenderResult } from './RenderResult';
import { RenderError } from './RenderError';
import type { RenderType } from '../types/render';

export interface RenderPanelProps {
  projectId: string;
  hasMedia: boolean;
  ruleText: string;
  videoLengthSeconds: number;
  timelineMediaIds: string[];
  savedTimelineMediaIds?: string[] | null;
}

interface RenderSectionProps {
  projectId: string;
  renderType: RenderType;
  hasMedia: boolean;
  ruleText: string;
  videoLengthSeconds: number;
}

/**
 * Individual render section (Preview or Final)
 * Timeline is auto-generated during render, so we only check for media availability.
 */
function RenderSection({
  projectId,
  renderType,
  hasMedia,
  ruleText,
  videoLengthSeconds,
}: RenderSectionProps) {
  const { data: status, isLoading: isLoadingStatus, error: statusError } = useRenderStatus(
    projectId,
    renderType
  );
  const startRender = useStartRender(projectId);

  const isPreview = renderType === 'preview';
  const isIdle = status?.status === 'idle';
  const isRendering = status?.status === 'queued' || status?.status === 'running';
  const isComplete = status?.status === 'complete';
  const isFailed = status?.status === 'failed';

  // Determine if render button should be disabled and why
  const getDisabledState = (): { disabled: boolean; reason?: string } => {
    if (!hasMedia) {
      return { disabled: true, reason: 'Upload media first' };
    }
    if (isRendering) {
      return { disabled: true, reason: 'Render in progress' };
    }
    if (startRender.isPending) {
      return { disabled: true, reason: 'Starting render...' };
    }
    return { disabled: false };
  };

  const { disabled, reason } = getDisabledState();

  // Handle render start (no edlHash needed - timeline auto-generated)
  const handleRender = useCallback(() => {
    if (disabled) return;
    startRender.mutate({
      type: renderType,
      rule_text: ruleText || undefined,
      video_length_seconds: videoLengthSeconds,
    });
  }, [disabled, startRender, renderType, ruleText, videoLengthSeconds]);

  // Handle retry after error
  const handleRetry = useCallback(() => {
    startRender.mutate({
      type: renderType,
      rule_text: ruleText || undefined,
      video_length_seconds: videoLengthSeconds,
    });
  }, [startRender, renderType, ruleText, videoLengthSeconds]);

  // Parse mutation error
  const mutationError = startRender.error
    ? parseRenderError(startRender.error)
    : null;

  // Section styling
  const sectionClasses = clsx(
    'flex-1 p-4 rounded-xl',
    isPreview ? 'bg-blue-900/20 border border-blue-700/30' : 'bg-green-900/20 border border-green-700/30'
  );

  return (
    <div className={sectionClasses}>
      {/* Header */}
      <div className="mb-4">
        <h3 className={clsx(
          'text-lg font-semibold',
          isPreview ? 'text-blue-300' : 'text-green-300'
        )}>
          {isPreview ? 'Preview Render' : 'Final Render'}
        </h3>
        <p className="text-sm text-gray-400 mt-1">
          {isPreview ? (
            <>640x360 @ 24fps<span className="mx-2 text-gray-600">|</span>Fast &bull; Low Quality</>
          ) : (
            <>1920x1080 @ 30fps<span className="mx-2 text-gray-600">|</span>Slow &bull; High Quality</>
          )}
        </p>
      </div>

      {/* Content area */}
      <div className="space-y-4">
        {/* Show error from mutation */}
        {mutationError && (
          <div className="text-sm text-red-400 bg-red-900/20 rounded-lg p-3 border border-red-500/30">
            {mutationError.isRenderInProgress && (
              <span>A render is already in progress.</span>
            )}
            {mutationError.isTimelineNotReady && (
              <span>No media available for rendering.</span>
            )}
            {!mutationError.isRenderInProgress && !mutationError.isTimelineNotReady && (
              <span>{mutationError.message}</span>
            )}
          </div>
        )}

        {/* Loading state - only show spinner during initial fetch when we have no data at all */}
        {isLoadingStatus && status === undefined && (
          <div className="flex items-center justify-center py-4 text-gray-400">
            <svg
              className="animate-spin h-5 w-5 mr-2"
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
            <span>Loading...</span>
          </div>
        )}

        {/* Render button - always show when not failed, gray out when rendering */}
        {(isIdle || status?.status === 'cancelled' || isComplete || isRendering) && (
          <RenderButton
            label={
              isRendering
                ? (isPreview ? 'Rendering Preview...' : 'Rendering Final...')
                : (isPreview ? 'Render Preview' : 'Render Final')
            }
            onClick={handleRender}
            disabled={disabled}
            disabledReason={reason}
            isLoading={startRender.isPending || isRendering}
            variant={isPreview ? 'preview' : 'final'}
          />
        )}

        {/* Progress bar - show below button when rendering */}
        {isRendering && status && (
          <RenderProgress
            progress={status.progress_percent}
            message={status.progress_message}
            startedAt={status.started_at}
          />
        )}

        {/* Result - show when complete */}
        {isComplete && status && (
          <RenderResult
            projectId={projectId}
            renderType={renderType}
            status={status}
            onRerender={handleRender}
          />
        )}

        {/* Failed render */}
        {isFailed && status && (
          <RenderError
            error={status.error || 'Render failed'}
            onRetry={handleRetry}
          />
        )}

        {/* No render status available (404 - no render yet) */}
        {statusError && !status && !isLoadingStatus && (
          <RenderButton
            label={isPreview ? 'Render Preview' : 'Render Final'}
            onClick={handleRender}
            disabled={disabled}
            disabledReason={reason}
            isLoading={startRender.isPending}
            variant={isPreview ? 'preview' : 'final'}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Main RenderPanel component
 * Timeline is auto-generated during render - we only need to check for media.
 */
export function RenderPanel({ projectId, hasMedia, ruleText, videoLengthSeconds, timelineMediaIds: _timelineMediaIds, savedTimelineMediaIds: _savedTimelineMediaIds }: RenderPanelProps) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-6">
      {/* Panel header */}
      <div className="mb-6">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <svg
            className="h-6 w-6 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
            />
          </svg>
          Render Controls
        </h2>
        <p className="text-sm text-gray-400 mt-1">
          Export your video as a preview or final render
        </p>
      </div>

      {/* Render sections */}
      <div className="flex flex-col lg:flex-row gap-4">
        <RenderSection
          projectId={projectId}
          renderType="preview"
          hasMedia={hasMedia}
          ruleText={ruleText}
          videoLengthSeconds={videoLengthSeconds}
        />
        <RenderSection
          projectId={projectId}
          renderType="final"
          hasMedia={hasMedia}
          ruleText={ruleText}
          videoLengthSeconds={videoLengthSeconds}
        />
      </div>

      {/* No media warning */}
      {!hasMedia && (
        <div className="mt-4 flex items-center gap-2 text-sm text-gray-400 bg-gray-800 rounded-lg p-3">
          <svg
            className="h-5 w-5 flex-shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Upload media first to enable rendering.</span>
        </div>
      )}
    </div>
  );
}
