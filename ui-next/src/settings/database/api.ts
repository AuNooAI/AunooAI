import { api } from '../../shell';

/*
 * The Database Editor's calls, on the routes the old page used (templates/database_editor.html):
 * /api/topics, /api/topics/{topic}/articles and /stats, /api/article (GET, DELETE),
 * /api/save_article, /api/bulk_delete_articles, /api/vector-delete/{uri}, the option lists
 * (/api/categories, /api/future_signals, /api/sentiments, /api/time_to_impact, /api/driver_types)
 * and /api/articles/{uri}/annotations.
 */

export interface EditorArticle {
  uri: string;
  title?: string | null;
  news_source?: string | null;
  summary?: string | null;
  publication_date?: string | null;
  submission_date?: string | null;
  topic?: string | null;
  category?: string | null;
  sentiment?: string | null;
  sentiment_explanation?: string | null;
  future_signal?: string | null;
  future_signal_explanation?: string | null;
  time_to_impact?: string | null;
  time_to_impact_explanation?: string | null;
  driver_type?: string | null;
  driver_type_explanation?: string | null;
  tags?: string[] | string | null;
  analyzed?: boolean | number | string | null;
}

export interface Annotation {
  id: number;
  author: string;
  content: string;
  is_private: boolean;
  created_at: string;
}

export interface OptionLists {
  categories: string[];
  futureSignals: string[];
  sentiments: string[];
  timeToImpact: string[];
  driverTypes: string[];
}

/** The server caps one load at 1,000 articles (main.py get_topic_articles) */
export const LOAD_CAP = 1000;

export const listTopics = () => api<{ name: string }[]>('/api/topics').then((r) => r.map((t) => t.name));

export const topicStats = (topic: string) =>
  api<{ articleCount: number; latestArticle: string | null }>(`/api/topics/${encodeURIComponent(topic)}/stats`);

export const topicArticles = (topic: string, start: string, end: string) =>
  api<{ articles: EditorArticle[] }>(`/api/topics/${encodeURIComponent(topic)}/articles?${new URLSearchParams({ start_date: start, end_date: end })}`).then((r) => r.articles ?? []);

export const getArticle = (uri: string) => api<EditorArticle>(`/api/article?uri=${encodeURIComponent(uri)}`);

const list = (path: string, topic?: string) =>
  api<unknown>(`${path}${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`).then(
    (r) => (Array.isArray(r) ? r.filter((x): x is string => typeof x === 'string' && x.length > 0) : []),
    () => [] as string[],
  );

/** The topic's own allowed values for each field, used by the edit form's pickers */
export async function optionLists(topic?: string): Promise<OptionLists> {
  const [categories, futureSignals, sentiments, timeToImpact, driverTypes] = await Promise.all([
    list('/api/categories', topic), list('/api/future_signals', topic), list('/api/sentiments', topic), list('/api/time_to_impact', topic), list('/api/driver_types', topic),
  ]);
  return { categories, futureSignals, sentiments, timeToImpact, driverTypes };
}

/** Every field is required by the server's ArticleData model, so blanks go as empty strings */
export interface SaveBody {
  title: string; news_source: string; uri: string; publication_date: string; summary: string;
  category: string; future_signal: string; future_signal_explanation: string; sentiment: string; sentiment_explanation: string;
  time_to_impact: string; time_to_impact_explanation: string; tags: string[]; driver_type: string; driver_type_explanation: string;
  submission_date: string; topic: string;
}
export const saveArticle = (body: SaveBody) => api('/api/save_article', { method: 'POST', json: body });

export const deleteArticle = (uri: string) => api(`/api/article?uri=${encodeURIComponent(uri)}`, { method: 'DELETE' });

/** Also removes the article from the search index (pgvector); the old page offered this as "Database + Vector Store" */
export const deleteFromIndex = (uri: string) => api(`/api/vector-delete/${encodeURIComponent(uri)}`, { method: 'DELETE' });

// The bulk route decodes each address twice (database.bulk_delete_articles), so each is encoded twice.
// The old page encoded once, so an address containing "%" or "+" was decoded too far and missed.
export const bulkDelete = (uris: string[]) =>
  api<{ deleted_count: number; message?: string }>('/api/bulk_delete_articles', { method: 'DELETE', json: { uris: uris.map((u) => encodeURIComponent(encodeURIComponent(u))) } });

// The annotation routes decode the URI twice, so it is encoded twice. The old page's edit call
// encoded it once; edits and deletes are matched by id, so both ways work, but this keeps one form.
const annoPath = (uri: string) => `/api/articles/${encodeURIComponent(encodeURIComponent(uri))}/annotations`;
export const listAnnotations = (uri: string) => api<Annotation[]>(`${annoPath(uri)}?include_private=true`).then((r) => (Array.isArray(r) ? r : []));
export const addAnnotation = (uri: string, content: string, isPrivate: boolean) => api(annoPath(uri), { method: 'POST', json: { content, is_private: isPrivate } });
export const updateAnnotation = (uri: string, id: number, content: string, isPrivate: boolean) =>
  api(`${annoPath(uri)}/${id}`, { method: 'PUT', json: { content, is_private: isPrivate } });
export const deleteAnnotation = (uri: string, id: number) => api(`${annoPath(uri)}/${id}`, { method: 'DELETE' });

export const isAnalyzed = (a: EditorArticle) => a.analyzed === true || a.analyzed === 1 || a.analyzed === '1' || a.analyzed === 'true';

export function isoDay(d: Date) {
  return d.toISOString().slice(0, 10);
}

export function formatDay(s?: string | null) {
  if (!s) return '—';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
