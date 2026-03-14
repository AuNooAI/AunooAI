/**
 * useGeopoliticalHotspots Hook
 * State management for the geopolitical hotspots feature
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getOverviewStats,
  getMapData,
  getCountriesData,
  getHotspots,
  getHotspotById,
  getHotspotArticles,
  getTimelineData,
  getRegionsData,
  getCategoriesData,
  type OverviewStats,
  type Hotspot,
  type CountryStats,
  type HotspotArticle,
  type TimelineDataPoint,
  type RegionData,
  type CategoryData,
  type ThreatCategory,
  type RiskLevel,
} from '../services/geopoliticalHotspotsApi';

export interface GeopoliticalConfig {
  topic?: string;
  daysBack: number;
  selectedCategories: ThreatCategory[];
  selectedRiskLevels: RiskLevel[];
  page: number;
  pageSize: number;
  sortBy: 'intensity' | 'articles' | 'recent' | 'name' | 'updated';
  sortOrder: 'asc' | 'desc';
}

const DEFAULT_CONFIG: GeopoliticalConfig = {
  topic: undefined,
  daysBack: 30,
  selectedCategories: [],
  selectedRiskLevels: [],
  page: 1,
  pageSize: 20,
  sortBy: 'intensity',
  sortOrder: 'desc',
};

export function useGeopoliticalHotspots(initialTopic?: string) {
  // Configuration state
  const [config, setConfig] = useState<GeopoliticalConfig>({
    ...DEFAULT_CONFIG,
    topic: initialTopic,
  });

  // Data state
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [mapHotspots, setMapHotspots] = useState<Hotspot[]>([]);
  const [countries, setCountries] = useState<CountryStats[]>([]);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [totalHotspots, setTotalHotspots] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedHotspot, setSelectedHotspot] = useState<Hotspot | null>(null);
  const [hotspotArticles, setHotspotArticles] = useState<HotspotArticle[]>([]);
  const [timeline, setTimeline] = useState<TimelineDataPoint[]>([]);
  const [regions, setRegions] = useState<RegionData[]>([]);
  const [categories, setCategories] = useState<CategoryData[]>([]);

  // Loading state
  const [loadingStats, setLoadingStats] = useState(false);
  const [loadingMap, setLoadingMap] = useState(false);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingHotspots, setLoadingHotspots] = useState(false);
  const [loadingHotspot, setLoadingHotspot] = useState(false);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Combined loading state
  const loading = loadingStats || loadingMap || loadingHotspots;

  // Update config
  const updateConfig = useCallback((updates: Partial<GeopoliticalConfig>) => {
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
        categories: config.selectedCategories.length > 0 ? config.selectedCategories : undefined,
        riskLevels: config.selectedRiskLevels.length > 0 ? config.selectedRiskLevels : undefined,
        daysBack: config.daysBack,
      });
      setMapHotspots(data);
    } catch (err) {
      console.error('Error fetching map data:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch map data');
    } finally {
      setLoadingMap(false);
    }
  }, [config.topic, config.selectedCategories, config.selectedRiskLevels, config.daysBack]);

  // Fetch countries data
  const fetchCountries = useCallback(async () => {
    setLoadingCountries(true);
    try {
      const data = await getCountriesData(config.topic);
      setCountries(data);
    } catch (err) {
      console.error('Error fetching countries:', err);
    } finally {
      setLoadingCountries(false);
    }
  }, [config.topic]);

  // Fetch hotspots list
  const fetchHotspots = useCallback(async () => {
    setLoadingHotspots(true);
    try {
      const result = await getHotspots({
        topic: config.topic,
        categories: config.selectedCategories.length > 0 ? config.selectedCategories : undefined,
        riskLevels: config.selectedRiskLevels.length > 0 ? config.selectedRiskLevels : undefined,
        daysBack: config.daysBack,
        page: config.page,
        pageSize: config.pageSize,
        sortBy: config.sortBy,
        sortOrder: config.sortOrder,
      });
      setHotspots(result.data);
      setTotalHotspots(result.total);
      setTotalPages(result.total_pages);
    } catch (err) {
      console.error('Error fetching hotspots:', err);
    } finally {
      setLoadingHotspots(false);
    }
  }, [
    config.topic,
    config.selectedCategories,
    config.selectedRiskLevels,
    config.daysBack,
    config.page,
    config.pageSize,
    config.sortBy,
    config.sortOrder,
  ]);

  // Fetch single hotspot
  const fetchHotspot = useCallback(async (hotspotId: number) => {
    setLoadingHotspot(true);
    try {
      const data = await getHotspotById(hotspotId);
      setSelectedHotspot(data);
      return data;
    } catch (err) {
      console.error('Error fetching hotspot:', err);
      return null;
    } finally {
      setLoadingHotspot(false);
    }
  }, []);

  // Fetch hotspot articles
  const fetchHotspotArticles = useCallback(
    async (hotspotId: number, page: number = 1) => {
      setLoadingArticles(true);
      try {
        const result = await getHotspotArticles(hotspotId, page, config.pageSize);
        setHotspotArticles(result.data);
        return result;
      } catch (err) {
        console.error('Error fetching hotspot articles:', err);
        return null;
      } finally {
        setLoadingArticles(false);
      }
    },
    [config.pageSize]
  );

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

  // Fetch regions data
  const fetchRegions = useCallback(async () => {
    setLoadingRegions(true);
    try {
      const data = await getRegionsData(config.topic);
      setRegions(data);
    } catch (err) {
      console.error('Error fetching regions:', err);
    } finally {
      setLoadingRegions(false);
    }
  }, [config.topic]);

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
    await Promise.all([fetchStats(), fetchMapData(), fetchHotspots()]);
  }, [fetchStats, fetchMapData, fetchHotspots]);

  // Initial data fetch
  useEffect(() => {
    fetchStats();
    fetchMapData();
  }, [fetchStats, fetchMapData]);

  // Fetch hotspots when pagination/filter changes
  useEffect(() => {
    fetchHotspots();
  }, [fetchHotspots]);

  return {
    // Data
    stats,
    mapHotspots,
    countries,
    hotspots,
    totalHotspots,
    totalPages,
    selectedHotspot,
    hotspotArticles,
    timeline,
    regions,
    categories,

    // Config
    config,
    updateConfig,

    // Loading states
    loading,
    loadingStats,
    loadingMap,
    loadingCountries,
    loadingHotspots,
    loadingHotspot,
    loadingArticles,
    loadingTimeline,
    loadingRegions,
    loadingCategories,

    // Error
    error,
    clearError,

    // Actions
    fetchStats,
    fetchMapData,
    fetchCountries,
    fetchHotspots,
    fetchHotspot,
    fetchHotspotArticles,
    fetchTimeline,
    fetchRegions,
    fetchCategories,
    refresh,
    setSelectedHotspot,
  };
}
