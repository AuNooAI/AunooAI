/**
 * Custom React hook for Narrative Explorer functionality
 * Handles Highlights (incident tracking) and Narratives (article insights)
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getIncidentTracking,
  getArticleInsights,
  getTopics,
  getOrganizationalProfiles,
  getAvailableModels,
  type Incident,
  type ArticleTheme,
  type IncidentTrackingResponse,
} from '../services/narrativeExplorerApi';

export type DateRange = '24h' | '7d' | '14d' | '30d' | '3m';

export interface NarrativeExplorerConfig {
  selectedTopics: string[];
  dateRange: DateRange;
  customStartDate?: string;
  customEndDate?: string;
  model: string;
  profileId?: number;
}

export interface Topic {
  name: string;
  description?: string;
}

export interface OrganizationalProfile {
  id: number;
  name: string;
  description?: string;
  is_default?: boolean;
}

export interface AIModel {
  id: string;
  name: string;
  provider: string;
}

export interface UseNarrativeExplorerReturn {
  // Data
  incidents: Incident[];
  themes: ArticleTheme[];
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  config: NarrativeExplorerConfig;
  incidentResponse: IncidentTrackingResponse | null;

  // State
  loadingHighlights: boolean;
  loadingNarratives: boolean;
  loadingInitial: boolean;
  highlightsError: string | null;
  narrativesError: string | null;
  isFromCache: boolean; // Whether current data is from cache
  cachedAt: string | null; // When the cached data was generated

  // Actions
  updateConfig: (updates: Partial<NarrativeExplorerConfig>) => void;
  generateHighlights: (forceRegenerate?: boolean) => Promise<void>;
  generateNarratives: (forceRegenerate?: boolean) => Promise<void>;
  generateAll: (forceRegenerate?: boolean) => Promise<void>;
  clearErrors: () => void;
}

const DEFAULT_CONFIG: NarrativeExplorerConfig = {
  selectedTopics: [],
  dateRange: '7d',
  model: 'gpt-4o-mini',
};

const STORAGE_KEY = 'narrativeExplorer_config';
const INCIDENTS_CACHE_KEY = 'narrativeExplorer_incidents';
const THEMES_CACHE_KEY = 'narrativeExplorer_themes';

// Cache structure for storing results
interface CacheEntry<T> {
  data: T;
  key: string; // Hash of topics+dateRange+model for cache validation
  cachedAt: string; // ISO date for display
  response?: IncidentTrackingResponse; // For incidents, store the full response
}

// Generate a cache key from config
function generateCacheKey(config: NarrativeExplorerConfig): string {
  return `${config.selectedTopics.sort().join(',')}_${config.dateRange}_${config.model}_${config.profileId || ''}`;
}

function getDaysFromRange(dateRange: DateRange): number {
  switch (dateRange) {
    case '24h': return 1;
    case '7d': return 7;
    case '14d': return 14;
    case '30d': return 30;
    case '3m': return 90;
    default: return 7;
  }
}

function getDateRange(dateRange: DateRange): { startDate: string; endDate: string } {
  const now = new Date();
  const endDate = now.toISOString().split('T')[0];
  const days = getDaysFromRange(dateRange);
  const startDateObj = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  const startDate = startDateObj.toISOString().split('T')[0];
  return { startDate, endDate };
}

export function useNarrativeExplorer(): UseNarrativeExplorerReturn {
  // Load config from localStorage
  const loadStoredConfig = (): NarrativeExplorerConfig => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
      }
    } catch (err) {
      console.error('Error loading stored config:', err);
    }
    return DEFAULT_CONFIG;
  };

  // State
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [themes, setThemes] = useState<ArticleTheme[]>([]);
  const [incidentResponse, setIncidentResponse] = useState<IncidentTrackingResponse | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [profiles, setProfiles] = useState<OrganizationalProfile[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [config, setConfig] = useState<NarrativeExplorerConfig>(loadStoredConfig);

  // Loading states
  const [loadingHighlights, setLoadingHighlights] = useState(false);
  const [loadingNarratives, setLoadingNarratives] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(true);

  // Error states
  const [highlightsError, setHighlightsError] = useState<string | null>(null);
  const [narrativesError, setNarrativesError] = useState<string | null>(null);

  // Cache states
  const [isFromCache, setIsFromCache] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  // Load cached data on mount
  useEffect(() => {
    const loadCachedData = () => {
      try {
        const cacheKey = generateCacheKey(config);

        // Try to load incidents cache
        const incidentsCacheStr = localStorage.getItem(INCIDENTS_CACHE_KEY);
        if (incidentsCacheStr) {
          const incidentsCache: CacheEntry<Incident[]> = JSON.parse(incidentsCacheStr);
          if (incidentsCache.key === cacheKey) {
            setIncidents(incidentsCache.data);
            if (incidentsCache.response) {
              setIncidentResponse(incidentsCache.response);
            }
            setIsFromCache(true);
            setCachedAt(incidentsCache.cachedAt);
          }
        }

        // Try to load themes cache
        const themesCacheStr = localStorage.getItem(THEMES_CACHE_KEY);
        if (themesCacheStr) {
          const themesCache: CacheEntry<ArticleTheme[]> = JSON.parse(themesCacheStr);
          if (themesCache.key === cacheKey) {
            setThemes(themesCache.data);
            setIsFromCache(true);
            if (!cachedAt) {
              setCachedAt(themesCache.cachedAt);
            }
          }
        }
      } catch (err) {
        console.error('Error loading cached data:', err);
      }
    };

    // Only load cache if we have topics selected
    if (config.selectedTopics.length > 0) {
      loadCachedData();
    }
  }, []); // Only run once on mount

  // Save config to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch (err) {
      console.error('Error saving config:', err);
    }
  }, [config]);

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [topicsData, profilesData, modelsData] = await Promise.all([
          getTopics().catch(() => []),
          getOrganizationalProfiles().catch(() => []),
          getAvailableModels().catch(() => []),
        ]);

        const safeTopics = Array.isArray(topicsData) ? topicsData : [];
        const safeProfiles = Array.isArray(profilesData) ? profilesData : [];
        const safeModels = Array.isArray(modelsData) ? modelsData : [];

        setTopics(safeTopics);
        setProfiles(safeProfiles);
        setModels(safeModels);

        // Set default profile if available
        const defaultProfile = safeProfiles.find(p => p.is_default);
        if (defaultProfile && !config.profileId) {
          setConfig(prev => ({ ...prev, profileId: defaultProfile.id }));
        }

        // Set default topic if none selected and topics available
        if (config.selectedTopics.length === 0 && safeTopics.length > 0) {
          setConfig(prev => ({ ...prev, selectedTopics: [safeTopics[0].name] }));
        }
      } catch (err) {
        console.error('Error loading initial data:', err);
      } finally {
        setLoadingInitial(false);
      }
    };

    loadInitialData();
  }, []);

  // Generate Highlights (Incident Tracking)
  const generateHighlights = useCallback(async (forceRegenerate: boolean = false) => {
    if (config.selectedTopics.length === 0) {
      setHighlightsError('Please select at least one topic');
      return;
    }

    setLoadingHighlights(true);
    setHighlightsError(null);
    setIsFromCache(false); // Clear cache flag when generating

    try {
      const { startDate, endDate } = getDateRange(config.dateRange);
      const response = await getIncidentTracking({
        topics: config.selectedTopics,
        startDate,
        endDate,
        daysLimit: getDaysFromRange(config.dateRange),
        model: config.model,
        forceRegenerate,
        profileId: config.profileId,
      });

      const newIncidents = response.incidents || [];
      setIncidents(newIncidents);
      setIncidentResponse(response);

      // Save to cache
      const cacheKey = generateCacheKey(config);
      const cachedAtTime = new Date().toISOString();
      const cacheEntry: CacheEntry<Incident[]> = {
        data: newIncidents,
        key: cacheKey,
        cachedAt: cachedAtTime,
        response,
      };
      try {
        localStorage.setItem(INCIDENTS_CACHE_KEY, JSON.stringify(cacheEntry));
      } catch (cacheErr) {
        console.warn('Failed to cache incidents:', cacheErr);
      }
      setCachedAt(cachedAtTime);
    } catch (err) {
      console.error('Error generating highlights:', err);
      setHighlightsError(err instanceof Error ? err.message : 'Failed to generate highlights');
    } finally {
      setLoadingHighlights(false);
    }
  }, [config]);

  // Generate Narratives (Article Insights)
  const generateNarratives = useCallback(async (forceRegenerate: boolean = false) => {
    if (config.selectedTopics.length === 0) {
      setNarrativesError('Please select at least one topic');
      return;
    }

    setLoadingNarratives(true);
    setNarrativesError(null);

    try {
      const { startDate, endDate } = getDateRange(config.dateRange);

      // Fetch themes for each selected topic and combine
      const allThemes: ArticleTheme[] = [];

      for (const topic of config.selectedTopics) {
        try {
          const topicThemes = await getArticleInsights({
            topic,
            startDate,
            endDate,
            daysLimit: getDaysFromRange(config.dateRange),
            model: config.model,
            forceRegenerate,
          });
          allThemes.push(...topicThemes);
        } catch (err) {
          console.warn(`Failed to get insights for topic ${topic}:`, err);
        }
      }

      setThemes(allThemes);

      // Save to cache
      const cacheKey = generateCacheKey(config);
      const cachedAtTime = new Date().toISOString();
      const cacheEntry: CacheEntry<ArticleTheme[]> = {
        data: allThemes,
        key: cacheKey,
        cachedAt: cachedAtTime,
      };
      try {
        localStorage.setItem(THEMES_CACHE_KEY, JSON.stringify(cacheEntry));
      } catch (cacheErr) {
        console.warn('Failed to cache themes:', cacheErr);
      }
      setCachedAt(cachedAtTime);
    } catch (err) {
      console.error('Error generating narratives:', err);
      setNarrativesError(err instanceof Error ? err.message : 'Failed to generate narratives');
    } finally {
      setLoadingNarratives(false);
    }
  }, [config]);

  // Generate both
  const generateAll = useCallback(async (forceRegenerate: boolean = false) => {
    await Promise.all([
      generateHighlights(forceRegenerate),
      generateNarratives(forceRegenerate),
    ]);
  }, [generateHighlights, generateNarratives]);

  // Update config
  const updateConfig = useCallback((updates: Partial<NarrativeExplorerConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }));
  }, []);

  // Clear errors
  const clearErrors = useCallback(() => {
    setHighlightsError(null);
    setNarrativesError(null);
  }, []);

  return {
    incidents,
    themes,
    topics,
    profiles,
    models,
    config,
    incidentResponse,
    loadingHighlights,
    loadingNarratives,
    loadingInitial,
    highlightsError,
    narrativesError,
    isFromCache,
    cachedAt,
    updateConfig,
    generateHighlights,
    generateNarratives,
    generateAll,
    clearErrors,
  };
}
