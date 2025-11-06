/**
 * Custom React hook for trend convergence analysis
 */

import { useState, useEffect, useCallback } from 'react';
import {
  generateTrendConvergence,
  getTopics,
  getOrganizationalProfiles,
  getAvailableModels,
  type TrendConvergenceData,
  type Topic,
  type OrganizationalProfile,
  type AIModel,
} from '../services/api';

export interface AnalysisConfig {
  topic: string;
  timeframe_days: number;
  model: string;
  analysis_depth: string;
  sample_size_mode: string;
  custom_limit?: number;
  consistency_mode: string;
  enable_caching: boolean;
  cache_duration_hours: number;
  profile_id?: number;
  tab?: string;  // Active tab: consensus, strategic, signals, timeline, horizons
}

export interface UseTrendConvergenceReturn {
  // Data
  data: TrendConvergenceData | null;
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  config: AnalysisConfig;

  // State
  loading: boolean;
  error: string | null;

  // Actions
  generateAnalysis: (forceRefresh?: boolean) => Promise<void>;
  updateConfig: (updates: Partial<AnalysisConfig>) => void;
  clearError: () => void;
}

const DEFAULT_CONFIG: AnalysisConfig = {
  topic: '',
  timeframe_days: 365,
  model: 'gpt-4o',
  analysis_depth: 'standard',
  sample_size_mode: 'auto',
  consistency_mode: 'balanced',
  enable_caching: true,
  cache_duration_hours: 24,
};

const STORAGE_KEYS = {
  CONFIG: 'trendConvergence_config',
  DATA: 'trendConvergence_data', // Legacy key
  DATA_PREFIX: 'trendConvergence_data_', // Per-tab keys: trendConvergence_data_consensus, etc.
  TOPIC: 'trendConvergence_topic'
};

export function useTrendConvergence(): UseTrendConvergenceReturn {
  // Load config from localStorage or use defaults
  const loadStoredConfig = (): AnalysisConfig => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.CONFIG);
      if (stored) {
        return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
      }
    } catch (err) {
      console.error('Error loading stored config:', err);
    }
    return DEFAULT_CONFIG;
  };

  // Load cached analysis data for current tab
  const loadStoredData = (tab?: string): TrendConvergenceData | null => {
    try {
      // Try per-tab cache first
      if (tab) {
        const tabKey = `${STORAGE_KEYS.DATA_PREFIX}${tab}`;
        const stored = localStorage.getItem(tabKey);
        if (stored) {
          return JSON.parse(stored);
        }
      }
      // Fall back to legacy key
      const stored = localStorage.getItem(STORAGE_KEYS.DATA);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (err) {
      console.error('Error loading stored data:', err);
    }
    return null;
  };

  // State
  const [data, setData] = useState<TrendConvergenceData | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [profiles, setProfiles] = useState<OrganizationalProfile[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [config, setConfig] = useState<AnalysisConfig>(loadStoredConfig);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Save config to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(config));
      if (config.topic) {
        localStorage.setItem(STORAGE_KEYS.TOPIC, config.topic);
      }
    } catch (err) {
      console.error('Error saving config:', err);
    }
  }, [config]);

  // Load initial data
  useEffect(() => {
    loadInitialData();
  }, []);

  // Load tab-specific data when config.tab changes
  useEffect(() => {
    if (config.tab) {
      const cachedData = loadStoredData(config.tab);
      if (cachedData) {
        setData(cachedData);
      }
    }
  }, [config.tab]);

  const loadInitialData = async () => {
    try {
      const [topicsData, profilesData, modelsData] = await Promise.all([
        getTopics(),
        getOrganizationalProfiles(),
        getAvailableModels(),
      ]);

      setTopics(topicsData);
      setProfiles(profilesData);
      setModels(modelsData);

      // Set default topic if available and not already set
      if (topicsData.length > 0 && !config.topic) {
        setConfig(prev => ({ ...prev, topic: topicsData[0].name }));
      }

      // Set default model if available and not already set
      if (modelsData.length > 0 && !config.model) {
        setConfig(prev => ({ ...prev, model: modelsData[0].id }));
      }
    } catch (err) {
      console.error('Error loading initial data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load initial data');
    }
  };

  // Generate analysis
  const generateAnalysis = useCallback(async (forceRefresh: boolean = false) => {
    if (!config.topic) {
      setError('Please select a topic');
      return;
    }

    if (!config.model) {
      setError('Please select a model');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // If force refresh, disable caching temporarily
      const analysisConfig = forceRefresh
        ? { ...config, enable_caching: false }
        : config;

      const result = await generateTrendConvergence(analysisConfig);
      setData(result);

      // Save analysis data to localStorage (per-tab)
      try {
        if (config.tab) {
          const tabKey = `${STORAGE_KEYS.DATA_PREFIX}${config.tab}`;
          localStorage.setItem(tabKey, JSON.stringify(result));
        }
        // Also save to legacy key for backwards compatibility
        localStorage.setItem(STORAGE_KEYS.DATA, JSON.stringify(result));
      } catch (err) {
        console.error('Error saving analysis data:', err);
      }
    } catch (err) {
      console.error('Error generating analysis:', err);
      setError(err instanceof Error ? err.message : 'Failed to generate analysis');
    } finally {
      setLoading(false);
    }
  }, [config]);

  // Update configuration
  const updateConfig = useCallback((updates: Partial<AnalysisConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }));
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    data,
    topics,
    profiles,
    models,
    config,
    loading,
    error,
    generateAnalysis,
    updateConfig,
    clearError,
  };
}
