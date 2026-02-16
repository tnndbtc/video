import { useState, useCallback } from 'react';
import type { MediaAsset } from '../types/media';
import { MediaCard } from './MediaCard';
import { DND_MEDIA_ID } from '../utils/dndTypes';

interface MediaGridProps {
  projectId: string;
  media: MediaAsset[];
  onReorder?: (newOrder: string[]) => void;
  onDelete?: (mediaId: string) => void;
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <svg
        className="w-16 h-16 text-gray-600 mb-4"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
        />
      </svg>
      <h3 className="text-lg font-medium text-gray-400 mb-1">No media files</h3>
      <p className="text-sm text-gray-500">
        Upload images or videos to get started
      </p>
    </div>
  );
}

export function MediaGrid({ projectId: _projectId, media, onReorder, onDelete }: MediaGridProps) {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

  const handleDragStart = useCallback((e: React.DragEvent<HTMLDivElement>, id: string) => {
    setDraggedId(id);
    e.dataTransfer.effectAllowed = 'copy';
    // Set both custom MIME type and text/plain for Safari compatibility
    e.dataTransfer.setData(DND_MEDIA_ID, id);
    e.dataTransfer.setData('text/plain', id);
    // Set drag image for better visual feedback
    if (e.currentTarget) {
      e.dataTransfer.setDragImage(e.currentTarget, 50, 50);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>, id: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (id !== draggedId) {
      setDragOverId(id);
    }
  }, [draggedId]);

  const handleDragLeave = useCallback(() => {
    setDragOverId(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    setDragOverId(null);

    if (!draggedId || draggedId === targetId || !onReorder) {
      setDraggedId(null);
      return;
    }

    // Create new order by moving draggedId to targetId position
    const currentOrder = media.map((m) => m.id);
    const draggedIndex = currentOrder.indexOf(draggedId);
    const targetIndex = currentOrder.indexOf(targetId);

    if (draggedIndex === -1 || targetIndex === -1) {
      setDraggedId(null);
      return;
    }

    // Remove dragged item and insert at target position
    const newOrder = [...currentOrder];
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, draggedId);

    onReorder(newOrder);
    setDraggedId(null);
  }, [draggedId, media, onReorder]);

  const handleDragEnd = useCallback(() => {
    setDraggedId(null);
    setDragOverId(null);
  }, []);

  if (media.length === 0) {
    return <EmptyState />;
  }

  // Sort media by sort_order
  const sortedMedia = [...media].sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {sortedMedia.map((asset) => (
        <div
          key={asset.id}
          draggable={true}
          onDragStart={(e) => handleDragStart(e, asset.id)}
          onDragOver={(e) => handleDragOver(e, asset.id)}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDrop(e, asset.id)}
          onDragEnd={handleDragEnd}
          className={`
            transition-all duration-200 cursor-grab
            ${draggedId === asset.id ? 'opacity-50 scale-95' : ''}
            ${dragOverId === asset.id ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-gray-900' : ''}
          `}
        >
          <MediaCard
            asset={asset}
            onDelete={onDelete}
          />
        </div>
      ))}
    </div>
  );
}

export default MediaGrid;
