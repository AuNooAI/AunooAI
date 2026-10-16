import { useCallback, useEffect, useRef, useState } from 'react';
import { generateTrendConvergence, getPreviousAnalysis, loadCachedTrendConvergence } from '@monolith/api';
import { api, errorText } from '../../shell';
import { ARTICLES_SEGMENT, referencesOf, type Payload, type Reference } from './model';
import type { AnalysisConfig } from './useWorkspace';

export type AnalysisStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'generating';

export function params(config: AnalysisConfig, tab: string) {
  const custom = config.articleLimit !== 'auto';
  return {
    topic: config.topic,
    model: config.model,
    timeframe_days: config.timeframeDays,
    source_quality: config.sourceQuality,
    sample_size_mode: custom ? 'custom' : 'auto',
    custom_limit: custom ? Number(config.articleLimit) : undefined,
    consistency_mode: 'balanced',
    profile_id: config.profileId ?? undefined,
    tab,
  };
}

/** What a tab shows for these settings: the cached run, else the latest stored run, else null. */
export async function fetchTabData(config: AnalysisConfig, backendTab: string): Promise<Payload | null> {
  const cached = await loadCachedTrendConvergence(params(config, backendTab)).catch(() => null);
  return ((cached ?? (await getPreviousAnalysis(config.topic, backendTab).catch(() => null))) as Payload | null) || null;
}

/**
 * One analysis tab's data. Loads the cached run for these settings, else the latest stored run
 * for the topic (GET …/previous), else shows the empty state; Generate runs a new analysis.
 * `saved`: a saved analysis's data for this tab (null when it has none) shows instead; undefined = live.
 */
export function useAnalysis(backendTab: string | undefined, config: AnalysisConfig, ready: boolean, saved?: Payload | null) {
  const [status, setStatus] = useState<AnalysisStatus>('idle');
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [refs, setRefs] = useState<Reference[]>([]);
  const seq = useRef(0);

  const show = useCallback((d: Payload | null) => {
    setData(d);
    setStatus(d ? 'ready' : 'empty');
  }, []);

  const load = useCallback(async () => {
    if (!backendTab || !config.topic || !config.model) return;
    const n = ++seq.current;
    setError(null);
    if (saved !== undefined) {
      show(saved);
      return;
    }
    setStatus('loading');
    const d = await fetchTabData(config, backendTab);
    if (n === seq.current) show(d);
    // Only the settings that pick a cached run matter here; generating uses the rest
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendTab, config.topic, config.model, config.timeframeDays, config.sourceQuality, config.articleLimit, config.profileId, saved, show]);

  useEffect(() => {
    if (!ready || !backendTab) {
      setStatus(backendTab ? 'loading' : 'idle');
      return;
    }
    void load();
  }, [ready, backendTab, load]);

  // Citations: the numbered sources behind "[n]" (consensus carries them in article_list)
  useEffect(() => {
    setRefs([]);
    if (!data || !backendTab) return;
    if (Array.isArray(data.article_list)) {
      setRefs(referencesOf(data.article_list));
      return;
    }
    if (!data.analysis_id) return;
    let alive = true;
    api<{ articles: Payload[] }>(
      `/api/trend-convergence/${ARTICLES_SEGMENT[backendTab]}/${encodeURIComponent(data.analysis_id)}/articles?topic=${encodeURIComponent(config.topic)}`,
    ).then(
      (r) => alive && setRefs(referencesOf(r.articles)),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [data?.analysis_id, backendTab, config.topic]);

  const generate = useCallback(
    async (force = false) => {
      if (!backendTab || !config.topic) return;
      const n = ++seq.current;
      setStatus('generating');
      setStartedAt(Date.now());
      setError(null);
      try {
        const d = await generateTrendConvergence({ ...params(config, backendTab), enable_caching: !force, cache_duration_hours: 24 });
        if (n === seq.current) show(d as Payload);
      } catch (e) {
        if (n !== seq.current) return;
        setError(errorText(e));
        setStatus('error');
      }
    },
    [backendTab, config, show],
  );

  return { status, data, error, startedAt, refs, reload: load, generate, setLoaded: show };
}

export type Analysis = ReturnType<typeof useAnalysis>;
