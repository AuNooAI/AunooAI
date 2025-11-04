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
  generateAnalysis: () => Promise<void>;
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
  DATA: 'trendConvergence_data',
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

  // Load cached analysis data
  const loadStoredData = (): TrendConvergenceData | null => {
    try {
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
  const [data, setData] = useState<TrendConvergenceData | null>(loadStoredData);
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
  const generateAnalysis = useCallback(async () => {
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
      const result = await generateTrendConvergence(config);
      setData(result);

      // Save analysis data to localStorage
      try {
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
