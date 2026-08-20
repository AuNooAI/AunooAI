/**
 * Market Monitor Tab
 *
 * A market is a tracked vendor portfolio built on Brand Watcher brands. Four
 * views: the registry, the collection setup, the review queue, and source
 * health. Everything reads app/routes/market_monitor_routes.py.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Globe, LineChart,
  Linkedin, Loader2, Play, RefreshCw, Search, Settings, ToggleLeft, ToggleRight,
  X,
} from 'lucide-react';
import { MarketVendorPage } from './MarketVendorPage';
import {
  BarChart, Bar, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  datasetCsvUrl, discoverCandidates, feedUrl, generateMarketTimeline, getBrief,
  getCollectionPlan, getFacets, getMarketTimeline, getMarkets, getReviewTasks,
  getRuns, getSourceHealth, getSources, getVendors, saveSources,
  setCollectionTerms, setVendorCollection, setupCollection, updateReviewTask,
  type CollectionPlan, type CollectionRun, type DiscoveryResult, type Facets,
  type Market, type MarketBrief, type ReviewTask, type SourceHealth,
  type SourceSetting, type TimelineEvent, type Vendor, type VendorFilter,
} from '../../services/marketMonitorApi';

/** Three surfaces. Configuration lives behind a settings control rather than
 *  beside the report — it is visited rarely and by a different person. */
type View = 'brief' | 'wire' | 'vendors';
/** Curation folds into the registry: both segments are about the same 83 rows. */
type Segment = 'all' | 'review' | 'entrants';
type SettingsPanel = 'collection' | 'sources' | 'health';

const SEVERITY_TONE: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-slate-50 text-slate-600 border-slate-200',
};

function fundingLabel(v: Vendor): string {
  const f = v.baseline?.funding_baseline;
  if (!f?.status) return '—';
  // A null amount under Undisclosed means the raise was never disclosed. Show
  // the state, not a zero we invented.
  if (f.total_musd === null || f.total_musd === undefined) return f.status;
  return `$${f.total_musd}M`;
}

export function MarketMonitorTab() {
  const [markets, setMarkets] = useState<Market[] | null>(null);
  const [marketId, setMarketId] = useState<number | null>(null);
  const [view, setView] = useState<View>('brief');
  const [segment, setSegment] = useState<Segment>('all');
  const [settingsOpen, setSettingsOpen] = useState<SettingsPanel | null>(null);
  // URL-addressable: this app has no router, so a vendor is a query param that
  // survives a refresh and can be sent to somebody.
  const [openVendor, setOpenVendor] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [vendors, setVendors] = useState<Vendor[] | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [tasks, setTasks] = useState<ReviewTask[] | null>(null);
  const [health, setHealth] = useState<SourceHealth | null>(null);
  const [runs, setRuns] = useState<CollectionRun[] | null>(null);
  const [plan, setPlan] = useState<CollectionPlan | null>(null);

  const [search, setSearch] = useState('');
  const [fundingFilter, setFundingFilter] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [toggleResult, setToggleResult] = useState<string | null>(null);
  const [showKeywords, setShowKeywords] = useState(false);
  const [vendorMode, setVendorMode] =
    useState<'none' | 'funded' | 'all'>('funded');
  const [termsDraft, setTermsDraft] = useState<string>('');
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null);
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [brief, setBrief] = useState<MarketBrief | null>(null);
  const [sources, setSources] = useState<SourceSetting[] | null>(null);
  const [minInterval, setMinInterval] = useState(6);

  const market = useMemo(
    () => markets?.find(m => m.id === marketId) ?? null, [markets, marketId]);

  // Read the vendor out of the URL on mount, and keep the two in step after.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const v = p.get('vendor');
    if (v && /^\d+$/.test(v)) setOpenVendor(Number(v));
    const onPop = () => {
      const q = new URLSearchParams(window.location.search).get('vendor');
      setOpenVendor(q && /^\d+$/.test(q) ? Number(q) : null);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  function openVendorPage(brandId: number) {
    const url = new URL(window.location.href);
    url.searchParams.set('vendor', String(brandId));
    window.history.pushState({}, '', url.toString());
    setOpenVendor(brandId);
  }

  function closeVendorPage() {
    const url = new URL(window.location.href);
    url.searchParams.delete('vendor');
    window.history.pushState({}, '', url.toString());
    setOpenVendor(null);
  }

  useEffect(() => {
    getMarkets()
      .then(list => {
        setMarkets(list);
        if (list.length && marketId === null) setMarketId(list[0].id);
      })
      .catch(e => setError(String(e.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reload = useCallback(() => {
    if (marketId === null) return;
    setError(null);
    Promise.all([
      getVendors(marketId), getFacets(marketId),
      getReviewTasks(marketId, { status: 'open' }),
      getSourceHealth(marketId), getRuns(marketId, 20),
      getCollectionPlan(marketId, vendorMode), getBrief(marketId, 7),
      getSources(marketId),
    ]).then(([v, f, t, h, r, p, b, s]) => {
      setBrief(b); setSources(s.sources); setMinInterval(s.min_interval_hours);
      setVendors(v); setFacets(f); setTasks(t); setHealth(h); setRuns(r); setPlan(p);
      setTermsDraft(p.market_terms.join('\n'));
    }).catch(e => setError(String(e.message ?? e)));
  }, [marketId, vendorMode]);

  useEffect(() => { reload(); }, [reload]);

  const shown = useMemo(() => {
    if (!vendors) return [];
    const q = search.trim().toLowerCase();
    return vendors.filter(v => {
      if (q && !v.display_name.toLowerCase().includes(q)) return false;
      if (fundingFilter &&
          v.baseline?.funding_baseline?.status !== fundingFilter) return false;
      return true;
    });
  }, [vendors, search, fundingFilter]);

  async function applyFilterToggle(filter: VendorFilter, enabled: boolean,
                                   dryRun: boolean) {
    if (marketId === null) return;
    setBusy(true); setToggleResult(null);
    try {
      const res = await setVendorCollection(marketId, enabled, filter, dryRun);
      setToggleResult(
        dryRun
          ? `${res.matched} vendors match; ${res.would_change ?? 0} would change.`
          : `${res.changed ?? 0} vendors updated.`);
      if (!dryRun) reload();
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function buildTimeline() {
    if (!plan?.topic_name) return;
    setBusy(true);
    try {
      const res = await generateMarketTimeline(plan.topic_name, 7);
      setToggleResult(
        `${res.events_created} events from ${res.articles_processed} articles ` +
        `(${res.events_deduplicated} merged into existing ones).`);
      reload();
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function runDiscovery() {
    if (marketId === null) return;
    setBusy(true);
    try {
      const res = await discoverCandidates(marketId, 30, false);
      setDiscovery(res);
      setToggleResult(res.error
        ? res.error
        : `Scanned ${res.scanned} articles, ${res.candidates} candidates.`);
      reload();
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function saveTerms() {
    if (marketId === null) return;
    setBusy(true);
    try {
      const terms = termsDraft.split('\n').map(s => s.trim()).filter(Boolean);
      const res = await setCollectionTerms(marketId, terms);
      setToggleResult(
        res.truncated?.length
          ? `${terms.length} saved, but ${res.truncated.length} exceed 30 ` +
            `characters and will be searched as: ` +
            res.truncated.map(x => `"${x.searched_as}"`).join(', ')
          : `${terms.length} collection terms saved.`);
      reload();
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function runSetup(dryRun: boolean) {
    if (marketId === null) return;
    setBusy(true);
    try {
      const res = await setupCollection(marketId, {
        qualifier: plan?.qualifier ?? 'security',
        vendorNames: vendorMode,
        dryRun,
      });
      if (res.error) { setToggleResult(res.error); setPlan(res); return; }
      setPlan(res);
      if (!dryRun) {
        setToggleResult(
          `Keyword group ${res.group_created ? 'created' : 'updated'} with ` +
          `${res.keywords_written ?? 0} keywords.`);
        reload();
      }
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  if (error && !markets) {
    return (
      <div className="p-6 text-red-600 flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 mt-0.5" />
        <div>{error}</div>
      </div>
    );
  }
  if (!markets) {
    return <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>;
  }
  if (!markets.length) {
    return (
      <div className="p-8 text-center text-slate-600">
        <LineChart className="w-10 h-10 mx-auto mb-3 text-slate-400" />
        <p className="font-medium">No markets yet.</p>
        <p className="text-sm mt-1">
          Create one, then import a vendor registry to populate it.
        </p>
      </div>
    );
  }

  const collectionLive = Boolean(plan?.existing);

  if (openVendor !== null && marketId !== null) {
    return (
      <MarketVendorPage marketId={marketId} brandId={openVendor}
                        onBack={closeVendorPage} />
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <LineChart className="w-5 h-5 text-slate-700" />
            <select
              className="text-lg font-semibold bg-transparent border-none focus:ring-0 p-0"
              value={marketId ?? ''}
              onChange={e => setMarketId(Number(e.target.value))}
            >
              {markets.map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          {market?.question && (
            <p className="text-sm text-slate-600 mt-1 max-w-3xl">{market.question}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={reload}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-md hover:bg-slate-50">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          {/* Configuration is rare and belongs to a different reader than the
              report, so it sits behind one control rather than beside it. */}
          <button onClick={() => setSettingsOpen('collection')}
            title="Collection, sources and health"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-md hover:bg-slate-50">
            <Settings className="w-4 h-4" /> Settings
          </button>
        </div>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ['Vendors', market?.vendors ?? 0],
          ['Collecting', market?.collecting ?? 0],
          ['Open reviews', tasks?.length ?? 0],
          ['No LinkedIn', health?.coverage?.without_linkedin ?? 0],
        ].map(([label, value]) => (
          <div key={String(label)} className="border rounded-lg p-3 bg-white">
            <div className="text-2xl font-semibold text-slate-800">{value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Collection state — the thing that decides whether anything arrives */}
      {!collectionLive && (
        <div className="border border-amber-200 bg-amber-50 rounded-lg p-3 text-sm text-amber-800 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <span className="font-medium">No news collection yet.</span> This
            market has no keyword group, so nothing is being gathered about the
            category. Set the terms under <em>Collection</em>.
          </div>
        </div>
      )}

      {/* View tabs */}
      <div className="flex gap-1 border-b">
        {([
          ['brief', 'Brief'],
          ['wire', 'Wire'],
          ['vendors', `Vendors${market?.vendors ? ` (${market.vendors})` : ''}`],
        ] as [View, string][]).map(([id, label]) => (
          <button key={id} onClick={() => setView(id)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${
              view === id ? 'border-slate-800 font-medium text-slate-900'
                          : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {toggleResult && (
        <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700">
          {toggleResult}
        </div>
      )}

      {/* ---- Brief ---- */}
      {view === 'brief' && brief && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600">
              Last {brief.period_days} days · {brief.coverage.watching} of{' '}
              {brief.coverage.registry} vendors watched
            </span>
            <div className="flex-1" />
            <a href={datasetCsvUrl(marketId!)}
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50">
              Download dataset (CSV)
            </a>
            <a href={feedUrl(marketId!)} target="_blank" rel="noreferrer"
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50">
              RSS feed
            </a>
          </div>

          {brief.standing_summary && (
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800 mb-1">
                Where the market stands
              </div>
              <p className="text-sm text-slate-700 whitespace-pre-line">
                {brief.standing_summary}
              </p>
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Headcount movement — the workbook baseline against LinkedIn today.
                Signed, so shrinking vendors read as clearly as growing ones. */}
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Headcount change since the registry was built
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                LinkedIn today versus the imported baseline. Only vendors with both.
              </p>
              {brief.headcount_movers.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  No vendor has both a baseline and a profile reading yet.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={brief.headcount_movers.slice(0, 8)}
                            layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" fontSize={11} />
                    <YAxis type="category" dataKey="vendor" width={110}
                           fontSize={11} interval={0} />
                    <Tooltip formatter={(v: number, _n, p: any) =>
                      [`${v > 0 ? '+' : ''}${v} staff (${p.payload.pct}%)`, 'change']} />
                    <Bar dataKey="delta" radius={[0, 3, 3, 0]}>
                      {brief.headcount_movers.slice(0, 8).map((m, i) => (
                        <Cell key={i} fill={m.delta >= 0 ? '#30a46c' : '#e5484d'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Loudest on LinkedIn
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                Posts in the window. Volume is not momentum — it is who is talking.
              </p>
              {brief.loudest_vendors.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  No vendor posts collected in this window.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={brief.loudest_vendors.slice(0, 8)}
                            layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" fontSize={11} allowDecimals={false} />
                    <YAxis type="category" dataKey="vendor" width={110}
                           fontSize={11} interval={0} />
                    <Tooltip />
                    <Bar dataKey="posts" fill="#d6409f" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="border rounded-lg p-4 bg-white">
            <div className="text-sm font-medium text-slate-800 mb-2">
              What changed
            </div>
            {brief.events.length === 0 ? (
              <p className="text-sm text-slate-500 py-4">
                No events in this window.
              </p>
            ) : (
              <ol className="space-y-2">
                {brief.events.map((e, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${
                      SEVERITY_TONE[e.significance === 'critical' ? 'high' : e.significance]
                        ?? SEVERITY_TONE.low}`}>
                      {e.significance}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm text-slate-800">{e.title}</div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {e.event_date} · {e.event_type} · {e.article_count} article
                        {e.article_count === 1 ? '' : 's'}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {brief.open_questions.length > 0 && (
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800 mb-2">
                Still unresolved
              </div>
              <div className="flex flex-wrap gap-2">
                {brief.open_questions.map((q, i) => (
                  <span key={i} className={`text-xs px-2 py-1 rounded border ${
                    SEVERITY_TONE[q.severity] ?? SEVERITY_TONE.low}`}>
                    {q.n} {q.kind.replace(/_/g, ' ')} ({q.severity})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ---- Timeline ---- */}
      {view === 'wire' && (
        <div className="space-y-3 max-w-4xl">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600">
              What changed in this market, day by day — the same timeline
              machinery the brands use, scoped to the market rather than to each
              of its {market?.vendors ?? 0} vendors.
            </p>
            <button disabled={busy || !plan?.topic_name} onClick={buildTimeline}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50 shrink-0">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Build from the last 7 days
            </button>
          </div>

          {events === null && (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
          )}
          {events?.length === 0 && (
            <p className="text-sm text-slate-500 py-6 text-center">
              No events yet. Daily extraction runs for the previous full day, so
              a market that started collecting today has nothing to read until
              tomorrow — or press the button above.
            </p>
          )}
          {events && events.length > 0 && (
            <ol className="space-y-2">
              {events.map(e => (
                <li key={e.id} className="border rounded-lg p-3 bg-white">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800">{e.title}</div>
                      {e.description && (
                        <p className="text-sm text-slate-600 mt-1">{e.description}</p>
                      )}
                      <div className="text-xs text-slate-500 mt-1.5">
                        {e.event_date} · {e.event_type}
                        {e.event_subtype ? ` · ${e.event_subtype}` : ''}
                        {' · '}{e.article_count} article
                        {e.article_count === 1 ? '' : 's'}
                        {e.occurrence_count > 1 && ` · seen ${e.occurrence_count}x`}
                      </div>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${
                      SEVERITY_TONE[e.significance === 'critical' ? 'high' : e.significance]
                        ?? SEVERITY_TONE.low}`}>
                      {e.significance}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {/* ---- Vendors ---- */}
      {view === 'vendors' && (
        <div className="space-y-3">
          {/* One table, three lenses. Review and new entrants are about these
              same rows, so they are segments rather than separate places. */}
          <div className="flex gap-1 p-0.5 bg-slate-100 rounded-md w-fit">
            {([
              ['all', `All (${vendors?.length ?? 0})`],
              ['review', `Needs review${tasks?.length ? ` (${tasks.length})` : ''}`],
              ['entrants', 'New entrants'],
            ] as [Segment, string][]).map(([id, label]) => (
              <button key={id} onClick={() => setSegment(id)}
                className={`text-sm px-3 py-1 rounded ${
                  segment === id ? 'bg-white shadow-sm text-slate-900'
                                 : 'text-slate-600 hover:text-slate-800'}`}>
                {label}
              </button>
            ))}
          </div>

          {segment === 'all' && (
          <>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Find a vendor"
                className="pl-8 pr-3 py-1.5 text-sm border rounded-md w-56" />
            </div>
            <select value={fundingFilter} onChange={e => setFundingFilter(e.target.value)}
              className="text-sm border rounded-md px-2 py-1.5">
              <option value="">All funding states</option>
              {facets?.funding_status.map(f => (
                <option key={f.value} value={f.value}>{f.value} ({f.n})</option>
              ))}
            </select>
            <div className="flex-1" />
            <button disabled={busy}
              onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] }, true, true)}
              className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50">
              Preview: collect funded only
            </button>
          </div>

          <div className="overflow-x-auto border rounded-lg bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  {['Vendor', 'Sub-category', 'Country', 'Founded', 'Staff',
                    'Funding', 'Links', 'Collecting'].map(h => (
                    <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map(v => (
                  <tr key={v.brand_id}
                      onClick={() => openVendorPage(v.brand_id)}
                      className="border-t hover:bg-slate-50 cursor-pointer">
                    <td className="px-3 py-2">
                      <div className="font-medium text-slate-800 hover:underline">
                        {v.display_name}</div>
                      {v.role === 'excluded' && (
                        <span className="text-xs text-slate-500">out of scope</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                      {v.baseline?.taxonomy?.sub_category ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                      {v.baseline?.hq_country ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600">
                      {v.baseline?.founded_year ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600">
                      {v.baseline?.metrics?.employee_count ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                      {fundingLabel(v)}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5 text-slate-400">
                        {v.identifiers?.some(i => i.kind === 'website_url') && (
                          <Globe className="w-4 h-4" aria-label="website" />)}
                        {v.identifiers?.some(i => i.kind === 'linkedin_company_url') && (
                          <Linkedin className="w-4 h-4" aria-label="LinkedIn" />)}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {v.collection_enabled
                        ? <ToggleRight className="w-5 h-5 text-emerald-600" />
                        : <ToggleLeft className="w-5 h-5 text-slate-300" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500">
            Showing {shown.length} of {vendors?.length ?? 0}. Select a vendor for
            everything we hold about it.
          </p>
          </>
          )}

          {segment === 'review' && (
            <div className="space-y-2 max-w-4xl">
              {!tasks?.length && (
                <p className="text-sm text-slate-500 py-6 text-center">
                  Nothing open. Review tasks are raised where the registry was
                  ambiguous rather than guessed at.
                </p>
              )}
              {tasks?.map(t => (
                <div key={t.id} className="border rounded-lg p-3 bg-white flex items-start gap-3">
                  <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${
                    SEVERITY_TONE[t.severity] ?? SEVERITY_TONE.low}`}>
                    {t.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-slate-800">{t.message}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      {t.brand_id ? (
                        <button onClick={() => openVendorPage(t.brand_id!)}
                          className="hover:underline">{t.vendor ?? 'vendor'}</button>
                      ) : 'market'} · {t.kind}{t.field ? ` · ${t.field}` : ''}
                    </div>
                  </div>
                  <button
                    onClick={async () => {
                      if (marketId === null) return;
                      await updateReviewTask(marketId, t.id, 'resolved');
                      reload();
                    }}
                    className="text-xs px-2 py-1 border rounded hover:bg-slate-50 shrink-0">
                    Resolve
                  </button>
                </div>
              ))}
            </div>
          )}

          {segment === 'entrants' && (
            <div className="space-y-3 max-w-4xl">
              <div className="border rounded-lg p-4 bg-white space-y-2">
                <div className="font-medium text-slate-800">Vendors we do not have</div>
                <p className="text-sm text-slate-600">
                  New entrants announce themselves by raising money. This reads the
                  funding coverage already collected and proposes companies missing
                  from the registry. Nothing is added automatically — a headline is
                  a lead.
                </p>
                <button disabled={busy} onClick={runDiscovery}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  Scan the last 30 days
                </button>
                {discovery && !discovery.error && (
                  <p className="text-xs text-slate-500">
                    Scanned {discovery.scanned} articles
                    {discovery.below_alignment_floor ? `, skipped ${discovery.below_alignment_floor} below the relevance floor` : ''}.
                  </p>
                )}
                {discovery?.error && (
                  <div className="text-sm border border-amber-200 bg-amber-50 rounded-md p-2.5 text-amber-800">
                    {discovery.error}
                  </div>
                )}
              </div>
              {discovery && discovery.proposals.length > 0 && (
                <div className="border rounded-lg bg-white overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600">
                      <tr>{['Company', 'Raised', 'Round', 'Seen in', 'Source'].map(h => (
                        <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
                    </thead>
                    <tbody>
                      {discovery.proposals.map(c => (
                        <tr key={c.name} className="border-t">
                          <td className="px-3 py-2 font-medium text-slate-800">{c.name}</td>
                          <td className="px-3 py-2 text-slate-600">
                            {c.amount_musd !== null ? `$${c.amount_musd}M` : '—'}</td>
                          <td className="px-3 py-2 text-slate-600">{c.round ?? '—'}</td>
                          <td className="px-3 py-2 text-slate-500">
                            {c.mentions} article{c.mentions === 1 ? '' : 's'}</td>
                          <td className="px-3 py-2 text-slate-500 max-w-xs truncate"
                              title={c.article_title ?? ''}>
                            {c.news_source ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {discovery && !discovery.proposals.length && !discovery.error && (
                <p className="text-sm text-slate-500 py-4">
                  No companies found outside the registry.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ---- Settings drawer ---- */}
      {settingsOpen !== null && (
        <div className="fixed inset-0 z-40 flex justify-end"
             onClick={() => setSettingsOpen(null)}>
          <div className="absolute inset-0 bg-slate-900/20" />
          <div className="relative bg-slate-50 w-full max-w-3xl h-full overflow-y-auto shadow-xl"
               onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b px-4 py-3 flex items-center gap-3">
              <div className="font-medium text-slate-800">Market settings</div>
              <div className="flex gap-1 p-0.5 bg-slate-100 rounded-md">
                {([
                  ['collection', 'Collection'],
                  ['sources', 'Sources & schedules'],
                  ['health', 'Health'],
                ] as [SettingsPanel, string][]).map(([id, label]) => (
                  <button key={id} onClick={() => setSettingsOpen(id)}
                    className={`text-sm px-3 py-1 rounded ${
                      settingsOpen === id ? 'bg-white shadow-sm text-slate-900'
                                          : 'text-slate-600 hover:text-slate-800'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex-1" />
              <button onClick={() => setSettingsOpen(null)}
                className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4">

      {settingsOpen === 'collection' && plan && (
        <div className="space-y-4 max-w-3xl">
          <div className="border rounded-lg p-4 bg-white space-y-3">
            <div>
              <div className="font-medium text-slate-800">What this market collects</div>
              <p className="text-sm text-slate-600 mt-1">
                The market's own language — what the category is called — not a
                list of {plan.vendors} company names. A market brief is about
                where the category is moving; the registry below is what you
                measure that coverage against.
              </p>
            </div>

            <div>
              <label className="text-sm text-slate-700">
                Collection terms, one per line
              </label>
              <textarea
                value={termsDraft}
                onChange={e => setTermsDraft(e.target.value)}
                rows={8}
                placeholder={'SOC automation\nautonomous SOC\nAI SOC analyst'}
                className="mt-1 w-full text-sm border rounded-md px-2 py-1.5 font-mono"
              />
              <div className="flex items-center gap-2 mt-2">
                <button disabled={busy} onClick={saveTerms}
                  className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50">
                  Save terms
                </button>
                <span className="text-xs text-slate-500">
                  {plan.market_terms.length} saved · 30 characters max
                </span>
              </div>
              {plan.truncated && plan.truncated.length > 0 && (
                <div className="text-xs border border-amber-200 bg-amber-50 rounded-md p-2 mt-2 text-amber-800">
                  {plan.truncated.length} term
                  {plan.truncated.length === 1 ? ' is' : 's are'} over 30
                  characters and will be searched as the shorter, broader form:
                  <ul className="mt-1 space-y-0.5">
                    {plan.truncated.map(x => (
                      <li key={x.term}>
                        <code className="bg-white border px-1 rounded">{x.term}</code>
                        {' → '}
                        <code className="bg-white border px-1 rounded">{x.searched_as}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="pt-1">
              <div className="text-sm text-slate-700">Also search vendors by name</div>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {([
                  ['none', 'None', 'Market language only'],
                  ['funded', `Funded (${plan.funded_vendors ?? 0})`,
                   'Vendors with a disclosed raise'],
                  ['all', `All (${plan.vendors})`, 'Every active vendor'],
                ] as ['none' | 'funded' | 'all', string, string][]).map(
                  ([mode, label, hint]) => (
                    <button key={mode} onClick={() => setVendorMode(mode)}
                      title={hint}
                      className={`text-sm px-2.5 py-1 rounded-md border ${
                        vendorMode === mode
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'hover:bg-slate-50'}`}>
                      {label}
                    </button>
                  ))}
              </div>
              <p className="text-xs text-slate-500 mt-1.5">
                A disclosed raise is the best proxy for a vendor active enough
                to generate coverage. Searching all {plan.vendors} spends quota
                on companies nobody writes about, and a third of this registry
                is single-word — so ambiguous names carry
                <code className="mx-1 bg-slate-100 px-1 rounded">{plan.qualifier}</code>
                as a second required word.
              </p>
            </div>

            {plan.error && (
              <div className="text-sm border border-amber-200 bg-amber-50 rounded-md p-2.5 text-amber-800">
                {plan.error}
              </div>
            )}

            <div className="text-sm text-slate-700 space-y-1 border-t pt-3">
              <div>Group: <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{plan.group_name}</code></div>
              <div>Topic: <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{plan.topic_name}</code></div>
              <div>{plan.keywords.length} search terms in total</div>
            </div>

            {plan.keywords.length > 0 && (
              <>
                <button onClick={() => setShowKeywords(s => !s)}
                  className="text-sm text-slate-600 flex items-center gap-1">
                  {showKeywords ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  {showKeywords ? 'Hide' : 'Show'} the full search list
                </button>
                {showKeywords && (
                  <div className="flex flex-wrap gap-1">
                    {plan.keywords.map(k => (
                      <span key={k} className={`text-xs border rounded px-1.5 py-0.5 ${
                        plan.vendor_keywords.includes(k)
                          ? 'bg-white text-slate-500' : 'bg-slate-100'}`}>{k}</span>
                    ))}
                  </div>
                )}
              </>
            )}

            <div className="flex items-center gap-2 pt-1">
              <button disabled={busy || !plan.keywords.length} onClick={() => runSetup(false)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {collectionLive ? 'Update keyword group' : 'Create keyword group'}
              </button>
              {collectionLive && (
                <span className="text-sm text-emerald-700 flex items-center gap-1">
                  <CheckCircle2 className="w-4 h-4" /> Live
                </span>
              )}
            </div>
          </div>

          <div className="border rounded-lg p-4 bg-white space-y-2">
            <div className="font-medium text-slate-800">Narrow the registry</div>
            <p className="text-sm text-slate-600">
              Which vendors the market spends anything watching directly —
              their websites, and LinkedIn where it is switched on. A rule that
              names no role never touches out-of-scope vendors.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button disabled={busy}
                onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] }, true, false)}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50">
                Watch only funded vendors
              </button>
              <button disabled={busy}
                onClick={() => applyFilterToggle(
                  { funding_status: ['Undisclosed', 'Bootstrapped'] }, false, false)}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50">
                Stop watching unfunded
              </button>
              <button disabled={busy}
                onClick={() => applyFilterToggle({ has_linkedin: false }, false, false)}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50">
                Stop watching vendors with no LinkedIn
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---- Settings: health ---- */}
      {settingsOpen === 'health' && health && (
        <div className="space-y-3 max-w-4xl">
          <div className="flex flex-wrap gap-2 text-sm">
            <span className={`px-2 py-1 rounded border ${
              health.providers.brightdata_linkedin_enabled
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-50 text-slate-600'}`}>
              LinkedIn collection {health.providers.brightdata_linkedin_enabled ? 'on' : 'off'}
            </span>
            <span className={`px-2 py-1 rounded border ${
              health.providers.webhook_secret_set
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-50 text-slate-600'}`}>
              Callback secret {health.providers.webhook_secret_set ? 'set' : 'unset'}
            </span>
          </div>

          {!health.sources.length && (
            <p className="text-sm text-slate-500 py-4">
              No collection runs in the last 30 days.
            </p>
          )}
          {health.sources.map(s => (
            <div key={`${s.source}:${s.provider}`} className="border rounded-lg p-3 bg-white">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-sm text-slate-800">{s.source}</div>
                <span className={`text-xs px-2 py-0.5 rounded border ${
                  s.healthy ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-red-50 text-red-700 border-red-200'}`}>
                  {s.healthy ? 'healthy' : 'failing'}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {s.succeeded} succeeded, {s.failed} failed
                {s.stale_hours !== null && ` · last success ${s.stale_hours}h ago`}
                {/* Ran and found nothing is a different state from failed. */}
                {s.found_nothing && ' · ran, found nothing new'}
              </div>
              {s.last_error && (
                <div className="text-xs text-red-600 mt-1 truncate">{s.last_error}</div>
              )}
            </div>
          ))}

          {runs && runs.length > 0 && (
            <div className="border rounded-lg bg-white overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>{['Run', 'Source', 'Status', 'New', 'Latency', 'Started'].map(h => (
                    <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
                </thead>
                <tbody>
                  {runs.map(r => (
                    <tr key={r.id} className="border-t">
                      <td className="px-3 py-1.5 text-slate-500">#{r.id}</td>
                      <td className="px-3 py-1.5">{r.source}</td>
                      <td className="px-3 py-1.5">{r.status}</td>
                      <td className="px-3 py-1.5">{r.records_new}</td>
                      <td className="px-3 py-1.5 text-slate-500">
                        {r.latency_ms !== null ? `${r.latency_ms} ms` : '—'}</td>
                      <td className="px-3 py-1.5 text-slate-500">
                        {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---- Settings: sources and schedules ---- */}
      {settingsOpen === 'sources' && sources && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            What runs, and how often. Paid sources bill per record, so the
            interval is the main cost control. The floor is {minInterval} hours —
            below that a market source spends money to learn nothing sooner.
          </p>
          <div className="border rounded-lg bg-white overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>{['Source', 'Cost', 'On', 'Every', 'Last success'].map(h => (
                  <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
              </thead>
              <tbody>
                {sources.map(s => (
                  <tr key={s.source} className="border-t">
                    <td className="px-3 py-2 text-slate-800">
                      {s.source.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        s.paid ? 'bg-amber-50 text-amber-700 border-amber-200'
                               : 'bg-slate-50 text-slate-500'}`}>
                        {s.paid ? 'per record' : 'bandwidth'}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={async () => {
                          if (marketId === null) return;
                          const next = Object.fromEntries(sources.map(x => [
                            x.source,
                            { enabled: x.source === s.source ? !x.enabled : x.enabled,
                              interval_hours: x.interval_hours },
                          ]));
                          setBusy(true);
                          try { await saveSources(marketId, next); reload(); }
                          finally { setBusy(false); }
                        }}
                        disabled={busy}>
                        {s.enabled
                          ? <ToggleRight className="w-5 h-5 text-emerald-600" />
                          : <ToggleLeft className="w-5 h-5 text-slate-300" />}
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      <input type="number" min={minInterval}
                        defaultValue={s.effective_interval_hours}
                        onBlur={async e => {
                          if (marketId === null) return;
                          const hours = Number(e.target.value);
                          if (!hours || hours === s.effective_interval_hours) return;
                          const next = Object.fromEntries(sources.map(x => [
                            x.source,
                            { enabled: x.enabled,
                              interval_hours: x.source === s.source
                                ? hours : x.interval_hours },
                          ]));
                          setBusy(true);
                          try { await saveSources(marketId, next); reload(); }
                          finally { setBusy(false); }
                        }}
                        className="w-20 border rounded px-1.5 py-0.5 text-sm" />
                      <span className="text-xs text-slate-500 ml-1">h</span>
                      {s.interval_hours && (
                        <span className="text-xs text-slate-400 ml-1">
                          (default {s.default_interval_hours}h)</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-500 text-xs">
                      {s.last_success
                        ? new Date(s.last_success).toLocaleString()
                        : 'never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
