import { DEFAULT_TRACKER_TOPIC, type PolicyArticlesResponse } from '@monolith/policyTrackerApi';

/*
 * The calls the shared ui/src/services/policyTrackerApi.ts gets wrong, plus small helpers. Everything
 * else is imported from it directly.
 */

export const TRACKER_TOPIC = DEFAULT_TRACKER_TOPIC;

export type SortBy = 'date' | 'relevance' | 'category_count';

/**
 * The article list. The shared client leaves days_back out when it is 0, so the server falls back to
 * its default of 365 and "All time" quietly showed only the last year. This one always sends it.
 */
export async function fetchPolicyArticles(p: { topic: string; categories: string[]; daysBack: number; sortBy: SortBy; page: number; perPage: number }): Promise<PolicyArticlesResponse> {
  const q = new URLSearchParams({ topic: p.topic, days_back: String(p.daysBack), sort_by: p.sortBy, page: String(p.page), per_page: String(p.perPage) });
  if (p.categories.length) q.set('categories', p.categories.join(','));
  const r = await fetch(`/api/policy-tracker/articles?${q}`, { credentials: 'include' });
  if (!r.ok) throw new Error(`The articles didn’t load (${r.status})`);
  return r.json();
}

/** The AI report and category routes accept 7 to 730 days; "All time" (0) is sent as the widest they allow */
export const aiDays = (daysBack: number) => (daysBack === 0 ? 730 : Math.max(7, Math.min(daysBack, 730)));

export const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
  { value: '0', label: 'All time' },
];

export const periodText = (days: number) => (days === 0 ? 'all time' : days === 365 ? 'the last year' : days === 180 ? 'the last 6 months' : `the last ${days} days`);

export const fmtDate = (s: string | null | undefined) => {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

/** Ticks for a line chart's y axis: 0 to a round ceiling in four steps */
export function niceTicks(max: number): { domain: [number, number]; ticks: number[] } {
  if (max <= 0) return { domain: [0, 4], ticks: [0, 1, 2, 3, 4] };
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const top = step * 4;
  return { domain: [0, top], ticks: [0, step, step * 2, step * 3, top] };
}

