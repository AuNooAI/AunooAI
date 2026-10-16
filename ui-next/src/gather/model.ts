/**
 * View types for the Gather page and the mappings from the monolith API.
 * The page components are the design's (AuNooAI/aunoo-design apps/aunoo/gather), which work on
 * these types; the API clients are shared with the React 18 app (ui/src/services).
 */
import type { SelectOption } from '@aunoo/ui';
import type {
  ArticleMatch, AvailableModel, AvailableProvider, KeywordGroupSettings, KeywordGroupSummary, KeywordMonitorSettings,
  KeywordStats, MonitoredKeyword, RSSFeed,
} from '@monolith/gatherApi';
import { stamp } from './lib';

/* ---------- Settings ---------- */

export type IntervalUnit = 'minutes' | 'hours' | 'days';
export const UNIT_OPTIONS: SelectOption[] = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

/** Keyword settings store the unit as seconds: 60 / 3600 / 86400. */
const UNIT_SECONDS: Record<IntervalUnit, number> = { minutes: 60, hours: 3600, days: 86400 };
const unitFromSeconds = (s: number | undefined): IntervalUnit => (s === 86400 ? 'days' : s === 3600 ? 'hours' : 'minutes');

export interface CollectSettings {
  interval: string;
  unit: IntervalUnit;
  dateRange: string;
  dailyLimit: string;
  providers: string[];
  /** Xpoz platforms for a group; null = the site default. */
  socialPlatforms: string[] | null;
  autoProcessing: boolean;
  qualityControl: boolean;
  approvedOnly: boolean;
  /** 0–100 */
  minRelevance: number;
  model: string;
  /** 0–2 */
  temperature: number;
  maxTokens: string;
  autoRegenerate: boolean;
}

const parseList = (raw: string | null | undefined): string[] | null => {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : null;
  } catch {
    return null;
  }
};

export function toCollectSettings(s: KeywordMonitorSettings): CollectSettings {
  return {
    interval: String(s.check_interval ?? 1),
    unit: unitFromSeconds(s.interval_unit),
    dateRange: String(s.search_date_range ?? 7),
    dailyLimit: String(s.daily_request_limit ?? 100),
    providers: parseList(s.providers) ?? [s.provider || 'newsapi'],
    socialPlatforms: null,
    autoProcessing: Boolean(s.auto_ingest_enabled),
    qualityControl: Boolean(s.quality_control_enabled),
    approvedOnly: Boolean(s.auto_save_approved_only),
    minRelevance: Math.round((s.min_relevance_threshold ?? 0) * 100),
    model: s.default_llm_model ?? '',
    temperature: s.llm_temperature ?? 0.7,
    maxTokens: String(s.llm_max_tokens ?? 1000),
    autoRegenerate: Boolean(s.auto_regenerate_reports),
  };
}

/** Global settings to save: the loaded record with the form's values on top. */
export function fromCollectSettings(c: CollectSettings, base: KeywordMonitorSettings): KeywordMonitorSettings {
  return {
    ...base,
    check_interval: Number(c.interval),
    interval_unit: UNIT_SECONDS[c.unit],
    search_date_range: Number(c.dateRange),
    daily_request_limit: Number(c.dailyLimit),
    providers: JSON.stringify(c.providers),
    auto_ingest_enabled: c.autoProcessing,
    quality_control_enabled: c.qualityControl,
    auto_save_approved_only: c.approvedOnly,
    min_relevance_threshold: c.minRelevance / 100,
    default_llm_model: c.model || undefined,
    llm_temperature: c.temperature,
    llm_max_tokens: Number(c.maxTokens),
    auto_regenerate_reports: c.autoRegenerate,
  };
}

/** A group's effective settings: the global form values with the group's own values on top. */
export function groupCollectSettings(g: KeywordGroupSettings, global: CollectSettings): CollectSettings {
  return {
    ...global,
    ...(g.check_interval != null && { interval: String(g.check_interval) }),
    ...(g.interval_unit != null && { unit: unitFromSeconds(g.interval_unit) }),
    ...(g.search_date_range != null && { dateRange: String(g.search_date_range) }),
    ...(parseList(g.providers) && { providers: parseList(g.providers)! }),
    socialPlatforms: parseList(g.social_platforms),
    ...(g.auto_ingest_enabled != null && { autoProcessing: g.auto_ingest_enabled }),
    ...(g.quality_control_enabled != null && { qualityControl: g.quality_control_enabled }),
    ...(g.auto_save_approved_only != null && { approvedOnly: g.auto_save_approved_only }),
    ...(g.min_relevance_threshold != null && { minRelevance: Math.round(g.min_relevance_threshold * 100) }),
    ...(g.default_llm_model && { model: g.default_llm_model }),
    ...(g.llm_temperature != null && { temperature: g.llm_temperature }),
    ...(g.llm_max_tokens != null && { maxTokens: String(g.llm_max_tokens) }),
  };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/**
 * Per-group update: a field that matches the global value is sent as null, so it inherits
 * again (the facade writes NULL); a field that differs is stored on the group.
 */
export function groupSettingsPatch(c: CollectSettings, global: CollectSettings) {
  const pick = <T,>(key: keyof CollectSettings, value: T) => (same(c[key], global[key]) ? null : value);
  const scheduleCustom = !same(c.interval, global.interval) || !same(c.unit, global.unit);
  return {
    // Interval and unit only make sense together
    check_interval: scheduleCustom ? Number(c.interval) : null,
    interval_unit: scheduleCustom ? UNIT_SECONDS[c.unit] : null,
    search_date_range: pick('dateRange', Number(c.dateRange)),
    providers: pick('providers', JSON.stringify(c.providers)),
    social_platforms: c.providers.includes('xpoz') && c.socialPlatforms?.length ? JSON.stringify(c.socialPlatforms) : null,
    auto_ingest_enabled: pick('autoProcessing', c.autoProcessing),
    min_relevance_threshold: pick('minRelevance', c.minRelevance / 100),
    quality_control_enabled: pick('qualityControl', c.qualityControl),
    auto_save_approved_only: pick('approvedOnly', c.approvedOnly),
    default_llm_model: pick('model', c.model),
    llm_temperature: pick('temperature', c.temperature),
    llm_max_tokens: pick('maxTokens', Number(c.maxTokens)),
  };
}

export const providerOptions = (providers: AvailableProvider[]) => providers;

export function modelOptions(models: AvailableModel[], current: string): SelectOption[] {
  const opts = models.map((m) => ({ value: m.name, label: m.label ?? m.name }));
  // A saved alias that's no longer offered stays listed, so opening the dialog doesn't change it
  if (current && !opts.some((o) => o.value === current)) opts.unshift({ value: current, label: `${current} (no longer offered)` });
  return opts;
}

/* ---------- Keyword groups ---------- */

export interface Keyword {
  id: string;
  text: string;
  matches: number;
  /** Average relevance, 0–100 */
  avg: number;
  highPct: number;
  lowPct: number;
}

export type GroupStatus = 'success' | 'error' | 'pending' | 'never_run';

export interface KeywordGroup {
  id: string;
  name: string;
  topic: string;
  keywords: Keyword[];
  total: number;
  relevant: number;
  irrelevant: number;
  unscored: number;
  last24h: number;
  week: number;
  paused: boolean;
  status: GroupStatus;
  customSettings: boolean;
  lastChecked: string;
  /** null = no schedule known */
  nextAt: Date | null;
  lastError?: string;
  trend: number[];
}

const TREND_DAYS = 30;

/** daily_counts holds only the days with articles; fill the last 30 days, oldest first. */
function trendFrom(daily: [string, number][] | undefined): number[] {
  const byDay = new Map((daily ?? []).map(([d, n]) => [d.slice(0, 10), n]));
  const out: number[] = [];
  const today = new Date();
  for (let i = TREND_DAYS - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - i));
    out.push(byDay.get(d.toISOString().slice(0, 10)) ?? 0);
  }
  return out;
}

export function buildGroups(summaries: KeywordGroupSummary[], keywords: MonitoredKeyword[], stats: KeywordStats[]): KeywordGroup[] {
  const statById = new Map(stats.map((s) => [s.keyword_id, s]));
  return summaries.map((s) => ({
    id: String(s.id),
    name: s.name,
    topic: s.topic,
    keywords: keywords
      .filter((k) => k.group_id === s.id)
      .map((k) => {
        const st = statById.get(k.id);
        return {
          id: String(k.id),
          text: k.keyword,
          matches: st?.total_matches ?? 0,
          avg: Math.round((st?.avg_relevance ?? 0) * 100),
          highPct: Math.round(st?.high_relevance_pct ?? 0),
          lowPct: Math.round(st?.low_relevance_pct ?? 0),
        };
      }),
    total: s.total_articles ?? 0,
    relevant: s.relevant_count ?? 0,
    irrelevant: s.irrelevant_count ?? 0,
    unscored: s.unscored_count ?? 0,
    last24h: s.articles_past_24h ?? 0,
    week: s.articles_past_week ?? 0,
    paused: s.is_active === false,
    status: s.status,
    customSettings: Boolean(s.has_custom_schedule || s.has_custom_providers),
    lastChecked: s.last_checked ? stamp(new Date(s.last_checked)) : 'Never',
    nextAt: s.next_check_at ? new Date(s.next_check_at) : null,
    lastError: s.last_error,
    trend: trendFrom(s.daily_counts),
  }));
}

/* ---------- Articles ---------- */

/** keyword_relevance_score at or above this counts as relevant (as in the old detail panel). */
export const RELEVANT_CUTOFF = 0.39;

export interface Article {
  id: string;
  uri: string;
  title: string;
  source: string;
  date: string;
  /** 0–100, or null when unscored */
  score: number | null;
  relevant: boolean;
  sentiment?: string;
  raw: ArticleMatch;
}

export const toArticle = (a: ArticleMatch): Article => ({
  id: String(a.id),
  uri: a.uri,
  title: a.title || a.uri,
  source: a.source ?? '',
  date: a.publication_date ? new Date(a.publication_date).toLocaleDateString('en-GB') : '',
  score: a.keyword_relevance_score == null ? null : Math.round(a.keyword_relevance_score * 100),
  relevant: (a.keyword_relevance_score ?? 0) >= RELEVANT_CUTOFF,
  sentiment: a.sentiment,
  raw: a,
});

/* ---------- RSS feeds ---------- */

/** The backend's spelling ('very high', 'mostly factual'…); 'none' = don't set. */
export type FactualReporting = 'none' | 'very high' | 'high' | 'mostly factual' | 'mixed' | 'low' | 'very low';
export const FACTUAL_OPTIONS: SelectOption[] = [
  { value: 'none', label: 'Don’t set (use MBFC/AI)' },
  { value: 'very high', label: 'Very High' },
  { value: 'high', label: 'High' },
  { value: 'mostly factual', label: 'Mostly Factual' },
  { value: 'mixed', label: 'Mixed' },
  { value: 'low', label: 'Low' },
  { value: 'very low', label: 'Very Low' },
];

export interface Feed {
  id: string;
  name: string;
  url: string;
  topic: string;
  description: string;
  interval: string;
  unit: IntervalUnit;
  active: boolean;
  /** 0–100; 0 = off */
  threshold: number;
  factual: FactualReporting;
  lastScan: string;
  lastCheckedAt: Date | null;
  detected: number;
  enriched: number;
  error?: string;
}

const asUnit = (u: string | undefined): IntervalUnit => (u === 'hours' || u === 'days' ? u : 'minutes');

export const toFeed = (f: RSSFeed): Feed => ({
  id: String(f.id),
  name: f.name,
  url: f.url,
  topic: f.topic,
  description: f.description ?? '',
  interval: String(f.check_interval ?? 60),
  unit: asUnit(f.interval_unit),
  active: f.is_active,
  threshold: Math.round(f.relevance_threshold ?? 0),
  factual: (FACTUAL_OPTIONS.some((o) => o.value === f.default_factual_reporting) ? f.default_factual_reporting : 'none') as FactualReporting,
  lastScan: f.last_checked_at ? stamp(new Date(f.last_checked_at)) : 'Never',
  lastCheckedAt: f.last_checked_at ? new Date(f.last_checked_at) : null,
  detected: f.articles_fetched ?? 0,
  enriched: f.articles_enriched ?? 0,
  error: f.last_error || undefined,
});

export const minutesFor = (interval: string, unit: IntervalUnit) => Number(interval) * (UNIT_SECONDS[unit] / 60);
