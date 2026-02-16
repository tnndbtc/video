/**
 * Drag and Drop MIME type for the timeline editor.
 *
 * Used for dragging media from MediaGrid -> Timeline (native HTML5 DnD).
 * Timeline internal reordering uses @dnd-kit (pointer-based, not HTML5 DnD).
 */

// For dragging media items from the media library INTO the timeline
export const DND_MEDIA_ID = 'application/x-beatstitch-media-id';
