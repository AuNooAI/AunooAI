/**
 * Custom React hook for Science Funding Tracker functionality
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getScienceStats,
  getScienceArticles,
  getCategoryDistribution,
  getTemporalData,
  getRelatedArticles,
  searchScienceArticles,
  getThemes,
  getThemesEvolution,
  getEntities,
  getGeography,
  getEscalationMarkers,
  getEscalationTrends,
  getDayOfWeek,
  getDailyIntensity,
  getCooccurrenceMatrix,
  DEFAULT_SCIENCE_TOPIC,
  type ScienceStats,
  type ScienceArticle,
  type ScienceCategory,
  type TemporalData,
  type RelatedArticle,
  type ThemeData,
  type ThemeEvolution,
  type EntityData,
  type GeographyData,
  type EscalationMarkerData,
  type EscalationTrend,
  type DayOfWeekData,
  type DailyIntensityData,
  type CooccurrenceMatrix,
} from '../services/scienceFundingApi';

export interface ScienceFundingConfig {
  topic: string;
  daysBack: number;
  selectedCategories: string[];
  sortBy: 'date' | 'relevance' | 'category_count';
  page: number;
  perPage: number;
}

export interface UseScienceFundingReturn {
  // Data
  stats: ScienceStats | null;
  articles: ScienceArticle[];
  categories: ScienceCategory[];
  temporalData: TemporalData[];
  relatedArticles: RelatedArticle[];
  searchResults: ScienceArticle[];
  config: ScienceFundingConfig;

  // EDA Analysis Data
  themes: ThemeData[];
  themesEvolution: ThemeEvolution[];
  entities: EntityData[];
  geography: GeographyData[];
  escalationMarkers: EscalationMarkerData[];
  escalationTrends: EscalationTrend[];
  dayOfWeek: DayOfWeekData[];
  dailyIntensity: DailyIntensityData[];
  cooccurrenceMatrix: CooccurrenceMatrix | null;

  // Pagination
  totalArticles: number;
  totalPages: number;

  // Loading states
  loading: boolean;
  loadingStats: boolean;
  loadingArticles: boolean;
  loadingCategories: boolean;
  loadingTemporal: boolean;
  loadingRelated: boolean;
  loadingSearch: boolean;
  loadingThemes: boolean;
  loadingEntities: boolean;
  loadingGeography: boolean;
  loadingEscalation: boolean;
  loadingTimeline: boolean;
  loadingMatrix: boolean;

  // Error
  error: string | null;

  // Actions
  updateConfig: (updates: Partial<ScienceFundingConfig>) => void;
  fetchStats: () => Promise<void>;
  fetchArticles: () => Promise<void>;
  fetchCategories: () => Promise<void>;
  fetchTemporalData: () => Promise<void>;
  fetchRelatedArticles: (uri: string) => Promise<void>;
  searchArticles: (query: string) => Promise<void>;
  fetchThemesData: () => Promise<void>;
  fetchEntitiesData: () => Promise<void>;
  fetchGeographyData: () => Promise<void>;
  fetchEscalationData: () => Promise<void>;
  fetchTimelineData: () => Promise<void>;
  fetchMatrixData: () => Promise<void>;
  clearSearch: () => void;
  clearError: () => void;
  refresh: () => Promise<void>;
}

const DEFAULT_CONFIG: ScienceFundingConfig = {
  topic: DEFAULT_SCIENCE_TOPIC,
  daysBack: 365,
  selectedCategories: [],
  sortBy: 'date',
  page: 1,
  perPage: 25,
};

const STORAGE_KEY = 'scienceFunding_config';

export function useScienceFunding(): UseScienceFundingReturn {
  const loadStoredConfig = (): ScienceFundingConfig => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Always use the current default topic to avoid stale topic mismatches
        parsed.topic = DEFAULT_CONFIG.topic;
        return { ...DEFAULT_CONFIG, ...parsed };
      }
    } catch (err) {
      console.error('Error loading science funding config:', err);
    }
    return DEFAULT_CONFIG;
  };

  // State
  const [stats, setStats] = useState<ScienceStats | null>(null);
  const [articles, setArticles] = useState<ScienceArticle[]>([]);
  const [categories, setCategories] = useState<ScienceCategory[]>([]);
  const [temporalData, setTemporalData] = useState<TemporalData[]>([]);
  const [relatedArticles, setRelatedArticles] = useState<RelatedArticle[]>([]);
  const [searchResults, setSearchResults] = useState<ScienceArticle[]>([]);
  const [config, setConfig] = useState<ScienceFundingConfig>(loadStoredConfig);

  // EDA Analysis State
  const [themes, setThemes] = useState<ThemeData[]>([]);
  const [themesEvolution, setThemesEvolution] = useState<ThemeEvolution[]>([]);
  const [entities, setEntities] = useState<EntityData[]>([]);
  const [geography, setGeography] = useState<GeographyData[]>([]);
  const [escalationMarkers, setEscalationMarkers] = useState<EscalationMarkerData[]>([]);
  const [escalationTrends, setEscalationTrends] = useState<EscalationTrend[]>([]);
  const [dayOfWeek, setDayOfWeek] = useState<DayOfWeekData[]>([]);
  const [dailyIntensity, setDailyIntensity] = useState<DailyIntensityData[]>([]);
  const [cooccurrenceMatrix, setCooccurrenceMatrix] = useState<CooccurrenceMatrix | null>(null);

  // Pagination
  const [totalArticles, setTotalArticles] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Loading states
  const [loadingStats, setLoadingStats] = useState(false);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [loadingTemporal, setLoadingTemporal] = useState(false);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [loadingThemes, setLoadingThemes] = useState(false);
  const [loadingEntities, setLoadingEntities] = useState(false);
  const [loadingGeography, setLoadingGeography] = useState(false);
  const [loadingEscalation, setLoadingEscalation] = useState(false);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [loadingMatrix, setLoadingMatrix] = useState(false);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Derived loading state
  const loading = loadingStats || loadingArticles || loadingCategories || loadingTemporal;

  // Save config to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch (err) {
      console.error('Error saving science funding config:', err);
    }
  }, [config]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    setLoadingStats(true);
    setError(null);

    try {
      const data = await getScienceStats(config.topic, config.daysBack);
      setStats(data);
    } catch (err) {
      console.error('Error fetching science stats:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch stats');
    } finally {
      setLoadingStats(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setLoadingArticles(true);
    setError(null);

    try {
      const response = await getScienceArticles({
        topic: config.topic,
        categories: config.selectedCategories.length > 0 ? config.selectedCategories : undefined,
        daysBack: config.daysBack,
        sortBy: config.sortBy,
        page: config.page,
        perPage: config.perPage,
      });

      setArticles(response.articles);
      setTotalArticles(response.total_count);
      setTotalPages(response.total_pages);
    } catch (err) {
      console.error('Error fetching science articles:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch articles');
    } finally {
      setLoadingArticles(false);
    }
  }, [config.topic, config.selectedCategories, config.daysBack, config.sortBy, config.page, config.perPage]);

  // Fetch categories
  const fetchCategories = useCallback(async () => {
    setLoadingCategories(true);

    try {
      const data = await getCategoryDistribution(config.topic, config.daysBack);
      setCategories(data);
    } catch (err) {
      console.error('Error fetching category distribution:', err);
    } finally {
      setLoadingCategories(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch temporal data
  const fetchTemporalData = useCallback(async () => {
    setLoadingTemporal(true);

    try {
      const data = await getTemporalData(config.topic, Math.max(config.daysBack, 90));
      setTemporalData(data);
    } catch (err) {
      console.error('Error fetching temporal data:', err);
    } finally {
      setLoadingTemporal(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch related articles
  const fetchRelatedArticles = useCallback(async (uri: string) => {
    setLoadingRelated(true);

    try {
      const data = await getRelatedArticles(uri);
      setRelatedArticles(data);
    } catch (err) {
      console.error('Error fetching related articles:', err);
    } finally {
      setLoadingRelated(false);
    }
  }, []);

  // Search articles
  const searchArticles = useCallback(async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }

    setLoadingSearch(true);

    try {
      const result = await searchScienceArticles(query, config.topic);
      setSearchResults(result.articles);
    } catch (err) {
      console.error('Error searching articles:', err);
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoadingSearch(false);
    }
  }, [config.topic]);

  const clearSearch = useCallback(() => {
    setSearchResults([]);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Fetch themes data
  const fetchThemesData = useCallback(async () => {
    setLoadingThemes(true);

    try {
      const [themesData, evolutionData] = await Promise.all([
        getThemes(config.topic, config.daysBack),
        getThemesEvolution(config.topic, config.daysBack),
      ]);
      setThemes(themesData);
      setThemesEvolution(evolutionData);
    } catch (err) {
      console.error('Error fetching themes data:', err);
    } finally {
      setLoadingThemes(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch entities data
  const fetchEntitiesData = useCallback(async () => {
    setLoadingEntities(true);

    try {
      const data = await getEntities(config.topic, config.daysBack);
      setEntities(data);
    } catch (err) {
      console.error('Error fetching entities data:', err);
    } finally {
      setLoadingEntities(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch geography data
  const fetchGeographyData = useCallback(async () => {
    setLoadingGeography(true);

    try {
      const data = await getGeography(config.topic, config.daysBack);
      setGeography(data);
    } catch (err) {
      console.error('Error fetching geography data:', err);
    } finally {
      setLoadingGeography(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch escalation data
  const fetchEscalationData = useCallback(async () => {
    setLoadingEscalation(true);

    try {
      const [markersData, trendsData] = await Promise.all([
        getEscalationMarkers(config.topic, config.daysBack),
        getEscalationTrends(config.topic, config.daysBack),
      ]);
      setEscalationMarkers(markersData);
      setEscalationTrends(trendsData);
    } catch (err) {
      console.error('Error fetching escalation data:', err);
    } finally {
      setLoadingEscalation(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch timeline data
  const fetchTimelineData = useCallback(async () => {
    setLoadingTimeline(true);

    try {
      const [dowData, intensityData] = await Promise.all([
        getDayOfWeek(config.topic, config.daysBack),
        getDailyIntensity(config.topic, config.daysBack),
      ]);
      setDayOfWeek(dowData);
      setDailyIntensity(intensityData);
    } catch (err) {
      console.error('Error fetching timeline data:', err);
    } finally {
      setLoadingTimeline(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch co-occurrence matrix
  const fetchMatrixData = useCallback(async () => {
    setLoadingMatrix(true);

    try {
      const data = await getCooccurrenceMatrix(config.topic, config.daysBack);
      setCooccurrenceMatrix(data);
    } catch (err) {
      console.error('Error fetching matrix data:', err);
    } finally {
      setLoadingMatrix(false);
    }
  }, [config.topic, config.daysBack]);

  // Update config
  const updateConfig = useCallback((updates: Partial<ScienceFundingConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      if (
        updates.selectedCategories !== undefined ||
        updates.sortBy !== undefined ||
        updates.daysBack !== undefined
      ) {
        newConfig.page = 1;
      }
      return newConfig;
    });
  }, []);

  // Refresh all data
  const refresh = useCallback(async () => {
    await Promise.all([
      fetchStats(),
      fetchArticles(),
      fetchCategories(),
      fetchTemporalData(),
    ]);
  }, [fetchStats, fetchArticles, fetchCategories, fetchTemporalData]);

  // Initial data load
  useEffect(() => {
    fetchStats();
    fetchCategories();
    fetchTemporalData();
  }, [config.topic, config.daysBack]);

  // Fetch articles when relevant config changes
  useEffect(() => {
    fetchArticles();
  }, [config.topic, config.selectedCategories, config.daysBack, config.sortBy, config.page, config.perPage]);

  return {
    stats,
    articles,
    categories,
    temporalData,
    relatedArticles,
    searchResults,
    config,
    themes,
    themesEvolution,
    entities,
    geography,
    escalationMarkers,
    escalationTrends,
    dayOfWeek,
    dailyIntensity,
    cooccurrenceMatrix,
    totalArticles,
    totalPages,
    loading,
    loadingStats,
    loadingArticles,
    loadingCategories,
    loadingTemporal,
    loadingRelated,
    loadingSearch,
    loadingThemes,
    loadingEntities,
    loadingGeography,
    loadingEscalation,
    loadingTimeline,
    loadingMatrix,
    error,
    updateConfig,
    fetchStats,
    fetchArticles,
    fetchCategories,
    fetchTemporalData,
    fetchRelatedArticles,
    searchArticles,
    fetchThemesData,
    fetchEntitiesData,
    fetchGeographyData,
    fetchEscalationData,
    fetchTimelineData,
    fetchMatrixData,
    clearSearch,
    clearError,
    refresh,
  };
}
