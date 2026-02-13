/**
 * Time formatting utility functions for BeatStitch video editor
 */

/**
 * Format milliseconds as MM:SS duration
 * @param ms - Duration in milliseconds
 * @returns Formatted string like "2:30"
 */
export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

/**
 * Format milliseconds as MM:SS:FF timecode (assuming 30fps)
 * @param ms - Time in milliseconds
 * @param fps - Frames per second (default 30)
 * @returns Formatted string like "00:02:15"
 */
export function formatTimecode(ms: number, fps: number = 30): string {
  const totalSeconds = ms / 1000;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const frames = Math.floor((totalSeconds % 1) * fps);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
}

/**
 * Format milliseconds as human-readable duration
 * @param ms - Duration in milliseconds
 * @returns Formatted string like "2m 30s" or "45s"
 */
export function formatDurationHuman(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }

  if (remainingSeconds === 0) {
    return `${minutes}m`;
  }

  return `${minutes}m ${remainingSeconds}s`;
}

/**
 * Format milliseconds for display on timeline ruler
 * @param ms - Time in milliseconds
 * @returns Formatted string like "0:05" or "1:30"
 */
export function formatTimelineTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}
