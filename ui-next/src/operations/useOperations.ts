import { useCallback, useEffect, useState } from 'react';
import { api } from '../shell';

/** Health, totals and metrics refresh this often, as on the old page. */
const POLL_MS = 30000;

export interface Stats {
  total_articles: number;
  articles_today: number;
  keyword_groups: number;
  topics: number;
}

/** GET /health/detailed (app/routes/health_routes.py). Only the fields the page shows. */
export interface Health {
  /** healthy · degraded */
  status: string;
  warnings?: string[];
  /** Each field is the whole uptime in that unit (seconds: 11.9, minutes: 0.2…), not a breakdown. */
  uptime: { seconds: number };
  cpu: { process_percent: number; system_percent: number; core_count: number; load_average?: number[] };
  memory:
    | { process: { rss_mb: number; percent: number; num_threads: number }; system: { used_gb: number; total_gb: number; percent: number } }
    | { error: string };
  disk: { root: { used_gb: number; total_gb: number; free_gb: number; percent: number } | null } | { error: string };
  api_health?: {
    status: string;
    apis: Record<'collector' | 'ai_provider' | 'firecrawl', string>;
    configured_count: number;
    total_checked: number;
  };
  autopolling?: {
    status: string;
    is_enabled?: boolean;
    requests_today?: number;
    daily_request_limit?: number;
    last_poll_time?: string | null;
    last_error?: string | null;
  };
  database?: { status: string; article_count?: number; size_mb?: number; locked?: boolean; error?: string };
}

export interface Headline {
  id: string;
  title: string;
  href: string;
  source?: string;
  published?: Date;
}

interface FeedArticle {
  uri?: string;
  url?: string;
  title?: string;
  news_source?: string;
  source?: string;
  publication_date?: string;
}

/** Totals and system health, polled every 30 s. */
export function useOperations() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState(() => Date.now());

  const load = useCallback(async () => {
    const [s, h] = await Promise.allSettled([api<Stats>('/api/dashboard/stats'), api<Health>('/health/detailed')]);
    if (s.status === 'fulfilled') setStats(s.value);
    if (h.status === 'fulfilled') {
      setHealth(h.value);
      setLoadedAt(Date.now());
    }
    const failed = [s, h].find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
    setError(failed ? (failed.reason instanceof Error ? failed.reason.message : String(failed.reason)) : null);
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(t);
  }, [load]);

  return { stats, health, error, loadedAt };
}

/** Latest headlines for the ticker (GET /api/news-feed/articles), re-read on `refreshKey` changes. */
export function useHeadlines(count: number, range: string, refreshKey: number) {
  const [items, setItems] = useState<Headline[] | null>(null);
  useEffect(() => {
    let alive = true;
    // The endpoint loads max_articles rows (default 1,000) whatever per_page says, so cap that too (its minimum is 10)
    api<{ articles?: { items?: FeedArticle[] } | FeedArticle[] }>(
      `/api/news-feed/articles?per_page=${count}&max_articles=${Math.max(10, count)}&date_range=${encodeURIComponent(range)}`,
    ).then(
      (r) => {
        if (!alive) return;
        const list = Array.isArray(r.articles) ? r.articles : (r.articles?.items ?? []);
        setItems(
          list.slice(0, count).flatMap((a, i) => {
            const href = a.uri || a.url;
            if (!href || !a.title) return [];
            return [{ id: `${i}-${href}`, title: a.title, href, source: a.news_source || a.source, published: a.publication_date ? new Date(a.publication_date) : undefined }];
          }),
        );
      },
      () => alive && setItems([]),
    );
    return () => {
      alive = false;
    };
  }, [count, range, refreshKey]);
  return items;
}
