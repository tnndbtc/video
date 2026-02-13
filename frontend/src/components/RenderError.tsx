/**
 * RenderError - Error display for failed renders with retry option
 */

export interface RenderErrorProps {
  error: string;
  onRetry: () => void;
}

export function RenderError({ error, onRetry }: RenderErrorProps) {
  // Determine possible cause based on error message
  const getPossibleCause = (errorMessage: string): string | null => {
    const lowerError = errorMessage.toLowerCase();

    if (lowerError.includes('memory') || lowerError.includes('oom')) {
      return 'The video may be too long or complex. Try rendering a shorter segment.';
    }
    if (lowerError.includes('codec') || lowerError.includes('format')) {
      return 'Some video formats may not be supported. Try re-uploading the source videos.';
    }
    if (lowerError.includes('timeout') || lowerError.includes('timed out')) {
      return 'The render took too long. Try rendering a shorter segment or using preview quality.';
    }
    if (lowerError.includes('disk') || lowerError.includes('space') || lowerError.includes('storage')) {
      return 'Server storage may be full. Please try again later or contact support.';
    }
    if (lowerError.includes('network') || lowerError.includes('connection')) {
      return 'Network issues occurred. Check your connection and try again.';
    }

    return null;
  };

  const possibleCause = getPossibleCause(error);

  return (
    <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-4 space-y-3">
      {/* Error header */}
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className="h-5 w-5 text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-red-400">Render Failed</h4>
          <p className="mt-1 text-sm text-red-300/80 break-words">{error}</p>
        </div>
      </div>

      {/* Possible cause hint */}
      {possibleCause && (
        <div className="flex items-start gap-2 text-sm text-gray-400 bg-gray-800/50 rounded p-2">
          <svg
            className="h-4 w-4 flex-shrink-0 mt-0.5"
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
          <span>{possibleCause}</span>
        </div>
      )}

      {/* Retry button */}
      <button
        type="button"
        onClick={onRetry}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500 text-white font-medium rounded-lg transition-colors"
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
        <span>Retry Render</span>
      </button>
    </div>
  );
}
