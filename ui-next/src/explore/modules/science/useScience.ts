import { useCallback, useEffect, useState } from 'react';
import {
  getCategoryDistribution, getScienceArticles, getScienceStats, getTemporalData, searchScienceArticles,
  type ScienceArticle, type ScienceCategory, type ScienceStats, type TemporalData,
} from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { SCIENCE_TOPIC } from './labels';

/*
 * The reads several ScienceWatch sub-tabs share, as the old useScienceFunding hook: stats,
 * categories, the monthly series and the article list. Everything else (themes, timeline,
 * heatmap, insights) is loaded by its own sub-tab while it is open, for the period picked here.
 * The settings live in localStorage under the old page's key, so the period carries over.
 */

export type SortBy = 'date' | 'relevance' | 'category_count';

export interface ScienceConfig {
  daysBack: number;
  selectedCategories: string[];
  sortBy: SortBy;
  page: number;
  perPage: number;
}

const DEFAULTS: ScienceConfig = { daysBack: 365, selectedCategories: [], sortBy: 'date', page: 1, perPage: 25 };
const STORAGE_KEY = 'scienceFunding_config';

function loadConfig(): ScienceConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        ...DEFAULTS,
        daysBack: typeof p.daysBack === 'number' ? p.daysBack : DEFAULTS.daysBack,
        selectedCategories: Array.isArray(p.selectedCategories) ? p.selectedCategories : [],
        sortBy: p.sortBy === 'category_count' ? 'category_count' : 'date',
        page: 1,
      };
    }
  } catch {
    // the defaults
  }
  return DEFAULTS;
}

export function useScience() {
  const topic = SCIENCE_TOPIC;
  const [config, setConfig] = useState<ScienceConfig>(loadConfig);
  const [stats, setStats] = useState<ScienceStats | null>(null);
  const [categories, setCategories] = useState<ScienceCategory[] | null>(null);
  const [temporal, setTemporal] = useState<TemporalData[] | null>(null);
  const [articles, setArticles] = useState<{ list: ScienceArticle[]; total: number; pages: number } | null>(null);
  const [search, setSearch] = useState<{ query: string; results: ScienceArticle[] | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    try {
      // The old key also held the topic; the old page ignored it, so it is left out here
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...config, topic }));
    } catch {
      // per visit only
    }
  }, [config, topic]);

  // Stats, categories and the monthly series follow the period
  useEffect(() => {
    let live = true;
    setOverviewLoading(true);
    setError(null);
    Promise.all([
      getScienceStats(topic, config.daysBack),
      getCategoryDistribution(topic, config.daysBack),
      // The monthly series always covers at least 90 days, as on the old page, so a 7-day window still shows a trend
      getTemporalData(topic, config.daysBack === 0 ? 0 : Math.max(config.daysBack, 90)),
    ]).then(
      ([s, c, t]) => {
        if (!live) return;
        setStats(s);
        setCategories(c);
        setTemporal(t);
      },
      (e) => {
        if (!live) return;
        setError(errorText(e));
        setStats(null);
        setCategories([]);
        setTemporal([]);
      },
    ).finally(() => live && setOverviewLoading(false));
    return () => {
      live = false;
    };
  }, [topic, config.daysBack, reloadKey]);

  // The article list follows the period, the category filter, the sort and the page
  useEffect(() => {
    let live = true;
    setArticlesLoading(true);
    getScienceArticles({
      topic, daysBack: config.daysBack, sortBy: config.sortBy, page: config.page, perPage: config.perPage,
      categories: config.selectedCategories.length ? config.selectedCategories : undefined,
    }).then(
      (r) => live && setArticles({ list: r.articles, total: r.total_count, pages: r.total_pages }),
      (e) => {
        if (!live) return;
        setError(errorText(e));
        setArticles({ list: [], total: 0, pages: 0 });
      },
    ).finally(() => live && setArticlesLoading(false));
    return () => {
      live = false;
    };
  }, [topic, config.daysBack, config.sortBy, config.page, config.perPage, config.selectedCategories, reloadKey]);

  const updateConfig = useCallback((patch: Partial<ScienceConfig>) => {
    setConfig((c) => {
      const next = { ...c, ...patch };
      if (patch.selectedCategories !== undefined || patch.sortBy !== undefined || patch.daysBack !== undefined) next.page = 1;
      return next;
    });
  }, []);

  const runSearch = useCallback(async (query: string) => {
    const q = query.trim();
    if (!q) {
      setSearch(null);
      return;
    }
    setSearch({ query: q, results: null });
    try {
      const r = await searchScienceArticles(q, topic);
      setSearch((s) => (s?.query === q ? { query: q, results: r.articles } : s));
    } catch (e) {
      setError(errorText(e));
      setSearch((s) => (s?.query === q ? { query: q, results: [] } : s));
    }
  }, [topic]);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  return {
    topic, config, updateConfig, stats, categories, temporal, articles, articlesLoading, overviewLoading,
    search, runSearch, clearSearch: () => setSearch(null),
    error, clearError: () => setError(null), refresh, reloadKey,
  };
}

export type ScienceData = ReturnType<typeof useScience>;
