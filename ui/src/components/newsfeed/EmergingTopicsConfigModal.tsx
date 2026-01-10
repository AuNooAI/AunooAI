/**
 * Emerging Topics Config Modal - Configure Detection Settings
 */

import { useState, useEffect } from 'react';
import {
  Settings2,
  Info,
  Sliders,
  Save,
  RotateCcw,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Label } from '../ui/label';
import { Slider } from '../ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

export interface EmergingTopicsConfig {
  sampleSize: number;
  daysBack: number;
  distanceThreshold: number;
  minArticlesPerTheme: number;
  maxArticlesPerTheme: number;
  model: string;
}

interface AIModel {
  id: string;
  name: string;
  provider: string;
}

interface EmergingTopicsConfigModalProps {
  open: boolean;
  onClose: () => void;
  config: EmergingTopicsConfig;
  onSave: (config: EmergingTopicsConfig) => void;
  availableModels: AIModel[];
}

const DEFAULT_CONFIG: EmergingTopicsConfig = {
  sampleSize: 250,
  daysBack: 7,
  distanceThreshold: 0.85,
  minArticlesPerTheme: 3,
  maxArticlesPerTheme: 30,
  model: 'gpt-4o',
};

const STORAGE_KEY = 'emergingTopicsConfig';

export function loadEmergingTopicsConfig(): EmergingTopicsConfig {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
    }
  } catch (e) {
    console.error('Failed to load emerging topics config', e);
  }
  return DEFAULT_CONFIG;
}

export function saveEmergingTopicsConfigToStorage(config: EmergingTopicsConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

export function EmergingTopicsConfigModal({
  open,
  onClose,
  config: initialConfig,
  onSave,
  availableModels,
}: EmergingTopicsConfigModalProps) {
  const [config, setConfig] = useState<EmergingTopicsConfig>(initialConfig);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setConfig(initialConfig);
    }
  }, [open, initialConfig]);

  // Compute valid model options - use API models or fallback defaults
  const modelOptions = availableModels.length > 0
    ? availableModels
    : [
        { id: 'gpt-4o', name: 'gpt-4o', provider: 'openai' },
        { id: 'gpt-4o-mini', name: 'gpt-4o-mini', provider: 'openai' },
        { id: 'claude-sonnet-4-20250514', name: 'claude-sonnet-4', provider: 'anthropic' },
      ];

  // Ensure selected model exists in options, fallback to first option
  const selectedModel = modelOptions.find(m => m.id === config.model)?.id
    || modelOptions[0]?.id
    || 'gpt-4o';

  const handleSave = () => {
    saveEmergingTopicsConfigToStorage(config);
    onSave(config);
    onClose();
  };

  const handleReset = () => {
    setConfig(DEFAULT_CONFIG);
  };

  const updateField = <K extends keyof EmergingTopicsConfig>(
    field: K,
    value: EmergingTopicsConfig[K]
  ) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-auto min-w-[500px] max-w-[600px] max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            Emerging Topics Detection Settings
          </DialogTitle>
          <DialogDescription>
            Configure how emerging topics are detected and analyzed
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto overflow-x-hidden pr-2">
        <Tabs defaultValue="detection" className="mt-4">
          <TabsList className="w-full grid grid-cols-2">
            <TabsTrigger value="detection" className="gap-1 text-xs">
              <Sliders className="w-3.5 h-3.5" />
              Detection
            </TabsTrigger>
            <TabsTrigger value="info" className="gap-1 text-xs">
              <Info className="w-3.5 h-3.5" />
              Info
            </TabsTrigger>
          </TabsList>

          {/* Info Tab */}
          <TabsContent value="info" className="space-y-4 mt-4">
            <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <h4 className="font-semibold text-blue-900 dark:text-blue-100 flex items-center gap-2 mb-2">
                <Info className="w-4 h-4" />
                About Emerging Topics Detection
              </h4>
              <p className="text-sm text-blue-800 dark:text-blue-200">
                This system identifies emerging developments from your news articles.
                It samples recent high-novelty articles, proposes specific themes,
                then validates them with semantic search.
              </p>
            </div>

            <div className="space-y-3">
              <SettingInfo
                title="Sample Size"
                description="Number of recent articles to sample for theme proposal. Larger samples find more themes but take longer."
                recommended="250 articles"
              />
              <SettingInfo
                title="Days Back"
                description="How many days of articles to analyze. Shorter windows focus on very recent developments."
                recommended="7 days"
              />
              <SettingInfo
                title="Distance Threshold"
                description="Cosine distance threshold for assigning articles to themes. Higher values are more lenient and include more articles."
                recommended="0.85"
              />
              <SettingInfo
                title="Min Articles Per Theme"
                description="Minimum number of articles required for a theme to be considered valid. Lower values catch more niche topics."
                recommended="3 articles"
              />
              <SettingInfo
                title="Max Articles Per Theme"
                description="Maximum articles to assign to each theme. Limits theme size for focused analysis."
                recommended="30 articles"
              />
            </div>

            {/* Score Calculation */}
            <div className="bg-purple-50 dark:bg-purple-950 border border-purple-200 dark:border-purple-800 rounded-lg p-4 mt-4">
              <h4 className="font-semibold text-purple-900 dark:text-purple-100 mb-3">
                How Scores Are Calculated
              </h4>
              <p className="text-sm text-purple-800 dark:text-purple-200 mb-3">
                The composite score (0-100) combines four weighted components:
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-purple-700 dark:text-purple-300">
                  <span><strong>Volume (25%)</strong></span>
                  <span className="text-xs">10 articles = 50, 20+ = 100</span>
                </div>
                <div className="flex justify-between text-purple-700 dark:text-purple-300">
                  <span><strong>Velocity (30%)</strong></span>
                  <span className="text-xs">Recent growth rate</span>
                </div>
                <div className="flex justify-between text-purple-700 dark:text-purple-300">
                  <span><strong>Diversity (20%)</strong></span>
                  <span className="text-xs">7+ sources = 100</span>
                </div>
                <div className="flex justify-between text-purple-700 dark:text-purple-300">
                  <span><strong>Novelty (25%)</strong></span>
                  <span className="text-xs">Semantic uniqueness</span>
                </div>
              </div>
              <p className="text-xs text-purple-600 dark:text-purple-400 mt-3">
                Velocity compares articles in first vs second half of time window:
                accelerating (75-100), stable (50-75), decelerating (0-50).
              </p>
            </div>
          </TabsContent>

          {/* Detection Tab */}
          <TabsContent value="detection" className="space-y-6 mt-4">
            {/* AI Model */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">AI Model</Label>
              </div>
              <Select
                value={selectedModel}
                onValueChange={(v) => updateField('model', v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {model.name} ({model.provider})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-500">
                Model used for theme proposal and deep analysis
              </p>
            </div>

            {/* Sample Size */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">Sample Size</Label>
                <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {config.sampleSize} articles
                </span>
              </div>
              <Slider
                value={[config.sampleSize]}
                onValueChange={([value]) => updateField('sampleSize', value)}
                min={50}
                max={500}
                step={50}
                className="w-full"
              />
              <p className="text-xs text-gray-500">
                More articles = better coverage but slower detection
              </p>
            </div>

            {/* Days Back */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">Days Back</Label>
                <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {config.daysBack} days
                </span>
              </div>
              <Slider
                value={[config.daysBack]}
                onValueChange={([value]) => updateField('daysBack', value)}
                min={1}
                max={30}
                step={1}
                className="w-full"
              />
              <p className="text-xs text-gray-500">
                Shorter = recent developments only, Longer = more context
              </p>
            </div>

            {/* Distance Threshold */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">Distance Threshold</Label>
                <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {config.distanceThreshold.toFixed(2)}
                </span>
              </div>
              <Slider
                value={[config.distanceThreshold * 100]}
                onValueChange={([value]) => updateField('distanceThreshold', value / 100)}
                min={30}
                max={100}
                step={5}
                className="w-full"
              />
              <p className="text-xs text-gray-500">
                Higher = more lenient matching, Lower = stricter relevance
              </p>
            </div>

            {/* Min Articles Per Theme */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">Min Articles Per Theme</Label>
                <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {config.minArticlesPerTheme}
                </span>
              </div>
              <Slider
                value={[config.minArticlesPerTheme]}
                onValueChange={([value]) => updateField('minArticlesPerTheme', value)}
                min={2}
                max={20}
                step={1}
                className="w-full"
              />
              <p className="text-xs text-gray-500">
                Lower = catch niche topics, Higher = only well-covered topics
              </p>
            </div>

            {/* Max Articles Per Theme */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="font-medium">Max Articles Per Theme</Label>
                <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {config.maxArticlesPerTheme}
                </span>
              </div>
              <Slider
                value={[config.maxArticlesPerTheme]}
                onValueChange={([value]) => updateField('maxArticlesPerTheme', value)}
                min={10}
                max={100}
                step={5}
                className="w-full"
              />
              <p className="text-xs text-gray-500">
                Limits how many articles are analyzed per theme
              </p>
            </div>
          </TabsContent>
        </Tabs>
        </div>

        <DialogFooter className="flex items-center justify-between gap-2 border-t pt-4 mt-4 flex-shrink-0">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleReset} disabled={loading}>
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Reset
            </Button>
            <Button size="sm" onClick={handleSave} disabled={loading}>
              <Save className="w-3.5 h-3.5 mr-1.5" />
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SettingInfo({
  title,
  description,
  recommended,
}: {
  title: string;
  description: string;
  recommended: string;
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm">{title}</h5>
      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">{description}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
        <span className="font-medium">Recommended:</span> {recommended}
      </p>
    </div>
  );
}
