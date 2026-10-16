import { api } from '../../../shell';
import type { EmergingTopic, HighNoveltyArticle, HistoryPoint, HorizonsResult, TopicDetail } from './types';

/* /api/emerging-topics, as the old EmergingTopicsTab.tsx called it. */

const B = '/api/emerging-topics';
const q = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.append(k, String(v));
  return p.toString();
};

export const fetchTopics = (topic?: string) =>
  api<{ topics?: EmergingTopic[] }>(`${B}/topics?${q({ days_back: 7, limit: 20, topic })}`).then((r) => r.topics ?? []);

export const fetchHighNovelty = (topic?: string) =>
  api<{ articles?: HighNoveltyArticle[] }>(`${B}/high-novelty?${q({ threshold: 70, days_back: 3, limit: 10, topic })}`).then((r) => r.articles ?? [], () => []);

export const fetchTrackedIds = () =>
  api<{ topics?: { id: number }[] }>(`${B}/tracked`).then((r) => new Set((r.topics ?? []).map((t) => t.id)), () => new Set<number>());

export const fetchHistories = (ids: number[]) =>
  api<{ histories?: Record<number, HistoryPoint[]> }>(`${B}/batch-history?topic_ids=${ids.join(',')}`).then((r) => r.histories ?? {}, () => ({}));

export const fetchDetail = (id: number) => api<TopicDetail>(`${B}/topics/${id}`);

export const fetchRetired = (topic?: string) =>
  api<{ topics?: EmergingTopic[] }>(`${B}/retired?${q({ topic, limit: 50 })}`).then((r) => r.topics ?? []);

export const deleteTopic = (id: number) => api(`${B}/topics/${id}`, { method: 'DELETE' });
export const clearTopics = (topic?: string) => api(`${B}/topics${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`, { method: 'DELETE' });
export const retireTopic = (id: number) => api(`${B}/topics/${id}/retire`, { method: 'POST', json: { reason: 'manual' } });
export const restoreTopic = (id: number) => api(`${B}/topics/${id}/restore`, { method: 'POST' });
export const setTracked = (id: number, on: boolean) => api(`${B}/topics/${id}/track`, { method: on ? 'POST' : 'DELETE' });

/** Calls the AI: a futures cone over the next 15 years */
export const runHorizons = (id: number, model: string) =>
  api<HorizonsResult>(`${B}/topics/${id}/future-horizons`, { method: 'POST', json: { model, future_horizon: 15 } });
export const saveHorizons = (id: number, result: HorizonsResult) => api(`${B}/topics/${id}/save-horizons`, { method: 'POST', json: result });
