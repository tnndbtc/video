import { useState, useCallback, useRef } from 'react';
import { useUploadAudio, useBeatsStatus } from '../hooks/useMedia';
import { AudioStatus } from './ProcessingStatus';
import type { AudioTrack } from '../types/media';
import { API_BASE_URL } from '../config';

interface AudioUploaderProps {
  projectId: string;
  currentAudio?: AudioTrack | null;
}

const ACCEPTED_AUDIO_TYPES = [
  'audio/mpeg',
  'audio/mp3',
  'audio/wav',
  'audio/wave',
  'audio/x-wav',
  'audio/flac',
  'audio/aac',
  'audio/ogg',
  'audio/mp4',
  'audio/x-m4a',
];
const ACCEPTED_EXTENSIONS = '.mp3,.wav,.flac,.aac,.ogg,.m4a';

function MusicIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
      />
    </svg>
  );
}

function PlayIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 19.991c-1.25.687-2.779-.217-2.779-1.643V5.653z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function PauseIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M6.75 5.25a.75.75 0 01.75-.75H9a.75.75 0 01.75.75v13.5a.75.75 0 01-.75.75H7.5a.75.75 0 01-.75-.75V5.25zm7.5 0A.75.75 0 0115 4.5h1.5a.75.75 0 01.75.75v13.5a.75.75 0 01-.75.75H15a.75.75 0 01-.75-.75V5.25z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function AudioUploader({ projectId, currentAudio }: AudioUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const dragCounterRef = useRef(0);

  const { mutate: uploadAudio, isPending: isUploading } = useUploadAudio(projectId);
  const { data: beatsStatus } = useBeatsStatus(projectId);

  const validateFile = useCallback((file: File): boolean => {
    // Check by MIME type
    if (ACCEPTED_AUDIO_TYPES.includes(file.type)) {
      return true;
    }
    // Also check by extension for edge cases
    const ext = file.name.toLowerCase().split('.').pop();
    return ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].includes(ext || '');
  }, []);

  const handleUpload = useCallback((file: File) => {
    setError(null);

    if (!validateFile(file)) {
      setError('Invalid file type. Please upload an MP3, WAV, FLAC, AAC, OGG, or M4A file.');
      return;
    }

    uploadAudio(file, {
      onError: (err) => {
        setError(err instanceof Error ? err.message : 'Failed to upload audio');
      },
    });
  }, [uploadAudio, validateFile]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      // Only take the first file for audio
      handleUpload(files[0]);
    }
  }, [handleUpload]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length > 0) {
      handleUpload(files[0]);
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [handleUpload]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const togglePlayPause = useCallback(() => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  }, [isPlaying]);

  const handleAudioEnded = useCallback(() => {
    setIsPlaying(false);
  }, []);

  // Show current audio info if exists
  if (currentAudio) {
    const audioUrl = `${API_BASE_URL}/projects/${projectId}/audio/stream`;

    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        {/* Hidden audio element */}
        <audio
          ref={audioRef}
          src={audioUrl}
          onEnded={handleAudioEnded}
          onPause={() => setIsPlaying(false)}
          onPlay={() => setIsPlaying(true)}
        />

        <div className="flex items-start gap-4">
          {/* Play/Pause button */}
          <button
            onClick={togglePlayPause}
            className="flex-shrink-0 w-12 h-12 bg-blue-600 hover:bg-blue-500 rounded-lg flex items-center justify-center transition-colors"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <PauseIcon className="w-6 h-6 text-white" />
            ) : (
              <PlayIcon className="w-6 h-6 text-white" />
            )}
          </button>
          <div className="flex-1 min-w-0">
            <h4 className="text-white font-medium truncate" title={currentAudio.filename}>
              {currentAudio.filename}
            </h4>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-400">
              <span>{formatDuration(currentAudio.duration_ms)}</span>
              {currentAudio.bpm && <span>{currentAudio.bpm} BPM</span>}
              {currentAudio.sample_rate && <span>{(currentAudio.sample_rate / 1000).toFixed(1)} kHz</span>}
            </div>
            <div className="mt-2 flex items-center gap-3">
              <AudioStatus
                status={currentAudio.analysis_status}
                error={currentAudio.analysis_error}
              />
              {beatsStatus?.beat_count !== undefined && currentAudio.analysis_status === 'complete' && (
                <span className="text-xs text-gray-500">
                  {beatsStatus.beat_count} beats detected
                </span>
              )}
            </div>
          </div>
          <button
            onClick={handleClick}
            disabled={isUploading}
            className="flex-shrink-0 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-sm text-white rounded-lg transition-colors disabled:opacity-50"
          >
            Replace
          </button>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        {isUploading && (
          <div className="mt-3 flex items-center gap-2 text-sm text-blue-400">
            <svg
              className="animate-spin h-4 w-4"
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
            Uploading new audio...
          </div>
        )}

        {error && (
          <div className="mt-3 p-2 bg-red-900/30 border border-red-700 rounded text-sm text-red-400">
            {error}
          </div>
        )}
      </div>
    );
  }

  // Show upload area when no audio
  return (
    <div className="space-y-3">
      <div
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`
          border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
          transition-all duration-200
          ${isDragging
            ? 'border-blue-500 bg-blue-500/10'
            : 'border-gray-600 hover:border-gray-500 hover:bg-gray-800/50'
          }
          ${isUploading ? 'pointer-events-none opacity-50' : ''}
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        <MusicIcon className={`w-10 h-10 mx-auto mb-3 ${isDragging ? 'text-blue-500' : 'text-gray-500'}`} />

        {isUploading ? (
          <div className="flex items-center justify-center gap-2">
            <svg
              className="animate-spin h-5 w-5 text-blue-500"
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
            <span className="text-blue-400 font-medium">Uploading...</span>
          </div>
        ) : (
          <>
            <p className={`font-medium mb-1 ${isDragging ? 'text-blue-400' : 'text-gray-300'}`}>
              {isDragging ? 'Drop audio file here' : 'Drop audio or click to upload'}
            </p>
            <p className="text-sm text-gray-500">
              MP3, WAV, FLAC, AAC, OGG, M4A
            </p>
          </>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}

export default AudioUploader;
