/**
 * RenderButton - Individual render button with loading state and tooltip
 */

import { clsx } from 'clsx';

export interface RenderButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  disabledReason?: string;
  isLoading?: boolean;
  variant?: 'preview' | 'final';
}

export function RenderButton({
  label,
  onClick,
  disabled = false,
  disabledReason,
  isLoading = false,
  variant = 'preview',
}: RenderButtonProps) {
  const isDisabled = disabled || isLoading;

  const baseClasses =
    'relative w-full px-4 py-3 rounded-lg font-medium text-white transition-all duration-200 flex items-center justify-center gap-2';

  const variantClasses = {
    preview: isDisabled
      ? 'bg-blue-600/50 cursor-not-allowed'
      : 'bg-blue-600 hover:bg-blue-500 active:bg-blue-700',
    final: isDisabled
      ? 'bg-green-600/50 cursor-not-allowed'
      : 'bg-green-600 hover:bg-green-500 active:bg-green-700',
  };

  return (
    <div className="relative group">
      <button
        type="button"
        onClick={onClick}
        disabled={isDisabled}
        className={clsx(baseClasses, variantClasses[variant])}
        aria-busy={isLoading}
        aria-disabled={isDisabled}
      >
        {isLoading && (
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
        )}
        {!isLoading && (
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
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        )}
        <span>{label}</span>
      </button>

      {/* Tooltip for disabled reason */}
      {disabled && disabledReason && !isLoading && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-700 text-sm text-gray-200 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 whitespace-nowrap pointer-events-none z-10">
          {disabledReason}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-700" />
        </div>
      )}
    </div>
  );
}
