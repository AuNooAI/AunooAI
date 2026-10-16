import { api, ApiError } from '../shell';

/*
 * Submit Articles on the existing routes in app/main.py and app/routes/api_routes.py:
 * links stream through /api/bulk-research-stream (NDJSON, one analysed article per line), pasted
 * text goes to /research (form post), and saving is /api/save_article or /api/save-bulk-articles.
 */

export interface Analysis {
  uri: string;
  title?: string;
  summary?: string;
  news_source?: string;
  publication_date?: string;
  category?: string;
  sentiment?: string;
  sentiment_explanation?: string;
  future_signal?: string;
  future_signal_explanation?: string;
  time_to_impact?: string;
  time_to_impact_explanation?: string;
  driver_type?: string;
  driver_type_explanation?: string;
  tags?: string[] | string;
  bias?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  topic?: string;
  submission_date?: string;
  /** Set by the stream for a link it couldn't fetch or analyse */
  error?: string;
}

export interface Settings {
  topic: string;
  model: string;
  /** Words, as a string: the routes take it that way */
  length: string;
  voice: string;
}

/** The topic's allowed labels for each field the analysis fills */
export interface Labels {
  categories: string[];
  sentiments: string[];
  futureSignals: string[];
  timeToImpacts: string[];
  driverTypes: string[];
}

const list = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);

export async function loadLabels(topic: string): Promise<Labels> {
  const q = topic ? `?topic=${encodeURIComponent(topic)}` : '';
  const [categories, sentiments, futureSignals, timeToImpacts, driverTypes] = await Promise.all(
    ['categories', 'sentiments', 'future_signals', 'time_to_impact', 'driver_types'].map((p) => api(`/api/${p}${q}`).then(list, () => [])),
  );
  return { categories, sentiments, futureSignals, timeToImpacts, driverTypes };
}

export const loadRecent = () => api<Analysis[]>('/api/enriched_articles?limit=10').then((r) => (Array.isArray(r) ? r : []));
export const loadArticle = (uri: string) => api<Analysis>(`/api/article?uri=${encodeURIComponent(uri)}`);
export const deleteArticle = (uri: string) => api(`/api/article?uri=${encodeURIComponent(uri)}`, { method: 'DELETE' });

// The old page called this 'curious_ai_long' for both paths; the stream fell back to
// 'curious_ai' because it never received the field (see analyseLinks)
const SUMMARY_TYPE = 'curious_ai_long';

/**
 * Analyses each link and yields results as they arrive. The stream reads snake_case fields; the old
 * page sent camelCase, so its model, length and voice choices were ignored for links.
 */
export async function* analyseLinks(urls: string[], s: Settings, signal: AbortSignal): AsyncGenerator<Analysis> {
  const res = await fetch('/api/bulk-research-stream', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({ urls, topic: s.topic, model_name: s.model, summary_length: s.length, summary_voice: s.voice, summary_type: SUMMARY_TYPE }),
  });
  if (res.status === 401) window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  if (!res.ok || !res.body) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const d = (await res.json())?.detail;
      if (typeof d === 'string') msg = d;
    } catch {
      // keep the status text
    }
    throw new ApiError(msg, res.status);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const parse = (line: string): Analysis | null => {
    try {
      return line.trim() ? (JSON.parse(line) as Analysis) : null;
    } catch {
      return null;
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const a = parse(line);
      if (a) yield a;
    }
  }
  const last = parse(buffer);
  if (last) yield last;
}

export interface Pasted { url: string; title: string; source: string; date: string; content: string }

/** Analyses pasted text. The title, source and date you typed win over what the analysis finds. */
export async function analysePasted(p: Pasted, s: Settings): Promise<Analysis> {
  const form = new FormData();
  form.append('articleUrl', p.url);
  form.append('articleContent', p.content);
  form.append('selectedTopic', s.topic);
  form.append('modelName', s.model);
  form.append('summaryType', SUMMARY_TYPE);
  form.append('summaryVoice', s.voice);
  form.append('summaryLength', s.length);
  form.append('preservedMetadata', JSON.stringify({ title: p.title, source: p.source, publication_date: p.date }));
  const r = await api<Analysis>('/research', { method: 'POST', body: form });
  return { ...r, title: p.title || r.title, news_source: p.source || r.news_source, publication_date: p.date || r.publication_date };
}

export const tagList = (t: Analysis['tags']): string[] =>
  Array.isArray(t) ? t : (t ?? '').split(',').map((x) => x.trim()).filter(Boolean);

const forSave = (a: Analysis, topic: string) => {
  const { error: _error, ...rest } = a;
  return { ...rest, topic, tags: tagList(a.tags), submission_date: new Date().toISOString() };
};

export const saveOne = (a: Analysis, topic: string) => api('/api/save_article', { method: 'POST', json: forSave(a, topic) });

export const saveMany = (items: Analysis[], topic: string) =>
  api<{ success?: Analysis[]; errors?: { uri?: string; error?: string }[] }>('/api/save-bulk-articles', {
    method: 'POST',
    json: { articles: items.map((a) => ({ ...forSave(a, topic), analyzed: true })) },
  });

/** Asks the AI to draft an incident from a saved article, then files it, as the old page did. */
export async function promoteToIncident(a: Analysis, topic: string): Promise<boolean> {
  const r = await api<{ success?: boolean; suggested_incident?: Record<string, unknown> }>('/api/analyze-article-for-incident', {
    method: 'POST',
    json: { article_uri: a.uri, topic },
  });
  if (!r.success || !r.suggested_incident) return false;
  await api('/api/news-feed/saved/incidents', {
    method: 'POST',
    json: {
      ...r.suggested_incident,
      topic,
      article_uris: [a.uri],
      article_metadata: [{ uri: a.uri, title: a.title, summary: a.summary, source: a.news_source, publication_date: a.publication_date }],
    },
  });
  return true;
}
