import { createElement, type MouseEvent } from 'react';
import { api } from '../../shell';
import type { NewsArticle, SixArticlesReport, TopStory } from '@monolith/newsFeedApi';
import type { ArticleTheme, Incident } from '@monolith/narrativeExplorerApi';
import type { DateRange, ExploreConfig } from '../lib/useExploreConfig';

/*
 * The News Feed's calls, on the same routes and parameters as the old page (ui/src/services/
 * newsFeedApi.ts, narrativeExplorerApi.ts). Reads go through the old helpers; writes go through
 * `api` here so a failure reaches the user instead of the console.
 */

export type { NewsArticle, SixArticlesReport, TopStory, ArticleTheme, Incident };

// ── Dates ───────────────────────────────────────────────────────────────

const DAYS: Record<DateRange, number> = { '24h': 1, '72h': 3, '7d': 7, '30d': 30, '3m': 90, '1y': 365, all: 365 };
/** Incident tracking reads at most 90 days */
export const incidentDays = (r: DateRange) => Math.min(DAYS[r], 90);
export const windowDates = (days: number) => {
  const now = new Date();
  const iso = (d: Date) => d.toISOString().split('T')[0];
  return { startDate: iso(new Date(now.getTime() - days * 86400000)), endDate: iso(now) };
};

// ── Starred articles (kept in this browser, shared with the old page) ──

const STARRED = 'newsFeed_starred';
export function loadStarred(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STARRED) ?? '[]');
  } catch {
    return [];
  }
}
export function saveStarred(uris: string[]) {
  try {
    localStorage.setItem(STARRED, JSON.stringify(uris));
  } catch {
    // lasts for this visit
  }
}

// ── Executive briefing ──────────────────────────────────────────────────

/** GET /api/news-feed/six-articles. Generates with the AI when the server has no briefing for this key today. */
export async function fetchBriefing(c: ExploreConfig, topic: string | undefined, starred: string[], force: boolean): Promise<SixArticlesReport> {
  const q = new URLSearchParams({ date_range: c.dateRange, persona: c.persona, article_count: String(c.articleCount), model: c.model });
  if (topic) q.set('topic', topic);
  if (c.profileId != null) q.set('profile_id', String(c.profileId));
  if (force) q.set('force_regenerate', 'true');
  if (starred.length) q.set('starred_articles', starred.join(','));
  const r = await api<{ six_articles?: TopStory[] } & Partial<SixArticlesReport>>(`/api/news-feed/six-articles?${q}`);
  // The route returns { six_articles: [...] }; the old client also accepted a full report
  return {
    date: r.date ?? new Date().toISOString().slice(0, 10),
    title: r.title ?? 'Executive Briefing',
    articles: r.six_articles ?? r.articles ?? [],
    generated_at: r.generated_at ?? new Date().toISOString(),
    executive_summary: r.executive_summary ?? '',
    key_themes: r.key_themes ?? [],
    bias_distribution: r.bias_distribution ?? {},
    factuality_overview: r.factuality_overview ?? {},
  };
}

export interface Snapshot {
  generated_at: string;
  persona?: string;
  topic?: string | null;
  briefing_articles?: TopStory[];
}

/** The scheduled run's latest briefing. A database read only. */
export const fetchSnapshot = (topic?: string) =>
  api<{ has_snapshot?: boolean; snapshot?: Snapshot }>(`/api/news-feed/dashboard/snapshot/latest${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`)
    .then((r) => (r.has_snapshot && r.snapshot?.briefing_articles?.length ? r.snapshot : null))
    .catch(() => null);

export interface BriefingPrefs {
  more_like: { headline: string }[];
  less_like: { headline: string }[];
}
export const fetchBriefingPrefs = () => api<BriefingPrefs>('/api/briefing-preferences').catch(() => ({ more_like: [], less_like: [] }));
export const fetchHiddenBriefings = () => api<{ hidden_briefings?: string[] }>('/api/hidden-briefings').then((r) => r.hidden_briefings ?? [], () => []);
export const hideBriefing = (headline: string) => api('/api/briefing-hide', { method: 'POST', json: { headline } });

export function setBriefingPreference(s: TopStory, pref: 'more' | 'less' | null) {
  const headline = s.headline || s.title;
  if (!pref) return api('/api/briefing-preference', { method: 'DELETE', json: { headline } });
  return api('/api/briefing-preference', {
    method: 'POST',
    json: {
      headline,
      preference: pref,
      briefing_data: {
        summary: s.summary, category: s.category, executive_takeaway: s.executive_takeaway, strategic_relevance: s.strategic_relevance,
        signal_strength: s.signal_strength, risk_opportunity: s.risk_opportunity, time_horizon: s.time_horizon, source: s.source, url: s.url ?? s.uri,
      },
    },
  });
}

// ── Incidents ───────────────────────────────────────────────────────────

export interface IncidentPrefs {
  more_like: { incident_name: string }[];
  less_like: { incident_name: string }[];
}
export const fetchIncidentPrefs = () => api<IncidentPrefs>('/api/incident-preferences').catch(() => ({ more_like: [], less_like: [] }));

export function setIncidentPreference(i: Incident, pref: 'more' | 'less' | null, browsingTopic?: string) {
  const name = i.name || i.title || '';
  if (!pref) return api('/api/incident-preference', { method: 'DELETE', json: { incident_name: name } });
  const meta = i.article_metadata ?? [];
  return api('/api/incident-preference', {
    method: 'POST',
    json: {
      incident_name: name,
      preference: pref,
      incident_data: {
        type: i.type, topic: i.topic, entities: i.entities, summary: i.description || i.summary,
        article_urls: i.article_uris ?? meta.map((m) => m.uri).filter(Boolean), article_titles: meta.map((m) => m.title),
        significance: i.significance, browsing_topic: browsingTopic,
      },
    },
  });
}

/** Marks an incident deleted so the next run leaves it out. */
export const hideIncident = (name: string) => api('/api/incident-status', { method: 'POST', json: { incident_name: name, status: 'deleted' } });

export interface SavedIncident extends Incident {
  _saved_id?: number;
}
export const fetchSavedIncidents = () => api<{ incidents?: SavedIncident[] }>('/api/news-feed/saved/incidents').then((r) => r.incidents ?? [], () => []);

export function saveIncident(i: Incident, topic: string) {
  return api('/api/news-feed/saved/incidents', {
    method: 'POST',
    json: {
      name: i.name || i.title, title: i.title, type: i.type, significance: i.significance, description: i.description, summary: i.summary, topic,
      entities: i.entities, timeline: i.timeline, organizational_relevance: i.organizational_relevance, plausibility: i.plausibility,
      source_quality: i.source_quality, article_uris: i.article_uris, articles: i.articles, article_metadata: i.article_metadata,
      investigation_leads: i.investigation_leads, credibility_summary: i.credibility_summary, misinfo_flags: i.misinfo_flags,
    },
  });
}
export const unsaveIncident = (name: string, topic: string) =>
  api(`/api/news-feed/saved/incidents/${encodeURIComponent(name)}?topic=${encodeURIComponent(topic)}`, { method: 'DELETE' });

export const addIncidentNote = (name: string, topic: string, analyst: string, comment: string, savedId?: number) =>
  api(`/api/news-feed/saved/incidents/${encodeURIComponent(name)}/notes`, { method: 'POST', json: { topic, analyst, comment, saved_id: savedId } });

// ── Narratives ──────────────────────────────────────────────────────────

export const fetchSavedNarrativeNames = () =>
  api<{ narratives?: { name: string }[] }>('/api/news-feed/saved/narratives').then((r) => (r.narratives ?? []).map((n) => n.name), () => []);

export function saveNarrative(t: ArticleTheme, topic?: string) {
  return api('/api/news-feed/saved/narratives', {
    method: 'POST',
    json: {
      name: t.theme_name, description: t.theme_summary || t.description, sentiment: t.sentiment, confidence: t.confidence,
      article_count: t.article_count, source_count: t.source_count, key_entities: t.key_entities, topic,
    },
  });
}
export const unsaveNarrative = (name: string, topic?: string) =>
  api(`/api/news-feed/saved/narratives/${encodeURIComponent(name)}${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`, { method: 'DELETE' });

// ── Articles ────────────────────────────────────────────────────────────

export const setArticlePreference = (uri: string, preference: 'more' | 'less' | 'clear') =>
  api('/api/article-preference', { method: 'POST', json: { uri, preference } });

/** Opens the Auspex assistant with a question, as the old pages' "Ask Auspex" buttons do. */
export const askAuspex = (query: string, topic?: string) =>
  window.dispatchEvent(new CustomEvent('auspex:open', { detail: { query, topic } }));

/** Saves text as a file in the browser. */
export function download(name: string, text: string, type = 'text/markdown') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const cleanTitle = (t: string) => t.replace(/^\s*\*+|\*+\s*$/g, '').replace(/^#+\s*/, '').trim();

/**
 * A card title that opens the article's details on click and still works as a link to the
 * original (new tab, copy link). Styled by the card's own title-link rule.
 */
export function TitleLink({ href, onOpen, children }: { href: string; onOpen: () => void; children: React.ReactNode }) {
  return createElement('a', {
    href,
    onClick: (e: MouseEvent) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      onOpen();
    },
  }, children);
}
