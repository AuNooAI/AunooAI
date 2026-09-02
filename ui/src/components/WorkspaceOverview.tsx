/**
 * WorkspaceOverview — the Explore "Overview" tab.
 *
 * Explains what this workspace is set up to do: the organization profile, the
 * questions it exists to answer, each topic with WHY it is collected and its
 * classification taxonomy, the brands being watched, and where reports live.
 * Everything is read from existing APIs; sections hide when empty, so the tab
 * works on any tenant with a default organizational profile.
 *
 * Convention: lines in the default profile's custom_context that start with
 * "Q:" render as "Questions we're answering".
 */
import { useEffect, useState } from 'react';
import { Building2, HelpCircle, Layers, Target, Loader2, FileText, ChevronDown } from 'lucide-react';

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
  description: string;
  categories: string[];
  languages: string[];
  countries: string[];
  providers: string[];
  active: boolean;
  collected: number;
  enriched: number;
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

const LANG_NAMES: Record<string, string> = {
  en: 'English', ja: 'Japanese', de: 'German', fr: 'French', es: 'Spanish', it: 'Italian',
};

function TopicCard({ topic }: { topic: OverviewTopic }) {
  const [showTaxonomy, setShowTaxonomy] = useState(false);
  const langs = topic.languages.map(l => LANG_NAMES[l] || l).join(', ');
  return (
    <div className={`rounded border border-gray-100 dark:border-gray-700 px-4 py-3 ${topic.active ? '' : 'opacity-60'}`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{topic.name}</span>
        <span className="text-xs text-gray-400 shrink-0">
          {topic.enriched} analysed / {topic.collected} collected
        </span>
      </div>
      {topic.description && (
        <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{topic.description}</p>
      )}
      <div className="flex flex-wrap gap-1.5 mt-2 text-xs">
        {langs && (
          <span className="px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">{langs}</span>
        )}
        {topic.providers.length > 0 && (
          <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
            {topic.providers.join(' · ')}
          </span>
        )}
        {!topic.active && (
          <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">collection paused</span>
        )}
      </div>
      {topic.categories.length > 0 && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setShowTaxonomy(v => !v)}
            className="inline-flex items-center gap-1 text-xs font-medium text-pink-600 dark:text-pink-400 hover:underline"
          >
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showTaxonomy ? 'rotate-180' : ''}`} />
            Taxonomy — {topic.categories.length} categories
          </button>
          {showTaxonomy && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {topic.categories.map(c => (
                <span key={c} className="text-xs px-2 py-0.5 rounded bg-gray-50 dark:bg-gray-700/60 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300">
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
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
        get('/api/news-feed/workspace/topics-overview'),
        get('/api/brand-watcher/brands'),
        get('/api/signal-reports?limit=10'),
      ]);
      if (cancelled) return;

      const profiles: OverviewProfile[] = profilesRes?.profiles || [];
      setProfile(profiles.find(p => p.is_default) || profiles[0] || null);
      setTopics(topicsRes?.topics || []);
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

  const questionTopics = topics.filter(t => !t.name.startsWith('Brand Monitoring'));
  const brandTopics = topics.filter(t => t.name.startsWith('Brand Monitoring'));

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

      {questionTopics.length > 0 && (
        <div className={card}>
          <div className={heading}>
            <Layers className="w-4 h-4 text-pink-500" />
            What we collect, and why
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Each topic below is a continuously collected stream. Every article that passes the
            relevance gate is classified into the topic's taxonomy (expand it under each topic),
            plus sentiment, future signal, time to impact and driver type — that shared structure
            is what makes topics comparable side by side.
          </p>
          <div className="space-y-2">
            {questionTopics.map(t => <TopicCard key={t.name} topic={t} />)}
          </div>
        </div>
      )}

      {brands.length > 0 && (
        <div className={card}>
          <div className={heading}>
            <Target className="w-4 h-4 text-pink-500" />
            Brands being watched
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Each brand has its own monitoring stream (news, and social where configured), classified
            into a brand taxonomy — product, financial, leadership, sentiment, legal, ESG and more —
            feeding Brand Watcher's perception, risk and alerting views.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
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
          {brandTopics.length > 0 && (
            <div className="space-y-2">
              {brandTopics.map(t => <TopicCard key={t.name} topic={t} />)}
            </div>
          )}
        </div>
      )}

      <div className={card}>
        <div className={heading}>
          <FileText className="w-4 h-4 text-pink-500" />
          Where reports live
        </div>
        <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1.5">
          <li><span className="font-medium">Consensus Analysis, Future Horizons, Strategic Recommendations, Market Signals, Impact Timeline</span> — on the Anticipate page: pick a topic and open the tab; the last saved analysis loads automatically.</li>
          <li><span className="font-medium">Observer agent reports</span> — Explore → Observer Agents, with each agent's alerts and saved reports.</li>
          <li><span className="font-medium">Topic Reports</span> (long-form, per period) — Anticipate → Topic Reports. If the tab isn't visible, enable it via the tab-settings gear at the top right of Anticipate.</li>
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
