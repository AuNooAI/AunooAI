/**
 * Custom React hook for Brand Watcher functionality
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getBrands,
  createBrand,
  updateBrand,
  deleteBrand,
  toggleBrand,
  setPrimaryBrand,
  setupBrandMonitoring,
  getStats,
  getCategories,
  getTemporal,
  getArticles,
  getComparison,
  getShareOfVoice,
  getTopics,
  getOpointCoverage,
  getSocialPosts,
  type BWOpointCoverageResponse,
  type BWSocialResponse,
  type Brand,
  type BrandCreate,
  type BrandUpdate,
  type BWStats,
  type BWCategory,
  type BWTemporalData,
  type BWArticle,
  type BWComparison,
  type BWShareOfVoice,
} from '../services/brandWatcherApi';

export interface BrandWatcherConfig {
  daysBack: number;
  selectedBrandIds: number[];
  selectedTopics: string[];
  selectedCategories: string[];
  sortBy: 'date' | 'category_count';
  page: number;
  perPage: number;
}

const DEFAULT_CONFIG: BrandWatcherConfig = {
  daysBack: 365,
  selectedBrandIds: [],
  selectedTopics: [],
  selectedCategories: [],
  sortBy: 'date',
  page: 1,
  perPage: 25,
};

const STORAGE_KEY = 'brandWatcher_config';

export function useBrandWatcher() {
  const loadStoredConfig = (): BrandWatcherConfig => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Migrate legacy selectedTopic -> selectedTopics
        if (parsed.selectedTopic && !parsed.selectedTopics) {
          parsed.selectedTopics = [parsed.selectedTopic];
          delete parsed.selectedTopic;
        }
        // Migrate legacy selectedBrandId -> selectedBrandIds
        if (parsed.selectedBrandId !== undefined && !parsed.selectedBrandIds) {
          parsed.selectedBrandIds = parsed.selectedBrandId ? [parsed.selectedBrandId] : [];
          delete parsed.selectedBrandId;
        }
        return { ...DEFAULT_CONFIG, ...parsed };
      }
    } catch (err) {
      console.error('Error loading brand watcher config:', err);
    }
    return DEFAULT_CONFIG;
  };

  // State
  const [brands, setBrands] = useState<Brand[]>([]);
  const [topics, setTopics] = useState<{ topic: string; article_count: number }[]>([]);
  const [stats, setStats] = useState<BWStats | null>(null);
  const [categories, setCategories] = useState<BWCategory[]>([]);
  const [temporalData, setTemporalData] = useState<BWTemporalData[]>([]);
  const [articles, setArticles] = useState<BWArticle[]>([]);
  const [comparison, setComparison] = useState<BWComparison[]>([]);
  const [shareOfVoice, setShareOfVoice] = useState<BWShareOfVoice[]>([]);
  const [opointCoverage, setOpointCoverage] = useState<BWOpointCoverageResponse | null>(null);
  const [social, setSocial] = useState<BWSocialResponse | null>(null);
  const [config, setConfig] = useState<BrandWatcherConfig>(loadStoredConfig);

  // Pagination
  const [totalArticles, setTotalArticles] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Loading
  const [loadingBrands, setLoadingBrands] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [loadingTemporal, setLoadingTemporal] = useState(false);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [loadingShareOfVoice, setLoadingShareOfVoice] = useState(false);
  const [loadingOpoint, setLoadingOpoint] = useState(false);
  const [loadingSocial, setLoadingSocial] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loading = loadingStats || loadingCategories || loadingArticles;

  const topicsOrUndefined = config.selectedTopics.length > 0 ? config.selectedTopics : undefined;
  const brandIdsOrUndefined = config.selectedBrandIds.length > 0 ? config.selectedBrandIds : undefined;

  // Save config
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); }
    catch (err) { console.error('Error saving brand watcher config:', err); }
  }, [config]);

  // Fetch brands
  const fetchBrands = useCallback(async () => {
    setLoadingBrands(true);
    try {
      const data = await getBrands();
      setBrands(data);
    } catch (err) {
      console.error('Error fetching brands:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch brands');
    } finally {
      setLoadingBrands(false);
    }
  }, []);

  // Fetch topics
  const fetchTopics = useCallback(async () => {
    try {
      const data = await getTopics();
      setTopics(data);
    } catch (err) {
      console.error('Error fetching topics:', err);
    }
  }, []);

  // Brand CRUD
  const handleCreateBrand = useCallback(async (brand: BrandCreate) => {
    const created = await createBrand(brand);
    setBrands(prev => [...prev, created]);
    return created;
  }, []);

  const handleUpdateBrand = useCallback(async (id: number, updates: BrandUpdate) => {
    const updated = await updateBrand(id, updates);
    setBrands(prev => prev.map(b => b.id === id ? updated : b));
    return updated;
  }, []);

  const handleDeleteBrand = useCallback(async (id: number, cleanupMonitoring: boolean = false) => {
    await deleteBrand(id, cleanupMonitoring || undefined);
    setBrands(prev => prev.filter(b => b.id !== id));
    if (config.selectedBrandIds.includes(id)) {
      setConfig(prev => ({ ...prev, selectedBrandIds: prev.selectedBrandIds.filter(bid => bid !== id) }));
    }
  }, [config.selectedBrandIds]);

  const handleToggleBrand = useCallback(async (id: number) => {
    const result = await toggleBrand(id);
    setBrands(prev => prev.map(b => b.id === id ? { ...b, enabled: result.enabled } : b));
  }, []);

  // Set primary brand
  const handleSetPrimary = useCallback(async (id: number) => {
    await setPrimaryBrand(id);
    setBrands(prev => prev.map(b => ({ ...b, is_primary: b.id === id })));
  }, []);

  // Auto-select primary brand on initial load when no brands are selected
  useEffect(() => {
    if (brands.length > 0 && config.selectedBrandIds.length === 0) {
      const primary = brands.find(b => b.is_primary && b.enabled);
      if (primary) {
        setConfig(prev => ({ ...prev, selectedBrandIds: [primary.id] }));
      }
    }
  }, [brands]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    setLoadingStats(true);
    setError(null);
    try {
      const data = await getStats(brandIdsOrUndefined, config.daysBack, topicsOrUndefined);
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch stats');
    } finally {
      setLoadingStats(false);
    }
  }, [brandIdsOrUndefined, config.daysBack, topicsOrUndefined]);

  // Fetch categories
  const fetchCategories = useCallback(async () => {
    setLoadingCategories(true);
    try {
      const data = await getCategories(brandIdsOrUndefined, config.daysBack, topicsOrUndefined);
      setCategories(data);
    } catch (err) {
      console.error('Error fetching categories:', err);
    } finally {
      setLoadingCategories(false);
    }
  }, [brandIdsOrUndefined, config.daysBack, topicsOrUndefined]);

  const fetchOpointCoverage = useCallback(async (minRelevance: number = 0.4, excludeScholarly: boolean = false) => {
    setLoadingOpoint(true);
    try {
      const data = await getOpointCoverage(config.daysBack, minRelevance, excludeScholarly);
      setOpointCoverage(data);
    } catch (err) {
      console.error('Error fetching Opoint coverage:', err);
    } finally {
      setLoadingOpoint(false);
    }
  }, [config.daysBack]);

  const fetchSocial = useCallback(async (minRelevance: number = 0, source?: string) => {
    setLoadingSocial(true);
    try {
      const data = await getSocialPosts(topicsOrUndefined, config.daysBack, minRelevance, source);
      setSocial(data);
    } catch (err) {
      console.error('Error fetching social posts:', err);
    } finally {
      setLoadingSocial(false);
    }
  }, [config.daysBack, topicsOrUndefined]);

  // Fetch temporal
  const fetchTemporal = useCallback(async () => {
    setLoadingTemporal(true);
    try {
      const data = await getTemporal(brandIdsOrUndefined, Math.max(config.daysBack, 90), topicsOrUndefined);
      setTemporalData(data);
    } catch (err) {
      console.error('Error fetching temporal:', err);
    } finally {
      setLoadingTemporal(false);
    }
  }, [brandIdsOrUndefined, config.daysBack, topicsOrUndefined]);

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setLoadingArticles(true);
    try {
      const res = await getArticles({
        brand_ids: brandIdsOrUndefined,
        topics: topicsOrUndefined,
        categories: config.selectedCategories.length > 0 ? config.selectedCategories : undefined,
        days_back: config.daysBack,
        sort_by: config.sortBy,
        page: config.page,
        per_page: config.perPage,
      });
      setArticles(res.articles);
      setTotalArticles(res.total_count);
      setTotalPages(res.total_pages);
    } catch (err) {
      console.error('Error fetching articles:', err);
    } finally {
      setLoadingArticles(false);
    }
  }, [config]);

  // Fetch comparison
  const fetchComparison = useCallback(async () => {
    setLoadingComparison(true);
    try {
      const data = await getComparison(config.daysBack, topicsOrUndefined);
      setComparison(data);
    } catch (err) {
      console.error('Error fetching comparison:', err);
    } finally {
      setLoadingComparison(false);
    }
  }, [config.daysBack, topicsOrUndefined]);

  // Fetch share of voice
  const fetchShareOfVoice = useCallback(async () => {
    setLoadingShareOfVoice(true);
    try {
      const data = await getShareOfVoice(config.daysBack, topicsOrUndefined);
      setShareOfVoice(data);
    } catch (err) {
      console.error('Error fetching share of voice:', err);
    } finally {
      setLoadingShareOfVoice(false);
    }
  }, [config.daysBack, topicsOrUndefined]);

  // Update config
  const updateConfig = useCallback((updates: Partial<BrandWatcherConfig>) => {
    setConfig(prev => {
      const next = { ...prev, ...updates };
      if (updates.selectedCategories !== undefined || updates.sortBy !== undefined ||
          updates.daysBack !== undefined || updates.selectedBrandIds !== undefined ||
          updates.selectedTopics !== undefined) {
        next.page = 1;
      }
      return next;
    });
  }, []);

  const clearError = useCallback(() => setError(null), []);

  // Refresh all
  const refresh = useCallback(async () => {
    await Promise.all([fetchStats(), fetchCategories(), fetchTemporal(), fetchArticles()]);
  }, [fetchStats, fetchCategories, fetchTemporal, fetchArticles]);

  // Initial load
  useEffect(() => { fetchBrands(); fetchTopics(); }, []);
  useEffect(() => { fetchStats(); fetchCategories(); fetchTemporal(); },
    [config.selectedBrandIds, config.daysBack, config.selectedTopics]);
  useEffect(() => { fetchArticles(); },
    [config.selectedBrandIds, config.selectedTopics, config.selectedCategories, config.daysBack, config.sortBy, config.page, config.perPage]);

  return {
    brands, topics, stats, categories, temporalData, articles,
    comparison, shareOfVoice, opointCoverage, social, config,
    totalArticles, totalPages,
    loading, loadingBrands, loadingStats, loadingCategories,
    loadingTemporal, loadingArticles, loadingComparison, loadingShareOfVoice,
    loadingOpoint, loadingSocial,
    error,
    updateConfig, clearError, refresh,
    fetchBrands, fetchTopics, fetchStats, fetchCategories, fetchTemporal,
    fetchArticles, fetchComparison, fetchShareOfVoice, fetchOpointCoverage, fetchSocial,
    createBrand: handleCreateBrand, updateBrand: handleUpdateBrand,
    deleteBrand: handleDeleteBrand, toggleBrand: handleToggleBrand,
    setPrimary: handleSetPrimary,
  };
}
