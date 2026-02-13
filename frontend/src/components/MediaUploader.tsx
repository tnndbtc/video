import { useState, useCallback, useRef } from 'react';
import { useUploadMedia } from '../hooks/useMedia';

interface MediaUploaderProps {
  projectId: string;
  onUploadComplete?: () => void;
}

const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const ACCEPTED_VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/webm'];
const ACCEPTED_TYPES = [...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_VIDEO_TYPES];
const ACCEPTED_EXTENSIONS = '.jpg,.jpeg,.png,.gif,.webp,.mp4,.mov,.webm';

function UploadIcon({ className = '' }: { className?: string }) {
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
        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
      />
    </svg>
  );
}

interface UploadResult {
  success: number;
  failed: { filename: string; error: string }[];
}

export function MediaUploader({ projectId, onUploadComplete }: MediaUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);

  const { mutate: uploadMedia, isPending: isUploading } = useUploadMedia(projectId);

  const validateFiles = useCallback((files: File[]): { valid: File[]; invalid: string[] } => {
    const valid: File[] = [];
    const invalid: string[] = [];

    files.forEach((file) => {
      if (ACCEPTED_TYPES.includes(file.type)) {
        valid.push(file);
      } else {
        invalid.push(`${file.name} - Invalid file type`);
      }
    });

    return { valid, invalid };
  }, []);

  const handleUpload = useCallback((files: File[]) => {
    const { valid, invalid } = validateFiles(files);

    if (valid.length === 0 && invalid.length > 0) {
      setUploadResult({
        success: 0,
        failed: invalid.map((error) => ({ filename: error.split(' - ')[0], error: 'Invalid file type' })),
      });
      return;
    }

    if (valid.length === 0) return;

    uploadMedia(valid, {
      onSuccess: (data) => {
        setUploadResult({
          success: data.total_uploaded,
          failed: [
            ...invalid.map((error) => ({ filename: error.split(' - ')[0], error: 'Invalid file type' })),
            ...data.failed,
          ],
        });
        onUploadComplete?.();
      },
      onError: (error) => {
        setUploadResult({
          success: 0,
          failed: valid.map((f) => ({
            filename: f.name,
            error: error instanceof Error ? error.message : 'Upload failed',
          })),
        });
      },
    });
  }, [uploadMedia, validateFiles, onUploadComplete]);

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
      handleUpload(files);
    }
  }, [handleUpload]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length > 0) {
      handleUpload(files);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [handleUpload]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const dismissResult = useCallback(() => {
    setUploadResult(null);
  }, []);

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`
          relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
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
          multiple
          accept={ACCEPTED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        <UploadIcon className={`w-12 h-12 mx-auto mb-4 ${isDragging ? 'text-blue-500' : 'text-gray-500'}`} />

        {isUploading ? (
          <div className="space-y-2">
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
            <p className="text-sm text-gray-500">Please wait while your files are being uploaded</p>
          </div>
        ) : (
          <>
            <p className={`font-medium mb-1 ${isDragging ? 'text-blue-400' : 'text-gray-300'}`}>
              {isDragging ? 'Drop files here' : 'Drop files here or click to upload'}
            </p>
            <p className="text-sm text-gray-500">
              Supports: JPG, PNG, GIF, WebP, MP4, MOV, WebM
            </p>
          </>
        )}
      </div>

      {/* Upload Result */}
      {uploadResult && (
        <div className={`rounded-lg p-4 ${uploadResult.failed.length > 0 && uploadResult.success === 0 ? 'bg-red-900/30 border border-red-700' : uploadResult.failed.length > 0 ? 'bg-yellow-900/30 border border-yellow-700' : 'bg-green-900/30 border border-green-700'}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              {uploadResult.success > 0 && (
                <p className="text-green-400 font-medium mb-1">
                  {uploadResult.success} file{uploadResult.success !== 1 ? 's' : ''} uploaded successfully
                </p>
              )}
              {uploadResult.failed.length > 0 && (
                <div className="space-y-1">
                  <p className="text-red-400 font-medium">
                    {uploadResult.failed.length} file{uploadResult.failed.length !== 1 ? 's' : ''} failed:
                  </p>
                  <ul className="text-sm text-red-300 space-y-0.5">
                    {uploadResult.failed.map((f, i) => (
                      <li key={i}>
                        {f.filename}: {f.error}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <button
              onClick={dismissResult}
              className="text-gray-400 hover:text-gray-300 p-1"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default MediaUploader;
