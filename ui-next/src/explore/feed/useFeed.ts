import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getArticleInsights, getIncidentConfigFromStorage, getIncidentTracking, getNarrativesConfig,
  type IncidentTrackingProgress, type IncidentTrackingResponse,
} from '@monolith/narrativeExplorerApi';
import { errorText } from '../../shell';
import { feedTopic, type ExploreConfig } from '../lib/useExploreConfig';
import {
  fetchBriefing, fetchSavedIncidents, fetchSavedNarrativeNames, fetchSnapshot, incidentDays, loadStarred, saveStarred, windowDates,
  type ArticleTheme, type SavedIncident, type SixArticlesReport,
} from './api';

/*
 * The News Feed's three AI sections.
 *  - Briefing: from this browser's cache, else the scheduled run's snapshot, else the server
 *    (which writes one with the AI when it has none for today, as the old page did on load).
 *  - Incidents and narratives: on load only the stored results are read (cache_only);
 *    the AI runs only from Refresh or a section's Generate button.
 */

const BRIEFING_CACHE = 'newsFeed_sixArticles';
const briefingKey = (c: ExploreConfig) => `${c.persona}_${feedTopic(c) || 'all'}_${c.dateRange}_${c.profileId || 'none'}`;

function cachedBriefing(key: string): { data: SixArticlesReport; cachedAt: string } | null {
  try {
    const e = JSON.parse(localStorage.getItem(BRIEFING_CACHE) ?? 'null');
    return e && e.key === key ? e : null;
  } catch {
    return null;
  }
}
function cacheBriefing(key: string, data: SixArticlesReport, cachedAt = new Date().toISOString()) {
  try {
    localStorage.setItem(BRIEFING_CACHE, JSON.stringify({ data, key, cachedAt }));
  } catch {
    // lasts for this visit
  }
}

export function useFeed(config: ExploreConfig, allTopics: string[], ready: boolean) {
  const topic = feedTopic(config);
  // Incidents and narratives cover the picked topics, or the first 25 when none are picked
  const topics = config.topics.length ? config.topics : allTopics.slice(0, 25);
  const topicsKey = topics.join('|');

  // ── Starred ──
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const toggleStar = useCallback((uri: string) => {
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });
  }, []);

  // ── Briefing ──
  const [briefing, setBriefing] = useState<SixArticlesReport | null>(null);
  const [briefingBusy, setBriefingBusy] = useState(false);
  const [briefingError, setBriefingError] = useState<string | null>(null);
  const firstLoad = useRef(true);
  const starredRef = useRef(starred);
  starredRef.current = starred;

  const loadBriefing = useCallback(async (force: boolean) => {
    const key = briefingKey(config);
    setBriefingBusy(true);
    setBriefingError(null);
    try {
      const data = await fetchBriefing(config, feedTopic(config), starredRef.current, force);
      setBriefing(data);
      cacheBriefing(key, data);
    } catch (e) {
      setBriefingError(errorText(e));
    } finally {
      setBriefingBusy(false);
    }
  }, [config]);

  const bKey = briefingKey(config);
  useEffect(() => {
    if (!ready) return;
    let stale = false;
    void (async () => {
      const cached = cachedBriefing(bKey);
      // On the first load a newer scheduled run beats this browser's copy
      if (firstLoad.current) {
        firstLoad.current = false;
        const snap = await fetchSnapshot(feedTopic(config));
        if (stale) return;
        if (snap && (!cached || new Date(snap.generated_at) > new Date(cached.cachedAt))) {
          const data: SixArticlesReport = {
            date: snap.generated_at.split('T')[0], title: 'Executive Briefing', articles: snap.briefing_articles ?? [], generated_at: snap.generated_at,
            executive_summary: '', key_themes: [], bias_distribution: {}, factuality_overview: {},
          };
          setBriefing(data);
          cacheBriefing(bKey, data, snap.generated_at);
          return;
        }
      }
      if (cached) setBriefing(cached.data);
      else void loadBriefing(false);
    })();
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, bKey]);

  // ── Incidents ──
  const [incidents, setIncidents] = useState<IncidentTrackingResponse | null>(null);
  const [incidentsBusy, setIncidentsBusy] = useState(false);
  const [progress, setProgress] = useState<IncidentTrackingProgress | null>(null);
  const [incidentsError, setIncidentsError] = useState<string | null>(null);

  const runIncidents = useCallback(async (cacheOnly: boolean) => {
    if (!topics.length) return;
    const days = incidentDays(config.dateRange);
    const { startDate, endDate } = windowDates(days);
    const prompts = getIncidentConfigFromStorage() ?? {};
    setIncidentsBusy(true);
    setIncidentsError(null);
    setProgress(null);
    try {
      const r = await getIncidentTracking({
        topics, daysLimit: days, startDate, endDate, model: config.model, cacheOnly, profileId: config.profileId ?? undefined,
        onProgress: setProgress,
        systemPrompt: prompts.system_prompt, userPrompt: prompts.user_prompt, baseOntology: prompts.base_ontology,
        analysisInstructions: prompts.analysis_instructions, qualityGuidelines: prompts.quality_guidelines,
      });
      setIncidents(r);
    } catch (e) {
      setIncidentsError(errorText(e));
    } finally {
      setIncidentsBusy(false);
      setProgress(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsKey, config.dateRange, config.model, config.profileId]);

  // ── Narratives ──
  const [themes, setThemes] = useState<(ArticleTheme & { topic: string })[]>([]);
  const [narrativesBusy, setNarrativesBusy] = useState(false);
  const [narrativesError, setNarrativesError] = useState<string | null>(null);

  const runNarratives = useCallback(async (mode: 'cache' | 'generate' | 'force') => {
    if (!topics.length) return;
    const days = incidentDays(config.dateRange);
    const { startDate, endDate } = windowDates(days);
    const prompts = getNarrativesConfig();
    setNarrativesBusy(true);
    setNarrativesError(null);
    const out: (ArticleTheme & { topic: string })[] = [];
    let failed = 0;
    for (const t of topics) {
      try {
        const r = await getArticleInsights({
          topic: t, startDate, endDate, daysLimit: days, model: config.model,
          cacheOnly: mode === 'cache', forceRegenerate: mode === 'force',
          systemPrompt: prompts?.system_prompt, userPrompt: prompts?.user_prompt,
        });
        out.push(...(Array.isArray(r) ? r : []).map((x) => ({ ...x, topic: t })));
      } catch {
        // A topic with nothing stored yet answers 404 on a cache read
        failed += 1;
      }
    }
    setThemes(out);
    if (mode !== 'cache' && failed === topics.length) setNarrativesError('No narratives could be generated for these topics.');
    setNarrativesBusy(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsKey, config.dateRange, config.model]);

  // Stored incidents and narratives for the current filters (no AI)
  useEffect(() => {
    if (!ready || !topics.length) return;
    void runIncidents(true);
    void runNarratives('cache');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, topicsKey, config.dateRange, config.profileId]);

  // ── Saved ──
  const [saved, setSaved] = useState<SavedIncident[]>([]);
  const [savedNarratives, setSavedNarratives] = useState<string[]>([]);
  const reloadSaved = useCallback(() => {
    void fetchSavedIncidents().then(setSaved);
    void fetchSavedNarrativeNames().then(setSavedNarratives);
  }, []);
  useEffect(reloadSaved, [reloadSaved]);

  return {
    topic, topics, starred, toggleStar,
    briefing, briefingBusy, briefingError, loadBriefing, setBriefing,
    incidents, setIncidents, incidentsBusy, progress, incidentsError, runIncidents,
    themes, narrativesBusy, narrativesError, runNarratives,
    saved, savedNarratives, reloadSaved,
  };
}

export type Feed = ReturnType<typeof useFeed>;
