/**
 * useThreatIntelligence Hook
 * State management for the threat intelligence feature
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getOverviewStats,
  getMapData,
  getThreats,
  getThreatById,
  getThreatArticles,
  getActors,
  getActorById,
  getTimelineData,
  getDailyCounts,
  getCategoriesData,
  type OverviewStats,
  type ThreatMapData,
  type Threat,
  type ThreatArticle,
  type ThreatActor,
  type TimelineDataPoint,
  type DailyCount,
  type CategoryData,
  type ThreatCategory,
  type SeverityLevel,
  type ActorType,
} from '../services/threatIntelligenceApi';

export interface ThreatIntelConfig {
  topic?: string;
  daysBack: number;
  selectedThreatTypes: ThreatCategory[];
  selectedSeverityLevels: SeverityLevel[];
  page: number;
  pageSize: number;
  sortBy: 'severity' | 'articles' | 'name' | 'type' | 'updated';
  sortOrder: 'asc' | 'desc';
}

const DEFAULT_CONFIG: ThreatIntelConfig = {
  topic: undefined,
  daysBack: 30,
  selectedThreatTypes: [],
  selectedSeverityLevels: [],
  page: 1,
  pageSize: 20,
  sortBy: 'severity',
  sortOrder: 'desc',
};

export function useThreatIntelligence(initialTopic?: string) {
  // Configuration state
  const [config, setConfig] = useState<ThreatIntelConfig>({
    ...DEFAULT_CONFIG,
    topic: initialTopic,
  });

  // Data state
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [mapThreats, setMapThreats] = useState<ThreatMapData[]>([]);
  const [threats, setThreats] = useState<Threat[]>([]);
  const [totalThreats, setTotalThreats] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedThreat, setSelectedThreat] = useState<Threat | null>(null);
  const [threatArticles, setThreatArticles] = useState<ThreatArticle[]>([]);
  const [actors, setActors] = useState<ThreatActor[]>([]);
  const [selectedActor, setSelectedActor] = useState<ThreatActor | null>(null);
  const [timeline, setTimeline] = useState<TimelineDataPoint[]>([]);
  const [dailyCounts, setDailyCounts] = useState<DailyCount[]>([]);
  const [categories, setCategories] = useState<CategoryData[]>([]);

  // Loading state
  const [loadingStats, setLoadingStats] = useState(false);
  const [loadingMap, setLoadingMap] = useState(false);
  const [loadingThreats, setLoadingThreats] = useState(false);
  const [loadingThreat, setLoadingThreat] = useState(false);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [loadingActors, setLoadingActors] = useState(false);
  const [loadingActor, setLoadingActor] = useState(false);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [loadingDailyCounts, setLoadingDailyCounts] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Combined loading state
  const loading = loadingStats || loadingMap || loadingThreats;

  // Update config
  const updateConfig = useCallback((updates: Partial<ThreatIntelConfig>) => {
    setConfig((prev) => ({ ...prev, ...updates }));
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Fetch overview stats
  const fetchStats = useCallback(async () => {
    setLoadingStats(true);
    setError(null);
    try {
      const data = await getOverviewStats(config.topic, config.daysBack);
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch stats');
    } finally {
      setLoadingStats(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch map data
  const fetchMapData = useCallback(async () => {
    setLoadingMap(true);
    setError(null);
    try {
      const data = await getMapData({
        topic: config.topic,
        threatTypes: config.selectedThreatTypes.length > 0 ? config.selectedThreatTypes : undefined,
        severityLevels: config.selectedSeverityLevels.length > 0 ? config.selectedSeverityLevels : undefined,
        daysBack: config.daysBack,
      });
      setMapThreats(data);
    } catch (err) {
      console.error('Error fetching map data:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch map data');
    } finally {
      setLoadingMap(false);
    }
  }, [config.topic, config.selectedThreatTypes, config.selectedSeverityLevels, config.daysBack]);

  // Fetch threats list
  const fetchThreats = useCallback(async () => {
    setLoadingThreats(true);
    try {
      const result = await getThreats({
        topic: config.topic,
        threatTypes: config.selectedThreatTypes.length > 0 ? config.selectedThreatTypes : undefined,
        severityLevels: config.selectedSeverityLevels.length > 0 ? config.selectedSeverityLevels : undefined,
        daysBack: config.daysBack,
        page: config.page,
        pageSize: config.pageSize,
        sortBy: config.sortBy,
        sortOrder: config.sortOrder,
      });
      setThreats(result.data);
      setTotalThreats(result.total);
      setTotalPages(result.total_pages);
    } catch (err) {
      console.error('Error fetching threats:', err);
    } finally {
      setLoadingThreats(false);
    }
  }, [
    config.topic,
    config.selectedThreatTypes,
    config.selectedSeverityLevels,
    config.daysBack,
    config.page,
    config.pageSize,
    config.sortBy,
    config.sortOrder,
  ]);

  // Fetch single threat
  const fetchThreat = useCallback(async (threatId: number) => {
    setLoadingThreat(true);
    try {
      const data = await getThreatById(threatId);
      setSelectedThreat(data);
      return data;
    } catch (err) {
      console.error('Error fetching threat:', err);
      return null;
    } finally {
      setLoadingThreat(false);
    }
  }, []);

  // Fetch threat articles
  const fetchThreatArticles = useCallback(
    async (threatId: number, page: number = 1) => {
      setLoadingArticles(true);
      try {
        const result = await getThreatArticles(threatId, page, config.pageSize);
        setThreatArticles(result.data);
        return result;
      } catch (err) {
        console.error('Error fetching threat articles:', err);
        return null;
      } finally {
        setLoadingArticles(false);
      }
    },
    [config.pageSize]
  );

  // Fetch actors list
  const fetchActors = useCallback(async (actorType?: ActorType) => {
    setLoadingActors(true);
    try {
      const result = await getActors({
        actorType,
        page: 1,
        pageSize: 50,
        sortBy: 'threat_count',
        sortOrder: 'desc',
      });
      setActors(result.data);
    } catch (err) {
      console.error('Error fetching actors:', err);
    } finally {
      setLoadingActors(false);
    }
  }, []);

  // Fetch single actor
  const fetchActor = useCallback(async (actorId: number) => {
    setLoadingActor(true);
    try {
      const data = await getActorById(actorId);
      setSelectedActor(data);
      return data;
    } catch (err) {
      console.error('Error fetching actor:', err);
      return null;
    } finally {
      setLoadingActor(false);
    }
  }, []);

  // Fetch timeline data
  const fetchTimeline = useCallback(async () => {
    setLoadingTimeline(true);
    try {
      const data = await getTimelineData(config.topic, config.daysBack);
      setTimeline(data);
    } catch (err) {
      console.error('Error fetching timeline:', err);
    } finally {
      setLoadingTimeline(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch daily counts
  const fetchDailyCounts = useCallback(async () => {
    setLoadingDailyCounts(true);
    try {
      const data = await getDailyCounts(config.topic, config.daysBack);
      setDailyCounts(data);
    } catch (err) {
      console.error('Error fetching daily counts:', err);
    } finally {
      setLoadingDailyCounts(false);
    }
  }, [config.topic, config.daysBack]);

  // Fetch categories data
  const fetchCategories = useCallback(async () => {
    setLoadingCategories(true);
    try {
      const data = await getCategoriesData(config.topic);
      setCategories(data);
    } catch (err) {
      console.error('Error fetching categories:', err);
    } finally {
      setLoadingCategories(false);
    }
  }, [config.topic]);

  // Refresh all data
  const refresh = useCallback(async () => {
    await Promise.all([fetchStats(), fetchMapData(), fetchThreats()]);
  }, [fetchStats, fetchMapData, fetchThreats]);

  // Initial data fetch
  useEffect(() => {
    fetchStats();
    fetchMapData();
  }, [fetchStats, fetchMapData]);

  // Fetch threats when pagination/filter changes
  useEffect(() => {
    fetchThreats();
  }, [fetchThreats]);

  return {
    // Data
    stats,
    mapThreats,
    threats,
    totalThreats,
    totalPages,
    selectedThreat,
    threatArticles,
    actors,
    selectedActor,
    timeline,
    dailyCounts,
    categories,

    // Config
    config,
    updateConfig,

    // Loading states
    loading,
    loadingStats,
    loadingMap,
    loadingThreats,
    loadingThreat,
    loadingArticles,
    loadingActors,
    loadingActor,
    loadingTimeline,
    loadingDailyCounts,
    loadingCategories,

    // Error
    error,
    clearError,

    // Actions
    fetchStats,
    fetchMapData,
    fetchThreats,
    fetchThreat,
    fetchThreatArticles,
    fetchActors,
    fetchActor,
    fetchTimeline,
    fetchDailyCounts,
    fetchCategories,
    refresh,
    setSelectedThreat,
    setSelectedActor,
  };
}
