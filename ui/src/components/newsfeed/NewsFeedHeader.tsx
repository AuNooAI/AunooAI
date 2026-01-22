/**
 * News Feed Header - Full config controls matching news_feed_new.html
 * Multi-topic dropdown, model dropdown, profile dropdown, date range, filter
 */

import { useState, useRef, useEffect } from 'react';
import {
  Calendar,
  ChevronDown,
  RefreshCw,
  Check,
  X,
  Building2,
  Tag,
  Clock,
} from 'lucide-react';
import { type NewsFeedConfig, type Topic, type OrganizationalProfile, type AIModel } from '../../hooks/useNewsFeed';
import { type NarrativeExplorerConfig } from '../../hooks/useNarrativeExplorer';
import { type DateRange } from '../../services/newsFeedApi';
import { Button } from '../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface NewsFeedHeaderProps {
  config: NewsFeedConfig;
  narrativeConfig: NarrativeExplorerConfig;
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  loading: boolean;
  onConfigChange: (updates: Partial<NewsFeedConfig>) => void;
  onNarrativeConfigChange: (updates: Partial<NarrativeExplorerConfig>) => void;
  onRefresh: () => void;
  onScheduleClick?: () => void;
}

const dateRangeOptions: { value: DateRange; label: string }[] = [
  { value: '24h', label: 'Last 24 hours' },
  { value: '72h', label: 'Last 72 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '3m', label: 'Last 3 months' },
  { value: '1y', label: 'Last year' },
  { value: 'all', label: 'All time' },
];

export function NewsFeedHeader({
  config,
  narrativeConfig,
  topics,
  profiles,
  models,
  loading,
  onConfigChange,
  onNarrativeConfigChange,
  onRefresh,
  onScheduleClick,
}: NewsFeedHeaderProps) {
  const [topicDropdownOpen, setTopicDropdownOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [dateDropdownOpen, setDateDropdownOpen] = useState(false);

  // Use local state for model to match working pattern from LLMConfigModal
  const [localModel, setLocalModel] = useState(config.model || 'gpt-4o-mini');

  // Sync local model with config when it changes externally
  useEffect(() => {
    setLocalModel(config.model || 'gpt-4o-mini');
  }, [config.model]);

  const selectedTopics = narrativeConfig.selectedTopics || [];
  const selectedProfileId = config.profileId;

  // Get display label for profile
  const getProfileLabel = () => {
    if (!selectedProfileId) return 'General Analysis';
    const profile = profiles.find((p) => p.id === selectedProfileId);
    return profile?.name || 'General Analysis';
  };

  // Handle topic toggle
  const toggleTopic = (topicName: string) => {
    const newTopics = selectedTopics.includes(topicName)
      ? selectedTopics.filter((t) => t !== topicName)
      : [...selectedTopics, topicName];

    onNarrativeConfigChange({ selectedTopics: newTopics });
    // Also update the main config topic if single topic selected
    if (newTopics.length === 1) {
      onConfigChange({ topic: newTopics[0] });
    }
  };

  // Select all topics
  const selectAllTopics = () => {
    const allTopicNames = topics.map((t) => t.name);
    onNarrativeConfigChange({ selectedTopics: allTopicNames });
  };

  // Clear all topics
  const clearAllTopics = () => {
    onNarrativeConfigChange({ selectedTopics: [] });
    onConfigChange({ topic: undefined });
  };

  // Handle model change - update local state immediately, then propagate to parent
  const handleModelChange = (modelId: string) => {
    setLocalModel(modelId);
    onConfigChange({ model: modelId });
    onNarrativeConfigChange({ model: modelId });
  };

  // Handle profile change
  const setProfile = (profileId: number | undefined) => {
    onConfigChange({ profileId });
    onNarrativeConfigChange({ profileId });
    setProfileDropdownOpen(false);
  };

  // Handle date range change
  const handleDateRangeChange = (value: DateRange) => {
    onConfigChange({ dateRange: value, page: 1 });
    setDateDropdownOpen(false);
  };

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-3">
      <div className="flex items-center justify-between flex-wrap gap-4">
        {/* Left side - Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Topics Multi-Select Dropdown */}
          <div className="relative">
            <button
              onClick={() => setTopicDropdownOpen(!topicDropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-200 rounded-md hover:border-gray-300 min-w-[180px] justify-between"
            >
              <div className="flex items-center gap-2 truncate">
                <Tag className="w-4 h-4 text-gray-700 dark:text-gray-300 shrink-0" />
                <span className="truncate">
                  {selectedTopics.length === 0
                    ? 'Select Topics'
                    : selectedTopics.length === 1
                    ? selectedTopics[0]
                    : `${selectedTopics.length} topics`}
                </span>
              </div>
              {selectedTopics.length > 0 && (
                <span className="bg-pink-500 text-white text-xs px-1.5 py-0.5 rounded-full shrink-0">
                  {selectedTopics.length}
                </span>
              )}
              <ChevronDown className="w-4 h-4 text-gray-600 dark:text-gray-300 shrink-0" />
            </button>

            {topicDropdownOpen && (
              <DropdownMenu onClose={() => setTopicDropdownOpen(false)}>
                <div className="py-1">
                  <button
                    onClick={selectAllTopics}
                    className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Check className="w-4 h-4 text-gray-600 dark:text-gray-300" />
                    Select All
                  </button>
                  <button
                    onClick={clearAllTopics}
                    className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                  >
                    <X className="w-4 h-4 text-gray-600 dark:text-gray-300" />
                    Clear All
                  </button>
                  <div className="border-t border-gray-300 dark:border-gray-700 my-1" />
                  {topics.map((topic) => (
                    <button
                      key={topic.name}
                      onClick={() => toggleTopic(topic.name)}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Check
                        className={`w-4 h-4 ${
                          selectedTopics.includes(topic.name)
                            ? 'text-green-500'
                            : 'invisible'
                        }`}
                      />
                      {topic.name}
                    </button>
                  ))}
                </div>
              </DropdownMenu>
            )}
          </div>

          {/* Date Range Dropdown */}
          <div className="relative">
            <button
              onClick={() => setDateDropdownOpen(!dateDropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-200 rounded-md hover:border-gray-300 min-w-[150px] justify-between"
            >
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                <span>
                  {dateRangeOptions.find((o) => o.value === config.dateRange)?.label ||
                    'Date Range'}
                </span>
              </div>
              <ChevronDown className="w-4 h-4 text-gray-600 dark:text-gray-300" />
            </button>

            {dateDropdownOpen && (
              <DropdownMenu onClose={() => setDateDropdownOpen(false)}>
                <div className="py-1">
                  {dateRangeOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => handleDateRangeChange(option.value)}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Check
                        className={`w-4 h-4 ${
                          config.dateRange === option.value
                            ? 'text-green-500'
                            : 'invisible'
                        }`}
                      />
                      {option.label}
                    </button>
                  ))}
                </div>
              </DropdownMenu>
            )}
          </div>

          {/* Model Select */}
          <Select value={localModel} onValueChange={handleModelChange}>
            <SelectTrigger className="w-auto min-w-[140px]">
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              {models.length > 0 ? (
                models.map((model) => (
                  <SelectItem key={model.name} value={model.name}>
                    {model.name} ({model.provider})
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

          {/* Profile Dropdown */}
          <div className="relative">
            <button
              onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-200 rounded-md hover:border-gray-300 min-w-[160px] justify-between"
            >
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                <span className="truncate">{getProfileLabel()}</span>
              </div>
              <ChevronDown className="w-4 h-4 text-gray-600 dark:text-gray-300" />
            </button>

            {profileDropdownOpen && (
              <DropdownMenu onClose={() => setProfileDropdownOpen(false)}>
                <div className="py-1">
                  <button
                    onClick={() => setProfile(undefined)}
                    className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Check
                      className={`w-4 h-4 ${
                        !selectedProfileId ? 'text-green-500' : 'invisible'
                      }`}
                    />
                    General Analysis
                  </button>
                  {profiles.map((profile) => (
                    <button
                      key={profile.id}
                      onClick={() => setProfile(profile.id)}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Check
                        className={`w-4 h-4 ${
                          selectedProfileId === profile.id
                            ? 'text-green-500'
                            : 'invisible'
                        }`}
                      />
                      {profile.name}
                      {profile.is_default && (
                        <span className="text-xs text-gray-600 dark:text-gray-300">(Default)</span>
                      )}
                    </button>
                  ))}
                </div>
              </DropdownMenu>
            )}
          </div>
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center gap-2">
          {onScheduleClick && (
            <Button
              variant="outline"
              size="sm"
              onClick={onScheduleClick}
              title="Schedule automatic generation"
            >
              <Clock className="w-4 h-4" />
            </Button>
          )}
          <Button
            variant="default"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
            className="gap-2 bg-pink-500 hover:bg-pink-600"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Generating...' : 'Refresh'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Dropdown menu wrapper component
function DropdownMenu({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose();
      }
    };

    // Use requestAnimationFrame to skip the current event loop
    // This ensures the opening click completes before we listen for closes
    const frameId = requestAnimationFrame(() => {
      document.addEventListener('click', handleClickOutside);
    });

    return () => {
      cancelAnimationFrame(frameId);
      document.removeEventListener('click', handleClickOutside);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 mt-1 w-full min-w-[200px] bg-white border border-gray-200 rounded-md shadow-lg z-50 max-h-60 overflow-y-auto"
    >
      {children}
    </div>
  );
}
