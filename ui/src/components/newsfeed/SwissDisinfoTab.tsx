/**
 * Swiss Election Watch tab: container, sub-tab bar, Overview and Articles panels.
 * The other panels live in SwissDisinfoPanels.tsx.
 */

import { useEffect, useState } from 'react';
import {
  LayoutDashboard, MessageSquareWarning, Radio, Crosshair, Languages, CalendarDays, ShieldCheck,
  Sparkles, FileText, Loader2, Play, AlertCircle, X, ExternalLink, BookOpen,
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, BarChart, Bar,
} from 'recharts';
import { useSwissDisinfo, type UseSwissDisinfo } from '../../hooks/useSwissDisinfo';
import {
  NarrativesPanel, SourcesPanel, TargetsPanel, LanguagesPanel, CalendarPanel, ResponsesPanel, InsightsPanel,
  HowItWorksPanel,
  Spinner, Empty, TierBadge, LangBadge, StanceBadge, RefreshButton, STANCE_COLORS, card,
} from './SwissDisinfoPanels';

type SubTab = 'overview' | 'narratives' | 'sources' | 'targets' | 'languages' | 'calendar' | 'responses' | 'insights' | 'articles' | 'how';

const TABS: { id: SubTab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'narratives', label: 'Narratives', icon: MessageSquareWarning },
  { id: 'sources', label: 'Sources', icon: Radio },
  { id: 'targets', label: 'Targets', icon: Crosshair },
  { id: 'languages', label: 'Languages', icon: Languages },
  { id: 'calendar', label: 'Calendar', icon: CalendarDays },
  { id: 'responses', label: 'Responses', icon: ShieldCheck },
  { id: 'insights', label: 'Insights', icon: Sparkles },
  { id: 'articles', label: 'Articles', icon: FileText },
  { id: 'how', label: 'How it works', icon: BookOpen },
];

interface Props {
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

export function SwissDisinfoTab({ onArticleClick }: Props) {
  const h = useSwissDisinfo();
  const [tab, setTab] = useState<SubTab>('overview');
  const current = h.scopes.find((sc) => sc.topic === (h.topic ?? h.scopes[0]?.topic));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{current?.label ?? 'Swiss Election Watch'}</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">{current?.blurb ?? 'Disinformation and influence operations aimed at Swiss voters, Federal Elections 2027 and the votes before them.'}</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {h.scopes.length > 1 && (
            <>
              <label className="text-gray-500">Watch</label>
              <select value={h.topic ?? h.scopes[0].topic} onChange={(e) => h.setTopic(e.target.value)}
                className="border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600">
                {h.scopes.map((sc) => <option key={sc.topic} value={sc.topic}>{sc.label}</option>)}
              </select>
            </>
          )}
          <label className="text-gray-500">Window</label>
          <select value={h.daysBack} onChange={(e) => h.setDaysBack(Number(e.target.value))} className="border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600">
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>1 year</option>
          </select>
          <ProcessControl h={h} />
        </div>
      </div>

      {h.error && (
        <div className="flex items-center gap-2 p-3 rounded bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-sm">
          <AlertCircle className="w-4 h-4" /><span className="flex-1">{h.error}</span>
          <button onClick={h.clearError}><X className="w-4 h-4" /></button>
        </div>
      )}

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${active ? 'border-red-600 text-red-700 dark:text-red-300' : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}`}>
              <Icon className="w-4 h-4" />{t.label}
            </button>
          );
        })}
      </div>

      {tab === 'overview' && <OverviewPanel h={h} />}
      {tab === 'narratives' && <NarrativesPanel h={h} />}
      {tab === 'sources' && <SourcesPanel h={h} />}
      {tab === 'targets' && <TargetsPanel h={h} />}
      {tab === 'languages' && <LanguagesPanel h={h} />}
      {tab === 'calendar' && <CalendarPanel h={h} />}
      {tab === 'responses' && <ResponsesPanel h={h} />}
      {tab === 'insights' && <InsightsPanel h={h} />}
      {tab === 'articles' && <ArticlesPanel h={h} onArticleClick={onArticleClick} />}
      {tab === 'how' && <HowItWorksPanel h={h} />}
    </div>
  );
}

function ProcessControl({ h }: { h: UseSwissDisinfo }) {
  const s = h.processStatus;
  const running = !!s?.running;
  return (
    <div className="flex items-center gap-2">
      <button onClick={() => h.process(false)} disabled={running || h.unprocessed === 0}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-50"
        title="Extract narratives from approved articles that have not been analysed yet">
        {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {running ? `Analysing ${s?.processed ?? 0}/${s?.total ?? 0}` : `Analyse ${h.unprocessed ?? '…'} new`}
      </button>
    </div>
  );
}

function StatTile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: 'red' | 'blue' | 'green' | 'amber' }) {
  const tones = { red: 'text-red-600', blue: 'text-blue-600', green: 'text-green-600', amber: 'text-amber-600' };
  return (
    <div className={card}>
      <div className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${tone ? tones[tone] : 'text-gray-900 dark:text-gray-100'}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function OverviewPanel({ h }: { h: UseSwissDisinfo }) {
  const o = h.overview;
  if (h.loading.overview && !o) return <Spinner />;
  if (!o) return <Empty text="No data." />;
  const delta = o.approved - o.approved_prev;
  const quiet = o.approved < 5;
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><RefreshButton onClick={h.loadOverview} loading={h.loading.overview} /></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Narratives active, 7 days" value={o.narratives_active} sub={`${o.narratives_new} first seen this week`} tone="red" />
        <StatTile label="Articles passed the gate, 7 days" value={o.approved} sub={`${delta >= 0 ? '+' : ''}${delta} vs previous 7 days · ${o.rejected} rejected`} tone="blue" />
        <StatTile label="Share from state or alternative media" value={`${Math.round(o.vector_share * 100)}%`} sub={`of ${o.extracted} analysed articles`} tone="amber" />
        <StatTile label={o.next_vote ? 'Days to next federal vote' : 'Next vote'} value={o.next_vote ? o.next_vote.days_to : '–'} sub={o.next_vote?.label} tone="green" />
      </div>

      {quiet && (
        <div className="p-3 rounded bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-300">
          Quiet week: {o.sources_scanned} sources scanned, {o.approved + o.rejected} articles gated, {o.approved} kept. Silence here is coverage, not an outage.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className={card + ' lg:col-span-2'}>
          <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Narrative articles by day and stance</div>
          {o.stance_series.length === 0 ? <Empty text="Nothing analysed in the last 7 days. Use “Analyse new” above." /> : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={o.stance_series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
                {(['promotes', 'reports', 'debunks'] as const).map((s) => <Area key={s} type="monotone" isAnimationActive={false} dataKey={s} stackId="1" stroke={STANCE_COLORS[s]} fill={STANCE_COLORS[s]} fillOpacity={0.35} />)}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className={card}>
          <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Attribution, as reported</div>
          {o.attribution.length === 0 ? <Empty text="–" /> : o.attribution.map((a) => (
            <div key={a.actor} className="flex justify-between py-1 text-sm border-t border-gray-100 dark:border-gray-700"><span>{a.actor}</span><span className="font-medium">{a.count}</span></div>
          ))}
          <div className="text-xs text-gray-500 mt-2">What the articles say is behind it. Not a finding of this tool.</div>
        </div>
      </div>

      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Categories, articles passed in 7 days</div>
        {o.categories.length === 0 ? <Empty text="–" /> : (
          <ResponsiveContainer width="100%" height={Math.max(160, o.categories.length * 26)}>
            <BarChart data={o.categories} layout="vertical" margin={{ left: 160 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} fontSize={11} /><YAxis type="category" dataKey="category" fontSize={11} width={160} /><Tooltip /><Bar isAnimationActive={false} dataKey="count" fill="#2563eb" /></BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function ArticlesPanel({ h, onArticleClick }: { h: UseSwissDisinfo; onArticleClick?: Props['onArticleClick'] }) {
  const f = h.articleFilters;
  useEffect(() => { h.loadArticles({ page: 1 }); }, [h.loadArticles]);
  const set = (patch: Partial<typeof f>) => h.loadArticles({ ...f, ...patch, page: patch.page ?? 1 });
  const a = h.articles;
  const sel = 'border rounded px-2 py-1 text-sm dark:bg-gray-800 dark:border-gray-600';
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <select className={sel} value={f.language || ''} onChange={(e) => set({ language: e.target.value || undefined })}><option value="">All languages</option><option value="de">DE</option><option value="fr">FR</option><option value="it">IT</option><option value="en">EN</option></select>
        <select className={sel} value={f.tier || ''} onChange={(e) => set({ tier: e.target.value || undefined })}><option value="">All tiers</option>{['state_media', 'alt_media', 'mainstream', 'party', 'fact_checker', 'institution', 'research', 'unknown'].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select className={sel} value={f.attribution || ''} onChange={(e) => set({ attribution: e.target.value || undefined })}><option value="">Any attribution</option>{['russia', 'china', 'other_state', 'domestic', 'unattributed'].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <select className={sel} value={f.technique || ''} onChange={(e) => set({ technique: e.target.value || undefined })}><option value="">Any technique</option>{['deepfake', 'synthetic_text', 'bot_amplification', 'fake_account', 'forged_document', 'doctored_quote', 'decontextualised_media', 'astroturfing', 'state_media_placement'].map((t) => <option key={t} value={t}>{t}</option>)}</select>
        {a && <span className="text-sm text-gray-500">{a.total} articles</span>}
      </div>
      {h.loading.articles && !a ? <Spinner /> : !a || a.articles.length === 0 ? <Empty text="No articles match." /> : (
        <div className="space-y-2">
          {a.articles.map((art) => (
            <div key={art.uri} className={card}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <button onClick={() => onArticleClick?.({ uri: art.uri, title: art.title })} className="text-left font-medium text-gray-900 dark:text-gray-100 hover:underline">{art.title}</button>
                  <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap items-center gap-2">
                    <span>{art.news_source}</span><span>{(art.publication_date || art.submission_date || '').slice(0, 10)}</span>
                    <LangBadge lang={art.language} /><TierBadge tier={art.source_tier} />
                    {art.attribution && art.attribution !== 'unattributed' && <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700">as reported: {art.attribution}</span>}
                    {art.techniques.filter((t) => t !== 'none_reported').map((t) => <span key={t} className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">{t}</span>)}
                    {art.topic_alignment_score != null && <span>alignment {art.topic_alignment_score.toFixed(2)}</span>}
                    {art.url && <a href={art.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline"><ExternalLink className="w-3 h-3" />open</a>}
                  </div>
                </div>
              </div>
              {art.narratives && art.narratives.length > 0 && (
                <div className="mt-2 space-y-1">{art.narratives.map((n, i) => <div key={i} className="text-sm text-gray-700 dark:text-gray-300 flex items-start gap-2"><StanceBadge stance={n.stance} /><span>{n.statement}</span></div>)}</div>
              )}
              {art.targets && art.targets.length > 0 && <div className="text-xs text-gray-500 mt-1">Targets: {art.targets.map((t) => t.name).join(', ')}</div>}
              {!art.extracted_at && <div className="text-xs text-gray-400 mt-1">Not analysed yet</div>}
            </div>
          ))}
          {a.total > a.per_page && (
            <div className="flex items-center justify-center gap-3 text-sm">
              <button disabled={a.page <= 1} onClick={() => set({ page: a.page - 1 })} className="px-2 py-1 border rounded disabled:opacity-40">Previous</button>
              <span>Page {a.page} of {Math.ceil(a.total / a.per_page)}</span>
              <button disabled={a.page * a.per_page >= a.total} onClick={() => set({ page: a.page + 1 })} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SwissDisinfoTab;
