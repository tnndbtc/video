/**
 * TimelineSettings - Settings panel for timeline generation
 */

import { useState, useEffect } from 'react';
import type { ProjectSettings } from '../types';

export interface TimelineSettingsProps {
  projectId: string;
  settings: ProjectSettings;
  isStale?: boolean;
  onSettingsChange: (settings: Partial<ProjectSettings>) => void;
  isLoading?: boolean;
}

const BEATS_PER_CUT_OPTIONS = [1, 2, 4, 8, 16] as const;

const TRANSITION_TYPES: { value: ProjectSettings['transition_type']; label: string }[] = [
  { value: 'cut', label: 'Cut (No transition)' },
  { value: 'crossfade', label: 'Crossfade' },
  { value: 'fade', label: 'Fade' },
];

export function TimelineSettings({
  settings,
  isStale,
  onSettingsChange,
  isLoading = false,
}: TimelineSettingsProps) {
  const [localSettings, setLocalSettings] = useState<Partial<ProjectSettings>>({
    beats_per_cut: settings.beats_per_cut,
    transition_type: settings.transition_type,
    transition_duration_ms: settings.transition_duration_ms,
    ken_burns_enabled: settings.ken_burns_enabled,
  });

  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setLocalSettings({
      beats_per_cut: settings.beats_per_cut,
      transition_type: settings.transition_type,
      transition_duration_ms: settings.transition_duration_ms,
      ken_burns_enabled: settings.ken_burns_enabled,
    });
    setHasChanges(false);
  }, [settings]);

  const updateSetting = <K extends keyof ProjectSettings>(key: K, value: ProjectSettings[K]) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleApply = () => {
    onSettingsChange(localSettings);
    setHasChanges(false);
  };

  const showTransitionDuration = localSettings.transition_type !== 'cut';

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Timeline Settings</h3>
        {isStale && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-yellow-600 text-yellow-100">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Stale
          </span>
        )}
      </div>

      <div className="space-y-4">
        {/* Beats per Cut */}
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-2">
            Beats per Cut
          </label>
          <div className="flex flex-wrap gap-2">
            {BEATS_PER_CUT_OPTIONS.map((beats) => (
              <button
                key={beats}
                type="button"
                onClick={() => updateSetting('beats_per_cut', beats)}
                className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  localSettings.beats_per_cut === beats
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {beats}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            How many beats between each cut
          </p>
        </div>

        {/* Transition Type */}
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-2">
            Transition Type
          </label>
          <select
            value={localSettings.transition_type}
            onChange={(e) => updateSetting('transition_type', e.target.value as ProjectSettings['transition_type'])}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {TRANSITION_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {/* Transition Duration (only shown when not 'cut') */}
        {showTransitionDuration && (
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-2">
              Transition Duration: {localSettings.transition_duration_ms}ms
            </label>
            <input
              type="range"
              min="100"
              max="1000"
              step="50"
              value={localSettings.transition_duration_ms}
              onChange={(e) => updateSetting('transition_duration_ms', parseInt(e.target.value, 10))}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>100ms</span>
              <span>1000ms</span>
            </div>
          </div>
        )}

        {/* Ken Burns Toggle */}
        <div>
          <label className="flex items-center gap-3 cursor-pointer">
            <div className="relative">
              <input
                type="checkbox"
                checked={localSettings.ken_burns_enabled}
                onChange={(e) => updateSetting('ken_burns_enabled', e.target.checked)}
                className="sr-only"
              />
              <div
                className={`w-10 h-5 rounded-full transition-colors ${
                  localSettings.ken_burns_enabled ? 'bg-blue-600' : 'bg-gray-600'
                }`}
              >
                <div
                  className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                    localSettings.ken_burns_enabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </div>
            </div>
            <span className="text-sm text-gray-300">Ken Burns Effect</span>
          </label>
          <p className="mt-1 text-xs text-gray-500 ml-13">
            Apply pan and zoom to images
          </p>
        </div>

        {/* Output Resolution (readonly) */}
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-1">
            Output Resolution
          </label>
          <div className="px-3 py-2 bg-gray-700/50 border border-gray-600 rounded text-sm text-gray-400">
            {settings.output_width} x {settings.output_height} @ {settings.output_fps}fps
          </div>
        </div>

        {/* Apply Button */}
        <button
          type="button"
          onClick={handleApply}
          disabled={!hasChanges || isLoading}
          className={`w-full px-4 py-2 rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2 ${
            hasChanges && !isLoading
              ? 'bg-blue-600 text-white hover:bg-blue-500'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
          }`}
        >
          {isLoading ? (
            <>
              <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Applying...
            </>
          ) : (
            'Apply Settings'
          )}
        </button>
      </div>
    </div>
  );
}

export default TimelineSettings;
