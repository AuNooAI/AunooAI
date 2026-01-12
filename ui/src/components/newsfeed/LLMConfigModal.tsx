/**
 * Narrative Explorer Configuration Modal
 * Settings for model, profile, and topics for Highlights/Narratives generation
 */

import { useState, useEffect } from 'react';
import { Settings, Cpu, Building2, Save, RotateCcw, Tag, Check } from 'lucide-react';
import { type NewsFeedConfig, type AIModel, type OrganizationalProfile, type Topic } from '../../hooks/useNewsFeed';
import { type NarrativeExplorerConfig } from '../../hooks/useNarrativeExplorer';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Button } from '../ui/button';
import { Label } from '../ui/label';

interface LLMConfigModalProps {
  open: boolean;
  onClose: () => void;
  config: NewsFeedConfig;
  narrativeConfig: NarrativeExplorerConfig;
  topics: Topic[];
  models: AIModel[];
  profiles: OrganizationalProfile[];
  onConfigChange: (updates: Partial<NewsFeedConfig>) => void;
  onNarrativeConfigChange: (updates: Partial<NarrativeExplorerConfig>) => void;
}

export function LLMConfigModal({
  open,
  onClose,
  config,
  narrativeConfig,
  topics,
  models,
  profiles,
  onConfigChange,
  onNarrativeConfigChange,
}: LLMConfigModalProps) {
  const [localModel, setLocalModel] = useState(config.model || 'gpt-4o-mini');
  const [localProfileId, setLocalProfileId] = useState<number | undefined>(config.profileId);
  const [localSelectedTopics, setLocalSelectedTopics] = useState<string[]>(narrativeConfig.selectedTopics || []);

  // Sync local state when config changes
  useEffect(() => {
    setLocalModel(config.model || 'gpt-4o-mini');
    setLocalProfileId(config.profileId);
    setLocalSelectedTopics(narrativeConfig.selectedTopics || []);
  }, [config.model, config.profileId, narrativeConfig.selectedTopics, open]);

  const handleSave = () => {
    onConfigChange({
      model: localModel,
      profileId: localProfileId,
    });
    onNarrativeConfigChange({
      model: localModel,
      profileId: localProfileId,
      selectedTopics: localSelectedTopics,
    });
    onClose();
  };

  const handleReset = () => {
    setLocalModel('gpt-4o-mini');
    setLocalProfileId(undefined);
    setLocalSelectedTopics(topics.length > 0 ? [topics[0].name] : []);
  };

  const toggleTopic = (topicName: string) => {
    setLocalSelectedTopics(prev => {
      if (prev.includes(topicName)) {
        // Don't allow deselecting if it's the last one
        if (prev.length === 1) return prev;
        return prev.filter(t => t !== topicName);
      } else {
        return [...prev, topicName];
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Narrative Explorer Settings
          </DialogTitle>
          <DialogDescription>
            Configure AI model, profile, and topics for Incidents and Narratives generation
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Topics Selection for Highlights/Narratives */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Tag className="w-4 h-4" />
              Topics for Analysis
            </Label>
            <div className="flex flex-wrap gap-2 p-3 bg-gray-50 rounded-lg border max-h-32 overflow-y-auto">
              {topics.length > 0 ? (
                topics.map(topic => (
                  <button
                    key={topic.name}
                    type="button"
                    onClick={() => toggleTopic(topic.name)}
                    className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                      localSelectedTopics.includes(topic.name)
                        ? 'bg-pink-500 text-white'
                        : 'bg-white text-gray-700 border border-gray-200 hover:border-pink-300'
                    }`}
                  >
                    {localSelectedTopics.includes(topic.name) && (
                      <Check className="w-3 h-3" />
                    )}
                    {topic.name}
                  </button>
                ))
              ) : (
                <span className="text-sm text-gray-700 dark:text-gray-300">No topics available</span>
              )}
            </div>
            <p className="text-xs text-gray-700 dark:text-gray-300">
              Select one or more topics to analyze for Incidents and Narratives
            </p>
          </div>

          {/* Model Selection */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Cpu className="w-4 h-4" />
              AI Model
            </Label>
            <Select
              value={localModel}
              onValueChange={setLocalModel}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {models.length > 0 ? (
                  models.map(model => (
                    <SelectItem key={model.id} value={model.id}>
                      <div className="flex items-center gap-2">
                        <span>{model.name}</span>
                        <span className="text-xs text-gray-700 dark:text-gray-300">({model.provider})</span>
                      </div>
                    </SelectItem>
                  ))
                ) : (
                  <>
                    <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                    <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                    <SelectItem value="gpt-4.1-mini">GPT-4.1 Mini</SelectItem>
                    <SelectItem value="gpt-4.1">GPT-4.1</SelectItem>
                  </>
                )}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-700 dark:text-gray-300">
              The AI model used to analyze articles and generate insights
            </p>
          </div>

          {/* Organizational Profile Selection */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Building2 className="w-4 h-4" />
              Organizational Profile
            </Label>
            <Select
              value={localProfileId?.toString() || 'none'}
              onValueChange={(value) => setLocalProfileId(value === 'none' ? undefined : parseInt(value))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select profile" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">General Analysis</SelectItem>
                {profiles.map(profile => (
                  <SelectItem key={profile.id} value={profile.id.toString()}>
                    {profile.name} {profile.is_default && '(Default)'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-700 dark:text-gray-300">
              Organizational profiles customize the analysis to your organization's priorities
            </p>
          </div>

          {/* Info about what this affects */}
          <div className="p-3 bg-blue-50 rounded-lg border border-blue-100">
            <h4 className="text-sm font-medium text-blue-900 mb-1">These settings affect:</h4>
            <ul className="text-xs text-blue-700 space-y-1">
              <li>• <strong>Incidents</strong> - AI-identified incidents and key events</li>
              <li>• <strong>Narratives</strong> - Thematic article clustering and insights</li>
            </ul>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between">
          <Button variant="ghost" onClick={handleReset} className="gap-2">
            <RotateCcw className="w-4 h-4" />
            Reset
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              className="gap-2"
              disabled={localSelectedTopics.length === 0}
            >
              <Save className="w-4 h-4" />
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
