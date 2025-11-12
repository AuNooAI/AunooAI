/**
 * Custom React hook for trend convergence analysis
 */

import { useState, useEffect, useCallback } from 'react';
import {
  generateTrendConvergence,
  getTopics,
  getOrganizationalProfiles,
  getAvailableModels,
  getMarketSignals,
  type TrendConvergenceData,
  type MarketSignalsData,
  type Topic,
  type OrganizationalProfile,
  type AIModel,
} from '../services/api';

export interface AnalysisConfig {
  topic: string;
  timeframe_days: number;
  model: string;
  source_quality: string;  // 'all' or 'high_quality'
  sample_size_mode: string;
  custom_limit?: number;
  consistency_mode: string;
  enable_caching: boolean;
  cache_duration_hours: number;
  profile_id?: number;
  tab?: string;  // Active tab: consensus, strategic, signals, timeline, horizons
  custom_prompt?: string;  // Custom prompt override for tuning
}

export interface UseTrendConvergenceReturn {
  // Data (can be either TrendConvergenceData or MarketSignalsData depending on tab)
  data: TrendConvergenceData | MarketSignalsData | null;
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
  source_quality: 'all',
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
  const loadStoredData = (tab?: string): TrendConvergenceData | MarketSignalsData | null => {
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
  const [data, setData] = useState<TrendConvergenceData | MarketSignalsData | null>(null);
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
  const generateAnalysis = useCallback(async (forceRefresh: boolean = false, skipQualityFallback: boolean = false) => {
    if (!config.topic) {
      setError('Please select a topic');
      return;
    }

    if (!config.model && config.tab !== 'signals') {
      // Market Signals doesn't use the model config (it uses the prompt's model)
      setError('Please select a model');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      let result: TrendConvergenceData | MarketSignalsData;

      // All tabs now use the unified trend convergence endpoint
      // If force refresh, disable caching temporarily
      const analysisConfig = forceRefresh
        ? { ...config, enable_caching: false }
        : config;

      result = await generateTrendConvergence(analysisConfig);

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
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate analysis';

      // Check if this is an API quota error
      if (errorMessage.includes('API quota exceeded') || errorMessage.includes('exceeded your current quota')) {
        import('../utils/toast').then(({ showError }) => {
          showError(
            `API quota exceeded for ${config.model}. Please switch to a different model (e.g., claude-3.5-sonnet or gpt-4o-mini).`,
            10000
          );
        });
        setError(errorMessage);
        return;
      }

      // Check if this is an API authentication error
      if (errorMessage.includes('API authentication failed') || errorMessage.includes('Invalid API key')) {
        import('../utils/toast').then(({ showError }) => {
          showError(
            `API authentication failed for ${config.model}. Please check your API key configuration.`,
            10000
          );
        });
        setError(errorMessage);
        return;
      }

      // Check if this is a service unavailable error
      if (errorMessage.includes('temporarily unavailable') || errorMessage.includes('overloaded')) {
        import('../utils/toast').then(({ showWarning }) => {
          showWarning(
            `AI service temporarily unavailable. Please try again in a few moments.`,
            8000
          );
        });
        setError(errorMessage);
        return;
      }

      // Check if this is a "no high-quality articles" error (only try fallback once)
      if (!skipQualityFallback && errorMessage.includes('No high-quality articles found') && config.source_quality === 'high_quality') {
        // Import toast utility dynamically
        import('../utils/toast').then(({ showWarning, showSuccess }) => {
          // Extract article count from error message
          const countMatch = errorMessage.match(/Found (\d+) total articles/);
          const articleCount = countMatch ? countMatch[1] : 'all available';

          // Show warning toast
          showWarning(
            `No high-quality articles available for ${config.topic} (${articleCount} total). Switching to All Sources...`,
            6000
          );

          // Automatically switch to 'all' sources
          console.log('No high-quality articles found, switching to all sources...');
          const newConfig = { ...config, source_quality: 'all' };
          setConfig(newConfig);

          // Save updated config
          try {
            localStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(newConfig));
          } catch (e) {
            console.error('Error saving updated config:', e);
          }

          // Clear error state and retry ONCE with skipQualityFallback=true
          setError(null);
          setTimeout(() => {
            generateAnalysis(forceRefresh, true).then(() => {
              // Show success toast after analysis completes
              showSuccess(`Analysis complete using ${articleCount} articles from all sources`, 5000);
            }).catch((retryErr) => {
              // If retry also fails, show error
              const retryErrorMsg = retryErr instanceof Error ? retryErr.message : 'Analysis failed';
              import('../utils/toast').then(({ showError }) => {
                showError(retryErrorMsg, 7000);
              });
              setError(retryErrorMsg);
            });
          }, 1000);
        });
      } else {
        // For other errors, show error toast
        import('../utils/toast').then(({ showError }) => {
          showError(errorMessage, 7000);
        });
        setError(errorMessage);
      }
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
