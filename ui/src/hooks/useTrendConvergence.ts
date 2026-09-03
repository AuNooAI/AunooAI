/**
 * Custom React hook for trend convergence analysis
 */

import { useState, useEffect, useCallback } from 'react';
import {
  generateTrendConvergence,
  loadCachedTrendConvergence,
  getPreviousAnalysis,
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
  setData: (data: TrendConvergenceData | MarketSignalsData | null) => void;
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  config: AnalysisConfig;

  // State
  loading: boolean;
  error: string | null;
  needsGeneration: boolean;

  // Actions
  generateAnalysis: (forceRefresh?: boolean) => Promise<void>;
  loadCached: () => Promise<void>;
  updateConfig: (updates: Partial<AnalysisConfig>) => void;
  clearError: () => void;
}

const DEFAULT_CONFIG: AnalysisConfig = {
  topic: '',
  timeframe_days: 365,
  // Flagship tier. On the Bedrock-routed tenants the old 'gpt-5' default
  // already resolved to claude-sonnet-4-5 via the litellm alias — this names
  // the same model honestly now that aliases are hidden from the model list.
  // Users can override via the AI Model picker.
  model: 'claude-sonnet-4-5',
  source_quality: 'all',
  sample_size_mode: 'auto',
  consistency_mode: 'balanced',
  enable_caching: true,
  cache_duration_hours: 24,
};

const STORAGE_KEYS = {
  CONFIG: 'trendConvergence_config',
  DATA: 'trendConvergence_data', // Legacy topic-agnostic key — purged on write, never read
  DATA_PREFIX: 'trendConvergence_data_', // Per-topic+tab keys — see tcDataKey()
  TOPIC: 'trendConvergence_topic'
};

// Cache key for one topic+tab pair. The topic MUST be part of the key:
// tab-only keys let one topic's cached analysis (and its analysis_id)
// surface under another topic. That is how a January "U.S. Federal R&D
// Pullback" executive summary ended up rendered beneath a fresh
// "Market Monitoring SOC Automation" run (2026-09-02).
export const tcDataKey = (topic: string, tab: string) =>
  `${STORAGE_KEYS.DATA_PREFIX}${topic}::${tab}`;

// Stored configs from before the flagship-default change carry a
// non-flagship ``model`` value the user never explicitly picked (it was
// whatever ``modelsData[0]`` resolved to at the time — typically
// ``gpt-4.1-mini`` or ``gpt-4o``). Migrate those to the current flagship
// default so the AI Model picker doesn't read the stale auto-pick. Any
// model NOT in this set is treated as a deliberate user choice and
// preserved.
const LEGACY_AUTO_PICK_MODELS = new Set([
  'gpt-4o-mini',
  'gpt-4.1-mini',
  'gpt-4o',
  'gpt-4.1',  // transient default after gpt-5 was first added but before
              // reasoning_effort wiring landed.
  'gpt-5',    // former default; on these tenants it routed to claude-sonnet-4-5
              // anyway — same model, now under its own name.
]);

export function useTrendConvergence(): UseTrendConvergenceReturn {
  // Load config from localStorage or use defaults
  const loadStoredConfig = (): AnalysisConfig => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.CONFIG);
      if (stored) {
        const merged = { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
        if (LEGACY_AUTO_PICK_MODELS.has(merged.model)) {
          merged.model = DEFAULT_CONFIG.model;
        }
        return merged;
      }
    } catch (err) {
      console.error('Error loading stored config:', err);
    }
    return DEFAULT_CONFIG;
  };

  // Load cached analysis data for the current topic+tab
  const loadStoredData = (topic?: string, tab?: string): TrendConvergenceData | MarketSignalsData | null => {
    try {
      if (topic && tab) {
        const stored = localStorage.getItem(tcDataKey(topic, tab));
        if (stored) {
          return JSON.parse(stored);
        }
      }
      // Deliberately NO fallback to the legacy `trendConvergence_data` key:
      // it is topic- and tab-agnostic, so it resurrects whatever analysis
      // last wrote it — for any topic.
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
  const [needsGeneration, setNeedsGeneration] = useState(false);

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

  // Load topic+tab-specific data when either changes
  useEffect(() => {
    if (config.tab && config.topic) {
      const cachedData = loadStoredData(config.topic, config.tab);
      if (cachedData) {
        setData(cachedData);
      }
    }
  }, [config.tab, config.topic]);

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

      // Pre-select the tenant's default organisational profile when none is
      // stored (or the stored one no longer exists). A fresh browser used to
      // start with the picker empty, and every analysis then ran with no
      // organisation context.
      if (profilesData.length > 0 && !profilesData.some(p => p.id === config.profile_id)) {
        const fallback = profilesData.find(p => p.is_default) || profilesData[0];
        if (fallback?.id) {
          setConfig(prev => ({ ...prev, profile_id: fallback.id }));
        }
      }

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

  // Load cached analysis only (localStorage then backend cache, never generates)
  const loadCached = useCallback(async () => {
    if (!config.topic || !config.tab) return;

    // 1. Check localStorage
    const tabKey = tcDataKey(config.topic, config.tab);
    const localData = localStorage.getItem(tabKey);
    if (localData) {
      try {
        setData(JSON.parse(localData));
        setNeedsGeneration(false);
        return;
      } catch (err) {
        console.error('Error parsing cached data:', err);
      }
    }

    // 2. Try backend cache_only endpoint
    try {
      const result = await loadCachedTrendConvergence(config);
      if (result) {
        setData(result);
        setNeedsGeneration(false);
        // Save to localStorage for next time
        try {
          localStorage.setItem(tabKey, JSON.stringify(result));
        } catch (err) {
          console.error('Error saving cached data to localStorage:', err);
        }
        return;
      }
    } catch (err) {
      console.error('Error loading cached analysis from backend:', err);
    }

    // 3. Fall back to the topic's last SAVED analysis (any model/settings).
    // The cache_only endpoint keys on the exact current config, so an
    // analysis generated with different settings (or with caching off) is
    // invisible to it even though it exists. Only accept the saved payload
    // if it actually carries data for the tab being viewed.
    try {
      // The server returns the newest saved version that carries this tab's
      // content (404 when none exists), so a later run of a different tab
      // does not bury the sample.
      const previous = await getPreviousAnalysis(config.topic, config.tab as string);
      if (previous) {
        setData(previous);
        setNeedsGeneration(false);
        return;
      }
    } catch {
      // 404 = genuinely nothing saved for this topic+tab; fall through.
    }

    // 4. No cache anywhere — user needs to generate
    setNeedsGeneration(true);
  }, [config]);

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
    setNeedsGeneration(false);

    try {
      let result: TrendConvergenceData | MarketSignalsData;

      // All tabs now use the unified trend convergence endpoint
      // If force refresh, disable caching temporarily
      const analysisConfig = forceRefresh
        ? { ...config, enable_caching: false }
        : config;

      result = await generateTrendConvergence(analysisConfig);

      setData(result);

      // Save analysis data to localStorage (per topic+tab)
      try {
        if (config.tab) {
          localStorage.setItem(tcDataKey(config.topic, config.tab), JSON.stringify(result));
        }
        // Purge the legacy topic-agnostic key so data written by old
        // builds can never resurface under a different topic.
        localStorage.removeItem(STORAGE_KEYS.DATA);
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
    setConfig(prev => {
      // No-op when nothing actually changes: keeping the same object identity
      // keeps loadCached (and every effect depending on it) stable. Without
      // this, a tab-switch effect that sets an unchanged tab re-created the
      // config on every render and hammered the cache_only endpoint in an
      // infinite fetch loop (ERR_INSUFFICIENT_RESOURCES in the browser).
      const changed = (Object.keys(updates) as (keyof AnalysisConfig)[])
        .some(k => prev[k] !== updates[k]);
      return changed ? { ...prev, ...updates } : prev;
    });
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    data,
    setData,
    topics,
    profiles,
    models,
    config,
    loading,
    error,
    needsGeneration,
    generateAnalysis,
    loadCached,
    updateConfig,
    clearError,
  };
}
