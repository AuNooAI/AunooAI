/**
 * FH Tune Modal - Settings for Future Horizons Executive Summary
 *
 * Allows configuration of:
 * 1. Executive Summary generation settings
 * 2. Model and creativity (temperature) selection
 * 3. Organizational profile selection
 * 4. Regenerate executive summary option
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2, RefreshCw, Settings2, Building2, Sparkles } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';
import { TopicExecutiveSummary } from '@/types/horizonsExecutiveSummary';

interface AvailableModel {
  /** The id stored in config — must be a real litellm alias. */
  name: string;
  /** Human-readable label for the dropdown. */
  label?: string;
  provider?: string;
}

interface OrganizationalProfile {
  id: number;
  name: string;
  industry?: string;
  organization_type?: string;
}

interface FHTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Current state
  executiveSummary: TopicExecutiveSummary[] | null;
  executiveSummaryGeneratedAt: string | null;
  isGenerating: boolean;
  // Config from parent
  selectedProfileId: number | null;
  selectedModel: string;
  // Callbacks
  onProfileChange: (profileId: number | null) => void;
  onModelChange: (model: string) => void;
  onRegenerateExecutiveSummary: () => void;
  // Profiles list
  profiles: OrganizationalProfile[];
}

// User-friendly temperature presets
const CREATIVITY_PRESETS = [
  {
    value: '0.2',
    label: 'Precise',
    description: 'Highly focused analysis. Best for factual summaries.',
    color: 'bg-blue-100 text-blue-800'
  },
  {
    value: '0.4',
    label: 'Balanced',
    description: 'Mix of precision and insight. Recommended for executive summaries.',
    color: 'bg-green-100 text-green-800'
  },
  {
    value: '0.6',
    label: 'Exploratory',
    description: 'More varied perspectives. Good for strategic brainstorming.',
    color: 'bg-yellow-100 text-yellow-800'
  },
  {
    value: '0.8',
    label: 'Creative',
    description: 'Higher variety and novel insights. Best for scenario exploration.',
    color: 'bg-orange-100 text-orange-800'
  }
];

export function FHTuneModal({
  open,
  onOpenChange,
  executiveSummary,
  executiveSummaryGeneratedAt,
  isGenerating,
  selectedProfileId,
  selectedModel,
  onProfileChange,
  onModelChange,
  onRegenerateExecutiveSummary,
  profiles
}: FHTuneModalProps) {
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localModel, setLocalModel] = useState(selectedModel);
  const [localProfileId, setLocalProfileId] = useState<number | null>(selectedProfileId);
  const [localTemperature, setLocalTemperature] = useState('0.4');

  // Fetch available models when modal opens
  useEffect(() => {
    if (!open) return;

    const fetchModels = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch('/api/trend-convergence/models', { credentials: 'include' });
        if (res.ok) {
          // {id, name} — store the id as the value, the name as the label.
          const models = await res.json();
          setAvailableModels((models || []).map(
            (m: {id: string; name: string; provider?: string}) =>
              ({ name: m.id, label: m.name, provider: m.provider })));
        }
      } catch (err) {
        console.error('Failed to fetch models:', err);
        setError('Failed to load available models');
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
    // Reset local state to match parent state
    setLocalModel(selectedModel);
    setLocalProfileId(selectedProfileId);
  }, [open, selectedModel, selectedProfileId]);

  // Apply changes to parent
  const applyChanges = () => {
    if (localModel !== selectedModel) {
      onModelChange(localModel);
    }
    if (localProfileId !== selectedProfileId) {
      onProfileChange(localProfileId);
    }
  };

  // Handle regenerate with applied settings
  const handleRegenerate = () => {
    applyChanges();
    onRegenerateExecutiveSummary();
  };

  // Get creativity label
  const getCreativityLabel = (temp: string) => {
    const preset = CREATIVITY_PRESETS.find(p => p.value === temp);
    return preset?.label || 'Custom';
  };

  // Format the generated at date
  const formatGeneratedAt = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  const hasChanges = localModel !== selectedModel || localProfileId !== selectedProfileId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-indigo-500" />
            Future Horizons Settings
          </DialogTitle>
          <DialogDescription>
            Configure executive summary generation settings
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Executive Summary Status */}
          <div className="bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-indigo-900 dark:text-indigo-100 flex items-center gap-2">
                  <Sparkles className="w-4 h-4" />
                  Executive Summary
                </h3>
                <p className="text-sm text-indigo-700 dark:text-indigo-300 mt-1">
                  {executiveSummary && executiveSummary.length > 0
                    ? `${executiveSummary.length} summaries generated`
                    : 'Not yet generated'}
                </p>
                <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">
                  Last generated: {formatGeneratedAt(executiveSummaryGeneratedAt)}
                </p>
              </div>
              <button
                onClick={handleRegenerate}
                disabled={isGenerating}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-md hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    {executiveSummary ? 'Regenerate' : 'Generate'}
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div>
            <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 block mb-2">
              AI Model for Executive Summary
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Select the model to use for generating executive summaries
            </p>
            {loading ? (
              <div className="flex items-center gap-2 text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading models...
              </div>
            ) : (
              <Select value={localModel} onValueChange={setLocalModel}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {/* An already-saved model may no longer be offered; keep it listed
                      so the trigger is not blank. */}
                  {localModel && !availableModels.some(m => m.name === localModel) && (
                    <SelectItem value={localModel}>{localModel}</SelectItem>
                  )}
                  {availableModels.map((model) => (
                    <SelectItem key={model.name} value={model.name}>
                      {model.label || model.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {/* Creativity/Temperature */}
          <div>
            <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 block mb-2">
              Analysis Style
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Controls how creative vs. focused the executive summary analysis is
            </p>
            <Select value={localTemperature} onValueChange={setLocalTemperature}>
              <SelectTrigger className="w-full">
                <SelectValue>{getCreativityLabel(localTemperature)}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {CREATIVITY_PRESETS.map((preset) => (
                  <SelectItem key={preset.value} value={preset.value}>
                    <div className="flex flex-col">
                      <span className="font-medium">{preset.label}</span>
                      <span className="text-gray-500 text-xs">{preset.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Organizational Profile */}
          <div>
            <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 block mb-2 flex items-center gap-2">
              <Building2 className="w-4 h-4" />
              Organizational Context
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Executive summaries are tailored to your organization's context when a profile is selected
            </p>
            <Select
              value={localProfileId?.toString() || 'none'}
              onValueChange={(val) => setLocalProfileId(val === 'none' ? null : parseInt(val))}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select profile (optional)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No profile (generic analysis)</SelectItem>
                {profiles.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id.toString()}>
                    {profile.name}
                    {(profile.organization_type || profile.industry) && ` - ${profile.organization_type || profile.industry}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            <div className="text-sm text-gray-500">
              {hasChanges ? (
                <span className="text-orange-600 flex items-center gap-1">
                  <Settings2 className="w-4 h-4" />
                  Settings changed - regenerate to apply
                </span>
              ) : (
                <span className="text-green-600">Settings up to date</span>
              )}
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md text-sm font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
