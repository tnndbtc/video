/**
 * TimelineEmpty - Empty state when no timeline exists
 */

export interface TimelineEmptyProps {
  hasMedia: boolean;
  hasAudio: boolean;
  hasBeats: boolean;
  onGenerate: () => void;
  isGenerating: boolean;
}

function CheckIcon() {
  return (
    <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function TimelineIllustration() {
  return (
    <svg
      className="w-32 h-32 text-gray-600"
      viewBox="0 0 128 128"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Timeline track */}
      <rect x="8" y="54" width="112" height="20" rx="4" fill="currentColor" opacity="0.3" />

      {/* Segments */}
      <rect x="12" y="58" width="20" height="12" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="36" y="58" width="16" height="12" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="56" y="58" width="24" height="12" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="84" y="58" width="12" height="12" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="100" y="58" width="16" height="12" rx="2" fill="currentColor" opacity="0.6" />

      {/* Beat markers */}
      <line x1="22" y1="80" x2="22" y2="90" stroke="currentColor" strokeWidth="2" opacity="0.4" />
      <line x1="44" y1="80" x2="44" y2="90" stroke="currentColor" strokeWidth="2" opacity="0.4" />
      <line x1="68" y1="80" x2="68" y2="90" stroke="currentColor" strokeWidth="2" opacity="0.4" />
      <line x1="90" y1="80" x2="90" y2="90" stroke="currentColor" strokeWidth="2" opacity="0.4" />
      <line x1="108" y1="80" x2="108" y2="90" stroke="currentColor" strokeWidth="2" opacity="0.4" />

      {/* Time ruler */}
      <rect x="8" y="40" width="112" height="10" rx="2" fill="currentColor" opacity="0.2" />

      {/* Music notes */}
      <g opacity="0.5">
        <path d="M20 28c0-2.2 1.8-4 4-4v12c0 2.2-1.8 4-4 4s-4-1.8-4-4 1.8-4 4-4z" fill="currentColor" />
        <path d="M24 24v16" stroke="currentColor" strokeWidth="2" />
        <path d="M24 24c4-2 8 2 8-2" stroke="currentColor" strokeWidth="2" />
      </g>

      <g opacity="0.5">
        <path d="M100 24c0-2.2 1.8-4 4-4v12c0 2.2-1.8 4-4 4s-4-1.8-4-4 1.8-4 4-4z" fill="currentColor" />
        <path d="M104 20v16" stroke="currentColor" strokeWidth="2" />
      </g>
    </svg>
  );
}

export function TimelineEmpty({
  hasMedia,
  hasAudio,
  hasBeats,
  onGenerate,
  isGenerating,
}: TimelineEmptyProps) {
  const canGenerate = hasMedia && hasAudio && hasBeats;

  const prerequisites = [
    { label: 'Media uploaded', met: hasMedia },
    { label: 'Audio track uploaded', met: hasAudio },
    { label: 'Beat analysis complete', met: hasBeats },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      <TimelineIllustration />

      <h3 className="mt-6 text-lg font-semibold text-white">
        No Timeline Generated
      </h3>

      <p className="mt-2 text-sm text-gray-400 max-w-md">
        Generate a timeline to automatically sync your media to the beat of your audio track.
        Each segment will be placed on the timeline according to the detected beats.
      </p>

      {/* Prerequisites checklist */}
      <div className="mt-6 space-y-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
          Prerequisites
        </p>
        {prerequisites.map(({ label, met }) => (
          <div
            key={label}
            className={`flex items-center gap-2 text-sm ${
              met ? 'text-green-400' : 'text-gray-400'
            }`}
          >
            {met ? <CheckIcon /> : <XIcon />}
            <span>{label}</span>
          </div>
        ))}
      </div>

      {/* Generate button */}
      <button
        type="button"
        onClick={onGenerate}
        disabled={!canGenerate || isGenerating}
        className={`mt-8 px-6 py-3 rounded-lg font-medium text-white transition-all flex items-center gap-2 ${
          canGenerate && !isGenerating
            ? 'bg-blue-600 hover:bg-blue-500 active:bg-blue-700'
            : 'bg-gray-700 text-gray-500 cursor-not-allowed'
        }`}
      >
        {isGenerating ? (
          <>
            <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Generating...
          </>
        ) : (
          <>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Generate Timeline
          </>
        )}
      </button>

      {!canGenerate && (
        <p className="mt-3 text-xs text-gray-500">
          Complete all prerequisites to enable timeline generation
        </p>
      )}
    </div>
  );
}

export default TimelineEmpty;
