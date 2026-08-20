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
import { MarketAnalysisView } from './MarketAnalysisView';
import {
  BarChart, Bar, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  datasetCsvUrl, datasetCsvDownloadUrl, discoverCandidates, feedUrl,
  generateMarketTimeline, getBrief, getCollectionPlan, getCorpusArticles,
  getCorpusSummary, getDataInventory, getDrilldown, getMarketTable,
  getFacets,
  getMarketTimeline, getMarkets, getOverview, getReviewTasks,
  getRuns, getSourceHealth, getSources, getVendors, reviewPosts, saveSources,
  scanCorpus,
  setCollectionTerms, setVendorCollection, setupCollection, updateReviewTask,
  type CollectionPlan, type CollectionRun, type CorpusArticle,
  type ArticleClass, type CorpusSummary, type DatasetInfo,
  type DrilldownVendor,
  type DiscoveryResult, type Facets,
  type Market, type MarketBrief, type MarketOverview, type ReviewTask,
  type SourceHealth, type SourceSetting, type TimelineEvent, type Vendor,
  type VendorFilter,
} from '../../services/marketMonitorApi';

/** Top-level views. Configuration lives in a settings drawer.
 *
 * Overview is the standing picture and Brief is the week's changes. They are
 * separate because a reader should not have to reconstruct the state of a
 * market from a list of what happened in it lately. */
type View = 'overview' | 'analysis' | 'brief' | 'wire' | 'coverage'
  | 'vendors' | 'data';
/** Segments over the same vendor set. */
type Segment = 'all' | 'review' | 'entrants';
type SettingsPanel = 'collection' | 'sources' | 'health';

/** A vendor's own blog post is not a trade-press story. The feed says so and
 * so does the list, because a reader who cannot tell them apart is being
 * misled about how well corroborated a claim is. */
const CLASS_LABEL: Record<string, string> = {
  news: 'news', vendor: 'vendor blog', social: 'vendor post',
  research: 'research',
};

const CLASS_TONE: Record<string, string> = {
  news: 'bg-white text-slate-600 border-slate-200',
  vendor: 'bg-amber-50 text-amber-700 border-amber-200',
  social: 'bg-amber-50 text-amber-700 border-amber-200',
  research: 'bg-indigo-50 text-indigo-700 border-indigo-200',
};

/** What each drilldown is, in words. The URL carries the key; the reader
 *  needs the sentence. */
const DRILL_LABEL: Record<string, string> = {
  quiet: 'Vendors with no signal at all — no posts, no job listings, no coverage',
  watched: 'Vendors we are collecting for',
  paused: 'Vendors in the registry with collection switched off',
  observed: 'Vendors we have read at least once',
  unobserved: 'Vendors we have never read',
  disclosed: 'Vendors that disclosed a raise',
  undisclosed: 'Vendors that never disclosed a raise',
  no_linkedin: 'Vendors with no LinkedIn page on file',
  posting: 'Vendors that have announced something',
  hiring: 'Vendors with open job listings',
};

const VERDICT_TONE: Record<string, string> = {
  signal: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  commentary: 'bg-slate-50 text-slate-600 border-slate-200',
  noise: 'bg-slate-50 text-slate-400 border-slate-200',
};

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

/** One figure with the sentence that says what it counts.
 *
 * The hint is not decoration. A bare "38" invites the reader to assume it
 * means whatever they were already thinking. */
function Stat({ label, value, hint, onClick }: {
  label: string; value: string; hint?: string; onClick?: () => void;
}) {
  const body = (
    <>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold text-slate-900 tabular-nums mt-0.5">
        {value}
      </div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    </>
  );
  if (!onClick) {
    return <div className="border rounded-lg p-3 bg-white">{body}</div>;
  }
  return (
    <button onClick={onClick}
            className="border rounded-lg p-3 bg-white text-left w-full
                       hover:border-slate-400 hover:bg-slate-50 transition-colors">
      {body}
      <div className="text-xs text-slate-400 mt-1">Show these vendors →</div>
    </button>
  );
}


export function MarketMonitorTab() {
  const [markets, setMarkets] = useState<Market[] | null>(null);
  const [marketId, setMarketId] = useState<number | null>(null);
  const [view, setView] = useState<View>('overview');
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
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [corpus, setCorpus] = useState<CorpusSummary | null>(null);
  const [corpusArticles, setCorpusArticles] =
    useState<CorpusArticle[] | null>(null);
  const [corpusOrigin, setCorpusOrigin] = useState<'' | 'corpus' | 'collected'>('');
  const [corpusClass, setCorpusClass] = useState<'' | ArticleClass>('');
  const [allPosts, setAllPosts] = useState(false);
  const [inventory, setInventory] = useState<DatasetInfo[] | null>(null);
  const [openDataset, setOpenDataset] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] =
    useState<{ total: number; rows: Record<string, any>[] } | null>(null);
  const [scanResult, setScanResult] = useState<string | null>(null);
  // A drilldown is URL-addressable so it can be sent to somebody, the same way
  // ?vendor= already works.
  const [drill, setDrill] = useState<string | null>(null);
  const [drillRows, setDrillRows] = useState<DrilldownVendor[] | null>(null);

  const market = useMemo(
    () => markets?.find(m => m.id === marketId) ?? null, [markets, marketId]);

  // Read the vendor out of the URL on mount, and keep the two in step after.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const v = p.get('vendor');
    if (v && /^\d+$/.test(v)) setOpenVendor(Number(v));
    const d = p.get('drill');
    if (d) setDrill(d);
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

  function openDrilldown(name: string) {
    const url = new URL(window.location.href);
    url.searchParams.set('drill', name);
    window.history.pushState({}, '', url.toString());
    setDrill(name);
  }

  function closeDrilldown() {
    const url = new URL(window.location.href);
    url.searchParams.delete('drill');
    window.history.pushState({}, '', url.toString());
    setDrill(null);
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
      getSources(marketId), getOverview(marketId, 30),
    ]).then(([v, f, t, h, r, p, b, s, o]) => {
      setBrief(b); setSources(s.sources); setMinInterval(s.min_interval_hours);
      setOverview(o);
      setVendors(v); setFacets(f); setTasks(t); setHealth(h); setRuns(r); setPlan(p);
      setTermsDraft(p.market_terms.join('\n'));
      // Timeline is fetched after the plan because it is keyed on the market's
      // collection topic. Always resolve to an array: leaving `events` null
      // renders the Wire as a spinner that never stops.
      const topic = p.topic_name;
      if (!topic) { setEvents([]); return; }
      getMarketTimeline(topic)
        .then(res => setEvents(res.events))
        .catch(() => setEvents([]));
    }).catch(e => { setError(String(e.message ?? e)); setEvents([]); });
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

  // The Coverage view is the only consumer of the matched corpus, so it loads
  // on demand rather than on every market switch.
  useEffect(() => {
    if (marketId === null || view !== 'coverage') return;
    let live = true;
    Promise.all([
      getCorpusSummary(marketId, 30),
      getCorpusArticles(marketId, { limit: 100,
                                    origin: corpusOrigin || undefined,
                                    classes: corpusClass || undefined,
                                    allPosts }),
    ]).then(([sum, list]) => {
      if (!live) return;
      setCorpus(sum); setCorpusArticles(list.articles);
    }).catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, view, corpusOrigin, corpusClass, allPosts]);

  useEffect(() => {
    if (marketId === null || !drill) { setDrillRows(null); return; }
    let live = true;
    setDrillRows(null);
    getDrilldown(marketId, drill)
      .then(r => { if (live) setDrillRows(r.vendors); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, drill]);

  useEffect(() => {
    if (marketId === null || view !== 'data') return;
    let live = true;
    getDataInventory(marketId)
      .then(r => { if (live) setInventory(r.datasets); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, view]);

  useEffect(() => {
    if (marketId === null || !openDataset) { setDatasetRows(null); return; }
    let live = true;
    setDatasetRows(null);
    getMarketTable(marketId, openDataset, 200)
      .then(r => { if (live) setDatasetRows({ total: r.total, rows: r.rows }); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, openDataset]);

  async function runPostReview() {
    if (marketId === null) return;
    setBusy(true); setScanResult(null);
    try {
      const r = await reviewPosts(marketId, { limit: 600 });
      setScanResult(
        r.candidates === 0
          ? 'Every vendor post has already been read.'
          : `Read ${r.reviewed} posts with ${r.model}: ${r.counts.signal} state ` +
            `a fact, ${r.counts.commentary} are commentary, ${r.counts.noise} ` +
            `are noise.` +
            (r.failed_batches ? ` ${r.failed_batches} batches failed.` : ''));
      const [sum, list] = await Promise.all([
        getCorpusSummary(marketId, 30),
        getCorpusArticles(marketId, { limit: 100,
                                      origin: corpusOrigin || undefined,
                                      classes: corpusClass || undefined,
                                      allPosts }),
      ]);
      setCorpus(sum); setCorpusArticles(list.articles);
    } catch (e: any) {
      setScanResult(`Post review failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function runCorpusScan() {
    if (marketId === null) return;
    setBusy(true); setScanResult(null);
    try {
      const r = await scanCorpus(marketId, { limit: 50000 });
      setScanResult(
        `${r.matched} articles matched on ${r.terms} phrases — ` +
        `${r.inserted} new, ${r.updated} re-scored.` +
        (r.truncated ? ' Row limit reached; run again to continue.' : ''));
      const [sum, list] = await Promise.all([
        getCorpusSummary(marketId, 30),
        getCorpusArticles(marketId, { limit: 100,
                                      origin: corpusOrigin || undefined,
                                      classes: corpusClass || undefined }),
      ]);
      setCorpus(sum); setCorpusArticles(list.articles);
    } catch (e: any) {
      setScanResult(`Scan failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

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
          {/* Collection terms, source schedules, and source health. */}
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
            <span className="font-medium">No collection configured.</span> This
            market has no keyword group, so no articles are being gathered. Set
            the search terms in Settings → Collection.
          </div>
        </div>
      )}

      {/* View tabs */}
      <div className="flex gap-1 border-b">
        {([
          ['overview', 'Overview'],
          ['analysis', 'Analysis'],
          ['brief', 'Brief'],
          ['wire', 'Wire'],
          ['coverage', 'Coverage'],
          ['vendors', `Vendors${market?.vendors ? ` (${market.vendors})` : ''}`],
          ['data', 'Data'],
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

      {/* ---- Drilldown: the vendors behind a number ---- */}
      {drill && (
        <div className="border rounded-lg bg-white">
          <div className="flex items-center gap-2 p-3 border-b">
            <span className="text-sm font-medium text-slate-800">
              {DRILL_LABEL[drill] ?? drill}
            </span>
            <span className="text-sm text-slate-500">
              {drillRows ? `${drillRows.length} vendors` : ''}
            </span>
            <div className="flex-1" />
            <button onClick={closeDrilldown}
                    className="text-slate-400 hover:text-slate-700">
              <X className="w-4 h-4" />
            </button>
          </div>
          {drillRows === null ? (
            <div className="py-10 text-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : drillRows.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center">
              No vendors match.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-xs text-slate-500 text-left">
                    <th className="px-3 py-1.5 font-normal">Vendor</th>
                    <th className="px-3 py-1.5 font-normal">Country</th>
                    <th className="px-3 py-1.5 font-normal">Founded</th>
                    <th className="px-3 py-1.5 font-normal">Funding</th>
                    <th className="px-3 py-1.5 font-normal text-right">Staff</th>
                    <th className="px-3 py-1.5 font-normal text-right">Announced</th>
                    <th className="px-3 py-1.5 font-normal text-right">Open roles</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {drillRows.map(v => (
                    <tr key={v.brand_id} className="hover:bg-slate-50">
                      <td className="px-3 py-1.5">
                        <button onClick={() => openVendorPage(v.brand_id)}
                                className="text-slate-800 hover:underline">
                          {v.vendor}
                        </button>
                      </td>
                      <td className="px-3 py-1.5 text-slate-600">{v.country ?? '—'}</td>
                      <td className="px-3 py-1.5 text-slate-600">{v.founded ?? '—'}</td>
                      <td className="px-3 py-1.5 text-slate-600">
                        {v.musd !== null ? `$${v.musd}M`
                          : (v.funding_status ?? '—')}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                        {v.staff ?? '—'}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                        {v.announcements}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                        {v.openings}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---- Overview ---- */}
      {view === 'overview' && overview && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Vendors watched"
                  value={`${overview.coverage.watching} of ${
                    overview.coverage.registry - overview.coverage.excluded}`}
                  hint={`${overview.coverage.paused} paused · ${
                    overview.coverage.observed} observed at least once`}
                  onClick={() => openDrilldown('watched')} />
            <Stat label="Disclosed funding"
                  value={overview.funding.total_musd === null ? '—'
                    : `$${overview.funding.total_musd.toFixed(0)}M`}
                  hint={`${overview.funding.disclosed} vendors disclosed, ${
                    overview.funding.undisclosed} did not`}
                  onClick={() => openDrilldown('disclosed')} />
            <Stat label="Articles about the market"
                  value={String(overview.corpus?.total ?? 0)}
                  hint={`${overview.corpus?.corpus ?? 0} matched from articles collected for other topics`}
                  onClick={() => setView('coverage')} />
            <Stat label="Vendors with no signal"
                  value={String(overview.quiet_vendors)}
                  hint="No posts, no job listings, no coverage"
                  onClick={() => openDrilldown('quiet')} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Coverage by week
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                Articles matching the market&apos;s phrases, by publication week.
              </p>
              {!overview.corpus?.by_week?.length ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  Nothing matched yet. Run a scan from the Coverage view.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={overview.corpus.by_week}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="n" fill="#475569" name="Articles" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Largest disclosed raises
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                Total raised, from the imported registry. Vendors that never
                disclosed a figure are absent, not zero.
              </p>
              <div className="divide-y">
                {overview.top_funded.map(v => (
                  <button key={v.brand_id}
                          onClick={() => openVendorPage(v.brand_id)}
                          className="w-full flex items-center justify-between
                                     py-1.5 text-sm hover:bg-slate-50 text-left">
                    <span className="text-slate-700">{v.vendor}</span>
                    <span className="text-slate-500 tabular-nums">
                      ${v.musd?.toFixed(1)}M
                      {v.last_round ? ` · ${v.last_round}` : ''}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Most active vendors
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                LinkedIn posts in the last {overview.period_days} days plus open
                job listings. Activity, not performance.
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 text-left">
                    <th className="py-1 font-normal">Vendor</th>
                    <th className="py-1 font-normal text-right">Posts</th>
                    <th className="py-1 font-normal text-right">Jobs</th>
                    <th className="py-1 font-normal text-right">Articles</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {overview.most_active.map(v => (
                    <tr key={v.brand_id} className="hover:bg-slate-50">
                      <td className="py-1.5">
                        <button onClick={() => openVendorPage(v.brand_id)}
                                className="text-slate-700 hover:underline">
                          {v.vendor}
                        </button>
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-slate-600">{v.posts}</td>
                      <td className="py-1.5 text-right tabular-nums text-slate-600">{v.jobs}</td>
                      <td className="py-1.5 text-right tabular-nums text-slate-600">{v.articles}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Last run per source
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                State of the most recent run, not a 30-day history.
              </p>
              <div className="divide-y">
                {overview.last_runs.map(r => (
                  <div key={r.source}
                       className="flex items-center justify-between py-1.5 text-sm">
                    <span className="text-slate-700">{r.source}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-slate-500 tabular-nums">
                        {r.records_received} records
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        r.status === 'succeeded'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : r.status === 'partial'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-red-50 text-red-700 border-red-200'}`}>
                        {r.status}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---- Coverage ---- */}
      {view === 'coverage' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-slate-600 max-w-2xl">
              Articles already in the database that match this market&apos;s
              phrases. Brand classification matches vendor names, so an article
              about the category that names no vendor never reaches it. This
              does.
            </p>
            <div className="flex-1" />
            <a href={feedUrl(marketId!)} target="_blank" rel="noreferrer"
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50">
              RSS feed
            </a>
            <button onClick={runCorpusScan} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50
                               inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Search className="w-4 h-4" />}
              Rescan corpus
            </button>
            <button onClick={runPostReview} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50
                               inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Play className="w-4 h-4" />}
              Review vendor posts
            </button>
          </div>

          {scanResult && (
            <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700">
              {scanResult}
            </div>
          )}

          {corpus && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="Matched articles" value={String(corpus.total)}
                    hint={`Last scan ${corpus.last_scan
                      ? new Date(corpus.last_scan).toLocaleString() : 'never'}`} />
              <Stat label="From other topics" value={String(corpus.corpus)}
                    hint="Collected for something else, relevant here" />
              <Stat label={`Published in ${corpus.recent_days} days`}
                    value={String(corpus.recent)}
                    hint="By publication date, not collection date" />
            </div>
          )}

          {corpus && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="border rounded-lg p-4 bg-white">
                <div className="text-sm font-medium text-slate-800 mb-2">
                  Phrases that matched
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {corpus.top_terms.map(t => (
                    <span key={t.term}
                          className="text-xs px-2 py-0.5 rounded border
                                     bg-slate-50 text-slate-700">
                      {t.term} <span className="text-slate-400">{t.n}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="border rounded-lg p-4 bg-white">
                <div className="text-sm font-medium text-slate-800 mb-2">
                  Sources
                </div>
                <div className="divide-y">
                  {corpus.top_sources.map(t => (
                    <div key={t.source}
                         className="flex justify-between py-1 text-sm">
                      <span className="text-slate-700">{t.source}</span>
                      <span className="text-slate-500 tabular-nums">{t.n}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {corpus?.signal_kinds && corpus.signal_kinds.length > 0 && (
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Vendor posts that state a fact
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                Each post read once and judged. Only these reach the feed, the
                timeline and the observer agents; the rest are conference
                notices, employee spotlights and commentary.
                {' '}{corpus.by_verdict?.signal ?? 0} of{' '}
                {(corpus.by_verdict?.signal ?? 0)
                 + (corpus.by_verdict?.commentary ?? 0)
                 + (corpus.by_verdict?.noise ?? 0)} reviewed.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {corpus.signal_kinds.map(k => (
                  <span key={k.kind}
                        className="text-xs px-2 py-0.5 rounded border
                                   bg-emerald-50 text-emerald-700 border-emerald-200">
                    {k.kind} <span className="text-emerald-500">{k.n}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-1">
            {([['', 'All'], ['corpus', 'From other topics'],
               ['collected', 'From this market']] as const).map(([id, label]) => (
              <button key={id} onClick={() => setCorpusOrigin(id)}
                      className={`text-sm px-3 py-1 rounded-md border ${
                        corpusOrigin === id
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
                {label}
              </button>
            ))}
            <span className="w-3" />
            {([['', 'Any kind'], ['news', 'News'], ['vendor', 'Vendor blogs'],
               ['social', 'Vendor posts'], ['research', 'Research']] as const)
              .map(([id, label]) => (
              <button key={id} onClick={() => setCorpusClass(id)}
                      className={`text-sm px-3 py-1 rounded-md border ${
                        corpusClass === id
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
                {label}
                {id && corpus?.by_class
                  ? ` (${corpus.by_class[id as ArticleClass] ?? 0})` : ''}
              </button>
            ))}
            <span className="w-3" />
            <label className="text-sm text-slate-600 inline-flex items-center gap-1.5">
              <input type="checkbox" checked={allPosts}
                     onChange={e => setAllPosts(e.target.checked)} />
              Include posts judged noise
            </label>
          </div>

          {corpusArticles === null ? (
            <div className="py-12 text-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : corpusArticles.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center">
              Nothing matched. Run a scan, or widen the market&apos;s phrases in
              Settings.
            </p>
          ) : (
            <div className="border rounded-lg bg-white divide-y">
              {corpusArticles.map(a => (
                <div key={a.uri} className="p-3">
                  <div className="flex items-start gap-2">
                    <a href={a.uri} target="_blank" rel="noreferrer"
                       className="text-sm text-slate-800 hover:underline flex-1">
                      {a.title}
                    </a>
                    <span className="text-xs text-slate-400 tabular-nums shrink-0">
                      {a.published ? a.published.slice(0, 10) : '—'}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    <span className="text-xs text-slate-500">
                      {a.news_source || 'unknown source'}
                    </span>
                    <span className="text-xs text-slate-300">·</span>
                    <span className="text-xs text-slate-500">
                      {a.origin === 'corpus' ? 'other topic' : 'this market'}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${
                      CLASS_TONE[a.article_class] ?? 'bg-slate-50 text-slate-600'}`}>
                      {CLASS_LABEL[a.article_class] ?? a.article_class}
                    </span>
                    {a.review_verdict && (
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        VERDICT_TONE[a.review_verdict]}`}
                            title={a.review_reason ?? undefined}>
                        {a.review_verdict === 'signal' && a.review_kind
                          ? a.review_kind : a.review_verdict}
                      </span>
                    )}
                    {a.matched_terms.slice(0, 4).map(t => (
                      <span key={t}
                            className="text-xs px-1.5 py-0.5 rounded border
                                       bg-slate-50 text-slate-600">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---- Analysis ---- */}
      {view === 'analysis' && marketId !== null && (
        <MarketAnalysisView marketId={marketId} onVendor={openVendorPage} />
      )}

      {/* ---- Data ---- */}
      {view === 'data' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 max-w-3xl">
            Everything this market has stored. Click a dataset to see its rows;
            the CSV is the whole table, the on-screen preview is the first 200.
          </p>

          {inventory === null ? (
            <div className="py-12 text-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : (
            <div className="border rounded-lg bg-white divide-y">
              {inventory.map(d => (
                <div key={d.dataset}>
                  <div className="flex items-center gap-3 p-3">
                    <button
                      onClick={() => setOpenDataset(
                        openDataset === d.dataset ? null : d.dataset)}
                      className="flex items-center gap-2 text-left flex-1 min-w-0">
                      {openDataset === d.dataset
                        ? <ChevronDown className="w-4 h-4 shrink-0 text-slate-400" />
                        : <ChevronRight className="w-4 h-4 shrink-0 text-slate-400" />}
                      <span className="text-sm font-medium text-slate-800 w-24 shrink-0">
                        {d.dataset}
                      </span>
                      <span className="text-sm text-slate-500 truncate">
                        {d.description}
                      </span>
                    </button>
                    <span className="text-sm tabular-nums text-slate-700 shrink-0">
                      {d.rows.toLocaleString()}
                    </span>
                    <span className="text-xs text-slate-400 tabular-nums shrink-0
                                     hidden sm:inline w-32 text-right">
                      {d.last_updated
                        ? new Date(d.last_updated).toLocaleString() : 'never'}
                    </span>
                    <a href={datasetCsvDownloadUrl(marketId!, d.dataset)}
                       className="text-xs px-2 py-1 border rounded
                                  hover:bg-slate-50 shrink-0">
                      CSV
                    </a>
                  </div>

                  {openDataset === d.dataset && (
                    <div className="border-t bg-slate-50 p-3">
                      {datasetRows === null ? (
                        <div className="py-6 text-center text-slate-400">
                          <Loader2 className="w-4 h-4 animate-spin mx-auto" />
                        </div>
                      ) : datasetRows.rows.length === 0 ? (
                        <p className="text-sm text-slate-500 py-4 text-center">
                          Nothing stored yet.
                        </p>
                      ) : (
                        <>
                          <div className="text-xs text-slate-500 mb-2">
                            Showing {datasetRows.rows.length} of{' '}
                            {datasetRows.total.toLocaleString()} rows.
                          </div>
                          {/* Wide tables scroll inside their own box rather
                              than pushing the page sideways. */}
                          <div className="overflow-x-auto border rounded bg-white">
                            <table className="text-xs min-w-full">
                              <thead className="bg-slate-100">
                                <tr>
                                  {Object.keys(datasetRows.rows[0]).map(col => (
                                    <th key={col}
                                        className="px-2 py-1.5 text-left font-medium
                                                   text-slate-600 whitespace-nowrap">
                                      {col}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y">
                                {datasetRows.rows.map((row, i) => (
                                  <tr key={i} className="hover:bg-slate-50">
                                    {Object.keys(datasetRows.rows[0]).map(col => (
                                      <td key={col}
                                          className="px-2 py-1 text-slate-700
                                                     max-w-xs truncate"
                                          title={String(row[col] ?? '')}>
                                        {String(row[col] ?? '')}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---- Brief ---- */}
      {view === 'brief' && brief && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600">
              Last {brief.period_days} days · {brief.coverage.watching} of{' '}
              {brief.coverage.registry} vendors monitored
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
          <p className="text-xs text-slate-500 -mt-2">
            The feed carries matched articles and timeline events, newest first.
            Vendor LinkedIn posts are left out unless you ask for them with
            <code className="mx-1">?classes=news,vendor,social</code>.
          </p>

          {brief.standing_summary && (
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800 mb-1">
                Summary
              </div>
              <p className="text-sm text-slate-700 whitespace-pre-line">
                {brief.standing_summary}
              </p>
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Signed delta so decreases are distinguishable from increases. */}
            <div className="border rounded-lg p-4 bg-white">
              <div className="text-sm font-medium text-slate-800">
                Headcount change
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                LinkedIn count vs imported baseline. Vendors with both values only.
              </p>
              {brief.headcount_movers.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  No vendor has both values.
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
                LinkedIn post volume
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
                Posts published in the selected window.
              </p>
              {brief.loudest_vendors.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  No posts in this window.
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
              Events
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
                Open review tasks
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
              Market-level events extracted from collected articles, newest first.
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
              No events. Extraction runs daily for the previous full day.
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
          {/* Segments filter the same vendor set. */}
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
            Showing {shown.length} of {vendors?.length ?? 0}. Select a row for
            vendor detail.
          </p>
          </>
          )}

          {segment === 'review' && (
            <div className="space-y-2 max-w-4xl">
              {!tasks?.length && (
                <p className="text-sm text-slate-500 py-6 text-center">
                  No open review tasks.
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
                <div className="font-medium text-slate-800">New entrants</div>
                <p className="text-sm text-slate-600">
                  Scans collected funding articles for companies not in the
                  registry. Results are proposals for review, not additions.
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
                Search terms for the category. Vendor names are added separately
                below.
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
                Adds vendor names to the search. Short or ambiguous names are
                qualified with
                <code className="mx-1 bg-slate-100 px-1 rounded">{plan.qualifier}</code>
                to reduce false matches.
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
            <div className="font-medium text-slate-800">Vendor selection</div>
            <p className="text-sm text-slate-600">
              Which vendors are monitored directly (website and LinkedIn).
              Filters exclude out-of-scope vendors unless a role is specified.
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
                  s.state === 'healthy'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : s.state === 'failing'
                    ? 'bg-red-50 text-red-700 border-red-200'
                    : 'bg-slate-50 text-slate-600 border-slate-200'}`}>
                  {s.state === 'in_flight' ? 'running' : s.state}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {s.succeeded} succeeded, {s.failed} failed over 30 days
                {s.stale_hours !== null && ` · last success ${s.stale_hours}h ago`}
                {/* Zero new records is a different outcome from a failure. */}
                {s.found_nothing && ' · no new records'}
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
            Collection sources and intervals. Sources marked "per record" are
            billed by the provider. Minimum interval is {minInterval} hours.
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
