import { useCallback, useEffect, useState } from 'react';
import {
  getCategoryDistribution, getCooccurrenceMatrix, getDailyIntensity, getDayOfWeek, getEntities, getEscalationMarkers, getEscalationTrends,
  getGeography, getPolicyStats, getRelatedArticles, getTemporalData, getThemes, getThemesEvolution, searchPolicyArticles,
  type CooccurrenceMatrix, type DailyIntensityData, type DayOfWeekData, type EntityData, type EscalationMarkerData, type EscalationTrend,
  type GeographyData, type PolicyArticle, type PolicyCategory, type PolicyStats, type RelatedArticle, type TemporalData, type ThemeData,
  type ThemeEvolution,
} from '@monolith/policyTrackerApi';
import { errorText } from '../../../shell';
import { fetchPolicyArticles, TRACKER_TOPIC, type SortBy } from './api';

/*
 * A copy of ui/src/hooks/usePolicyTracker.ts. The overview figures and the article list load with the
 * tab; the heavier breakdowns (timeline, themes, entities, geography, escalation, co-occurrence) load
 * when their sub-tab opens, and again whenever the period changes. Every read here is a plain database
 * read: nothing writes or calls the AI.
 */

export interface PolicyConfig {
  topic: string;
  daysBack: number;
  selectedCategories: string[];
  sortBy: SortBy;
  page: number;
  perPage: number;
}

const DEFAULTS: PolicyConfig = { topic: TRACKER_TOPIC, daysBack: 365, selectedCategories: [], sortBy: 'date', page: 1, perPage: 25 };
// Shared with the old page, so the period and filters carry over
const STORAGE_KEY = 'policyTracker_config';

function loadConfig(): PolicyConfig {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (s) return { ...DEFAULTS, ...JSON.parse(s) };
  } catch {
    // defaults
  }
  return DEFAULTS;
}

/** One lazily loaded breakdown: its data, whether it is loading, and whether its read failed */
interface Slice<T> {
  data: T;
  loading: boolean;
  failed: boolean;
}
const slice = <T,>(data: T): Slice<T> => ({ data, loading: false, failed: false });

function useSlice<T>(empty: T, load: () => Promise<T>) {
  const [s, setS] = useState<Slice<T>>(slice(empty));
  const run = useCallback(async () => {
    setS((p) => ({ ...p, loading: true, failed: false }));
    try {
      const data = await load();
      setS({ data, loading: false, failed: false });
    } catch {
      setS({ data: empty, loading: false, failed: true });
    }
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps
  return [s, run] as const;
}

export function usePolicyTracker() {
  const [config, setConfig] = useState<PolicyConfig>(loadConfig);
  const { topic, daysBack } = config;
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {
      // per visit only
    }
  }, [config]);

  const [stats, setStats] = useState<PolicyStats | null>(null);
  const [categories, setCategories] = useState<PolicyCategory[]>([]);
  const [temporal, setTemporal] = useState<TemporalData[]>([]);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [articles, setArticles] = useState<PolicyArticle[]>([]);
  const [totalArticles, setTotalArticles] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loadingArticles, setLoadingArticles] = useState(false);

  const [search, setSearch] = useState<{ query: string; results: PolicyArticle[]; loading: boolean } | null>(null);

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    setError(null);
    // The monthly chart needs at least 90 days to show a trend; the old page also turned "All time"
    // into 90 days here, which this keeps as all time
    const temporalDays = daysBack === 0 ? 0 : Math.max(daysBack, 90);
    const [s, c, t] = await Promise.allSettled([getPolicyStats(topic, daysBack), getCategoryDistribution(topic, daysBack), getTemporalData(topic, temporalDays)]);
    if (s.status === 'fulfilled') setStats(s.value);
    else setError(errorText(s.reason));
    setCategories(c.status === 'fulfilled' ? c.value : []);
    setTemporal(t.status === 'fulfilled' ? t.value : []);
    setLoadingOverview(false);
  }, [topic, daysBack]);

  const loadArticles = useCallback(async () => {
    setLoadingArticles(true);
    try {
      const r = await fetchPolicyArticles({ ...config, categories: config.selectedCategories });
      setArticles(r.articles);
      setTotalArticles(r.total_count);
      setTotalPages(r.total_pages);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoadingArticles(false);
    }
  }, [config]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);
  useEffect(() => {
    void loadArticles();
  }, [loadArticles]);

  const [themes, loadThemes] = useSlice<{ themes: ThemeData[]; evolution: ThemeEvolution[] }>(
    { themes: [], evolution: [] },
    useCallback(async () => {
      const [themes, evolution] = await Promise.all([getThemes(topic, daysBack), getThemesEvolution(topic, daysBack)]);
      return { themes, evolution };
    }, [topic, daysBack]),
  );
  const [entities, loadEntities] = useSlice<EntityData[]>([], useCallback(() => getEntities(topic, daysBack), [topic, daysBack]));
  const [geography, loadGeography] = useSlice<GeographyData[]>([], useCallback(() => getGeography(topic, daysBack), [topic, daysBack]));
  const [escalation, loadEscalation] = useSlice<{ markers: EscalationMarkerData[]; trends: EscalationTrend[] }>(
    { markers: [], trends: [] },
    useCallback(async () => {
      const [markers, trends] = await Promise.all([getEscalationMarkers(topic, daysBack), getEscalationTrends(topic, daysBack)]);
      return { markers, trends };
    }, [topic, daysBack]),
  );
  const [timeline, loadTimeline] = useSlice<{ dayOfWeek: DayOfWeekData[]; daily: DailyIntensityData[] }>(
    { dayOfWeek: [], daily: [] },
    useCallback(async () => {
      const [dayOfWeek, daily] = await Promise.all([getDayOfWeek(topic, daysBack), getDailyIntensity(topic, daysBack)]);
      return { dayOfWeek, daily };
    }, [topic, daysBack]),
  );
  const [matrix, loadMatrix] = useSlice<CooccurrenceMatrix | null>(null, useCallback(() => getCooccurrenceMatrix(topic, daysBack), [topic, daysBack]));

  const updateConfig = useCallback((patch: Partial<PolicyConfig>) => {
    setConfig((prev) => {
      const next = { ...prev, ...patch };
      // A new filter, sort or period starts from page one
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
    setSearch({ query: q, results: [], loading: true });
    try {
      const r = await searchPolicyArticles(q, topic);
      setSearch({ query: q, results: r.articles, loading: false });
    } catch (e) {
      setSearch({ query: q, results: [], loading: false });
      setError(errorText(e));
    }
  }, [topic]);

  const related = useCallback((uri: string): Promise<RelatedArticle[]> => getRelatedArticles(uri), []);

  const refresh = useCallback(() => {
    void loadOverview();
    void loadArticles();
  }, [loadOverview, loadArticles]);

  return {
    config, updateConfig, error, clearError: () => setError(null), refresh,
    stats, categories, temporal, loadingOverview,
    articles, totalArticles, totalPages, loadingArticles,
    search, runSearch, clearSearch: () => setSearch(null), related,
    themes, loadThemes, entities, loadEntities, geography, loadGeography, escalation, loadEscalation,
    timeline, loadTimeline, matrix, loadMatrix,
  };
}

export type PolicyTracker = ReturnType<typeof usePolicyTracker>;
