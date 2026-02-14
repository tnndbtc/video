/**
 * Timeline - Main timeline viewer component for BeatStitch video editor
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import type { Timeline as TimelineType } from '../types/timeline';
import { TimelineSegment } from './TimelineSegment';
import { formatTimelineTime, formatDuration } from '../utils/formatTime';
import { useDeleteSegment } from '../hooks/useTimeline';

export interface TimelineProps {
  projectId: string;
  timeline: TimelineType | null;
}

// Zoom levels in pixels per millisecond
const ZOOM_LEVELS = [0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3] as const;
const DEFAULT_ZOOM_INDEX = 2;

// Time ruler intervals (in ms) for different zoom levels
function getTickInterval(pixelsPerMs: number): { major: number; minor: number } {
  if (pixelsPerMs < 0.02) {
    return { major: 30000, minor: 10000 }; // 30s major, 10s minor
  } else if (pixelsPerMs < 0.05) {
    return { major: 10000, minor: 5000 }; // 10s major, 5s minor
  } else if (pixelsPerMs < 0.1) {
    return { major: 5000, minor: 1000 }; // 5s major, 1s minor
  } else if (pixelsPerMs < 0.2) {
    return { major: 2000, minor: 500 }; // 2s major, 500ms minor
  } else {
    return { major: 1000, minor: 250 }; // 1s major, 250ms minor
  }
}

function ZoomControls({
  zoomIndex,
  onZoomIn,
  onZoomOut,
}: {
  zoomIndex: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1">
      <button
        type="button"
        onClick={onZoomOut}
        disabled={zoomIndex === 0}
        className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        title="Zoom out"
      >
        <svg className="w-4 h-4 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
        </svg>
      </button>
      <span className="text-xs text-gray-400 min-w-[40px] text-center">
        {Math.round(ZOOM_LEVELS[zoomIndex] * 1000)}x
      </span>
      <button
        type="button"
        onClick={onZoomIn}
        disabled={zoomIndex === ZOOM_LEVELS.length - 1}
        className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        title="Zoom in"
      >
        <svg className="w-4 h-4 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
        </svg>
      </button>
    </div>
  );
}

function TimeRuler({
  totalDuration,
  pixelsPerMs,
}: {
  totalDuration: number;
  pixelsPerMs: number;
}) {
  const { major, minor } = getTickInterval(pixelsPerMs);
  const width = totalDuration * pixelsPerMs;
  const ticks: { position: number; time: number; isMajor: boolean }[] = [];

  for (let time = 0; time <= totalDuration; time += minor) {
    ticks.push({
      position: time * pixelsPerMs,
      time,
      isMajor: time % major === 0,
    });
  }

  return (
    <div
      className="relative h-6 bg-gray-800/50 border-b border-gray-700"
      style={{ width: `${width}px` }}
    >
      {ticks.map(({ position, time, isMajor }) => (
        <div
          key={time}
          className="absolute top-0 flex flex-col items-center"
          style={{ left: `${position}px` }}
        >
          <div
            className={`w-px ${isMajor ? 'h-4 bg-gray-500' : 'h-2 bg-gray-600'}`}
          />
          {isMajor && (
            <span className="text-[10px] text-gray-500 mt-0.5 whitespace-nowrap">
              {formatTimelineTime(time)}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function BeatMarkers({
  totalDuration,
  pixelsPerMs,
  beatsPerCut,
}: {
  totalDuration: number;
  pixelsPerMs: number;
  beatsPerCut: number;
}) {
  const width = totalDuration * pixelsPerMs;
  // Assume ~120 BPM for beat marker spacing visualization
  // In a real implementation, this would come from the audio analysis
  const beatIntervalMs = 500; // 120 BPM = 500ms per beat
  const markers: { position: number; isDownbeat: boolean }[] = [];

  let beatCount = 0;
  for (let time = 0; time <= totalDuration; time += beatIntervalMs) {
    const isDownbeat = beatCount % beatsPerCut === 0;
    markers.push({
      position: time * pixelsPerMs,
      isDownbeat,
    });
    beatCount++;
  }

  return (
    <div
      className="absolute bottom-0 left-0 h-4 pointer-events-none"
      style={{ width: `${width}px` }}
    >
      {markers.map(({ position, isDownbeat }, index) => (
        <div
          key={index}
          className={`absolute bottom-0 w-px ${
            isDownbeat ? 'h-4 bg-red-500/60' : 'h-2 bg-gray-600/40'
          }`}
          style={{ left: `${position}px` }}
        />
      ))}
    </div>
  );
}

export function Timeline({ projectId, timeline }: TimelineProps) {
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pixelsPerMs = ZOOM_LEVELS[zoomIndex];

  const deleteSegmentMutation = useDeleteSegment(projectId);

  const handleDeleteSegment = useCallback((index: number) => {
    if (timeline && timeline.segments.length <= 1) {
      alert('Cannot delete the last segment.');
      return;
    }

    if (window.confirm(`Remove segment ${index + 1} from the timeline?`)) {
      setDeletingIndex(index);
      deleteSegmentMutation.mutate(index, {
        onSettled: () => {
          setDeletingIndex(null);
        },
      });
    }
  }, [deleteSegmentMutation, timeline]);

  const handleZoomIn = useCallback(() => {
    setZoomIndex((prev) => Math.min(prev + 1, ZOOM_LEVELS.length - 1));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  // Handle scroll wheel zoom
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        if (e.deltaY < 0) {
          handleZoomIn();
        } else {
          handleZoomOut();
        }
      }
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleWheel);
  }, [handleZoomIn, handleZoomOut]);

  if (!timeline) {
    return null;
  }

  const { segments, total_duration_ms, settings_used } = timeline;
  const timelineWidth = total_duration_ms * pixelsPerMs;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header with controls */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-4">
          <h3 className="text-sm font-medium text-white">Timeline</h3>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>{segments.length} segments</span>
            <span className="text-gray-600">|</span>
            <span>{formatDuration(total_duration_ms)}</span>
            <span className="text-gray-600">|</span>
            <span>{settings_used.transition_type}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ZoomControls
            zoomIndex={zoomIndex}
            onZoomIn={handleZoomIn}
            onZoomOut={handleZoomOut}
          />
        </div>
      </div>

      {/* Scrollable timeline area */}
      <div
        ref={scrollContainerRef}
        className="overflow-x-auto overflow-y-hidden"
        style={{ maxHeight: '200px' }}
      >
        <div style={{ minWidth: `${Math.max(timelineWidth, 100)}px` }}>
          {/* Time ruler */}
          <TimeRuler totalDuration={total_duration_ms} pixelsPerMs={pixelsPerMs} />

          {/* Segments track */}
          <div className="relative bg-gray-800 min-h-[120px] py-2 px-2">
            <div
              className="flex items-center gap-1 h-[100px]"
              style={{ width: `${timelineWidth}px` }}
            >
              {segments.map((segment, index) => (
                <TimelineSegment
                  key={`${segment.media_asset_id}-${index}`}
                  segment={segment}
                  pixelsPerMs={pixelsPerMs}
                  showTransition={index > 0}
                  onDelete={handleDeleteSegment}
                  isDeleting={deletingIndex === index}
                />
              ))}
            </div>

            {/* Beat markers */}
            <BeatMarkers
              totalDuration={total_duration_ms}
              pixelsPerMs={pixelsPerMs}
              beatsPerCut={settings_used.beats_per_cut}
            />
          </div>
        </div>
      </div>

      {/* Footer with info */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800/50 border-t border-gray-700 text-xs text-gray-500">
        <div className="flex items-center gap-4">
          <span>Segments: {segments.length}</span>
          <span>Duration: {formatDuration(total_duration_ms)}</span>
          <span>Transition: {settings_used.transition_type}</span>
          <span>Beats/cut: {settings_used.beats_per_cut}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded border-2 border-blue-500 bg-blue-900/50"></span>
            Image
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded border-2 border-green-500 bg-green-900/50"></span>
            Video
          </span>
        </div>
      </div>

      {/* Keyboard hint */}
      <div className="px-4 py-1 bg-gray-900 text-[10px] text-gray-600 text-center">
        Tip: Hold Ctrl/Cmd + scroll to zoom
      </div>
    </div>
  );
}

export default Timeline;
