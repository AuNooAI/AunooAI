/**
 * Custom React hook for Narrative Explorer functionality
 * Handles Highlights (incident tracking) and Narratives (article insights)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getIncidentTracking,
  getArticleInsights,
  getTopics,
  getOrganizationalProfiles,
  getAvailableModels,
  getNarrativesConfig,
  getIncidentConfigFromStorage,
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
  model: 'bedrock-kimi-k2-5',
};

// Stored configs from before the default change carry a model the user never
// explicitly picked. Same pattern as useNewsFeed / useTrendConvergence.
const LEGACY_AUTO_PICK_MODELS = new Set([
  'gpt-4o-mini',
  'gpt-4o',
]);

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

  // Track the last cache key we loaded to avoid duplicate loads
  const lastLoadedCacheKeyRef = useRef<string | null>(null);
  const hasAutoLoadedRef = useRef<boolean>(false);

  // Auto-load incidents from backend cache when topics become available
  // This ensures scheduled runs and previous generations are shown on page load
  useEffect(() => {
    const autoLoadFromBackend = async () => {
      // Skip if we've already auto-loaded, or no topics available, or still loading initial data
      if (hasAutoLoadedRef.current || topics.length === 0 || loadingInitial) {
        return;
      }

      // Get effective topics (selected or all)
      const effectiveTopics = config.selectedTopics.length > 0
        ? config.selectedTopics
        : topics.slice(0, 25).map(t => t.name);

      if (effectiveTopics.length === 0) {
        return;
      }

      console.log('[useNarrativeExplorer] Auto-loading from backend cache...', { effectiveTopics });
      hasAutoLoadedRef.current = true;

      // Show loading indicators during auto-load
      setLoadingHighlights(true);
      setLoadingNarratives(true);

      // Load cached incident config
      const incidentConfig = getIncidentConfigFromStorage();

      // Calculate date range
      const { startDate, endDate } = getDateRange(config.dateRange);

      try {
        // Fetch incidents from backend (will return cached data if available)
        const response = await getIncidentTracking({
          topics: effectiveTopics,
          startDate,
          endDate,
          daysLimit: getDaysFromRange(config.dateRange),
          model: config.model,
          forceRegenerate: false, // Use cached data if available
          profileId: config.profileId,
          systemPrompt: incidentConfig?.system_prompt,
          userPrompt: incidentConfig?.user_prompt,
          baseOntology: incidentConfig?.base_ontology,
          analysisInstructions: incidentConfig?.analysis_instructions,
          qualityGuidelines: incidentConfig?.quality_guidelines,
        });

        if (response.incidents && response.incidents.length > 0) {
          console.log('[useNarrativeExplorer] Loaded incidents from backend cache', {
            count: response.incidents.length,
            timestamp: response.analysis_timestamp
          });
          setIncidents(response.incidents);
          setIncidentResponse(response);
          setIsFromCache(true);
          setCachedAt(response.analysis_timestamp || new Date().toISOString());
        }
      } catch (err) {
        console.log('[useNarrativeExplorer] No cached incidents available:', err);
        // Not an error - just no cached data
      } finally {
        setLoadingHighlights(false);
      }

      try {
        // Also try to load narratives for each topic
        const narrativesConfig = getNarrativesConfig();
        const allThemes: ArticleTheme[] = [];

        for (const topic of effectiveTopics) {
          try {
            const topicThemes = await getArticleInsights({
              topic,
              startDate,
              endDate,
              daysLimit: getDaysFromRange(config.dateRange),
              model: config.model,
              forceRegenerate: false, // Use cached data if available
              systemPrompt: narrativesConfig?.system_prompt,
              userPrompt: narrativesConfig?.user_prompt,
            });
            allThemes.push(...topicThemes);
          } catch {
            // Skip topics without cached data
          }
        }

        if (allThemes.length > 0) {
          console.log('[useNarrativeExplorer] Loaded narratives from backend cache', {
            count: allThemes.length
          });
          setThemes(allThemes);
        }
      } catch (err) {
        console.log('[useNarrativeExplorer] No cached narratives available:', err);
      } finally {
        setLoadingNarratives(false);
      }
    };

    autoLoadFromBackend();
  }, [topics, loadingInitial, config.selectedTopics, config.dateRange, config.model, config.profileId]);

  // Load cached data from localStorage when config changes (as fallback)
  useEffect(() => {
    const loadCachedData = () => {
      // Skip if no topics selected
      if (config.selectedTopics.length === 0) {
        return;
      }

      const cacheKey = generateCacheKey(config);

      // Skip if we already loaded this cache key
      if (lastLoadedCacheKeyRef.current === cacheKey) {
        return;
      }

      try {
        let loadedSomething = false;
        let cacheTime: string | null = null;

        // Try to load incidents cache
        const incidentsCacheStr = localStorage.getItem(INCIDENTS_CACHE_KEY);
        if (incidentsCacheStr) {
          const incidentsCache: CacheEntry<Incident[]> = JSON.parse(incidentsCacheStr);
          if (incidentsCache.key === cacheKey) {
            console.log('[useNarrativeExplorer] Loading cached incidents from localStorage', {
              count: incidentsCache.data.length,
              cachedAt: incidentsCache.cachedAt
            });
            setIncidents(incidentsCache.data);
            if (incidentsCache.response) {
              setIncidentResponse(incidentsCache.response);
            }
            loadedSomething = true;
            cacheTime = incidentsCache.cachedAt;
          }
        }

        // Try to load themes cache
        const themesCacheStr = localStorage.getItem(THEMES_CACHE_KEY);
        if (themesCacheStr) {
          const themesCache: CacheEntry<ArticleTheme[]> = JSON.parse(themesCacheStr);
          if (themesCache.key === cacheKey) {
            console.log('[useNarrativeExplorer] Loading cached themes from localStorage', {
              count: themesCache.data.length,
              cachedAt: themesCache.cachedAt
            });
            setThemes(themesCache.data);
            loadedSomething = true;
            if (!cacheTime) {
              cacheTime = themesCache.cachedAt;
            }
          }
        }

        if (loadedSomething) {
          setIsFromCache(true);
          setCachedAt(cacheTime);
        }

        // Mark this cache key as loaded (even if nothing was found)
        lastLoadedCacheKeyRef.current = cacheKey;
      } catch (err) {
        console.error('Error loading cached data:', err);
      }
    };

    loadCachedData();
  }, [config.selectedTopics, config.dateRange, config.model, config.profileId]);

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
    // When no topics selected, use all available topics (up to 25)
    const effectiveTopics = config.selectedTopics.length > 0
      ? config.selectedTopics
      : topics.slice(0, 25).map(t => t.name);

    console.log('[useNarrativeExplorer] generateHighlights called', {
      forceRegenerate,
      selectedTopics: config.selectedTopics,
      effectiveTopics,
      dateRange: config.dateRange,
      model: config.model
    });

    if (effectiveTopics.length === 0) {
      console.log('[useNarrativeExplorer] No topics available, skipping highlights');
      setHighlightsError('No topics available. Please wait for topics to load.');
      return;
    }

    setLoadingHighlights(true);
    setHighlightsError(null);
    setIsFromCache(false); // Clear cache flag when generating
    lastLoadedCacheKeyRef.current = null; // Reset so cache can be reloaded later

    try {
      const { startDate, endDate } = getDateRange(config.dateRange);
      console.log('[useNarrativeExplorer] Calling getIncidentTracking', { startDate, endDate, topics: effectiveTopics });

      // Load custom incident config from localStorage
      const incidentConfig = getIncidentConfigFromStorage();

      const response = await getIncidentTracking({
        topics: effectiveTopics,
        startDate,
        endDate,
        daysLimit: getDaysFromRange(config.dateRange),
        model: config.model,
        forceRegenerate,
        profileId: config.profileId,
        // Pass custom configuration if saved
        systemPrompt: incidentConfig?.system_prompt,
        userPrompt: incidentConfig?.user_prompt,
        baseOntology: incidentConfig?.base_ontology,
        analysisInstructions: incidentConfig?.analysis_instructions,
        qualityGuidelines: incidentConfig?.quality_guidelines,
      });

      const newIncidents = response.incidents || [];
      console.log('[useNarrativeExplorer] Got incidents response', { count: newIncidents.length, response });
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
      console.error('[useNarrativeExplorer] Error generating highlights:', err);
      setHighlightsError(err instanceof Error ? err.message : 'Failed to generate highlights');
    } finally {
      console.log('[useNarrativeExplorer] generateHighlights finished');
      setLoadingHighlights(false);
    }
  }, [config, topics]);

  // Generate Narratives (Article Insights)
  const generateNarratives = useCallback(async (forceRegenerate: boolean = false) => {
    // When no topics selected, use all available topics (up to 25)
    const effectiveTopics = config.selectedTopics.length > 0
      ? config.selectedTopics
      : topics.slice(0, 25).map(t => t.name);

    if (effectiveTopics.length === 0) {
      setNarrativesError('No topics available. Please wait for topics to load.');
      return;
    }

    setLoadingNarratives(true);
    setNarrativesError(null);
    lastLoadedCacheKeyRef.current = null; // Reset so cache can be reloaded later

    try {
      const { startDate, endDate } = getDateRange(config.dateRange);

      // Load custom narratives config from localStorage
      const narrativesConfig = getNarrativesConfig();

      // Fetch themes for each selected topic and combine
      const allThemes: ArticleTheme[] = [];

      for (const topic of effectiveTopics) {
        try {
          const topicThemes = await getArticleInsights({
            topic,
            startDate,
            endDate,
            daysLimit: getDaysFromRange(config.dateRange),
            model: config.model,
            forceRegenerate,
            // Pass custom prompts if configured
            systemPrompt: narrativesConfig?.system_prompt,
            userPrompt: narrativesConfig?.user_prompt,
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
  }, [config, topics]);

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
