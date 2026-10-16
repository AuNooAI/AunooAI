import { api } from '../../shell';

/*
 * Exploratory Analysis data, on the vector routes the old page used (app/routes/vector_routes.py,
 * app/routes/saved_searches.py). Searches go to /api/vector-search with the raw query: the server
 * parses the query language itself (app/kissql). A keyword="…" query takes the full-text path
 * (/api/search_articles) instead, as on the old page.
 */

export type Meta = Record<string, unknown> & {
  uri?: string;
  title?: string;
  summary?: string;
  news_source?: string;
  publication_date?: string;
  category?: string;
  sentiment?: string;
  topic?: string;
  driver_type?: string;
  time_to_impact?: string;
};

export interface SearchHit { id: string; score: number; metadata: Meta }
export type Facets = Record<string, Record<string, number>>;
/** category → date (YYYY-MM-DD) → count */
export type Timeline = Record<string, Record<string, number>>;
export interface Comparison {
  total_before: number;
  total_after: number;
  facet_impact?: Record<string, Record<string, { diff: number }>>;
}
export interface SearchResult {
  results: SearchHit[];
  facets: Facets;
  timeline: Timeline;
  comparison?: Comparison | null;
}

export interface SavedSearch { id: string; name: string; description?: string | null; tags?: string | null; query: string; created_at?: string | null }

export interface ProjectionPoint {
  id: string; x: number; y: number; cluster: number; title?: string | null;
  sentiment?: string | null; driver_type?: string | null; category?: string | null; time_to_impact?: string | null;
}
export interface ClusterInfo { keywords?: string[]; title?: string; summary?: string }
export interface Projection { points: ProjectionPoint[]; explain: Record<string, ClusterInfo | string[]>; error?: string }

export interface Patterns { ngrams: { text: string; count: number }[]; tag_stats?: Record<string, { total: number }>; error?: string }
export interface Anomaly { id: string; score: number; metadata?: Meta; error?: string }

/** Filters taken from the page address, as the old page did (?category=…) */
export const URL_FILTERS = ['category', 'topic', 'sentiment', 'news_source', 'future_signal'] as const;

export function urlFilters(): Record<string, string> {
  const p = new URLSearchParams(window.location.search);
  const out: Record<string, string> = {};
  for (const f of URL_FILTERS) {
    const v = p.get(f);
    if (v) out[f] = v;
  }
  return out;
}

/** The query string every analysis call shares, so the patterns and the map cover the same articles as the list */
export function scopeParams(q: string, topK: number, cluster?: number): URLSearchParams {
  const p = new URLSearchParams({ q, top_k: String(topK) });
  for (const [k, v] of Object.entries(urlFilters())) p.append(k, v);
  if (cluster !== undefined) p.append('cluster', String(cluster));
  return p;
}

export const vectorSearch = (params: URLSearchParams) => api<SearchResult>(`/api/vector-search?${params}`);

/** Facets and a per-category timeline counted in the browser (keyword searches, and after a date filter) */
export function facetsAndTimeline(results: SearchHit[]): { facets: Facets; timeline: Timeline } {
  const facets: Facets = {};
  const timeline: Timeline = {};
  for (const { metadata: m } of results) {
    for (const f of ['topic', 'category', 'news_source', 'driver_type', 'sentiment']) {
      const v = m[f];
      if (typeof v === 'string' && v) (facets[f] ??= {})[v] = (facets[f][v] ?? 0) + 1;
    }
    if (m.publication_date) {
      const d = new Date(m.publication_date);
      if (!Number.isNaN(d.getTime())) {
        const day = d.toISOString().slice(0, 10);
        const cat = m.category || 'Uncategorised';
        (timeline[cat] ??= {})[day] = (timeline[cat][day] ?? 0) + 1;
      }
    }
  }
  return { facets, timeline };
}

export async function keywordSearch(keyword: string, limit: number): Promise<SearchResult> {
  const p = new URLSearchParams({ keyword, per_page: String(limit), search_fields: 'title,summary,tags' });
  const raw = await api<{ articles?: Meta[] }>(`/api/search_articles?${p}`);
  const results = (raw.articles ?? []).map((a) => ({ id: String(a.uri ?? ''), score: 0, metadata: a }));
  return { results, ...facetsAndTimeline(results), comparison: null };
}

export const similarTo = (uri: string) => api<{ results: SearchHit[] }>(`/api/vector-similar?uri=${encodeURIComponent(uri)}&top_k=5`).then((r) => r.results ?? []);

export const getProjection = (params: URLSearchParams) => api<Projection>(`/api/embedding_projection?${params}`);
export const getPatterns = (params: URLSearchParams) => api<Patterns>(`/api/patterns?${params}`);
export async function getAnomalies(params: URLSearchParams): Promise<Anomaly[]> {
  const p = new URLSearchParams(params);
  // The old page capped outliers at 200
  if (Number(p.get('top_k') ?? 20) > 200) p.set('top_k', '200');
  const r = await api<Anomaly[]>(`/api/embedding_anomalies?${p}`);
  return Array.isArray(r) ? r.filter((a) => !a.error) : [];
}

/** AI summary of up to 100 articles (one model call, the site's default model) */
export const summarise = (ids: string[]) =>
  api<{ response?: string; error?: string }>('/api/vector-summary', { method: 'POST', json: { ids: ids.slice(0, 100) } }).then((r) => r.response || r.error || 'No summary came back.');

export const listSaved = () => api<SavedSearch[]>('/api/saved-searches');
export const saveSearch = (s: SavedSearch) => api<SavedSearch>('/api/saved-searches', { method: 'POST', json: s });
export const deleteSaved = (id: string) => api(`/api/saved-searches/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Removes the article's embedding only; the article stays in the database and the rest of the site */
export const removeFromSearch = (id: string) => api(`/api/vector-delete/${encodeURIComponent(id)}`, { method: 'DELETE' });
