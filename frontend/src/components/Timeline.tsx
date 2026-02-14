/**
 * Timeline - Main timeline viewer component for BeatStitch video editor
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import type { Timeline as TimelineType, PreviewSegment } from '../types/timeline';
import { TimelineSegment } from './TimelineSegment';
import { formatTimelineTime, formatDuration } from '../utils/formatTime';

export interface TimelineProps {
  timeline: TimelineType | null;
  previewSegments?: PreviewSegment[] | null;
  bpm?: number;
  beatsPerCut?: number;
  onDeleteMedia?: (mediaId: string) => void;
  onReorderMedia?: (fromIndex: number, toIndex: number) => void;
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
  bpm,
}: {
  totalDuration: number;
  pixelsPerMs: number;
  beatsPerCut: number;
  bpm?: number;
}) {
  const width = totalDuration * pixelsPerMs;
  // Use actual BPM if available, otherwise default to 120 BPM (500ms per beat)
  const beatIntervalMs = bpm ? Math.floor(60000 / bpm) : 500;
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

/**
 * Preview segment renderer for beat-synced timeline preview.
 * Simplified version of TimelineSegment for preview mode.
 */
function PreviewSegmentView({
  segment,
  pixelsPerMs,
  index,
  isLast,
  onDelete,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDragging,
  isDragOver,
}: {
  segment: PreviewSegment;
  pixelsPerMs: number;
  index: number;
  isLast: boolean;
  onDelete?: (mediaId: string) => void;
  onDragStart?: (e: React.DragEvent, index: number) => void;
  onDragOver?: (e: React.DragEvent, index: number) => void;
  onDrop?: (e: React.DragEvent, index: number) => void;
  onDragEnd?: () => void;
  isDragging?: boolean;
  isDragOver?: boolean;
}) {
  const width = Math.max(segment.duration_ms * pixelsPerMs, 40);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete) {
      onDelete(segment.media_id);
    }
  };

  return (
    <div
      className={`relative flex-shrink-0 h-[80px] cursor-grab active:cursor-grabbing transition-all ${
        isDragging ? 'opacity-50 scale-95' : ''
      } ${isDragOver ? 'translate-x-2' : ''}`}
      style={{ width: `${width}px` }}
      draggable={true}
      onDragStart={(e) => onDragStart?.(e, index)}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver?.(e, index);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop?.(e, index);
      }}
      onDragEnd={onDragEnd}
    >
      {/* Delete button */}
      <button
        onClick={handleDelete}
        className="absolute -top-2 -right-2 z-50 p-1 rounded-full bg-red-600 text-white hover:bg-red-700 shadow-lg border-2 border-white"
        title="Remove from timeline"
        draggable={false}
      >
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <div
        className={`relative h-full rounded-lg border-2 ${
          isLast ? 'border-purple-500 bg-gradient-to-b from-purple-900/50 to-purple-950/80' : 'border-blue-500 bg-gradient-to-b from-blue-900/50 to-blue-950/80'
        } overflow-hidden`}
      >
        {/* Thumbnail */}
        {segment.thumbnail_url ? (
          <img
            src={segment.thumbnail_url}
            alt={`Preview ${index + 1}`}
            className="w-full h-full object-cover"
            draggable={false}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-800 text-gray-500">
            {index + 1}
          </div>
        )}

        {/* Index badge */}
        <div className="absolute bottom-1 left-1 z-10">
          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-black/70 text-white">
            {index + 1}
          </span>
        </div>

        {/* Duration badge - moved to bottom right when delete button is present */}
        <div className={`absolute ${onDelete ? 'bottom-1 right-1' : 'top-1 right-1'} z-10`}>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-black/70 text-white">
            {(segment.duration_ms / 1000).toFixed(1)}s
          </span>
        </div>

        {/* Last segment indicator */}
        {isLast && (
          <div className="absolute top-1 left-1 z-10">
            <span className="px-1 py-0.5 rounded text-[8px] font-medium bg-purple-500/80 text-white">
              FILL
            </span>
          </div>
        )}

        {/* Hover tooltip */}
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80 transition-opacity pointer-events-none opacity-0 hover:opacity-100">
          <div className="text-center text-xs text-white p-2">
            <div className="font-medium mb-1">Preview {index + 1}</div>
            <div className="text-gray-300">
              {formatDuration(segment.duration_ms)}
            </div>
            <div className="text-gray-400 text-[10px] mt-1">
              {formatDuration(segment.timeline_in_ms)} - {formatDuration(segment.timeline_out_ms)}
            </div>
            {isLast && (
              <div className="text-purple-400 text-[10px] mt-1">
                Extends to fill audio
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Read-only timeline viewer component.
 * Displays timeline segments for preview - editing happens via media reordering.
 * Supports both rendered timeline and client-side preview segments.
 */
export function Timeline({ timeline, previewSegments, bpm, beatsPerCut: propBeatsPerCut, onDeleteMedia, onReorderMedia }: TimelineProps) {
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pixelsPerMs = ZOOM_LEVELS[zoomIndex];

  // Drag state for reordering
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const handleSegmentDragStart = useCallback((e: React.DragEvent, index: number) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  }, []);

  const handleSegmentDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (draggedIndex !== null && index !== draggedIndex) {
      setDragOverIndex(index);
    }
  }, [draggedIndex]);

  const handleSegmentDrop = useCallback((e: React.DragEvent, toIndex: number) => {
    e.preventDefault();
    if (draggedIndex !== null && draggedIndex !== toIndex && onReorderMedia) {
      onReorderMedia(draggedIndex, toIndex);
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  }, [draggedIndex, onReorderMedia]);

  const handleSegmentDragEnd = useCallback(() => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  }, []);

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

  // Determine if we're showing preview or rendered timeline
  // Preview mode takes priority - it reflects current settings (video length, beat rule)
  const isPreviewMode = previewSegments && previewSegments.length > 0;
  const isRenderedMode = !isPreviewMode && !!timeline;

  // Return null if nothing to show
  if (!isPreviewMode && !isRenderedMode) {
    return null;
  }

  // Calculate values based on mode
  const segments = isRenderedMode ? timeline.segments : null;
  const total_duration_ms = isRenderedMode
    ? timeline.total_duration_ms
    : previewSegments![previewSegments!.length - 1].timeline_out_ms;
  const settings_used = isRenderedMode ? timeline.settings_used : null;
  const beatsPerCut = settings_used?.beats_per_cut ?? propBeatsPerCut ?? 4;
  const timelineWidth = total_duration_ms * pixelsPerMs;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header with controls */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-4">
          <h3 className="text-sm font-medium text-white">
            {isPreviewMode ? 'Timeline Preview' : 'Timeline'}
          </h3>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            {isPreviewMode ? (
              <>
                <span className="text-amber-400 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                  </svg>
                  Beat-synced preview
                </span>
                <span className="text-gray-600">|</span>
                <span>{previewSegments!.length} segments</span>
                <span className="text-gray-600">|</span>
                <span>{formatDuration(total_duration_ms)}</span>
                {bpm && (
                  <>
                    <span className="text-gray-600">|</span>
                    <span>{Math.round(bpm)} BPM</span>
                  </>
                )}
              </>
            ) : (
              <>
                <span>{segments!.length} segments</span>
                <span className="text-gray-600">|</span>
                <span>{formatDuration(total_duration_ms)}</span>
                <span className="text-gray-600">|</span>
                <span>{settings_used!.transition_type}</span>
              </>
            )}
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
        className="overflow-x-auto overflow-y-visible"
      >
        <div style={{ minWidth: `${Math.max(timelineWidth, 100)}px` }}>
          {/* Time ruler */}
          <TimeRuler totalDuration={total_duration_ms} pixelsPerMs={pixelsPerMs} />

          {/* Segments track */}
          <div className="relative bg-gray-800 min-h-[100px] pt-5 pb-2 px-3">
            <div
              className="flex items-start gap-3 h-[80px]"
              style={{ width: `${timelineWidth}px` }}
            >
              {isRenderedMode ? (
                // Render actual timeline segments
                segments!.map((segment, index) => (
                  <TimelineSegment
                    key={`${segment.media_asset_id}-${index}`}
                    segment={segment}
                    pixelsPerMs={pixelsPerMs}
                    showTransition={index > 0}
                  />
                ))
              ) : (
                // Render preview segments
                previewSegments!.map((segment, index) => (
                  <PreviewSegmentView
                    key={`${segment.media_id}-${index}`}
                    segment={segment}
                    pixelsPerMs={pixelsPerMs}
                    index={index}
                    isLast={index === previewSegments!.length - 1}
                    onDelete={onDeleteMedia}
                    onDragStart={handleSegmentDragStart}
                    onDragOver={handleSegmentDragOver}
                    onDrop={handleSegmentDrop}
                    onDragEnd={handleSegmentDragEnd}
                    isDragging={draggedIndex === index}
                    isDragOver={dragOverIndex === index}
                  />
                ))
              )}
            </div>

            {/* Beat markers */}
            <BeatMarkers
              totalDuration={total_duration_ms}
              pixelsPerMs={pixelsPerMs}
              beatsPerCut={beatsPerCut}
              bpm={bpm}
            />
          </div>
        </div>
      </div>

      {/* Footer with info */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800/50 border-t border-gray-700 text-xs text-gray-500">
        <div className="flex items-center gap-4">
          {isPreviewMode ? (
            <>
              <span>Segments: {previewSegments!.length}</span>
              <span>Duration: {formatDuration(total_duration_ms)}</span>
              <span>Beats/cut: {beatsPerCut}</span>
              {bpm && <span>BPM: {Math.round(bpm)}</span>}
            </>
          ) : (
            <>
              <span>Segments: {segments!.length}</span>
              <span>Duration: {formatDuration(total_duration_ms)}</span>
              <span>Transition: {settings_used!.transition_type}</span>
              <span>Beats/cut: {settings_used!.beats_per_cut}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isPreviewMode ? (
            <>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded border-2 border-blue-500 bg-blue-900/50"></span>
                Segment
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded border-2 border-purple-500 bg-purple-900/50"></span>
                Last (fill)
              </span>
            </>
          ) : (
            <>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded border-2 border-blue-500 bg-blue-900/50"></span>
                Image
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded border-2 border-green-500 bg-green-900/50"></span>
                Video
              </span>
            </>
          )}
        </div>
      </div>

      {/* Keyboard hint */}
      <div className="px-4 py-1 bg-gray-900 text-[10px] text-gray-600 text-center">
        {isPreviewMode ? (
          <span>Preview based on beat rule • Click "Render Preview" to generate video</span>
        ) : (
          <span>Tip: Hold Ctrl/Cmd + scroll to zoom</span>
        )}
      </div>
    </div>
  );
}

export default Timeline;
