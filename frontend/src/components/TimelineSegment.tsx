/**
 * TimelineSegment - Individual segment in the timeline view
 */

import type { TimelineSegment as TimelineSegmentType } from '../types/timeline';
import { formatDuration } from '../utils/formatTime';

export interface TimelineSegmentProps {
  segment: TimelineSegmentType;
  pixelsPerMs: number;
  showTransition?: boolean;
}

function TransitionIcon({ type }: { type: 'cut' | 'crossfade' | 'fade' }) {
  if (type === 'cut') {
    return null;
  }

  return (
    <div className="absolute -left-3 top-1/2 -translate-y-1/2 z-10 flex items-center justify-center w-6 h-6 bg-gray-700 rounded-full border border-gray-600">
      {type === 'crossfade' ? (
        <svg className="w-3 h-3 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M7 4v16M17 4v16" strokeLinecap="round" />
          <path d="M7 12h10" strokeLinecap="round" strokeDasharray="2 2" />
        </svg>
      ) : (
        <svg className="w-3 h-3 text-yellow-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 3v18M3 12h18" strokeLinecap="round" opacity="0.5" />
          <circle cx="12" cy="12" r="6" fill="currentColor" opacity="0.3" />
        </svg>
      )}
    </div>
  );
}

function KenBurnsIcon() {
  return (
    <div className="absolute top-1 right-1 z-10" title="Ken Burns effect">
      <div className="w-4 h-4 bg-orange-500/80 rounded flex items-center justify-center">
        <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  );
}

function MediaTypeIcon({ type }: { type: 'image' | 'video' }) {
  return type === 'video' ? (
    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4 4a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-3.5l4 4V7.5l-4 4V6a2 2 0 00-2-2H4z" />
    </svg>
  ) : (
    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

export function TimelineSegment({ segment, pixelsPerMs, showTransition = true }: TimelineSegmentProps) {
  const width = Math.max(segment.render_duration_ms * pixelsPerMs, 40); // Minimum 40px width
  const hasKenBurns = segment.effects?.ken_burns != null;
  const hasTransitionIn = showTransition && segment.transition_in != null && segment.transition_in.type !== 'cut';

  const borderColor = segment.media_type === 'video' ? 'border-green-500' : 'border-blue-500';
  const bgGradient = segment.media_type === 'video'
    ? 'bg-gradient-to-b from-green-900/50 to-green-950/80'
    : 'bg-gradient-to-b from-blue-900/50 to-blue-950/80';

  return (
    <div
      className="relative flex-shrink-0 group"
      style={{ width: `${width}px` }}
    >
      {/* Transition indicator */}
      {hasTransitionIn && segment.transition_in && (
        <TransitionIcon type={segment.transition_in.type} />
      )}

      {/* Main segment container */}
      <div
        className={`relative h-full rounded-lg border-2 ${borderColor} ${bgGradient} overflow-hidden cursor-pointer transition-all hover:brightness-110 hover:border-white/50`}
      >
        {/* Thumbnail */}
        {segment.thumbnail_url ? (
          <img
            src={segment.thumbnail_url}
            alt={`Segment ${segment.index + 1}`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-800">
            <MediaTypeIcon type={segment.media_type} />
          </div>
        )}

        {/* Ken Burns indicator */}
        {hasKenBurns && <KenBurnsIcon />}

        {/* Segment index badge */}
        <div className="absolute bottom-1 left-1 z-10">
          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-black/70 text-white">
            <MediaTypeIcon type={segment.media_type} />
            <span>{segment.index + 1}</span>
          </span>
        </div>

        {/* Hover tooltip */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          <div className="text-center text-xs text-white p-2">
            <div className="font-medium mb-1">Segment {segment.index + 1}</div>
            <div className="text-gray-300">
              {formatDuration(segment.render_duration_ms)}
            </div>
            <div className="text-gray-400 text-[10px] mt-1">
              {formatDuration(segment.timeline_in_ms)} - {formatDuration(segment.timeline_out_ms)}
            </div>
            {hasKenBurns && segment.effects.ken_burns && (
              <div className="text-orange-400 text-[10px] mt-1">
                Ken Burns: {segment.effects.ken_burns.pan_direction}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default TimelineSegment;
