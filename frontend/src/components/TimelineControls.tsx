/**
 * TimelineControls - Control bar for timeline generation and status
 */

import type { TimelineStatus } from '../types/timeline';
import { formatDuration } from '../utils/formatTime';

export interface TimelineControlsProps {
  projectId: string;
  status: TimelineStatus;
  onGenerate: () => void;
  isGenerating: boolean;
}

function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
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
  );
}

function RefreshIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function PlayIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export function TimelineControls({
  status,
  onGenerate,
  isGenerating,
}: TimelineControlsProps) {
  const isProcessing = status.generation_status === 'queued' || status.generation_status === 'generating';
  const hasTimeline = status.generated && status.generation_status === 'ready';
  const hasFailed = status.generation_status === 'failed';

  const buttonLabel = hasTimeline ? 'Regenerate Timeline' : 'Generate Timeline';
  const buttonDisabled = isGenerating || isProcessing;

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      {/* Generate/Regenerate Button */}
      <div className="flex items-center gap-3 mb-4">
        <button
          type="button"
          onClick={onGenerate}
          disabled={buttonDisabled}
          className={`flex-1 px-4 py-2.5 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2 ${
            buttonDisabled
              ? 'bg-blue-600/50 text-white/70 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700'
          }`}
        >
          {isProcessing || isGenerating ? (
            <>
              <Spinner className="h-4 w-4" />
              {status.generation_status === 'queued' ? 'Queued...' : 'Generating...'}
            </>
          ) : (
            <>
              {hasTimeline ? <RefreshIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
              {buttonLabel}
            </>
          )}
        </button>
      </div>

      {/* Progress Indicator */}
      {isProcessing && typeof status.progress_percent === 'number' && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Progress</span>
            <span>{status.progress_percent}%</span>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${status.progress_percent}%` }}
            />
          </div>
        </div>
      )}

      {/* Error Message */}
      {hasFailed && status.error_message && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-600 rounded-lg">
          <div className="flex items-start gap-2">
            <svg className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="text-sm font-medium text-red-400">Generation Failed</p>
              <p className="text-xs text-red-300/80 mt-1">{status.error_message}</p>
            </div>
          </div>
        </div>
      )}

      {/* Stale Warning */}
      {status.stale && (
        <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-600 rounded-lg">
          <div className="flex items-start gap-2">
            <svg className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="text-sm font-medium text-yellow-400">Timeline Outdated</p>
              <p className="text-xs text-yellow-300/80 mt-1">
                {status.stale_reason || 'Project has been modified. Regenerate to apply changes.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Timeline Info */}
      {hasTimeline && (
        <div className="grid grid-cols-2 gap-3 pt-3 border-t border-gray-700">
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Segments</p>
            <p className="text-sm font-medium text-white">{status.segment_count}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Duration</p>
            <p className="text-sm font-medium text-white">
              {status.total_duration_ms ? formatDuration(status.total_duration_ms) : '--:--'}
            </p>
          </div>
          {status.generated_at && (
            <div className="col-span-2">
              <p className="text-xs text-gray-500 mb-0.5">Generated</p>
              <p className="text-xs text-gray-400">
                {new Date(status.generated_at).toLocaleString()}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TimelineControls;
