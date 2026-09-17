/**
 * Data hook for the Swiss Election Watch tab. Loads the overview on mount and
 * each panel's data on demand, so switching sub-tabs only fetches what is shown.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  getScopes, getHowItWorks, getOverview, getNarratives, getNarrativeDetail, getSources, getCooccurrence, getTargets,
  getTechniques, getLanguages, getCalendar, getResponses, getArticles, getBrief, generateBrief,
  getProcessStatus, startProcessing, getUnprocessedCount,
  type Overview, type Narrative, type NarrativeDetail, type SourceRow, type Cooccurrence,
  type TargetRow, type TechniqueRow, type LanguagesData, type CalendarData, type ResponsesData,
  type ArticlesPage, type Brief, type ProcessStatus, type Scope, type HowItWorks,
} from '../services/swissDisinfoApi';

export interface ArticleFilters {
  language?: string;
  tier?: string;
  attribution?: string;
  technique?: string;
  page: number;
}

export function useSwissDisinfo() {
  const [daysBack, setDaysBack] = useState(30);
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [topic, setTopic] = useState<string | undefined>(undefined);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [narratives, setNarratives] = useState<Narrative[]>([]);
  const [narrativeDetail, setNarrativeDetail] = useState<NarrativeDetail | null>(null);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [cooccurrence, setCooccurrence] = useState<Cooccurrence | null>(null);
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [techniques, setTechniques] = useState<TechniqueRow[]>([]);
  const [languages, setLanguages] = useState<LanguagesData | null>(null);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [responses, setResponses] = useState<ResponsesData | null>(null);
  const [articles, setArticles] = useState<ArticlesPage | null>(null);
  const [articleFilters, setArticleFilters] = useState<ArticleFilters>({ page: 1 });
  const [brief, setBrief] = useState<Brief | null>(null);
  const [processStatus, setProcessStatus] = useState<ProcessStatus | null>(null);
  const [unprocessed, setUnprocessed] = useState<number | null>(null);
  const [howItWorks, setHowItWorks] = useState<HowItWorks | null>(null);
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, set: (v: T) => void) => {
    setLoading((l) => ({ ...l, [key]: true }));
    try {
      set(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading((l) => ({ ...l, [key]: false }));
    }
  }, []);

  const loadOverview = useCallback(() => run('overview', () => getOverview(7, topic), setOverview), [run, topic]);
  const loadNarratives = useCallback((language?: string, stance?: string) =>
    run('narratives', () => getNarratives(daysBack, language, stance, topic), setNarratives), [run, daysBack, topic]);
  const loadNarrativeDetail = useCallback((id: number) =>
    run('narrativeDetail', () => getNarrativeDetail(id, topic), setNarrativeDetail), [run, topic]);
  const loadSources = useCallback(() => {
    run('sources', () => getSources(daysBack, topic), setSources);
    run('cooccurrence', () => getCooccurrence(daysBack, topic), setCooccurrence);
  }, [run, daysBack, topic]);
  const loadTargets = useCallback(() => {
    run('targets', () => getTargets(daysBack, topic), setTargets);
    run('techniques', () => getTechniques(daysBack, topic), setTechniques);
  }, [run, daysBack, topic]);
  const loadLanguages = useCallback(() => run('languages', () => getLanguages(daysBack, topic), setLanguages), [run, daysBack, topic]);
  const loadCalendar = useCallback(() => run('calendar', () => getCalendar(Math.max(daysBack, 60), topic), setCalendar), [run, daysBack, topic]);
  const loadResponses = useCallback(() => run('responses', () => getResponses(Math.max(daysBack, 90), topic), setResponses), [run, daysBack, topic]);
  const loadArticles = useCallback((f: ArticleFilters) => {
    setArticleFilters(f);
    return run('articles', () => getArticles({ days_back: daysBack, ...f, per_page: 25, topic }), setArticles);
  }, [run, daysBack, topic]);
  const loadBrief = useCallback(() => run('brief', () => getBrief(topic), setBrief), [run, topic]);
  const loadHowItWorks = useCallback(() => run('how', () => getHowItWorks(topic), setHowItWorks), [run, topic]);
  const makeBrief = useCallback((days: number) => run('brief', () => generateBrief(days, topic), setBrief), [run, topic]);
  const loadProcessStatus = useCallback(() => run('process', () => getProcessStatus(), setProcessStatus), [run]);
  const loadUnprocessed = useCallback(() => run('unprocessed', async () => (await getUnprocessedCount(topic)).count, setUnprocessed), [run, topic]);
  const process = useCallback(async (all = false) => {
    await run('process', () => startProcessing(all, 100, topic), setProcessStatus);
    // poll until done, then refresh what the user is looking at
    const tick = async () => {
      const s = await getProcessStatus();
      setProcessStatus(s);
      if (s.running) setTimeout(tick, 3000);
      else { loadOverview(); loadUnprocessed(); }
    };
    setTimeout(tick, 2000);
  }, [run, loadOverview, loadUnprocessed, topic]);

  useEffect(() => { getScopes().then((r) => setScopes(r.scopes)).catch(() => setScopes([])); }, []);
  useEffect(() => { loadOverview(); loadUnprocessed(); loadProcessStatus(); }, [loadOverview, loadUnprocessed, loadProcessStatus]);

  return {
    daysBack, setDaysBack, scopes, topic, setTopic,
    overview, narratives, narrativeDetail, setNarrativeDetail, sources, cooccurrence, targets, techniques,
    languages, calendar, responses, articles, articleFilters, brief, processStatus, unprocessed, howItWorks,
    loading, error, clearError: () => setError(null),
    loadOverview, loadNarratives, loadNarrativeDetail, loadSources, loadTargets, loadLanguages,
    loadCalendar, loadResponses, loadArticles, loadBrief, makeBrief, process, loadUnprocessed, loadHowItWorks,
  };
}

export type UseSwissDisinfo = ReturnType<typeof useSwissDisinfo>;
