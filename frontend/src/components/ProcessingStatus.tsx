import type { ProcessingStatus as ProcessingStatusType } from '../types/media';

interface ProcessingStatusProps {
  status: ProcessingStatusType;
  error?: string;
  className?: string;
}

const statusConfig: Record<ProcessingStatusType, { label: string; bgColor: string; textColor: string }> = {
  pending: {
    label: 'Pending',
    bgColor: 'bg-gray-600',
    textColor: 'text-gray-200',
  },
  processing: {
    label: 'Processing',
    bgColor: 'bg-yellow-600',
    textColor: 'text-yellow-100',
  },
  ready: {
    label: 'Ready',
    bgColor: 'bg-green-600',
    textColor: 'text-green-100',
  },
  failed: {
    label: 'Failed',
    bgColor: 'bg-red-600',
    textColor: 'text-red-100',
  },
};

function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin h-3 w-3 ${className}`}
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

function CheckIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`h-3 w-3 ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function XIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`h-3 w-3 ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ClockIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`h-3 w-3 ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function ProcessingStatus({ status, error, className = '' }: ProcessingStatusProps) {
  const config = statusConfig[status];

  const renderIcon = () => {
    switch (status) {
      case 'pending':
        return <ClockIcon />;
      case 'processing':
        return <Spinner />;
      case 'ready':
        return <CheckIcon />;
      case 'failed':
        return <XIcon />;
    }
  };

  return (
    <div className={`relative group ${className}`}>
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${config.bgColor} ${config.textColor}`}
      >
        {renderIcon()}
        {config.label}
      </span>
      {status === 'failed' && error && (
        <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10">
          <div className="bg-gray-900 text-red-400 text-xs rounded px-2 py-1 max-w-xs whitespace-normal border border-red-600 shadow-lg">
            {error}
          </div>
        </div>
      )}
    </div>
  );
}

// Audio-specific status component
interface AudioStatusProps {
  status: 'queued' | 'processing' | 'complete' | 'failed';
  error?: string;
  className?: string;
}

const audioStatusConfig: Record<AudioStatusProps['status'], { label: string; bgColor: string; textColor: string }> = {
  queued: {
    label: 'Queued',
    bgColor: 'bg-gray-600',
    textColor: 'text-gray-200',
  },
  processing: {
    label: 'Analyzing',
    bgColor: 'bg-yellow-600',
    textColor: 'text-yellow-100',
  },
  complete: {
    label: 'Complete',
    bgColor: 'bg-green-600',
    textColor: 'text-green-100',
  },
  failed: {
    label: 'Failed',
    bgColor: 'bg-red-600',
    textColor: 'text-red-100',
  },
};

export function AudioStatus({ status, error, className = '' }: AudioStatusProps) {
  const config = audioStatusConfig[status];

  const renderIcon = () => {
    switch (status) {
      case 'queued':
        return <ClockIcon />;
      case 'processing':
        return <Spinner />;
      case 'complete':
        return <CheckIcon />;
      case 'failed':
        return <XIcon />;
    }
  };

  return (
    <div className={`relative group ${className}`}>
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${config.bgColor} ${config.textColor}`}
      >
        {renderIcon()}
        {config.label}
      </span>
      {status === 'failed' && error && (
        <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10">
          <div className="bg-gray-900 text-red-400 text-xs rounded px-2 py-1 max-w-xs whitespace-normal border border-red-600 shadow-lg">
            {error}
          </div>
        </div>
      )}
    </div>
  );
}

export default ProcessingStatus;
