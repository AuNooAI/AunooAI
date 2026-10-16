import { useCallback, useEffect, useState } from 'react';
import { getAvailableModels, getOrganizationalProfiles, type AIModel, type OrganizationalProfile } from '@monolith/api';
import { api } from '../../shell';

export type DateRange = '24h' | '72h' | '7d' | '30d' | '3m' | '1y' | 'all';
export type Persona = 'CEO' | 'CMO' | 'CTO' | 'CISO';

/** The filters every Explore tab shares. */
export interface ExploreConfig {
  /** Topics picked in the filter bar. Incidents and narratives cover all of them; the article list and briefing follow one (see feedTopic). */
  topics: string[];
  dateRange: DateRange;
  model: string;
  /** Organisational profile; null = "General analysis" */
  profileId: number | null;
  persona: Persona;
  /** Articles in the executive briefing */
  articleCount: number;
}

const KEY = 'aunoo.explore.config';
/** The old page's keys, read once so a user's topic and settings carry over */
const OLD_FEED_KEY = 'newsFeed_config';
const OLD_NARRATIVE_KEY = 'narrativeExplorer_config';

// The old page's default model (useNewsFeed.ts): the tenants' default_llm_model
const DEFAULTS: ExploreConfig = { topics: [], dateRange: '7d', model: 'bedrock-kimi-k2-5', profileId: null, persona: 'CEO', articleCount: 6 };
const LEGACY_AUTO_PICK_MODELS = new Set(['gpt-4o', 'gpt-4o-mini']);

// The date range is never restored: every load starts at Last 7 days. A saved
// "Last 30 days" lived on for weeks and showed old articles at the top, which
// read as a date bug (wileytest, 2026-10-16). Topics, model, persona and profile carry over.
function load(): ExploreConfig {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) return { ...DEFAULTS, ...JSON.parse(saved), dateRange: DEFAULTS.dateRange };
    const feed = JSON.parse(localStorage.getItem(OLD_FEED_KEY) ?? 'null');
    const narr = JSON.parse(localStorage.getItem(OLD_NARRATIVE_KEY) ?? 'null');
    if (feed || narr) {
      const topics: string[] = Array.isArray(narr?.selectedTopics) ? narr.selectedTopics : feed?.topic ? [feed.topic] : [];
      const model = feed?.model && !LEGACY_AUTO_PICK_MODELS.has(feed.model) ? feed.model : DEFAULTS.model;
      return {
        ...DEFAULTS,
        topics,
        model,
        profileId: feed?.profileId ?? null,
        persona: feed?.persona ?? DEFAULTS.persona,
        articleCount: feed?.articleCount ?? DEFAULTS.articleCount,
      };
    }
  } catch {
    // storage unavailable or corrupt
  }
  return DEFAULTS;
}

/** The one topic the article list and briefing follow: set only when exactly one topic is picked. */
export const feedTopic = (c: ExploreConfig) => (c.topics.length === 1 ? c.topics[0] : undefined);

/** Topics, models and organisational profiles for the filter bar, plus the saved filters. */
export function useExploreConfig() {
  const [config, setConfigState] = useState<ExploreConfig>(load);
  const [topics, setTopics] = useState<string[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [profiles, setProfiles] = useState<OrganizationalProfile[]>([]);
  const [ready, setReady] = useState(false);

  const setConfig = useCallback((patch: Partial<ExploreConfig>) => {
    setConfigState((c) => {
      const next = { ...c, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // lasts for this visit
      }
      return next;
    });
  }, []);

  useEffect(() => {
    void Promise.all([
      api<{ name: string }[]>('/api/topics').catch(() => []),
      getAvailableModels().catch(() => [] as AIModel[]),
      getOrganizationalProfiles().catch(() => [] as OrganizationalProfile[]),
    ]).then(([t, m, p]) => {
      const names = (Array.isArray(t) ? t : []).map((x) => x.name).filter(Boolean);
      setTopics(names);
      setModels(m);
      setProfiles(p);
      setConfigState((c) => {
        const next = { ...c, topics: c.topics.filter((x) => names.includes(x)) };
        // As on the old page: the default profile when none is picked yet
        if (next.profileId == null) next.profileId = p.find((x) => (x as { is_default?: boolean }).is_default)?.id ?? null;
        return next;
      });
      setReady(true);
    });
  }, []);

  const reloadProfiles = useCallback(async () => {
    const p = await getOrganizationalProfiles().catch(() => [] as OrganizationalProfile[]);
    setProfiles(p);
    return p;
  }, []);

  return { config, setConfig, topics, models, profiles, reloadProfiles, ready };
}

export type ExploreWorkspace = ReturnType<typeof useExploreConfig>;
