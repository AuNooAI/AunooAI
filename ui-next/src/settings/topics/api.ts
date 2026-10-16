import { api } from '../../shell';

/*
 * Topic settings live in config.json. These are the routes the old Topic Editor
 * (templates/create_topic.html) used: /api/topics for the names, /api/topic/{name} for one topic,
 * POST /api/create_topic to create or replace one, DELETE /api/topic/{name} to remove it.
 */

/** The five label lists the AI analysis step picks each article's labels from */
export const LABEL_LISTS = ['future_signals', 'categories', 'sentiment', 'time_to_impact', 'driver_types'] as const;
export type LabelList = (typeof LABEL_LISTS)[number];

/** A topic as config.json holds it. Other keys (queries, flags) are kept as they are on save. */
export interface TopicConfig {
  name: string;
  description?: string;
  categories: string[];
  future_signals: string[];
  sentiment: string[];
  time_to_impact: string[];
  driver_types: string[];
  [key: string]: unknown;
}

export const listTopicNames = () => api<{ name: string }[]>('/api/topics').then((r) => r.map((t) => t.name));

export const getTopic = (name: string) => api<TopicConfig>(`/api/topic/${encodeURIComponent(name)}`);

/** Creates the topic, or replaces the one with the same name */
export const saveTopic = (topic: TopicConfig) => api('/api/create_topic', { method: 'POST', json: topic });

export const deleteTopic = (name: string, deleteArticles: boolean) =>
  api(`/api/topic/${encodeURIComponent(name)}`, { method: 'DELETE', json: deleteArticles });

/** Values used across the existing topics, most common first, as suggestions for each list */
export function suggestionsFrom(topics: TopicConfig[]): Record<LabelList, string[]> {
  const out = {} as Record<LabelList, string[]>;
  for (const key of LABEL_LISTS) {
    const counts = new Map<string, number>();
    for (const t of topics) {
      for (const v of Array.isArray(t[key]) ? t[key] : []) {
        const s = String(v).trim();
        if (s) counts.set(s, (counts.get(s) ?? 0) + 1);
      }
    }
    out[key] = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([v]) => v);
  }
  return out;
}

export const emptyLists = (t: Pick<TopicConfig, LabelList>) => LABEL_LISTS.filter((k) => !t[k]?.some((v) => String(v).trim()));
