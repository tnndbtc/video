/**
 * RenderProgress - Progress indicator for active render jobs
 */

import { useEffect, useState } from 'react';
import { formatElapsedTime } from '../utils/formatSize';

export interface RenderProgressProps {
  progress: number;
  message?: string;
  startedAt?: string;
  onCancel?: () => void;
}

export function RenderProgress({
  progress,
  message,
  startedAt,
  onCancel,
}: RenderProgressProps) {
  const [elapsedTime, setElapsedTime] = useState('0:00');

  // Update elapsed time every second
  useEffect(() => {
    if (!startedAt) return;

    const updateElapsed = () => {
      setElapsedTime(formatElapsedTime(startedAt));
    };

    updateElapsed();
    const interval = setInterval(updateElapsed, 1000);

    return () => clearInterval(interval);
  }, [startedAt]);

  const clampedProgress = Math.min(100, Math.max(0, progress));

  return (
    <div className="space-y-2">
      {/* Progress bar container */}
      <div className="relative h-4 bg-gray-700 rounded-full overflow-hidden">
        {/* Animated background stripes */}
        <div
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(255,255,255,0.1) 10px, rgba(255,255,255,0.1) 20px)',
            animation: 'stripe-animation 1s linear infinite',
          }}
        />

        {/* Progress fill */}
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-300 ease-out"
          style={{ width: `${clampedProgress}%` }}
        >
          {/* Pulse effect on the leading edge */}
          <div className="absolute right-0 top-0 bottom-0 w-4 bg-gradient-to-r from-transparent to-white/30 animate-pulse" />
        </div>

        {/* Percentage text */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-medium text-white drop-shadow-md">
            {Math.round(clampedProgress)}%
          </span>
        </div>
      </div>

      {/* Status row */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-gray-300">
          {/* Animated spinner */}
          <svg
            className="animate-spin h-4 w-4 text-blue-400"
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
          <span className="truncate max-w-[200px]">
            {message || 'Rendering...'}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Elapsed time */}
          {startedAt && (
            <span className="text-gray-400 tabular-nums">
              {elapsedTime}
            </span>
          )}

          {/* Cancel button */}
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-2 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* CSS for stripe animation */}
      <style>{`
        @keyframes stripe-animation {
          0% { background-position: 0 0; }
          100% { background-position: 40px 0; }
        }
      `}</style>
    </div>
  );
}
