/**
 * WorkspaceOverview — the Explore "Overview" tab.
 *
 * Summarises what this workspace is set up to do: the organization profile,
 * the questions it exists to answer, the topics being collected, and the
 * brands being watched. Everything is read from existing APIs, so the tab
 * works on any tenant with a default organizational profile; sections with
 * no data hide themselves.
 *
 * Convention: lines in the default profile's custom_context that start with
 * "Q:" render as "Questions we're answering".
 */
import { useEffect, useState } from 'react';
import { Building2, HelpCircle, Layers, Target, Loader2, FileText } from 'lucide-react';

interface OverviewProfile {
  name: string;
  description: string | null;
  industry: string | null;
  region: string | null;
  key_concerns: string[];
  strategic_priorities: string[];
  stakeholder_focus: string[];
  competitive_landscape: string[];
  custom_context: string | null;
  is_default: boolean;
}

interface OverviewTopic {
  name: string;
  display_name?: string;
  article_count?: number;
}

interface OverviewReport {
  id: number;
  report_name?: string;
  instruction_name?: string;
  topic?: string | null;
  created_at?: string;
}

interface OverviewBrand {
  id: number;
  display_name: string;
  enabled: boolean;
  is_primary?: boolean;
  color?: string | null;
  brand_keywords?: string[];
}

export function WorkspaceOverview() {
  const [profile, setProfile] = useState<OverviewProfile | null>(null);
  const [topics, setTopics] = useState<OverviewTopic[]>([]);
  const [brands, setBrands] = useState<OverviewBrand[]>([]);
  const [reports, setReports] = useState<OverviewReport[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const get = async (url: string) => {
        try {
          const r = await fetch(url, { credentials: 'include' });
          return r.ok ? await r.json() : null;
        } catch {
          return null;
        }
      };
      const [profilesRes, topicsRes, brandsRes, reportsRes] = await Promise.all([
        get('/api/organizational-profiles'),
        get('/api/topics'),
        get('/api/brand-watcher/brands'),
        get('/api/signal-reports?limit=10'),
      ]);
      if (cancelled) return;

      const profiles: OverviewProfile[] = profilesRes?.profiles || [];
      setProfile(profiles.find(p => p.is_default) || profiles[0] || null);

      const topicList: OverviewTopic[] = Array.isArray(topicsRes) ? topicsRes : topicsRes?.topics || [];
      setTopics(topicList);

      const brandList: OverviewBrand[] = Array.isArray(brandsRes) ? brandsRes : brandsRes?.brands || [];
      setBrands(brandList.filter(b => b.enabled));
      setReports(reportsRes?.reports || []);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
      </div>
    );
  }

  const questions = (profile?.custom_context || '')
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.toUpperCase().startsWith('Q:'))
    .map(l => l.slice(2).trim());

  const card = 'bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-5';
  const heading = 'flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3';

  return (
    <div className="space-y-4">
      {profile && (
        <div className={card}>
          <div className={heading}>
            <Building2 className="w-4 h-4 text-pink-500" />
            {profile.name}
            {(profile.industry || profile.region) && (
              <span className="font-normal text-xs text-gray-500 dark:text-gray-400">
                {[profile.industry, profile.region].filter(Boolean).join(' · ')}
              </span>
            )}
          </div>
          {profile.description && (
            <p className="text-sm text-gray-700 dark:text-gray-300">{profile.description}</p>
          )}
          {profile.strategic_priorities?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {profile.strategic_priorities.map(p => (
                <span key={p} className="text-xs px-2 py-1 rounded-full bg-pink-50 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300">
                  {p}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {questions.length > 0 && (
        <div className={card}>
          <div className={heading}>
            <HelpCircle className="w-4 h-4 text-pink-500" />
            Questions we're answering
          </div>
          <ol className="list-decimal list-inside space-y-2">
            {questions.map(q => (
              <li key={q} className="text-sm text-gray-700 dark:text-gray-300">{q}</li>
            ))}
          </ol>
        </div>
      )}

      {topics.length > 0 && (
        <div className={card}>
          <div className={heading}>
            <Layers className="w-4 h-4 text-pink-500" />
            Topics being collected
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {topics.map(t => (
              <div key={t.name} className="flex items-center justify-between px-3 py-2 rounded border border-gray-100 dark:border-gray-700">
                <span className="text-sm text-gray-700 dark:text-gray-300 truncate" title={t.name}>
                  {t.display_name || t.name}
                </span>
                {typeof t.article_count === 'number' && (
                  <span className="text-xs text-gray-400 ml-2 shrink-0">{t.article_count}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {brands.length > 0 && (
        <div className={card}>
          <div className={heading}>
            <Target className="w-4 h-4 text-pink-500" />
            Brands being watched
          </div>
          <div className="flex flex-wrap gap-2">
            {[...brands].sort((a, b) => Number(b.is_primary || false) - Number(a.is_primary || false)).map(b => (
              <span
                key={b.id}
                className="inline-flex items-center gap-2 text-sm px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300"
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: b.color || '#ec4899' }}
                />
                {b.display_name}
                {b.is_primary && (
                  <span className="text-[10px] uppercase tracking-wide text-pink-600 dark:text-pink-400">primary</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className={card}>
        <div className={heading}>
          <FileText className="w-4 h-4 text-pink-500" />
          Where reports live
        </div>
        <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1.5">
          <li><span className="font-medium">Consensus, Horizons, Signals, Timeline</span> — Anticipate: pick a topic and open the tab; the last saved analysis loads automatically.</li>
          <li><span className="font-medium">Observer agent reports</span> — Explore → Observer Agents, with each agent's alerts and saved reports.</li>
          <li><span className="font-medium">Topic reports (long-form)</span> — Anticipate → Reports, generated per period from a configured topic deck.</li>
        </ul>
        {reports.length > 0 && (
          <div className="mt-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">Latest observer reports</p>
            <ul className="space-y-1">
              {reports.slice(0, 5).map(r => (
                <li key={r.id} className="text-sm text-gray-700 dark:text-gray-300 flex items-center justify-between gap-2">
                  <span className="truncate">{r.report_name || r.instruction_name || `Report ${r.id}`}</span>
                  {r.created_at && (
                    <span className="text-xs text-gray-400 shrink-0">{String(r.created_at).slice(0, 10)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
