/**
 * Custom React hook for news feed functionality
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getNewsFeedArticles,
  getSixArticles,
  getAvailableDates,
  getSixArticlesConfig,
  saveSixArticlesConfig,
  getTopics,
  getOrganizationalProfiles,
  getAvailableModels,
  groupArticlesByCategory,
  getCategoryCounts,
  getLatestDashboardSnapshot,
  type NewsArticle,
  type SixArticlesReport,
  type AvailableDate,
  type SixArticlesConfig,
  type DateRange,
  type Persona,
} from '../services/newsFeedApi';

export interface NewsFeedConfig {
  dateRange: DateRange;
  customDateStart?: string;
  customDateEnd?: string;
  topic?: string;
  page: number;
  perPage: number;
  profileId?: number;
  model: string;
  persona: Persona;
  articleCount: number;
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

export interface UseNewsFeedReturn {
  // Data
  articles: NewsArticle[];
  groupedArticles: Record<string, NewsArticle[]>;
  categoryCounts: Record<string, number>;  // True database counts per category
  sixArticles: SixArticlesReport | null;
  availableDates: AvailableDate[];
  categories: string[];
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  config: NewsFeedConfig;
  sixArticlesConfig: SixArticlesConfig;

  // Pagination
  totalArticles: number;
  totalPages: number;

  // State
  loading: boolean;
  loadingSixArticles: boolean;
  error: string | null;

  // Actions
  updateConfig: (updates: Partial<NewsFeedConfig>) => void;
  fetchArticles: () => Promise<void>;
  fetchSixArticles: (forceRegenerate?: boolean) => Promise<void>;
  updateSixArticlesConfig: (config: SixArticlesConfig) => Promise<void>;
  starArticle: (uri: string) => void;
  unstarArticle: (uri: string) => void;
  clearError: () => void;

  // Starred articles
  starredArticles: string[];
}

const DEFAULT_CONFIG: NewsFeedConfig = {
  dateRange: '7d',
  page: 1,
  perPage: 100,  // Increased for better category distribution
  model: 'gpt-4o',
  persona: 'CEO',
  articleCount: 6,
};

const STORAGE_KEYS = {
  CONFIG: 'newsFeed_config',
  STARRED: 'newsFeed_starred',
  SIX_ARTICLES: 'newsFeed_sixArticles',
};

// Cache interface for sixArticles
interface SixArticlesCache {
  data: SixArticlesReport;
  key: string;
  cachedAt: string;
}

// Generate cache key for sixArticles based on config
function generateSixArticlesCacheKey(config: NewsFeedConfig): string {
  return `${config.persona}_${config.topic || 'all'}_${config.dateRange}_${config.profileId || 'none'}`;
}

export function useNewsFeed(): UseNewsFeedReturn {
  // Load config from localStorage
  const loadStoredConfig = (): NewsFeedConfig => {
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

  // Load starred articles from localStorage
  const loadStoredStarred = (): string[] => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.STARRED);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (err) {
      console.error('Error loading starred articles:', err);
    }
    return [];
  };

  // Load cached sixArticles from localStorage
  const loadCachedSixArticles = (currentConfig: NewsFeedConfig): SixArticlesReport | null => {
    try {
      const cached = localStorage.getItem(STORAGE_KEYS.SIX_ARTICLES);
      if (cached) {
        const cacheEntry: SixArticlesCache = JSON.parse(cached);
        const currentKey = generateSixArticlesCacheKey(currentConfig);
        if (cacheEntry.key === currentKey) {
          console.log('[useNewsFeed] Loaded sixArticles from cache');
          return cacheEntry.data;
        }
      }
    } catch (err) {
      console.error('Error loading cached sixArticles:', err);
    }
    return null;
  };

  // State
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [groupedArticles, setGroupedArticles] = useState<Record<string, NewsArticle[]>>({});
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  // Initialize sixArticles from cache if available
  const [sixArticles, setSixArticles] = useState<SixArticlesReport | null>(() => {
    const initialConfig = loadStoredConfig();
    return loadCachedSixArticles(initialConfig);
  });
  const [availableDates, setAvailableDates] = useState<AvailableDate[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [profiles, setProfiles] = useState<OrganizationalProfile[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [config, setConfig] = useState<NewsFeedConfig>(loadStoredConfig);
  const [sixArticlesConfig, setSixArticlesConfig] = useState<SixArticlesConfig>({});
  const [starredArticles, setStarredArticles] = useState<string[]>(loadStoredStarred);

  // Pagination
  const [totalArticles, setTotalArticles] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Loading states
  const [loading, setLoading] = useState(false);
  const [loadingSixArticles, setLoadingSixArticles] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Save config to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(config));
    } catch (err) {
      console.error('Error saving config:', err);
    }
  }, [config]);

  // Save starred articles to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.STARRED, JSON.stringify(starredArticles));
    } catch (err) {
      console.error('Error saving starred articles:', err);
    }
  }, [starredArticles]);

  // Check for auto-generated dashboard snapshot on mount
  useEffect(() => {
    const loadSnapshot = async () => {
      try {
        const snapshotResponse = await getLatestDashboardSnapshot(config.topic);
        if (snapshotResponse.has_snapshot && snapshotResponse.snapshot?.briefing_articles) {
          const snapshot = snapshotResponse.snapshot;
          const snapshotDate = new Date(snapshot.generated_at);

          // Check if snapshot is newer than local cache
          const cachedStr = localStorage.getItem(STORAGE_KEYS.SIX_ARTICLES);
          let useSnapshot = true;

          if (cachedStr) {
            try {
              const cached = JSON.parse(cachedStr);
              const cachedDate = new Date(cached.cachedAt);
              // Only use snapshot if it's newer than cache
              useSnapshot = snapshotDate > cachedDate;
            } catch {
              // If cache parsing fails, use snapshot
            }
          }

          if (useSnapshot && snapshot.briefing_articles.length > 0) {
            console.log('[useNewsFeed] Loading auto-generated dashboard snapshot from', snapshot.generated_at);
            setSixArticles({
              date: snapshot.generated_at.split('T')[0],
              title: 'Executive Briefing',
              articles: snapshot.briefing_articles,
              generated_at: snapshot.generated_at,
              executive_summary: '',
              key_themes: [],
              bias_distribution: {},
              factuality_overview: {},
            });

            // Update cache with snapshot data
            const cacheEntry = {
              data: {
                date: snapshot.generated_at.split('T')[0],
                title: 'Executive Briefing',
                articles: snapshot.briefing_articles,
                generated_at: snapshot.generated_at,
                executive_summary: '',
                key_themes: [],
                bias_distribution: {},
                factuality_overview: {},
              },
              key: `${snapshot.persona}_${snapshot.topic || 'all'}_24h_none`,
              cachedAt: snapshot.generated_at,
            };
            localStorage.setItem(STORAGE_KEYS.SIX_ARTICLES, JSON.stringify(cacheEntry));
          }
        }
      } catch (err) {
        console.log('[useNewsFeed] No auto-generated snapshot available:', err);
      }
    };

    loadSnapshot();
  }, []); // Run once on mount

  // Load initial data
  useEffect(() => {
    loadInitialData();
  }, []);

  // Fetch articles when config changes
  useEffect(() => {
    fetchArticles();
  }, [config.dateRange, config.topic, config.page, config.perPage, config.profileId, config.model]);


  const loadInitialData = async () => {
    try {
      const [topicsData, profilesData, modelsData, datesData, configData] = await Promise.all([
        getTopics().catch(() => []),
        getOrganizationalProfiles().catch(() => []),
        getAvailableModels().catch(() => []),
        getAvailableDates().catch(() => []),
        getSixArticlesConfig().catch(() => ({})),
      ]);

      // Ensure all data is array (safeguard against API format issues)
      const safeTopics = Array.isArray(topicsData) ? topicsData : [];
      const safeProfiles = Array.isArray(profilesData) ? profilesData : [];
      const safeModels = Array.isArray(modelsData) ? modelsData : [];
      const safeDates = Array.isArray(datesData) ? datesData : [];

      setTopics(safeTopics);
      setProfiles(safeProfiles);
      setModels(safeModels);
      setAvailableDates(safeDates);
      setSixArticlesConfig(configData || {});

      // Set default profile if available
      const defaultProfile = safeProfiles.find(p => p.is_default);
      if (defaultProfile && !config.profileId) {
        setConfig(prev => ({ ...prev, profileId: defaultProfile.id }));
      }

      // Set default model if available
      if (safeModels.length > 0 && !config.model) {
        setConfig(prev => ({ ...prev, model: safeModels[0].id }));
      }
    } catch (err) {
      console.error('Error loading initial data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load initial data');
    }
  };

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch articles and category counts in parallel
      const [response, counts] = await Promise.all([
        getNewsFeedArticles({
          dateRange: config.dateRange,
          customDateStart: config.customDateStart,
          topic: config.topic,
          maxArticles: config.perPage * 10, // Fetch more for grouping
          page: config.page,
          perPage: config.perPage,
          profileId: config.profileId,
        }),
        getCategoryCounts(config.dateRange, config.topic),
      ]);

      setArticles(response.articles);
      setTotalArticles(response.total);
      setTotalPages(response.total_pages);
      setCategoryCounts(counts);

      // Group articles by category
      const grouped = groupArticlesByCategory(response.articles);
      setGroupedArticles(grouped);

      // Extract unique categories
      const uniqueCategories = Object.keys(grouped).sort();
      setCategories(uniqueCategories);
    } catch (err) {
      console.error('Error fetching articles:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch articles');
    } finally {
      setLoading(false);
    }
  }, [config.dateRange, config.customDateStart, config.topic, config.page, config.perPage, config.profileId]);

  // Fetch six articles briefing
  const fetchSixArticles = useCallback(async (forceRegenerate: boolean = false) => {
    setLoadingSixArticles(true);
    setError(null);

    try {
      const response = await getSixArticles({
        dateRange: config.dateRange,
        topic: config.topic,
        profileId: config.profileId,
        persona: config.persona,
        articleCount: config.articleCount,
        forceRegenerate,
        starredArticles: starredArticles.length > 0 ? starredArticles : undefined,
        model: config.model,
      });

      setSixArticles(response);

      // Save to cache
      try {
        const cacheEntry: SixArticlesCache = {
          data: response,
          key: generateSixArticlesCacheKey(config),
          cachedAt: new Date().toISOString(),
        };
        localStorage.setItem(STORAGE_KEYS.SIX_ARTICLES, JSON.stringify(cacheEntry));
        console.log('[useNewsFeed] Saved sixArticles to cache');
      } catch (err) {
        console.error('Error saving sixArticles to cache:', err);
      }
    } catch (err) {
      console.error('Error fetching six articles:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch six articles briefing');
    } finally {
      setLoadingSixArticles(false);
    }
  }, [config.dateRange, config.topic, config.profileId, config.persona, config.articleCount, starredArticles, config.model]);

  // Fetch six articles briefing when relevant config changes
  useEffect(() => {
    fetchSixArticles();
  }, [fetchSixArticles]);

  // Update config
  const updateConfig = useCallback((updates: Partial<NewsFeedConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }));
  }, []);

  // Update six articles config
  const updateSixArticlesConfig = useCallback(async (newConfig: SixArticlesConfig) => {
    try {
      await saveSixArticlesConfig(newConfig);
      setSixArticlesConfig(newConfig);
    } catch (err) {
      console.error('Error saving six articles config:', err);
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    }
  }, []);

  // Star/unstar articles
  const starArticle = useCallback((uri: string) => {
    setStarredArticles(prev => {
      if (!prev.includes(uri)) {
        return [...prev, uri];
      }
      return prev;
    });
  }, []);

  const unstarArticle = useCallback((uri: string) => {
    setStarredArticles(prev => prev.filter(u => u !== uri));
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    articles,
    groupedArticles,
    categoryCounts,
    sixArticles,
    availableDates,
    categories,
    topics,
    profiles,
    models,
    config,
    sixArticlesConfig,
    totalArticles,
    totalPages,
    loading,
    loadingSixArticles,
    error,
    updateConfig,
    fetchArticles,
    fetchSixArticles,
    updateSixArticlesConfig,
    starArticle,
    unstarArticle,
    clearError,
    starredArticles,
  };
}
