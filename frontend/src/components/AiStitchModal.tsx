import { useState, useEffect, useRef } from 'react';
import {
  planAndApply,
  startRender,
  getRenderStatus,
  type EditPlanV1,
  type ApplyResponse,
  type RenderJobStatus,
} from '../lib/aiApi';
import { api } from '../lib/api';

const SAMPLE_PROMPTS = [
  'Start with the image for 3 seconds, then play the full video clip',
  'Play the video first, then end with the image held for 2 seconds',
  'Show the image for 2 seconds, cut to the best 5 seconds of video, end on the image',
  'Loop the video twice, bookended by the image at the start and end',
];

interface MediaAsset {
  id: string;
  filename: string;
  media_type: string;
  processing_status: string;
  sort_order: number;
}

interface AiStitchModalProps {
  projectId: string;
  projectName: string;
  onClose: () => void;
}

export function AiStitchModal({ projectId, projectName, onClose }: AiStitchModalProps) {
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>([]);
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState<'no_audio' | 'with_audio'>('no_audio');
  const [transitionType, setTransitionType] = useState<'cut' | 'crossfade'>('cut');
  const [editPlan, setEditPlan] = useState<EditPlanV1 | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [applyResult, setApplyResult] = useState<ApplyResponse | null>(null);
  const [renderStatus, setRenderStatus] = useState<RenderJobStatus | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [isLoadingMedia, setIsLoadingMedia] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load project media on mount
  useEffect(() => {
    const loadMedia = async () => {
      setIsLoadingMedia(true);
      try {
        const response = await api.get(`/projects/${projectId}`);
        setMediaAssets(response.data.media_assets || []);
      } catch (err: any) {
        setError(err.message || 'Failed to load project details');
      } finally {
        setIsLoadingMedia(false);
      }
    };
    loadMedia();
  }, [projectId]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  // Fetch video as authenticated blob when render is complete
  useEffect(() => {
    if (renderStatus?.status !== 'complete') return;

    let cancelled = false;
    let objectUrl: string | null = null;

    api.get(`/projects/${projectId}/render/final/download`, { responseType: 'blob' })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setVideoUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load video preview');
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [renderStatus?.status, projectId]);

  const handleGeneratePlan = async () => {
    if (!projectId || !prompt.trim()) return;
    setIsGenerating(true);
    setError(null);
    setEditPlan(null);
    setWarnings([]);
    setApplyResult(null);
    setRenderStatus(null);
    setVideoUrl(null);
    try {
      const result = await planAndApply(projectId, prompt, {
        mode,
        transition_type: transitionType,
      });
      setEditPlan(result.edit_plan);
      setWarnings(result.warnings || []);
      setApplyResult({
        ok: result.ok,
        edl_hash: result.edl_hash,
        segment_count: result.segment_count,
        total_duration_ms: result.total_duration_ms,
      });
    } catch (err: any) {
      setError(err.message || 'Failed to generate plan');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleRender = async () => {
    if (!projectId || !applyResult) return;
    setIsRendering(true);
    setError(null);
    setRenderStatus(null);
    setVideoUrl(null);
    try {
      const result = await startRender(projectId);
      setRenderStatus({ status: result.status as RenderJobStatus['status'], id: result.job_id });

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const status = await getRenderStatus(projectId);
          setRenderStatus(status);
          if (status.status === 'complete' || status.status === 'failed' || status.status === 'cancelled') {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setIsRendering(false);
          }
        } catch {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setIsRendering(false);
        }
      }, 2000);
    } catch (err: any) {
      setError(err.message || 'Failed to start render');
      setIsRendering(false);
    }
  };

  if (!projectId) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black bg-opacity-60" onClick={onClose} />

      {/* Modal panel */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-gray-800 rounded-lg shadow-xl w-full max-w-5xl border border-gray-700">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-700">
            <h2 className="text-xl font-semibold text-white">
              AI Stitch — {projectName}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-200 text-xl font-bold leading-none"
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div className="p-6">
            {error && (
              <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300">
                {error}
                <button
                  onClick={() => setError(null)}
                  className="ml-3 text-red-400 hover:text-red-200 text-sm underline"
                >
                  Dismiss
                </button>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Panel - Controls */}
              <div className="space-y-4">
                {/* Media Assets */}
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <h2 className="text-sm font-medium text-gray-300 mb-2">Media Assets</h2>
                  {isLoadingMedia ? (
                    <p className="text-gray-400 text-sm">Loading media...</p>
                  ) : mediaAssets.length === 0 ? (
                    <p className="text-gray-500 text-sm">No media assets in this project.</p>
                  ) : (
                    <ul className="space-y-1 max-h-48 overflow-auto">
                      {mediaAssets.map((asset) => (
                        <li key={asset.id} className="text-sm text-gray-300 flex items-center gap-2">
                          <span className="inline-block w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                          <span className="truncate">{asset.filename}</span>
                          <span className="text-gray-500 text-xs ml-auto flex-shrink-0">{asset.media_type}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Prompt */}
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Prompt
                  </label>

                  {/* Sample prompt chips */}
                  <div className="flex flex-wrap gap-2 mb-3">
                    {SAMPLE_PROMPTS.map((sample) => (
                      <button
                        key={sample}
                        type="button"
                        onClick={() => setPrompt(sample)}
                        className="text-xs bg-gray-600 hover:bg-indigo-600 text-gray-300 hover:text-white px-2 py-1 rounded-md transition-colors text-left"
                      >
                        {sample}
                      </button>
                    ))}
                  </div>

                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Describe the video you want to create..."
                    rows={4}
                    className="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-3 py-2 text-sm placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-vertical"
                  />
                </div>

                {/* Mode & Transition */}
                <div className="bg-gray-700/50 rounded-lg p-4 space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Mode</label>
                    <div className="flex gap-4">
                      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                        <input
                          type="radio"
                          name="modal-mode"
                          value="no_audio"
                          checked={mode === 'no_audio'}
                          onChange={() => setMode('no_audio')}
                          className="accent-indigo-500"
                        />
                        No Audio
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                        <input
                          type="radio"
                          name="modal-mode"
                          value="with_audio"
                          checked={mode === 'with_audio'}
                          onChange={() => setMode('with_audio')}
                          className="accent-indigo-500"
                        />
                        With Audio
                      </label>
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Transition Type</label>
                    <select
                      value={transitionType}
                      onChange={(e) => setTransitionType(e.target.value as 'cut' | 'crossfade')}
                      className="w-full bg-gray-700 text-white border border-gray-600 rounded-md px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="cut">Cut</option>
                      <option value="crossfade">Crossfade</option>
                    </select>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="bg-gray-700/50 rounded-lg p-4 space-y-3">
                  <button
                    onClick={handleGeneratePlan}
                    disabled={!projectId || !prompt.trim() || isGenerating}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-md text-sm transition-colors"
                  >
                    {isGenerating ? 'Generating Plan...' : 'Generate Plan'}
                  </button>
                  <button
                    onClick={handleRender}
                    disabled={!applyResult || isRendering}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-md text-sm transition-colors"
                  >
                    {isRendering ? 'Rendering...' : 'Render Video'}
                  </button>
                </div>

                {/* Warnings */}
                {warnings.length > 0 && (
                  <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-yellow-400 mb-2">Warnings</h3>
                    <ul className="space-y-1">
                      {warnings.map((w, i) => (
                        <li key={i} className="text-sm text-yellow-300">{w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Apply Result */}
                {applyResult && (
                  <div className="bg-green-900/30 border border-green-700 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-green-400 mb-2">Plan Ready</h3>
                    <div className="text-sm text-green-300 space-y-1">
                      <p>Segments: {applyResult.segment_count}</p>
                      <p>Total duration: {(applyResult.total_duration_ms / 1000).toFixed(1)}s</p>
                      <p className="text-xs text-green-500 truncate">EDL hash: {applyResult.edl_hash}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Panel - Plan Viewer & Render */}
              <div className="space-y-4">
                {/* Plan JSON Viewer */}
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <h2 className="text-sm font-medium text-gray-300 mb-2">Edit Plan</h2>
                  {editPlan ? (
                    <pre className="text-xs text-green-400 bg-gray-900 p-4 rounded overflow-auto max-h-96">
                      {JSON.stringify(editPlan, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-gray-500 text-sm">
                      No plan generated yet. Enter a prompt and click "Generate Plan".
                    </p>
                  )}
                </div>

                {/* Render Status */}
                {renderStatus && renderStatus.status !== 'idle' && (
                  <div className="bg-gray-700/50 rounded-lg p-4">
                    <h2 className="text-sm font-medium text-gray-300 mb-2">Render Status</h2>
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                          renderStatus.status === 'complete'
                            ? 'bg-green-900/50 text-green-400'
                            : renderStatus.status === 'failed'
                              ? 'bg-red-900/50 text-red-400'
                              : renderStatus.status === 'cancelled'
                                ? 'bg-gray-700 text-gray-400'
                                : 'bg-blue-900/50 text-blue-400'
                        }`}
                      >
                        {renderStatus.status}
                      </span>
                      {renderStatus.progress_percent != null && (
                        <span className="text-sm text-gray-400">{renderStatus.progress_percent}%</span>
                      )}
                    </div>
                    {renderStatus.progress_percent != null && renderStatus.progress_percent > 0 && (
                      <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-indigo-500 h-2 rounded-full transition-all"
                          style={{ width: `${renderStatus.progress_percent}%` }}
                        />
                      </div>
                    )}
                    {renderStatus.progress_message && (
                      <p className="text-xs text-gray-400 mt-2">{renderStatus.progress_message}</p>
                    )}
                  </div>
                )}

                {/* Video Preview — shown when blob URL is ready */}
                {videoUrl && (
                  <div className="bg-gray-700/50 rounded-lg p-4">
                    <h2 className="text-sm font-medium text-gray-300 mb-2">Preview</h2>
                    <video
                      key={videoUrl}
                      controls
                      autoPlay
                      className="w-full rounded"
                      src={videoUrl}
                    />
                    <a
                      href={videoUrl}
                      download="render_final.mp4"
                      className="inline-block mt-3 bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-4 rounded-md text-sm transition-colors"
                    >
                      Download Video
                    </a>
                  </div>
                )}

                {/* Loading indicator while fetching blob */}
                {renderStatus?.status === 'complete' && !videoUrl && (
                  <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                    <p className="text-sm text-gray-400">Loading preview…</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
