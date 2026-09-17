/**
 * Swiss Election Watch API client (/api/swiss-disinfo).
 * Types mirror app/services/swiss_disinfo_service.py.
 */

const BASE = '/api/swiss-disinfo';

async function get<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    }
  }
  const url = qs.toString() ? `${BASE}${path}?${qs}` : `${BASE}${path}`;
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export type Stance = 'promotes' | 'reports' | 'debunks';
export type Lang = 'de' | 'fr' | 'it' | 'en';

export interface Overview {
  days_back: number;
  approved: number;
  approved_prev: number;
  rejected: number;
  extracted: number;
  narratives_active: number;
  narratives_new: number;
  vector_share: number;
  sources_scanned: number;
  next_vote: { date: string; label: string; days_to: number } | null;
  stance_series: { day: string; promotes: number; reports: number; debunks: number }[];
  categories: { category: string; count: number }[];
  attribution: { actor: string; count: number }[];
}

export interface Narrative {
  id: number;
  name: string;
  statement: string;
  attribution: string | null;
  attribution_confidence: number | null;
  first_seen: string | null;
  last_seen: string | null;
  article_count: number;
  languages: string[];
  recent_count: number;
  promotes: number;
  reports: number;
  debunks: number;
  last7: number;
  prev7: number;
  top_outlets: string[];
}

export interface NarrativeArticle {
  uri: string;
  title: string;
  news_source: string | null;
  url: string | null;
  stance: Stance;
  language: string | null;
  source_domain: string | null;
  source_tier: string | null;
  article_date: string | null;
  topic_alignment_score: number | null;
}

export interface NarrativeDetail extends Omit<Narrative, 'recent_count' | 'promotes' | 'reports' | 'debunks' | 'last7' | 'prev7' | 'top_outlets'> {
  articles: NarrativeArticle[];
  language_series: { day: string; language: string; count: number }[];
  fact_checks: { uri: string; fact_check: Record<string, string>; date: string | null }[];
}

export interface SourceRow {
  domain: string;
  name: string;
  tier: string;
  language: string | null;
  articles: number;
  last7: number;
  narratives: number;
  promoted: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface Cooccurrence {
  sources: string[];
  narratives: { id: number; name: string }[];
  cells: { source: string; narrative_id: number; count: number }[];
}

export interface TargetRow {
  type: string;
  name: string;
  articles: number;
  last7: number;
  last_seen: string | null;
  seeded: boolean;
}

export interface TechniqueRow {
  technique: string;
  articles: number;
  last7: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface LanguagesData {
  totals: Record<string, number>;
  narratives: {
    id: number;
    name: string;
    by_language: Record<string, number>;
    first_by_language: Record<string, string>;
    crossed_from?: string;
    crossed_to?: string[];
    lag_days?: number;
  }[];
  crossings: LanguagesData['narratives'];
  weekly: { week: string; de: number; fr: number; it: number; en: number }[];
}

export interface CalendarData {
  daily: { day: string; count: number; promotes: number }[];
  first_seen: { id: number; name: string; day: string }[];
  events: { id: number; event_type: string; event_subtype: string | null; title: string; description: string | null; significance: string; event_date: string }[];
  votes: { date: string; label: string; days_to: number }[];
}

export interface ResponsesData {
  fact_checks: { uri: string; date: string | null; fact_check: Record<string, string>; title: string; news_source: string | null; url: string | null }[];
  responses: { uri: string; date: string | null; response: Record<string, string>; title: string; news_source: string | null; url: string | null }[];
}

export interface SdArticle {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  url: string | null;
  category: string | null;
  sentiment: string | null;
  publication_date: string | null;
  submission_date: string | null;
  topic_alignment_score: number | null;
  language: string | null;
  source_tier: string | null;
  attribution: string | null;
  techniques: string[];
  targets: { type: string; name: string }[] | null;
  narratives: { statement: string; stance: Stance }[] | null;
  fact_check: Record<string, string> | null;
  response: Record<string, string> | null;
  extracted_at: string | null;
}

export interface ArticlesPage {
  total: number;
  page: number;
  per_page: number;
  articles: SdArticle[];
}

export interface Brief {
  id: number;
  brief_text: string;
  sections: Record<string, string> | null;
  narrative_count: number;
  article_count: number;
  days_back: number;
  model: string | null;
  created_at: string;
}

export interface ProcessStatus {
  running: boolean;
  total: number;
  processed: number;
  on_topic: number;
  narratives_created: number;
  errors: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  status?: string;
  message?: string;
}

/** A scope is one watch: its own articles, narratives, prompt framing and calendar. */
export interface Scope {
  topic: string;
  label: string;
  blurb: string;
}

export interface HowItWorks {
  topic: string;
  label: string;
  blurb: string;
  keyword_groups: { id: number; name: string; language: string | null; providers: string | null; kind: string; is_active: boolean; keywords: string[]; threshold: number | null; last_checked: string | null }[];
  feeds: { id: number; name: string; url: string; is_active: boolean; tier: string | null; language: string | null; threshold: number | null; fetched: number | null; last_checked: string | null; error: string | null; produced: { articles: number; approved: number } }[];
  telegram_channels: { channel: string; url: string; tier: string }[];
  produced_by_source: { source: string; articles: number; approved: number }[];
  schedules: { name: string; enabled: boolean; every: string; model: string | null; batch_size: number; runs: number; last_run: string | null; next_run: string | null; status: string | null }[];
  settings: {
    relevance_threshold: number | null;
    search_fields: string | null;
    extraction_model: string;
    brief_model: string;
    social_min_alignment: number;
    narrative_shortlist_floor: number;
    stances: string[]; tiers: string[]; techniques: string[]; attributions: string[];
  };
}

export const getHowItWorks = (topic?: string) => get<HowItWorks>('/how-it-works', { topic });
export const getScopes = () => get<{ scopes: Scope[]; default: string }>('/scopes');
export const getOverview = (days_back: number, topic?: string) => get<Overview>('/overview', { days_back, topic });
export const getNarratives = (days_back: number, language?: string, stance?: string, topic?: string) =>
  get<Narrative[]>('/narratives', { days_back, language, stance, topic });
export const getNarrativeDetail = (id: number, topic?: string) =>
  get<NarrativeDetail>(`/narratives/${id}`, { topic });
export const getSources = (days_back: number, topic?: string) => get<SourceRow[]>('/sources', { days_back, topic });
export const getCooccurrence = (days_back: number, topic?: string) => get<Cooccurrence>('/cooccurrence', { days_back, topic });
export const getTargets = (days_back: number, topic?: string) => get<TargetRow[]>('/targets', { days_back, topic });
export const getTechniques = (days_back: number, topic?: string) => get<TechniqueRow[]>('/techniques', { days_back, topic });
export const getLanguages = (days_back: number, topic?: string) => get<LanguagesData>('/languages', { days_back, topic });
export const getCalendar = (days_back: number, topic?: string) => get<CalendarData>('/calendar', { days_back, topic });
export const getResponses = (days_back: number, topic?: string) => get<ResponsesData>('/responses', { days_back, topic });
export const getArticles = (p: { days_back: number; language?: string; tier?: string; attribution?: string; technique?: string; page?: number; per_page?: number; topic?: string }) =>
  get<ArticlesPage>('/articles', p);
export const getBrief = (topic?: string) => get<Brief | null>('/brief', { topic });
export const generateBrief = (days_back: number, topic?: string) => post<Brief>('/brief', { days_back, topic });
export const getProcessStatus = () => get<ProcessStatus>('/process-articles/status');
export const startProcessing = (process_all = false, batch_size = 100, topic?: string) =>
  post<ProcessStatus>('/process-articles', { process_all, batch_size, topic });
export const getUnprocessedCount = (topic?: string) => get<{ count: number }>('/unprocessed-count', { topic });
