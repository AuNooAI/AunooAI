import { useCallback, useEffect, useState } from 'react';
import { getAvailableModels, getOrganizationalProfiles, type AIModel, type OrganizationalProfile } from '@monolith/api';
import { api } from '../../shell';

export interface AnalysisConfig {
  topic: string;
  /** Days back; 0 = all time */
  timeframeDays: number;
  sourceQuality: 'all' | 'high_quality';
  /** Organisational profile id, or null for the server's default */
  profileId: number | null;
  model: string;
  /** "auto" or a fixed article count */
  articleLimit: string;
}

const KEY = 'aunoo.anticipate.config';
/** The old page's key, read once so a user's last topic and settings carry over. */
const OLD_KEY = 'trendConvergence_config';

const DEFAULTS: AnalysisConfig = { topic: '', timeframeDays: 365, sourceQuality: 'all', profileId: null, model: '', articleLimit: 'auto' };

function load(): AnalysisConfig {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) return { ...DEFAULTS, ...JSON.parse(saved) };
    const old = JSON.parse(localStorage.getItem(OLD_KEY) ?? 'null');
    if (old) {
      return {
        ...DEFAULTS,
        topic: old.topic && old.topic !== '__all__' ? old.topic : '',
        timeframeDays: Number(old.timeframe_days ?? 365),
        sourceQuality: old.source_quality === 'high_quality' ? 'high_quality' : 'all',
        profileId: old.profile_id ?? null,
        model: old.model ?? '',
        articleLimit: old.sample_size_mode === 'custom' && old.custom_limit ? String(old.custom_limit) : 'auto',
      };
    }
  } catch {
    // storage unavailable or corrupt
  }
  return DEFAULTS;
}

/** Topics, models and organisational profiles for the selectors, plus the saved analysis settings. */
export function useWorkspace() {
  const [config, setConfigState] = useState<AnalysisConfig>(load);
  const [topics, setTopics] = useState<string[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [profiles, setProfiles] = useState<OrganizationalProfile[]>([]);
  const [ready, setReady] = useState(false);

  const setConfig = useCallback((patch: Partial<AnalysisConfig>) => {
    setConfigState((c) => {
      const next = { ...c, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // per visit only
      }
      return next;
    });
  }, []);

  useEffect(() => {
    void Promise.all([
      api<{ name: string }[]>('/api/topics?include_config=false&with_articles=true&include_tracked=true').catch(() => []),
      getAvailableModels(),
      getOrganizationalProfiles().catch(() => []),
    ]).then(([t, m, p]) => {
      const names = t.map((x) => x.name).filter(Boolean);
      setTopics(names);
      setModels(m);
      setProfiles(p);
      // Fill in what's missing: first topic, first model, the default profile
      setConfigState((c) => {
        const next = { ...c };
        if (!next.topic || !names.includes(next.topic)) next.topic = names[0] ?? '';
        if (!next.model || !m.some((x) => x.id === next.model)) next.model = m[0]?.id ?? '';
        if (next.profileId == null || !p.some((x) => x.id === next.profileId)) {
          next.profileId = (p.find((x) => (x as { is_default?: boolean }).is_default) ?? p[0])?.id ?? null;
        }
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

export type Workspace = ReturnType<typeof useWorkspace>;

/** Rough context use, as the old Configure dialog showed it (utils/contextCalculation.ts). */
export function contextEstimate(config: AnalysisConfig, models: AIModel[]) {
  const limit = models.find((m) => m.id === config.model)?.context_limit || 200000;
  const articles =
    config.articleLimit === 'auto' ? Math.min(limit >= 1_000_000 ? 300 : 150, limit >= 1_000_000 ? 1000 : 400) : Number(config.articleLimit);
  const tokens = 500 + 10 + articles * 180;
  return { articles, tokens, percent: Math.round((tokens / limit) * 100), limit };
}
