import { useCallback, useEffect, useRef, useState } from 'react';
import * as g from '@monolith/gatherApi';
import type { ActiveJobsStatus, AvailableModel, AvailableProvider, KeywordMonitorSettings, MonitorStatus, RSSMonitorStatus } from '@monolith/gatherApi';
import { buildGroups, toCollectSettings, toFeed, type Feed, type KeywordGroup } from './model';

const JOBS_POLL_MS = 3000;
/** After Update Now / Run Check, the old page refreshed once after this delay. */
const CHECK_REFRESH_MS = 2000;

export interface GatherData {
  loading: boolean;
  error: string | null;
  groups: KeywordGroup[];
  topics: string[];
  settings: KeywordMonitorSettings | null;
  status: MonitorStatus | null;
  providers: AvailableProvider[];
  models: AvailableModel[];
}

/** Keyword groups, global settings and collection status (the Keyword Groups tab and the header). */
export function useGather() {
  const [data, setData] = useState<GatherData>({
    loading: true, error: null, groups: [], topics: [], settings: null, status: null, providers: [], models: [],
  });
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    try {
      const [summaries, keywords, stats, settings, status, providers, topics, models] = await Promise.all([
        g.getGroupSummaries(),
        g.getKeywords(),
        g.getRelevanceStats().catch(() => []),
        g.getSettings(),
        g.getMonitorStatus().catch(() => null),
        g.getAvailableProviders().catch(() => []),
        g.getTopics().catch(() => []),
        g.getAvailableModels().catch(() => []),
      ]);
      setData({
        loading: false, error: null, groups: buildGroups(summaries, keywords, stats), topics, settings, status, providers, models,
      });
    } catch (e) {
      setData((d) => ({ ...d, loading: false, error: e instanceof Error ? e.message : String(e) }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Runs a change, then reloads; returns false (and keeps the error) if it failed. */
  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      try {
        await fn();
        await load();
        return true;
      } catch (e) {
        setData((d) => ({ ...d, error: e instanceof Error ? e.message : String(e) }));
        return false;
      }
    },
    [load],
  );

  const checkNow = useCallback(
    async (groupId?: string) => {
      setChecking(true);
      try {
        const r = await g.triggerKeywordCheck(groupId ? Number(groupId) : undefined);
        window.setTimeout(() => void load(), CHECK_REFRESH_MS);
        return r;
      } finally {
        setChecking(false);
      }
    },
    [load],
  );

  return {
    ...data,
    checking,
    reload: load,
    clearError: () => setData((d) => ({ ...d, error: null })),
    globalSettings: data.settings ? toCollectSettings(data.settings) : null,
    checkNow,
    setEnabled: (enabled: boolean) => run(() => g.toggleScheduledCollection(enabled)),
    saveSettings: (s: KeywordMonitorSettings) => run(() => g.updateSettings(s)),
    createGroup: (name: string, topic: string) => run(() => g.createKeywordGroup(name, topic)),
    deleteGroup: (id: string) => run(() => g.deleteKeywordGroup(Number(id))),
    addKeyword: (groupId: string, text: string) => run(() => g.addKeyword(Number(groupId), text)),
    editKeyword: (keywordId: string, text: string) => run(() => g.updateKeyword(Number(keywordId), text)),
    removeKeyword: (keywordId: string) => run(() => g.deleteKeyword(Number(keywordId))),
    deleteUnscored: (groupId: string) => run(() => g.deleteUnscoredArticles(Number(groupId))),
  };
}

export type Gather = ReturnType<typeof useGather>;

/** RSS feeds and the RSS monitor's status (the RSS Feeds tab). Loads when first shown. */
export function useFeeds(enabled: boolean) {
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [monitor, setMonitor] = useState<RSSMonitorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const load = useCallback(async () => {
    try {
      const [list, status] = await Promise.all([g.getRSSFeeds(), g.getRSSMonitorStatus().catch(() => null)]);
      setFeeds(list.map(toFeed));
      setMonitor(status);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled && !started.current) {
      started.current = true;
      void load();
    }
  }, [enabled, load]);

  return { feeds, monitor, loading, error, clearError: () => setError(null), reload: load };
}

/** Background jobs (auto-collect, bulk processing), polled every 3 s like the old status badge. */
export function useActiveJobs() {
  const [jobs, setJobs] = useState<ActiveJobsStatus | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      g.getActiveJobsStatus().then(
        (j) => alive && setJobs(j),
        () => undefined,
      );
    void tick();
    const t = window.setInterval(tick, JOBS_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);
  return jobs;
}

/** "Auto-collecting: 40%" — the old ProcessingStatusBadge text, or null when nothing runs. */
export function jobsLabel(j: ActiveJobsStatus | null) {
  if (!j || !j.total_active || !j.active_jobs?.length) return null;
  const job = j.active_jobs[0];
  const name = job.job_type === 'keyword_monitor_auto_ingest' ? 'Auto-collecting' : job.job_type === 'bulk_processing' ? 'Processing' : 'Running';
  const detail = job.progress ? `${Math.round(job.progress)}%` : job.article_count ? `${job.article_count} articles` : '';
  return `${name}${detail ? `: ${detail}` : ''}${j.total_active > 1 ? ` (${j.total_active})` : ''}`;
}
