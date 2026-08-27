/**
 * Market Monitor Tab
 *
 * A market is a tracked vendor portfolio built on Brand Watcher brands. Four
 * views: the registry, the collection setup, the review queue, and source
 * health. Everything reads app/routes/market_monitor_routes.py.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTheme } from 'next-themes';
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Globe, Layers,
  LineChart, Linkedin, Loader2, Play, RefreshCw, Search, Settings, ToggleLeft,
  ToggleRight, X,
} from 'lucide-react';
import { MarketVendorPage } from './MarketVendorPage';
import { MarketGeographyMap } from './map/MarketGeographyMap';
import { MarketAnalysisView } from './MarketAnalysisView';
import { MarketBriefingsView } from './MarketBriefingsView';
import { DataTable } from './DataTable';
import { ConfidenceGate, type ThinPanel } from './ConfidenceGate';
import { MetricHeading, SourceLegend } from './MarketMetric';
import { DrilldownHost, type DrilldownSpec } from './MarketDrilldownHost';
import {
  BarChart, Bar, CartesianGrid, Cell, Legend, Line,
  LineChart as RLineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  addVendor,
  datasetCsvUrl, datasetCsvDownloadUrl, discoverCandidates,
  exportBundleUrl, feedUrl, getReportLink, reportUrl, ALL_IN_SCOPE,
  generateMarketTimeline, getAnalyses, getPulse, getCollectionPlan,
  getCorpusArticles,
  getCorpusSummary, getDataInventory, getDrilldown, getHeadcountTrend,
  getLeaderboards,
  getMarketTable, getFacets,
  getMarketTimeline, getMarkets, getOverview, getReviewTasks, getWireArticles,
  getCollectionState, getRuns, getSourceHealth, getSources, getVendors,
  reviewPosts, saveSources,
  scanCorpus,
  setCollectionTerms, setVendorCollection, setupCollection, updateMarket,
  autoCloseReviewTasks, closeReviewTask, fixReviewTask,
  type CollectionPlan, type CollectionRun, type CollectionStateResponse,
  type CorpusArticle,
  type ArticleClass, type CorpusSummary, type DatasetInfo,
  type DrilldownVendor,
  type DiscoveryResult, type Facets, type FundingAnalysis,
  type Leaderboards,
  type Market, type MarketPulse, type MarketHeadcountTrend,
  type MarketOverview, type ReviewTask,
  type SourceHealth, type SourceSetting, type TimelineEvent, type Vendor,
  type WireArticle,
  type VendorFilter, type VendorSwitch,
} from '../../services/marketMonitorApi';

/** Top-level modes. Configuration lives in a settings drawer.
 *
 * Findings is the market — what changed, evidence, cross-sectional analysis
 * — merged from what used to be four separate tabs (Pulse, Analysis, and the
 * two panels each duplicated between them) so a reader doesn't have to visit
 * several tabs to reconstruct where a market stands. Collection is the
 * pipeline: health, sources, the raw corpus and event feed, and dataset
 * export — "what did we collect and is it working", a different question
 * from "what does the market show", with its own sub-navigation below. */
type View = 'findings' | 'collection' | 'briefings' | 'vendors';
type CollectionSubView = 'overview' | 'health' | 'coverage' | 'wire' | 'data' | 'sourcemap';
/** Segments over the same vendor set. */
type Segment = 'all' | 'review' | 'entrants';
type SettingsPanel = 'collection' | 'sources' | 'health' | 'scope';

/** A vendor's own blog post is not a trade-press story. The feed says so and
 * so does the list, because a reader who cannot tell them apart is being
 * misled about how well corroborated a claim is. */
const CLASS_LABEL: Record<string, string> = {
  news: 'news', vendor: 'vendor blog', social: 'vendor post',
  discussion: 'practitioner', research: 'research',
};

const CLASS_TONE: Record<string, string> = {
  news: 'bg-white text-slate-600 border-slate-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  vendor: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800',
  social: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800',
  // Blue, not amber: a practitioner talking about the market is a different
  // kind of evidence from a vendor talking about itself.
  discussion: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800',
  research: 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/20 dark:text-indigo-400 dark:border-indigo-800',
};

/** What each drilldown is, in words. The URL carries the key; the reader
 *  needs the sentence. */
const DRILL_LABEL: Record<string, string> = {
  quiet: 'Vendors with no observed activity — no posts, no job listings, no matched coverage',
  watched: 'Vendors we are collecting for',
  paused: 'Vendors in the registry with collection switched off',
  observed: 'Vendors we have read at least once',
  unobserved: 'Vendors we have never read',
  disclosed: 'Vendors with a disclosed funding amount on file',
  undisclosed: 'Vendors with no disclosed funding amount on file',
  no_linkedin: 'Vendors with no LinkedIn page on file',
  posting: 'Vendors that have announced something',
  hiring: 'Vendors with open job listings',
};

/** Source -> field mapping for Collection -> Data Map. What each source
 *  extracts and where it lands is fixed by the code (see
 *  app/services/brightdata_linkedin.py, app/tasks/market_monitor.py); cadence
 *  and cost are read live from the `sources` state instead of hardcoded here,
 *  since an operator can change either in Settings -> Sources & schedules. */
const SOURCE_MAP: {
  source: string; label: string; collects: string; landsIn: string;
  requires: string; manualOnly?: boolean;
}[] = [
  { source: 'linkedin_company_profile', label: 'LinkedIn profile',
    collects: 'Country, founding year, headcount, industry, description',
    landsIn: 'Vendor snapshot; fills in a blank registry field (country, founded year, headcount) — never overwrites a value already on file',
    requires: 'A LinkedIn company URL on file' },
  { source: 'linkedin_company_post', label: 'LinkedIn posts',
    collects: 'Post text, author, publish date, likes/comments/shares',
    landsIn: 'Articles, tagged as a vendor post',
    requires: 'A LinkedIn company URL on file' },
  { source: 'linkedin_jobs', label: 'LinkedIn jobs',
    collects: 'Open roles: title, location, seniority, function, posted date',
    landsIn: 'Job-posting snapshot',
    requires: 'A LinkedIn company URL on file' },
  { source: 'crunchbase_company', label: 'Crunchbase',
    collects: 'Funding rounds, investors, growth/heat score, operating status — no dollar amounts; Crunchbase’s public record doesn’t carry them',
    landsIn: 'Vendor snapshot, kept separate from the registry’s own funding total',
    requires: 'A Crunchbase URL on file (guessed from the company name if missing, then corrected)' },
  { source: 'pitchbook_company', label: 'PitchBook',
    collects: 'Headcount, total funding, last round, investors — field names not yet checked against a live response',
    landsIn: 'Vendor snapshot',
    requires: 'A PitchBook URL, entered by hand — no auto-discovery' },
  { source: 'zoominfo_company', label: 'ZoomInfo',
    collects: 'Revenue, headcount, leadership, tech stack — field names not yet checked against a live response',
    landsIn: 'Vendor snapshot',
    requires: 'A ZoomInfo URL, entered by hand — no auto-discovery' },
  { source: 'indeed_jobs', label: 'Indeed jobs',
    collects: 'Open roles, matched to the vendor by employer name — not yet confirmed against a real response',
    landsIn: 'Job-posting snapshot, pooled with LinkedIn jobs',
    requires: 'Run one vendor at a time from its page — never the whole registry',
    manualOnly: true },
  { source: 'vendor_web', label: 'Vendor web pages',
    collects: 'Page-by-page diffs on pages already found for the vendor',
    landsIn: 'Page-state snapshot, only when something changed',
    requires: 'A page found by web-page discovery, below' },
  { source: 'vendor_web_discovery', label: 'Web-page discovery',
    collects: 'RSS/Atom feeds and pages worth watching on the vendor’s own site',
    landsIn: 'A feed added to the article collector; page URLs added for vendor web pages to watch',
    requires: 'A domain on file' },
  { source: 'funding_discovery', label: 'Funding scan',
    collects: 'Funding-round mentions found in the news already collected',
    landsIn: 'The review queue, for a person to confirm before it is written to the registry',
    requires: 'Nothing — reads what collection already gathered' },
  { source: 'corpus_match', label: 'Corpus match',
    collects: 'Articles matching this market’s search terms, including ones collected under an unrelated topic',
    landsIn: 'Market articles',
    requires: 'Nothing — reads what collection already gathered' },
  { source: 'post_review', label: 'Post review',
    collects: 'An AI check of vendor LinkedIn posts already collected, for whether they say what they claim',
    landsIn: 'A verdict attached to the post',
    requires: 'Nothing — reads what collection already gathered' },
  { source: 'monthly_briefing', label: 'Monthly briefing',
    collects: 'Checks daily; writes a summary once a month',
    landsIn: 'Reports',
    requires: 'Nothing — reads what collection already gathered' },
];

// Vendor, day and timeline grouping read the whole loaded batch at once —
// there is no "page 2" of a vendor's section — so the fetch is one wide
// window that grows on request ("Load more") rather than pages that flip.
const COVERAGE_START = 300;
const COVERAGE_STEP = 200;
const COVERAGE_MAX = 500; // the API's own ceiling (limit<=500)
// How the coverage list is organised.
type GroupMode = 'vendor' | 'day' | 'kind' | 'timeline';
// An article with no vendor — general coverage of the category that names
// no vendor — lands in its own bucket under this label: the market talked
// about something without any tracked competitor being the subject.
const NO_VENDOR = 'Market chatter';
// A post judged to state a fact carries a review_kind ("launch",
// "partnership", …). Everything else — commentary, promotion, unreviewed
// news — has no kind of its own; it lands here rather than in a fake
// "other" bucket that would imply it was judged and found kind-less.
const NOT_ANNOUNCED = 'Not an announcement';

/** Reactions on a post, summed from whichever engagement fields it carries.
 *  Shared by the card (to show the count) and the sort control (to rank by
 *  it) so the two never disagree about what "popular" means. */
function engagementOf(a: CorpusArticle): number {
  const sm = a.social_meta;
  if (!sm) return 0;
  return (sm.likes ?? 0) + (sm.comments ?? 0) + (sm.reposts ?? sm.shares ?? 0);
}

/** Dot color for the timeline swimlanes. Distinct hues (not the class
 *  badges' exact tints) because bare dots have no adjacent text label to
 *  lean on the way a badge does — validated with the dataviz palette
 *  checker for CVD separation. "news" stays a neutral gray on purpose: it
 *  is the unflagged default, not a category competing for identity. */
const CLASS_DOT: Record<string, string> = {
  news: '#64748b', vendor: '#b45309', social: '#b45309',
  discussion: '#0369a1', research: '#6d28d9',
};
/** Same identities, lightened for a dark surface — SVG fill/stroke props
 *  can't take a Tailwind `dark:` variant, so charts need their own pair. */
const CLASS_DOT_DARK: Record<string, string> = {
  news: '#94a3b8', vendor: '#fbbf24', social: '#fbbf24',
  discussion: '#38bdf8', research: '#a78bfa',
};

/** Pick a chart color for the current theme. Everywhere a Recharts stroke/
 *  fill prop needs to differ by theme (Tailwind's `dark:` variant only
 *  applies to className, not SVG props). */
function cc(isDark: boolean, light: string, dark: string): string {
  return isDark ? dark : light;
}

const BULK_BTN = 'text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700 '
  + 'disabled:opacity-50';

/** Plain words for the review verdicts. "States a fact" was internal jargon
 *  that told a reader nothing about what they were looking at. */
const VERDICT_LABEL: Record<string, string> = {
  signal: 'announcement', commentary: 'opinion', noise: 'promotion',
};

const VERDICT_TONE: Record<string, string> = {
  signal: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800',
  commentary: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-700',
  noise: 'bg-slate-50 text-slate-400 border-slate-200 dark:bg-gray-700 dark:text-gray-500 dark:border-gray-700',
};

const SEVERITY_TONE: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800',
  medium: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800',
  low: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-700',
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
// Color alone never carries the reading — the sign ('+'/'−') is already in
// the text, and the dot repeats the same call, so a color-blind reader isn't
// left guessing which way "the number" points.
const STAT_TONE = {
  positive: { text: 'text-emerald-700 dark:text-emerald-400', dot: 'bg-emerald-500' },
  negative: { text: 'text-rose-700 dark:text-rose-400', dot: 'bg-rose-500' },
  neutral: { text: 'text-slate-900 dark:text-gray-100', dot: 'bg-slate-300 dark:bg-gray-500' },
} as const;

/** Text color class for a signed delta, or the neutral tone for null/zero. */
function deltaTextClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return STAT_TONE.neutral.text;
  return v > 0 ? STAT_TONE.positive.text : STAT_TONE.negative.text;
}

/** "attention +3" / "attention -1" / "attention unchanged" — never a bare
 *  "attention 0", which reads as the score being zero rather than a change
 *  of zero. Written as plain English ("up 3", "down 1", "unchanged") rather
 *  than bare +/- numbers, so it reads as a change, not a score, to someone
 *  who has never heard of Crunchbase's 0-100 scale. */
function fmtScoreDelta(label: string, v: number): string {
  if (v === 0) return `${label} unchanged`;
  return `${label} ${v > 0 ? 'up' : 'down'} ${Math.abs(v)}`;
}

function Stat({ label, value, hint, onClick, tone }: {
  label: string; value: string; hint?: string; onClick?: () => void;
  tone?: keyof typeof STAT_TONE;
}) {
  const colors = tone ? STAT_TONE[tone] : null;
  const body = (
    <>
      <div className="text-xs text-slate-500 dark:text-gray-400">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums mt-0.5 flex items-center gap-1.5
                       ${colors ? colors.text : 'text-slate-900 dark:text-gray-100'}`}>
        {colors && <span className={`inline-block w-2 h-2 rounded-full ${colors.dot}`} />}
        {value}
      </div>
      {hint && <div className="text-xs text-slate-500 mt-1 dark:text-gray-400">{hint}</div>}
    </>
  );
  if (!onClick) {
    return <div className="border rounded-lg p-3 bg-white dark:bg-gray-800">{body}</div>;
  }
  return (
    <button onClick={onClick}
            className="border rounded-lg p-3 bg-white text-left w-full
                       hover:border-slate-400 hover:bg-slate-50 transition-colors dark:bg-gray-800 dark:hover:border-gray-500 dark:hover:bg-gray-700">
      {body}
      <div className="text-xs text-slate-400 mt-1 dark:text-gray-500">Show these vendors →</div>
    </button>
  );
}

/** Per-source outcomes and the raw run log. Shared by Collection's own
 *  Health sub-view and the Settings drawer's Health tab, which show the same
 *  read-only data for two different audiences (a reader checking the
 *  pipeline vs. an admin mid-configuration) — one component so they can't
 *  drift apart. */
/** Whether a zero on this page is a measurement.
 *
 *  Deliberately separate from HealthPanel below, which answers "is the
 *  collector working". This answers "may I believe this number", and the
 *  denominator is different: that source's own eligible vendors, not the whole
 *  registry. A source with no vendors configured for it is not broken, and a
 *  source that reached 20 of 39 vendors is not healthy — both used to read as
 *  the same "no data".
 */
function CollectionStatePanel({ state }: { state: CollectionStateResponse | null }) {
  if (!state) return null;
  const unmeasured = new Set(state.unmeasured_states);
  return (
    <div className="space-y-3 max-w-4xl">
      <div className="border rounded-lg p-3 bg-white dark:bg-gray-800">
        <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
          Can these numbers be believed?
        </div>
        <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
          One row per source. &ldquo;Collected&rdquo; is how many of the vendors
          this source <em>can</em> run for it actually reached — so a source with
          no configured vendors reads as unconfigured rather than empty.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-gray-400">
                <th className="py-1 pr-3 font-medium">Source</th>
                <th className="py-1 pr-3 font-medium">State</th>
                <th className="py-1 pr-3 font-medium">Collected</th>
                <th className="py-1 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {state.sources.map(s => (
                <tr key={s.source} className="border-t border-slate-100 dark:border-gray-700">
                  <td className="py-1 pr-3 text-slate-700 dark:text-gray-200">
                    {s.source}
                    {!s.scheduled && (
                      <span className="ml-1 text-slate-400 dark:text-gray-500">
                        (not scheduled)
                      </span>
                    )}
                  </td>
                  <td className="py-1 pr-3">
                    <span className={
                      s.state === 'healthy'
                        ? 'text-slate-600 dark:text-gray-300'
                        : unmeasured.has(s.state)
                        ? 'text-red-700 dark:text-red-400'
                        : 'text-amber-700 dark:text-amber-400'}>
                      {state.state_labels[s.state] ?? s.state}
                    </span>
                  </td>
                  <td className="py-1 pr-3 tabular-nums text-slate-600 dark:text-gray-300">
                    {s.coverage.eligible
                      ? `${s.coverage.successful}/${s.coverage.eligible}`
                      : '—'}
                  </td>
                  <td className="py-1 text-slate-500 dark:text-gray-400">
                    {s.state_detail ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="border rounded-lg p-3 bg-white dark:bg-gray-800">
        <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
          Where coverage comes from
        </div>
        <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
          The platform something was published on, and the provider we collected
          it through, are different things. Bright Data is a provider; LinkedIn
          is a platform; Xpoz is a provider whose items carry their own platform.
        </p>
        <SourceLegend rows={state.legend} />
      </div>
    </div>
  );
}


function HealthPanel({ health, runs }: {
  health: SourceHealth; runs: CollectionRun[] | null;
}) {
  return (
    <div className="space-y-3 max-w-4xl">
      <div className="flex flex-wrap gap-2 text-sm">
        <span className={`px-2 py-1 rounded border ${
          health.providers.brightdata_linkedin_enabled
            ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800'
            : 'bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400'}`}>
          LinkedIn collection {health.providers.brightdata_linkedin_enabled ? 'on' : 'off'}
        </span>
        <span className={`px-2 py-1 rounded border ${
          health.providers.webhook_secret_set
            ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800'
            : 'bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400'}`}>
          Callback secret {health.providers.webhook_secret_set ? 'set' : 'unset'}
        </span>
      </div>

      {!health.sources.length && (
        <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
          No collection runs in the last 30 days.
        </p>
      )}
      {health.sources.map(s => (
        <div key={`${s.source}:${s.provider}`} className="border rounded-lg p-3 bg-white dark:bg-gray-800">
          <div className="flex items-center justify-between gap-3">
            <div className="font-medium text-sm text-slate-800 dark:text-gray-100">{s.source}</div>
            <span className={`text-xs px-2 py-0.5 rounded border ${
              s.state === 'healthy'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800'
                : s.state === 'failing'
                ? 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'
                : 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-700'}`}>
              {s.state === 'in_flight' ? 'running' : s.state}
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-1 dark:text-gray-400">
            {s.succeeded} succeeded, {s.failed} failed over 30 days
            {s.stale_hours !== null && ` · last success ${s.stale_hours}h ago`}
            {/* Zero new records is a different outcome from a failure. */}
            {s.found_nothing && ' · no new records'}
          </div>
          {s.last_error && (
            <div className="text-xs text-red-600 mt-1 truncate dark:text-red-400">{s.last_error}</div>
          )}
        </div>
      ))}

      {runs && runs.length > 0 && (
        <div className="border rounded-lg bg-white overflow-x-auto dark:bg-gray-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
              <tr>{['Run', 'Source', 'Status', 'New', 'Latency', 'Started'].map(h => (
                <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} className="border-t">
                  <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">#{r.id}</td>
                  <td className="px-3 py-1.5">{r.source}</td>
                  <td className="px-3 py-1.5">{r.status}</td>
                  <td className="px-3 py-1.5">{r.records_new}</td>
                  <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">
                    {r.latency_ms !== null ? `${r.latency_ms} ms` : '—'}</td>
                  <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** "Today", "Yesterday", a weekday name inside the last week, else a date —
 *  the labels a reader would use for the same day, not a raw ISO string. */
function dayLabel(iso: string | null): string {
  if (!iso) return 'Undated';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Undated';
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOf(new Date()) - startOf(d)) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays > 1 && diffDays < 7) return d.toLocaleDateString(undefined, { weekday: 'long' });
  return d.toLocaleDateString(undefined,
    { month: 'short', day: 'numeric', year: diffDays > 300 ? 'numeric' : undefined });
}

/** One matched article. Used by every grouping mode so a card looks the
 *  same whether it is inside a story cluster, a vendor section or a day
 *  section — only the surrounding structure changes. */
function CoverageCard({ article: a, vendorFilter, setVendorFilter,
                        clusterOpen, onToggleCluster }: {
  article: CorpusArticle;
  vendorFilter: number | null;
  setVendorFilter: (id: number | null) => void;
  clusterOpen: boolean;
  onToggleCluster: () => void;
}) {
  const sm = a.social_meta ?? {};
  const engagement = engagementOf(a);
  const account = sm.author_name || sm.author;
  const isSocial = a.article_class === 'social' || a.article_class === 'discussion';
  return (
    <article className="border rounded-lg bg-white overflow-hidden
                         hover:border-slate-300 transition-colors dark:bg-gray-800 dark:hover:border-gray-600">
      {a.cluster && (
        <div className="px-3 pt-2 flex items-center gap-1.5 text-xs
                         font-medium text-violet-700 dark:text-violet-400">
          <Layers className="w-3.5 h-3.5" />
          {a.cluster.size} sources on this story
        </div>
      )}
      <div className="p-3 flex items-start gap-3">
        {sm.thumbnail && (
          <img src={sm.thumbnail} alt="" loading="lazy"
               referrerPolicy="no-referrer"
               onError={e => {
                 // A broken thumbnail leaves a torn-image icon, which reads
                 // worse than no image at all.
                 (e.currentTarget as HTMLImageElement).style.display = 'none';
               }}
               className="w-20 h-20 object-cover rounded border shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            <span className={`text-xs px-1.5 py-0.5 rounded border ${
              CLASS_TONE[a.article_class] ?? 'bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400'}`}>
              {CLASS_LABEL[a.article_class] ?? a.article_class}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded border
                             bg-white text-slate-600 dark:bg-gray-800 dark:text-gray-400">
              {isSocial ? (sm.platform ?? a.news_source)
                        : (a.news_source ?? 'unknown')}
            </span>
            {account && (
              <span className="text-xs text-slate-600 font-medium dark:text-gray-400">
                {sm.author && isSocial ? `@${sm.author}` : account}
              </span>
            )}
            {a.review_verdict && (
              <span className={`text-xs px-1.5 py-0.5 rounded border ${
                VERDICT_TONE[a.review_verdict]}`}
                    title={a.review_reason ?? undefined}>
                {a.review_verdict === 'signal' && a.review_kind
                  ? a.review_kind
                  : VERDICT_LABEL[a.review_verdict] ?? a.review_verdict}
              </span>
            )}
            <div className="flex-1" />
            <span className="text-xs text-slate-400 tabular-nums dark:text-gray-500">
              {a.published ? a.published.slice(0, 10) : '—'}
            </span>
          </div>

          <a href={a.uri} target="_blank" rel="noreferrer"
             className="text-sm font-medium text-slate-800 hover:underline block dark:text-gray-100">
            {a.title}
          </a>
          {a.summary && a.summary !== a.title && (
            <p className="text-xs text-slate-500 mt-1 dark:text-gray-400">
              {a.summary.slice(0, 200)}
              {a.summary.length > 200 ? '…' : ''}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            {a.vendors.slice(0, 4).map(v => (
              <button key={v.brand_id}
                      onClick={() => setVendorFilter(
                        vendorFilter === v.brand_id ? null : v.brand_id)}
                      className={`text-xs px-1.5 py-0.5 rounded border ${
                        vendorFilter === v.brand_id
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'bg-sky-50 text-sky-700 border-sky-200 hover:bg-sky-100 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800'}`}>
                {v.vendor}
              </button>
            ))}
            {a.matched_terms.slice(0, 3).map(t => (
              <span key={t}
                    className="text-xs px-1.5 py-0.5 rounded border
                               bg-slate-50 text-slate-500 dark:bg-gray-700 dark:text-gray-400">
                {t}
              </span>
            ))}
            <div className="flex-1" />
            {engagement > 0 && (
              <span className="text-xs text-slate-500 dark:text-gray-400"
                    title={`${sm.likes ?? 0} likes · ${sm.comments ?? 0} comments · ${sm.reposts ?? sm.shares ?? 0} reposts`}>
                {engagement} reactions
              </span>
            )}
          </div>
        </div>
      </div>

      {a.cluster && (
        <div className="border-t bg-slate-50 px-3 py-2 dark:bg-gray-700">
          <button onClick={onToggleCluster}
                  className="text-xs text-slate-600 inline-flex items-center gap-1 dark:text-gray-400">
            {clusterOpen ? <ChevronDown className="w-3 h-3" />
                         : <ChevronRight className="w-3 h-3" />}
            See the other {a.cluster.size - 1} post{a.cluster.size - 1 === 1 ? '' : 's'}
          </button>
          {clusterOpen && (
            <div className="mt-1.5 space-y-1">
              {a.cluster.others.map(o => (
                <a key={o.uri} href={o.uri} target="_blank" rel="noreferrer"
                   className="block text-xs text-slate-600 hover:underline truncate dark:text-gray-400">
                  {o.author ? `@${o.author}: ` : ''}{o.title}
                  <span className="text-slate-400 dark:text-gray-500">
                    {' '}· {o.news_source} · {(o.published ?? '').slice(0, 10)}
                  </span>
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

/** A collapsible section of cards — one vendor's coverage, or one day's.
 *  Capped to a handful of cards until asked for more, because a vendor with
 *  90 posts should not push every other vendor off the screen. */
function GroupSection({ title, count, hint, items, expanded, onToggle,
                        vendorFilter, setVendorFilter,
                        openCluster, setOpenCluster }: {
  title: string; count: number; hint?: string; items: CorpusArticle[];
  expanded: boolean; onToggle: () => void;
  vendorFilter: number | null; setVendorFilter: (id: number | null) => void;
  openCluster: string | null; setOpenCluster: (uri: string | null) => void;
}) {
  const CAP = 6;
  const visible = expanded ? items : items.slice(0, CAP);
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2 pt-1">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-gray-100">{title}</h3>
        <span className="text-xs text-slate-400 tabular-nums dark:text-gray-500">{count}</span>
        {hint && <span className="text-xs text-slate-400 dark:text-gray-500">· {hint}</span>}
      </div>
      <div className="space-y-2">
        {visible.map(a => (
          <CoverageCard key={a.uri} article={a} vendorFilter={vendorFilter}
                        setVendorFilter={setVendorFilter}
                        clusterOpen={openCluster === a.uri}
                        onToggleCluster={() => setOpenCluster(
                          openCluster === a.uri ? null : a.uri)} />
        ))}
      </div>
      {items.length > CAP && (
        <button onClick={onToggle}
                className="text-xs text-slate-500 hover:text-slate-700 inline-flex
                           items-center gap-1 dark:text-gray-400 dark:hover:text-gray-300">
          {expanded
            ? <><ChevronDown className="w-3 h-3" /> Show fewer</>
            : <><ChevronRight className="w-3 h-3" />
                Show {items.length - CAP} more</>}
        </button>
      )}
    </div>
  );
}

function TimelinePoint(props: any) {
  const { cx, cy, payload } = props;
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  if (cx == null || cy == null) return null;
  // A dot standing for several near-duplicate posts is bigger and rung, so a
  // day where five outlets covered the same announcement reads differently
  // from a day where one did.
  const clustered = (payload.clusterSize ?? 1) > 1;
  const dotMap = isDark ? CLASS_DOT_DARK : CLASS_DOT;
  return (
    <circle cx={cx} cy={cy} r={clustered ? 7 : 5}
            fill={dotMap[payload.cls] ?? cc(isDark, '#64748b', '#94a3b8')}
            stroke={cc(isDark, '#fff', '#1f2937')} strokeWidth={clustered ? 2 : 1}
            style={{ cursor: 'pointer' }} />
  );
}

function TimelineTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="bg-white border rounded-md shadow-sm px-2.5 py-1.5 text-xs
                     max-w-xs dark:bg-gray-800">
      <div className="font-medium text-slate-800 truncate dark:text-gray-100">{p.title}</div>
      <div className="text-slate-500 mt-0.5 dark:text-gray-400">
        {p.vendor} · {p.source ?? 'unknown source'} ·{' '}
        {(p.published ?? '').slice(0, 10)}
      </div>
      {p.clusterSize > 1 && (
        <div className="text-violet-700 mt-0.5 dark:text-violet-400">
          +{p.clusterSize - 1} more source{p.clusterSize - 1 === 1 ? '' : 's'} on this story
        </div>
      )}
    </div>
  );
}

/** One Wire event, with its article_uris fetched and shown only on request —
 *  a count and a significance are not something a reader can check without
 *  seeing what they were computed from. Vendor badges on each article pivot
 *  to that vendor's page, the same as Coverage already does. */
function WireEventCard({ event: e, onVendor }: {
  event: TimelineEvent; onVendor: (brandId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [articles, setArticles] = useState<WireArticle[] | null>(null);

  async function toggle() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (articles === null && e.article_uris?.length) {
      try {
        setArticles(await getWireArticles(e.article_uris));
      } catch {
        setArticles([]);
      }
    }
  }

  const hasArticles = (e.article_uris?.length ?? 0) > 0;

  return (
    <li className="border rounded-lg p-3 bg-white dark:bg-gray-800">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-slate-800 dark:text-gray-100">{e.title}</div>
          {e.description && (
            <p className="text-sm text-slate-600 mt-1 dark:text-gray-400">{e.description}</p>
          )}
          <div className="text-xs text-slate-500 mt-1.5 flex items-center gap-1.5 flex-wrap dark:text-gray-400">
            <span>
              {e.event_date} · {e.event_type}
              {e.event_subtype ? ` · ${e.event_subtype}` : ''}
              {' · '}{e.article_count} article{e.article_count === 1 ? '' : 's'}
              {e.occurrence_count > 1 && ` · seen ${e.occurrence_count}x`}
            </span>
            {hasArticles && (
              <button onClick={toggle}
                      className="text-slate-600 hover:text-slate-800 inline-flex
                                 items-center gap-0.5 dark:text-gray-400 dark:hover:text-gray-100">
                {open ? <ChevronDown className="w-3 h-3" />
                      : <ChevronRight className="w-3 h-3" />}
                {open ? 'Hide' : 'Show'} articles
              </button>
            )}
          </div>
          {open && (
            <div className="mt-2 pt-2 border-t space-y-1.5">
              {articles === null ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400 dark:text-gray-500" />
              ) : articles.length === 0 ? (
                <p className="text-xs text-slate-400 dark:text-gray-500">
                  {hasArticles ? 'Could not load these articles.'
                               : 'This event has no linked articles — it was ' +
                                 'computed from counts, not tied to specific ones.'}
                </p>
              ) : articles.map(a => (
                <div key={a.uri} className="text-xs">
                  <a href={a.uri} target="_blank" rel="noreferrer"
                     className="text-slate-700 hover:underline dark:text-gray-300">
                    {a.title}
                  </a>
                  <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                    <span className="text-slate-400 dark:text-gray-500">
                      {a.news_source ?? 'unknown source'}
                      {a.publication_date ? ` · ${a.publication_date.slice(0, 10)}` : ''}
                    </span>
                    {a.vendors.map(v => (
                      <button key={v.brand_id} onClick={() => onVendor(v.brand_id)}
                              className="text-xs px-1.5 py-0.5 rounded border
                                         bg-sky-50 text-sky-700 border-sky-200
                                         hover:bg-sky-100 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                        {v.vendor}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${
          SEVERITY_TONE[e.significance === 'critical' ? 'high' : e.significance]
            ?? SEVERITY_TONE.low}`}>
          {e.significance}
        </span>
      </div>
    </li>
  );
}

interface CoverageGroup {
  key: string; label: string; hint?: string; items: CorpusArticle[];
}

/** One section per vendor, most-covered first. Articles with no attributed
 *  vendor — general market news that names no vendor — land in one
 *  section rather than disappearing. */
function groupByVendor(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const v = a.vendors[0];
    const key = v ? `v${v.brand_id}` : 'no-vendor';
    const label = v ? v.vendor : NO_VENDOR;
    if (!map.has(key)) map.set(key, { key, label, items: [] });
    map.get(key)!.items.push(a);
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length);
}

/** One section per day, most recent day first. A real group-by rather than a
 *  scan for label changes — the input may arrive newest-first (default) or
 *  re-sorted by reactions (the "Most reactions" sort), and a scan-based
 *  version would fragment a single day into scattered one-item sections the
 *  moment the input isn't already in calendar order. */
function groupByDay(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const label = dayLabel(a.published);
    if (!map.has(label)) map.set(label, { key: label, label, items: [] });
    map.get(label)!.items.push(a);
  }
  return [...map.values()].sort((a, b) =>
    (b.items[0]?.published ?? '').localeCompare(a.items[0]?.published ?? ''));
}

/** One section per kind of announcement — launches, partnerships, customer
 *  wins, funding, acquisitions — the direct answer to "what shipped" rather
 *  than "who posted". Everything not judged to state a fact collects in one
 *  bucket, kept last regardless of size: it is a residue, not a category. */
function groupByKind(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const kind = a.review_verdict === 'signal' && a.review_kind
      ? a.review_kind : NOT_ANNOUNCED;
    const key = kind;
    if (!map.has(key)) {
      map.set(key, { key, label: kind === NOT_ANNOUNCED ? kind
        : kind.charAt(0).toUpperCase() + kind.slice(1), items: [] });
    }
    map.get(key)!.items.push(a);
  }
  const groups = [...map.values()];
  groups.sort((a, b) => {
    if (a.key === NOT_ANNOUNCED) return 1;
    if (b.key === NOT_ANNOUNCED) return -1;
    return b.items.length - a.items.length;
  });
  return groups;
}

function CoverageGrouped({ groups, expandedGroups, setExpandedGroups,
                           vendorFilter, setVendorFilter,
                           openCluster, setOpenCluster }: {
  groups: CoverageGroup[];
  expandedGroups: Set<string>; setExpandedGroups: (s: Set<string>) => void;
  vendorFilter: number | null; setVendorFilter: (id: number | null) => void;
  openCluster: string | null; setOpenCluster: (uri: string | null) => void;
}) {
  return (
    <div className="space-y-5">
      {groups.map(g => (
        <GroupSection key={g.key} title={g.label} count={g.items.length}
                      items={g.items}
                      expanded={expandedGroups.has(g.key)}
                      onToggle={() => {
                        const next = new Set(expandedGroups);
                        if (next.has(g.key)) next.delete(g.key); else next.add(g.key);
                        setExpandedGroups(next);
                      }}
                      vendorFilter={vendorFilter} setVendorFilter={setVendorFilter}
                      openCluster={openCluster} setOpenCluster={setOpenCluster} />
      ))}
    </div>
  );
}

/** A swimlane view: one row per vendor, one dot per article, positioned by
 *  publication date. A burst of dots in one vendor's lane on one day is a
 *  coverage spike a reader would otherwise have to notice by scrolling past
 *  twenty identical-looking cards. */
function CoverageTimeline({ articles }: { articles: CorpusArticle[] }) {
  const DEFAULT_LANES = 12;
  const [showAllLanes, setShowAllLanes] = useState(false);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const { lanes, points, hiddenVendors, hiddenArticles, undated } = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of articles) {
      const v = a.vendors[0];
      counts.set(v ? v.vendor : NO_VENDOR,
        (counts.get(v ? v.vendor : NO_VENDOR) ?? 0) + 1);
    }
    const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const cap = showAllLanes ? ranked.length : DEFAULT_LANES;
    const laneNames = ranked.slice(0, cap).map(([name]) => name);
    const laneIndex = new Map(laneNames.map((l, i) => [l, i]));
    const overflowArticles = ranked.slice(cap)
      .reduce((s, [, n]) => s + n, 0);
    const pts: any[] = [];
    let undatedCount = 0;
    for (const a of articles) {
      if (!a.published) { undatedCount++; continue; }
      const d = new Date(a.published);
      if (Number.isNaN(d.getTime())) { undatedCount++; continue; }
      const v = a.vendors[0];
      const lane = v ? v.vendor : NO_VENDOR;
      const idx = laneIndex.get(lane);
      if (idx === undefined) continue;
      pts.push({
        x: Math.floor(d.getTime() / 86400000), y: idx, cls: a.article_class,
        title: a.title, source: a.news_source, vendor: lane,
        published: a.published, uri: a.uri, clusterSize: a.cluster?.size ?? 1,
      });
    }
    return { lanes: laneNames, points: pts,
             hiddenVendors: Math.max(0, ranked.length - laneNames.length),
             hiddenArticles: overflowArticles, undated: undatedCount };
  }, [articles, showAllLanes]);

  if (lanes.length === 0) {
    return <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
      Nothing with a publication date to place on a timeline.
    </p>;
  }

  const legendClasses: ArticleClass[] = ['news', 'vendor', 'social', 'discussion', 'research'];

  return (
    <div className="border rounded-lg bg-white p-4 dark:bg-gray-800">
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 mb-3 dark:text-gray-400">
        {legendClasses.map(c => (
          <span key={c} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ background: (isDark ? CLASS_DOT_DARK : CLASS_DOT)[c] }} />
            {CLASS_LABEL[c]}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={Math.max(220, lanes.length * 34 + 40)}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={cc(isDark, '#e2e8f0', '#374151')} />
          <XAxis type="number" dataKey="x" domain={['dataMin - 1', 'dataMax + 1']}
                 tickFormatter={v => new Date(v * 86400000)
                   .toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                 stroke={cc(isDark, '#94a3b8', '#9ca3af')} tick={{ fontSize: 11 }} />
          <YAxis type="number" dataKey="y" domain={[-0.5, lanes.length - 0.5]}
                 ticks={lanes.map((_, i) => i)}
                 tickFormatter={i => lanes[i] ?? ''}
                 reversed width={140} stroke={cc(isDark, '#94a3b8', '#9ca3af')} tick={{ fontSize: 11 }} />
          <Tooltip content={<TimelineTooltip />} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={points} shape={<TimelinePoint />}
                   onClick={(p: any) =>
                     window.open(p.uri, '_blank', 'noreferrer')} />
        </ScatterChart>
      </ResponsiveContainer>
      {(hiddenVendors > 0 || undated > 0) && (
        <p className="text-xs text-slate-400 mt-2 dark:text-gray-500">
          {hiddenVendors > 0 &&
            `${hiddenArticles} article${hiddenArticles === 1 ? '' : 's'} from ` +
            `${hiddenVendors} vendor${hiddenVendors === 1 ? '' : 's'} outside the ` +
            `${DEFAULT_LANES} busiest lanes not shown.`}
          {hiddenVendors > 0 && (
            <button onClick={() => setShowAllLanes(true)}
                    className="text-slate-600 hover:text-slate-800 underline ml-1 dark:text-gray-400 dark:hover:text-gray-100">
              Show all {lanes.length + hiddenVendors} vendors
            </button>
          )}
          {hiddenVendors > 0 && undated > 0 && ' · '}
          {undated > 0 &&
            `${undated} without a usable date excluded.`}
        </p>
      )}
      {showAllLanes && hiddenVendors === 0 && lanes.length > DEFAULT_LANES && (
        <button onClick={() => setShowAllLanes(false)}
                className="text-xs text-slate-400 hover:text-slate-600 underline mt-2 dark:text-gray-500 dark:hover:text-gray-300">
          Show fewer
        </button>
      )}
    </div>
  );
}

export function MarketMonitorTab() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [markets, setMarkets] = useState<Market[] | null>(null);
  const [marketId, setMarketId] = useState<number | null>(null);
  const [view, setView] = useState<View>('findings');
  const [collectionSubView, setCollectionSubView] = useState<CollectionSubView>('overview');
  /** Jump straight to a Collection sub-view — used by Findings panels that
   *  link out to the raw articles or events behind a figure. */
  function openCollection(sub: CollectionSubView) {
    setView('collection');
    setCollectionSubView(sub);
  }
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
  const [collectionState, setCollectionState] =
    useState<CollectionStateResponse | null>(null);
  /** Which records the reader asked to see. One at a time: a stack of open
   *  drill-downs makes it unclear which figure the rows belong to.
   *
   *  Named `records` rather than `drill` because `drill` is already the vendor
   *  drill-down below, which lists vendors behind an overview figure. This one
   *  lists the underlying posts, articles, listings and funding rows. */
  const [records, setRecords] = useState<DrilldownSpec | null>(null);
  const [runs, setRuns] = useState<CollectionRun[] | null>(null);
  const [plan, setPlan] = useState<CollectionPlan | null>(null);

  const [search, setSearch] = useState('');
  const [fundingFilter, setFundingFilter] = useState<string>('');
  const [foundedFilter, setFoundedFilter] = useState<string>('');
  const [addVendorOpen, setAddVendorOpen] = useState(false);
  const [newVendorName, setNewVendorName] = useState('');
  const [newVendorWebsite, setNewVendorWebsite] = useState('');
  const [addingVendor, setAddingVendor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toggleResult, setToggleResult] = useState<string | null>(null);
  const [showKeywords, setShowKeywords] = useState(false);
  const [vendorMode, setVendorMode] =
    useState<'none' | 'funded' | 'all'>('funded');
  const [termsDraft, setTermsDraft] = useState<string>('');
  const [scopeDraft, setScopeDraft] = useState('');
  const [inclusionDraft, setInclusionDraft] = useState('');
  const [exclusionDraft, setExclusionDraft] = useState('');
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null);
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [pulse, setPulse] = useState<MarketPulse | null>(null);
  const [topArticles, setTopArticles] = useState<WireArticle[] | null>(null);
  /** Shared reporting window for Pulse, Coverage's Leaderboards, and every
   *  period-aware Analysis panel (signal/noise, hiring, share of voice, top
   *  voices, channel mix). Formation and funding describe the market's
   *  current state and never respond to this — see market_analysis.run. */
  const [periodDays, setPeriodDays] = useState(30);

  /** Which channel the activity leaderboard is ranked by. 'index' is the
   *  blended Activity Index; the others rank on one channel's raw count, which
   *  is only honest because the table shows that count in its own column. */
  const [activityRank, setActivityRank] =
    useState<'index' | 'posts' | 'jobs' | 'earned'>('index');
  const [activityShowAll, setActivityShowAll] = useState(false);
  const [headcountTrend, setHeadcountTrend] =
    useState<MarketHeadcountTrend | null>(null);
  const [fundingMomentum, setFundingMomentum] =
    useState<FundingAnalysis | null>(null);
  // A trend line needs at least two real points — one point means the window
  // is too new, not that anything is wrong. Same threshold the panels below
  // already used; this just lets both panels and the shared "not enough
  // data yet" strip agree on what "thin" means without duplicating it.
  const headcountConfidence = useMemo(() => {
    const withData = headcountTrend?.points
      ?.filter(p => p.avg_pct_vs_baseline !== null) ?? [];
    return { ok: withData.length > 1, withData };
  }, [headcountTrend]);
  const momentumConfidence = useMemo(() => {
    const withData = fundingMomentum?.by_month
      ?.filter(m => m.avg_heat_score !== null) ?? [];
    return { ok: withData.length > 1, withData };
  }, [fundingMomentum]);
  const pulseThinPanels: ThinPanel[] = useMemo(() => {
    const out: ThinPanel[] = [];
    if (!headcountConfidence.ok) {
      const total = headcountTrend?.points.length ?? 0;
      out.push({
        id: 'headcount-trend',
        title: 'Headcount, market-wide',
        why: "Average % change against each vendor's own baseline, by week.",
        need: total ? `${headcountConfidence.withData.length} of ${total} weeks read`
                     : 'loading, or no readings yet',
      });
    }
    if (!momentumConfidence.ok) {
      const total = fundingMomentum?.by_month.length ?? 0;
      out.push({
        id: 'momentum-trend',
        title: 'Overall market momentum, by month',
        why: 'Attention and predicted growth across the whole market, month by month.',
        need: total ? `${momentumConfidence.withData.length} of ${total} months`
                     : 'loading, or no readings yet',
      });
    }
    return out;
  }, [headcountConfidence, momentumConfidence, headcountTrend, fundingMomentum]);
  const [sources, setSources] = useState<SourceSetting[] | null>(null);
  const [minInterval, setMinInterval] = useState(6);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [corpus, setCorpus] = useState<CorpusSummary | null>(null);
  const [corpusArticles, setCorpusArticles] =
    useState<CorpusArticle[] | null>(null);
  const [leaderboards, setLeaderboards] = useState<Leaderboards | null>(null);
  const [corpusOrigin, setCorpusOrigin] = useState<'' | 'corpus' | 'collected'>('');
  const [corpusClass, setCorpusClass] = useState<'' | ArticleClass>('');
  const [allPosts, setAllPosts] = useState(false);
  const [vendorFilter, setVendorFilter] = useState<number | null>(null);
  const [coverageLimit, setCoverageLimit] = useState(COVERAGE_START);
  const [coverageMore, setCoverageMore] = useState(false);
  const [groupMode, setGroupMode] = useState<GroupMode>('day');
  const [sortMode, setSortMode] = useState<'newest' | 'popular'>('newest');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [openCluster, setOpenCluster] = useState<string | null>(null);
  const [inventory, setInventory] = useState<DatasetInfo[] | null>(null);
  const [openDataset, setOpenDataset] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] =
    useState<{ total: number; rows: Record<string, any>[] } | null>(null);
  const [scanResult, setScanResult] = useState<string | null>(null);
  // A drilldown is URL-addressable so it can be sent to somebody, the same way
  // ?vendor= already works.
  const [drill, setDrill] = useState<string | null>(null);
  const [drillRows, setDrillRows] = useState<DrilldownVendor[] | null>(null);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [fixing, setFixing] = useState<
    { id: number; value: string; source: string } | null>(null);

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
      getCollectionState(marketId),
      getCollectionPlan(marketId, vendorMode), getPulse(marketId, periodDays),
      getSources(marketId), getOverview(marketId, periodDays),
      getCorpusSummary(marketId, periodDays),
    ]).then(([v, f, t, h, r, colState, p, b, s, o, cs]) => {
      setCollectionState(colState);
      setPulse(b); setSources(s.sources); setMinInterval(s.min_interval_hours);
      setOverview(o); setCorpus(cs);
      setVendors(v); setFacets(f); setTasks(t); setHealth(h); setRuns(r); setPlan(p);
      setTermsDraft(p.market_terms.join('\n'));
      // Timeline is fetched after the plan because it is keyed on the market's
      // collection topic. Always resolve to an array: leaving `events` null
      // renders the Wire as a spinner that never stops.
      const topic = p.topic_name;
      if (!topic) { setEvents([]); return; }
      getMarketTimeline(topic, 50, periodDays)
        .then(res => setEvents(res.events))
        .catch(() => setEvents([]));
    }).catch(e => { setError(String(e.message ?? e)); setEvents([]); });
  }, [marketId, vendorMode, periodDays]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const uris = pulse?.top_article_uris;
    if (!uris || uris.length === 0) { setTopArticles(uris ? [] : null); return; }
    let live = true;
    getWireArticles(uris)
      .then(a => { if (live) setTopArticles(a); })
      .catch(() => { if (live) setTopArticles([]); });
    return () => { live = false; };
  }, [pulse?.top_article_uris]);

  // The drafts start blank; fill them from the loaded market the moment the
  // Scope panel opens, so editing shows what's actually saved rather than
  // an empty form that looks like nothing has ever been set.
  useEffect(() => {
    if (settingsOpen !== 'scope' || marketId === null || !markets) return;
    const m = markets.find(x => x.id === marketId);
    if (!m) return;
    setScopeDraft(m.market_scope_description ?? '');
    setInclusionDraft(m.inclusion_criteria ?? '');
    setExclusionDraft(m.exclusion_criteria ?? '');
  }, [settingsOpen, marketId, markets]);

  const shown = useMemo(() => {
    if (!vendors) return [];
    const q = search.trim().toLowerCase();
    return vendors.filter(v => {
      if (q && !v.display_name.toLowerCase().includes(q)) return false;
      if (fundingFilter &&
          v.baseline?.funding_baseline?.status !== fundingFilter) return false;
      if (foundedFilter &&
          String(v.baseline?.founded_year ?? '') !== foundedFilter) return false;
      return true;
    });
  }, [vendors, search, fundingFilter, foundedFilter]);

  // The Coverage view is the only consumer of the matched corpus, so it loads
  // on demand rather than on every market switch.
  const inCollectionCoverage = view === 'collection' && collectionSubView === 'coverage';
  useEffect(() => {
    if (marketId === null || !inCollectionCoverage) return;
    let live = true;
    // Clustering runs regardless of how the result is grouped on screen — a
    // story badge is useful whether you're browsing by vendor, by day or on
    // the timeline, not just in one dedicated mode.
    Promise.all([
      getCorpusSummary(marketId, periodDays),
      getCorpusArticles(marketId, {
        limit: coverageLimit, offset: 0,
        origin: corpusOrigin || undefined,
        classes: corpusClass || undefined,
        allPosts, group: true,
        vendorId: vendorFilter ?? undefined }),
    ]).then(([sum, list]) => {
      if (!live) return;
      setCorpus(sum); setCorpusArticles(list.articles);
      setCoverageMore(list.has_more);
    }).catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, inCollectionCoverage, corpusOrigin, corpusClass, allPosts, vendorFilter,
      coverageLimit, periodDays]);

  // Any filter change starts the window over; a widened window from a
  // previous filter has no bearing on the next one.
  useEffect(() => { setCoverageLimit(COVERAGE_START); setExpandedGroups(new Set()); },
           [corpusOrigin, corpusClass, allPosts, vendorFilter, groupMode]);

  // Independent of the corpus-list TYPE filters above (origin/class/etc) —
  // those don't apply to a ranking. It does follow the shared period,
  // same as Pulse.
  useEffect(() => {
    if (marketId === null || !inCollectionCoverage) return;
    let live = true;
    getLeaderboards(marketId, periodDays)
      .then(r => { if (live) setLeaderboards(r); })
      .catch(() => { if (live) setLeaderboards(null); });
    return () => { live = false; };
  }, [marketId, inCollectionCoverage, periodDays]);

  useEffect(() => {
    if (marketId === null || !drill) { setDrillRows(null); return; }
    let live = true;
    setDrillRows(null);
    getDrilldown(marketId, drill)
      .then(r => { if (live) setDrillRows(r.vendors); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, drill]);

  const inCollectionData = view === 'collection' && collectionSubView === 'data';
  useEffect(() => {
    if (marketId === null || !inCollectionData) return;
    let live = true;
    getDataInventory(marketId)
      .then(r => { if (live) setInventory(r.datasets); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, inCollectionData]);

  // Headcount trend and funding momentum are their own fetches — the
  // as-of join behind headcount-trend is O(vendors x weeks), and funding
  // momentum piggybacks on the wider /analysis/funding call — neither
  // belongs in the fast path every market switch already pays for. Coverage
  // also wants funding momentum, for its "featured" funding-moves list, so
  // it shares this fetch rather than triggering a second one.
  useEffect(() => {
    if (marketId === null || (view !== 'findings' && !inCollectionCoverage)) return;
    let live = true;
    if (view === 'findings') {
      getHeadcountTrend(marketId, 26)
        .then(r => { if (live) setHeadcountTrend(r); })
        .catch(e => { if (live) setError(String(e.message ?? e)); });
    }
    getAnalyses(marketId)
      .then(r => { if (live) setFundingMomentum(r.funding ?? null); })
      .catch(() => { /* Still renders without the momentum panel. */ });
    return () => { live = false; };
  }, [marketId, view, inCollectionCoverage]);

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
        getCorpusSummary(marketId, periodDays),
        getCorpusArticles(marketId, { limit: 100,
                                      origin: corpusOrigin || undefined,
                                      classes: corpusClass || undefined,
                                      allPosts,
                                      vendorId: vendorFilter ?? undefined }),
      ]);
      setCorpus(sum); setCorpusArticles(list.articles);
    } catch (e: any) {
      setScanResult(`Post review failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function makeShareLink() {
    if (marketId === null) return;
    setBusy(true);
    try {
      const r = await getReportLink(marketId, periodDays);
      setShareLink(r.url);
      await navigator.clipboard?.writeText(r.url).catch(() => {});
      setToggleResult(
        `Report link copied. It opens without a login and expires in ${r.ttl_days} days.`);
    } catch (e: any) {
      setToggleResult(`Could not create a link: ${e.message ?? e}`);
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
        getCorpusSummary(marketId, periodDays),
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
                                   dryRun: boolean,
                                   field: VendorSwitch = 'collection') {
    if (marketId === null) return;
    setBusy(true); setToggleResult(null);
    try {
      const res = await setVendorCollection(marketId, enabled, filter, dryRun,
                                            field);
      const what = field === 'collection' ? 'collection' : 'brand monitoring';
      setToggleResult(
        dryRun
          ? `${res.matched} vendors match; ${res.would_change ?? 0} would change.`
          : `${res.changed ?? 0} vendors updated (${what}).` +
            (res.keywords_rewritten
              ? ` ${res.keywords_rewritten} keyword list${
                  res.keywords_rewritten === 1 ? '' : 's'} rewritten to avoid ` +
                'matching ordinary words.'
              : ''));
      if (!dryRun) reload();
    } catch (e: any) {
      setToggleResult(`Failed: ${e.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function addVendorNow() {
    if (marketId === null || !newVendorName.trim()) return;
    setAddingVendor(true); setToggleResult(null);
    try {
      const r = await addVendor(marketId, newVendorName.trim(),
                                newVendorWebsite.trim() || undefined);
      setToggleResult(`${r.display_name} added and watched.`);
      setNewVendorName(''); setNewVendorWebsite(''); setAddVendorOpen(false);
      reload();
    } catch (e: any) {
      setToggleResult(`Could not add that vendor: ${e.message ?? e}`);
    } finally {
      setAddingVendor(false);
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

  async function saveScope() {
    if (marketId === null) return;
    setBusy(true);
    try {
      await updateMarket(marketId, {
        market_scope_description: scopeDraft,
        inclusion_criteria: inclusionDraft,
        exclusion_criteria: exclusionDraft,
      });
      setToggleResult('Market scope saved.');
      setMarkets(await getMarkets());
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
      <div className="p-6 text-red-600 flex items-start gap-2 dark:text-red-400">
        <AlertTriangle className="w-5 h-5 mt-0.5" />
        <div>{error}</div>
      </div>
    );
  }
  if (!markets) {
    return <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-slate-400 dark:text-gray-500" /></div>;
  }
  if (!markets.length) {
    return (
      <div className="p-8 text-center text-slate-600 dark:text-gray-400">
        <LineChart className="w-10 h-10 mx-auto mb-3 text-slate-400 dark:text-gray-500" />
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
                        onBack={closeVendorPage}
                        linkedinEnabled={health?.providers.brightdata_linkedin_enabled ?? false} />
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <LineChart className="w-5 h-5 text-slate-700 dark:text-gray-300" />
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
            <p className="text-sm text-slate-600 mt-1 max-w-3xl dark:text-gray-400">{market.question}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={reload}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          {/* Collection terms, source schedules, and source health. */}
          <button onClick={() => setSettingsOpen('collection')}
            title="Collection, sources and health"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
            <Settings className="w-4 h-4" /> Settings
          </button>
        </div>
      </div>

      {/* Collection state — the thing that decides whether anything arrives.
          Kept visible regardless of mode: a reader looking at Findings should
          still see immediately why there's nothing to find. */}
      {!collectionLive && (
        <div className="border border-amber-200 bg-amber-50 rounded-lg p-3 text-sm text-amber-800 flex items-start gap-2 dark:border-amber-800 dark:bg-amber-900/20">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <span className="font-medium">No collection configured.</span> This
            market has no keyword group, so no articles are being gathered. Set
            the search terms in Settings → Collection.
          </div>
        </div>
      )}

      {/* Mode switch. Vendors is a registry/detail page, not a market-vs-
          pipeline question, so it sits as a peer rather than inside either
          mode. */}
      <div className="flex items-center justify-between border-b">
        <div className="flex gap-1">
          {([
            ['findings', 'Findings'],
            ['collection', 'Collection'],
            ['briefings', 'Reports'],
            ['vendors', `Vendors${market?.vendors ? ` (${market.vendors})` : ''}`],
          ] as [View, string][]).map(([id, label]) => (
            <button key={id} onClick={() => setView(id)}
              className={`px-3 py-2 text-sm border-b-2 -mb-px ${
                view === id ? 'border-slate-800 font-medium text-slate-900 dark:text-gray-100'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-gray-400 dark:hover:text-gray-300'}`}>
              {label}
            </button>
          ))}
        </div>
        {(view === 'findings'
          || (view === 'collection' && (collectionSubView === 'coverage' || collectionSubView === 'wire'))
         ) && (
          <div className="flex items-center gap-1.5 pb-1.5 pr-1"
               title="Shared by Findings and Collection's Coverage and Wire sub-views. Founding years and current funding/stage data are always all-time, regardless of this setting.">
            <span className="text-xs text-slate-500 dark:text-gray-400">Period</span>
            <select value={periodDays}
                    onChange={e => setPeriodDays(Number(e.target.value))}
                    className="text-sm border rounded-md px-2 py-1 bg-white hover:bg-slate-50 dark:bg-gray-800 dark:hover:bg-gray-700">
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last 365 days</option>
            </select>
          </div>
        )}
      </div>

      {toggleResult && (
        <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-300">
          {toggleResult}
        </div>
      )}

      {/* ---- Drilldown: the vendors behind a number ---- */}
      {drill && (
        <div className="border rounded-lg bg-white dark:bg-gray-800">
          <div className="flex items-center gap-2 p-3 border-b">
            <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
              {DRILL_LABEL[drill] ?? drill}
            </span>
            <span className="text-sm text-slate-500 dark:text-gray-400">
              {drillRows ? `${drillRows.length} vendors` : ''}
            </span>
            <div className="flex-1" />
            <button onClick={closeDrilldown}
                    className="text-slate-400 hover:text-slate-700 dark:text-gray-500 dark:hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          </div>
          {drillRows === null ? (
            <div className="py-10 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : drillRows.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
              No vendors match.
            </p>
          ) : (
            <div className="p-3">
              <DataTable
                rows={drillRows} dense rowKey={v => v.brand_id}
                initialSort="vendor"
                onRowClick={v => openVendorPage(v.brand_id)}
                columns={[
                  { key: 'vendor', label: 'Vendor' },
                  { key: 'country', label: 'Country', groupable: true },
                  { key: 'founded', label: 'Founded', groupable: true },
                  { key: 'funding_status', label: 'Funding', groupable: true,
                    render: v => v.musd !== null ? `$${v.musd}M`
                                                 : (v.funding_status ?? '—') },
                  { key: 'staff', label: 'Staff', align: 'right' },
                  // Both counts are all-time, unlike the pulse strip above
                  // this table, which is scoped to period_days. Two windows on
                  // one screen with nothing saying so read as one window.
                  { key: 'announcements', label: 'Announced (all time)',
                    align: 'right' },
                  // No longer qualified as LinkedIn-only: listings now come
                  // from each company's own hiring system too, which is where
                  // most of them actually are. Dropzone AI read 0 here and had
                  // 11 on its own Greenhouse board.
                  //
                  // Zero is printed rather than dashed. Both collectors ran, so
                  // this is a measured zero; a dash would claim we had not
                  // looked. What a zero still cannot rule out is a company that
                  // publishes no structured listings anywhere, which the
                  // tooltip says.
                  { key: 'openings', label: 'Open roles',
                    align: 'right',
                    render: v => v.openings
                      ? <button
                          onClick={e => { e.stopPropagation();
                                          setRecords({
                                            kind: 'jobs',
                                            title: `${v.vendor}: job listings`,
                                            vendorId: v.brand_id,
                                            expectedTotal: v.openings,
                                          }); }}
                          className="text-sky-700 dark:text-sky-400 hover:underline
                                     tabular-nums">
                          {v.openings}
                        </button>
                      : <span className="tabular-nums text-slate-500 dark:text-gray-400"
                              title="None found on LinkedIn or on this company's own hiring system. A company that publishes no structured listings anywhere would also read as zero.">
                          0
                        </span> },
                ]} />
            </div>
          )}
        </div>
      )}

      {/* ---- Pulse: the one-look state of the market ---- */}
      {view === 'findings' && overview && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600 dark:text-gray-400">
              {pulse
                ? `Last ${pulse.period_days} days · ${pulse.coverage.watching} of ${pulse.coverage.vendors} vendors monitored`
                : `${overview.coverage.watching} of ${overview.coverage.vendors} vendors monitored`}
            </span>
            <div className="flex-1" />
            <a href={datasetCsvUrl(marketId!)}
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              Download dataset (CSV)
            </a>
            <a href={feedUrl(marketId!)} target="_blank" rel="noreferrer"
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              RSS feed
            </a>
            <a href={reportUrl(marketId!, periodDays)} target="_blank" rel="noreferrer"
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              Report (HTML)
            </a>
            <a href={exportBundleUrl(marketId!)}
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              Download everything (ZIP)
            </a>
            <button onClick={makeShareLink} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-gray-700">
              Share link
            </button>
          </div>
          {shareLink && (
            <p className="text-xs text-slate-600 -mt-2 break-all dark:text-gray-400">
              <span className="text-slate-500 dark:text-gray-400">Shareable report link: </span>
              {shareLink}
            </p>
          )}

          {pulse?.standing_summary && (
            <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
              <div className="text-sm font-medium text-slate-800 mb-1 dark:text-gray-100">
                Summary
              </div>
              <p className="text-sm text-slate-700 whitespace-pre-line dark:text-gray-300">
                {pulse.standing_summary}
              </p>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Stat label="Vendors watched"
                  value={`${overview.coverage.watching} of ${overview.coverage.vendors}`}
                  hint={`${overview.coverage.paused} paused · ${
                    overview.coverage.observed} observed at least once`}
                  onClick={() => openDrilldown('watched')} />
            <Stat label="Cumulative disclosed funding"
                  value={overview.funding.total_musd === null ? '—'
                    : overview.funding.total_musd >= 1000
                      ? `$${(overview.funding.total_musd / 1000).toFixed(3)}B`
                      : `$${overview.funding.total_musd.toFixed(0)}M`}
                  hint={`Across ${overview.funding.disclosed} of ${
                    overview.funding.disclosed + overview.funding.undisclosed} vendors`}
                  onClick={() => openDrilldown('disclosed')} />
            <Stat label="Coverage matched this period"
                  value={String(overview.corpus?.total ?? 0)}
                  hint={`${overview.corpus?.corpus ?? 0} of those were originally collected for other topics`}
                  onClick={() => openCollection('coverage')} />
            <Stat label="No observed activity"
                  value={String(overview.quiet_vendors)}
                  hint="No vendor posts, open roles or matched coverage were
                        observed from monitored sources during this period"
                  onClick={() => openDrilldown('quiet')} />
            {(() => {
              const trend = corpus?.sentiment_trend ?? [];
              const latest = [...trend].reverse().find(w => w.net_all !== null);
              const tone = !latest ? 'neutral'
                : latest.net_all! > 0 ? 'positive'
                : latest.net_all! < 0 ? 'negative' : 'neutral';
              return (
                <Stat label="Sentiment, latest week"
                      value={latest ? `${latest.net_all! > 0 ? '+' : ''}${latest.net_all}%` : '—'}
                      tone={tone}
                      hint="Net positive minus negative share of classified
                            coverage — not an average, and not shown for a
                            week with too little classified coverage to call
                            a direction."
                      onClick={() => openCollection('coverage')} />
              );
            })()}
          </div>

          {(() => {
            const all = overview.most_active ?? [];
            const scored = all.filter(v => v.activity_index !== null);
            const withheld = all.length - scored.length;
            // Ranking on the index can only order the vendors that have one.
            // Ranking on a raw channel can order every vendor, because the
            // count itself was measured even when a sibling channel was not.
            const pool = activityRank === 'index' ? scored : all;
            const key = activityRank === 'index' ? 'activity_index' : activityRank;
            const ranked = [...pool].sort((a, b) =>
              ((b as any)[key] ?? -1) - ((a as any)[key] ?? -1)
              || (b.earned ?? 0) - (a.earned ?? 0)
              || (a.vendor || '').localeCompare(b.vendor || ''));
            const rows = activityShowAll ? ranked : ranked.slice(0, 10);
            return (
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                    Most active vendors
                  </div>
                  <select value={activityRank}
                          onChange={e => setActivityRank(e.target.value as any)}
                          className="text-xs border rounded-md px-2 py-1 bg-white hover:bg-slate-50 dark:bg-gray-800 dark:hover:bg-gray-700">
                    <option value="index">Rank by overall activity</option>
                    <option value="posts">Rank by owned posts</option>
                    <option value="jobs">Rank by observed jobs</option>
                    <option value="earned">Rank by earned mentions</option>
                  </select>
                </div>
                <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                  The Activity Index scores three channels over the last{' '}
                  {overview.period_days} days — posts the vendor published
                  itself, job listings observed open, and coverage published
                  by somebody other than the vendor. Each is converted to a
                  percentile
                  against the vendors measured on all three, then averaged with
                  equal weight, so a vendor with dozens of open roles cannot
                  outrank one on job count alone. It measures activity, not
                  performance. Click a row to open that vendor's page.
                </p>
                <div className="max-h-[420px] overflow-y-auto">
                  <DataTable
                    rows={rows} rowKey={v => v.brand_id}
                    onRowClick={v => openVendorPage(v.brand_id)}
                    columns={[
                      { key: 'vendor', label: 'Vendor' },
                      { key: 'activity_index', label: 'Activity Index',
                        align: 'right',
                        render: v => v.activity_index === null ? (
                          <span className="text-slate-400 dark:text-gray-500"
                                title={v.index_unavailable_because ?? undefined}>
                            Partial
                          </span>
                        ) : <span>{v.activity_index}</span> },
                      { key: 'posts', label: 'Owned posts', align: 'right' },
                      { key: 'jobs', label: 'Observed jobs', align: 'right' },
                      { key: 'earned', label: 'Earned mentions', align: 'right' },
                    ]} />
                </div>
                <div className="flex items-center justify-between gap-2 mt-2 flex-wrap">
                  <p className="text-xs text-slate-500 dark:text-gray-400">
                    {withheld > 0
                      ? `${withheld} of ${all.length} vendors are shown as
                         Partial: at least one channel was not measured for
                         them this period, so an index would rank them on
                         evidence we do not have.`
                      : `All ${all.length} vendors were measured on all three
                         channels this period.`}
                  </p>
                  {ranked.length > 10 && (
                    <button onClick={() => setActivityShowAll(v => !v)}
                            className="text-xs text-blue-600 hover:underline dark:text-blue-400">
                      {activityShowAll ? 'Show top 10'
                        : `Show all ${ranked.length}`}
                    </button>
                  )}
                </div>
              </div>
            );
          })()}

          <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">Sentiment</div>
            {(() => {
              const latestAll = [...(corpus?.sentiment_trend ?? [])]
                .reverse().find(w => w.net_all !== null);
              if (!latestAll) return null;
              const net = latestAll.net_all!;
              const tone = net > 10 ? 'positive' : net < -10 ? 'negative' : 'neutral';
              const reading = tone === 'positive' ? 'leaned positive'
                : tone === 'negative' ? 'leaned negative' : 'was mixed';
              return (
                <p className="text-sm text-slate-700 mt-0.5 flex items-center gap-1.5 dark:text-gray-300">
                  <span className={`inline-block w-2 h-2 rounded-full ${STAT_TONE[tone].dot}`} />
                  Coverage in the latest week {reading}.
                </p>
              );
            })()}
            <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
              Weekly net-sentiment index (positive minus negative share of
              classified coverage). A week is left blank rather than plotted
              at zero when too few articles were classified that week to call
              a direction — a blank week is a low-confidence week, not a
              neutral one.
            </p>
            {!corpus?.sentiment_trend?.some(w => w.net_all !== null) ? (
              <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                Not enough classified coverage yet to chart sentiment.
              </p>
            ) : (() => {
              const trend = corpus.sentiment_trend;
              // Vendor-attributed sentiment needs an article both matched to
              // the market AND attributed to a tracked vendor AND scored —
              // three gates stacked, so it clears the confidence floor far
              // less often than the market-wide line. Below 3 real points a
              // "line" is two stranded dots, which reads as broken rather
              // than as a series that just needs more data.
              const vendorPoints = trend.filter(w => w.net_vendor !== null).length;
              const showVendorLine = vendorPoints >= 3;
              return (
                <>
                <ResponsiveContainer width="100%" height={220}>
                  <RLineChart data={trend}
                             margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={cc(isDark, '#e2e8f0', '#374151')} />
                    <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} unit="%" />
                    {/* A faint background wash, not the lines themselves —
                        the lines already carry series identity (broad vs
                        vendor coverage); recoloring them by value would
                        make color do two jobs at once. This just lets a
                        reader see "good stretch vs bad stretch" before
                        reading a single number. */}
                    <ReferenceArea y1={0} y2="dataMax" fill={cc(isDark, '#30a46c', '#4ade80')} fillOpacity={0.06} />
                    <ReferenceArea y1="dataMin" y2={0} fill={cc(isDark, '#e5484d', '#f87171')} fillOpacity={0.06} />
                    <ReferenceLine y={0} stroke={cc(isDark, '#cbd5e1', '#4b5563')} strokeWidth={1} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="net_broad" name="The market broadly"
                          stroke={cc(isDark, '#0369a1', '#38bdf8')} strokeWidth={2} dot={{ r: 3 }}
                          connectNulls={false} />
                    {showVendorLine && (
                      <Line type="monotone" dataKey="net_vendor"
                            name="Tracked vendors' own coverage"
                            stroke={cc(isDark, '#b45309', '#fbbf24')} strokeWidth={2} dot={{ r: 3 }}
                            connectNulls={false} />
                    )}
                  </RLineChart>
                </ResponsiveContainer>
                {!showVendorLine && (
                  <p className="text-xs text-slate-400 -mt-1 dark:text-gray-500">
                    Vendor-attributed sentiment isn&apos;t shown: only{' '}
                    {vendorPoints} week{vendorPoints === 1 ? '' : 's'} of
                    tracked-vendor coverage cleared the confidence floor, too
                    few to read as a line.
                  </p>
                )}
                </>
              );
            })()}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Signed delta so decreases are distinguishable from increases.
                Spans both columns when the market-wide trend beside it has
                collapsed into the "not enough data" strip below, so a thin
                sibling doesn't leave an empty grid cell. */}
            <div className={`border rounded-lg p-4 bg-white dark:bg-gray-800 ${
                              headcountConfidence.ok ? '' : 'lg:col-span-2'}`}>
              <MetricHeading title="Headcount change"
                             meta={pulse?.headcount_metric} />
              {/* This panel used to compare the latest LinkedIn reading against
                  the April workbook import and call the difference growth. Two
                  different measurements, four months apart, so nearly every
                  vendor looked like a mover. Movement now needs two LinkedIn
                  readings, which most vendors do not have yet — the first full
                  sweep was 2026-08-26 — so the list is short on purpose and
                  fills as the next sweep lands. */}
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Two LinkedIn readings of the same vendor, each with its own date.
                Vendors with only one reading are listed below as awaiting a
                second rather than shown as unchanged.
              </p>
              {pulse && (
                <div className="text-sm mb-3">
                  <span className="text-slate-500 dark:text-gray-400">
                    Observed market headcount{' '}
                  </span>
                  <span className="font-medium tabular-nums text-slate-800 dark:text-gray-100">
                    {pulse.observed_market_headcount.toLocaleString()}
                  </span>
                  <span className="text-slate-400 dark:text-gray-500">
                    {' '}across {pulse.headcount_cohort} vendor
                    {pulse.headcount_cohort === 1 ? '' : 's'} with a current
                    exact reading
                  </span>
                </div>
              )}
              {pulse && pulse.headcount_n > 0 && (
                <div className="flex gap-4 text-sm mb-3">
                  <span>
                    <span className="text-slate-500 dark:text-gray-400">Average </span>
                    <span className={`font-medium tabular-nums ${deltaTextClass(pulse.headcount_avg_pct)}`}>
                      {pulse.headcount_avg_pct !== null
                        ? `${pulse.headcount_avg_pct > 0 ? '+' : ''}${pulse.headcount_avg_pct}%`
                        : '—'}
                    </span>
                  </span>
                  <span>
                    <span className="text-slate-500 dark:text-gray-400">Median </span>
                    <span className={`font-medium tabular-nums ${deltaTextClass(pulse.headcount_median_pct)}`}>
                      {pulse.headcount_median_pct !== null
                        ? `${pulse.headcount_median_pct > 0 ? '+' : ''}${pulse.headcount_median_pct}%`
                        : '—'}
                    </span>
                  </span>
                  <span className="text-slate-400 dark:text-gray-500">
                    across {pulse.headcount_n} vendor{pulse.headcount_n === 1 ? '' : 's'}
                  </span>
                </div>
              )}
              {/* Why the average row above is absent. A withheld figure that
                  simply disappears reads as a rendering fault; this says it was
                  withheld and what would bring it back. */}
              {pulse && pulse.headcount_n === 0
                    && pulse.headcount_movers.length > 0 && (
                <p className="text-xs text-slate-500 mb-2 dark:text-gray-400">
                  No market average yet: it needs several vendors with two
                  readings, and {pulse.headcount_movers.length === 1
                    ? 'only one has' : `only ${pulse.headcount_movers.length} have`}
                  {' '}a second one so far. An average across one vendor is that
                  vendor&apos;s number, not the market&apos;s.
                </p>
              )}
              {!pulse || pulse.headcount_movers.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                  No vendor has two LinkedIn readings yet
                  {pulse ? `, so movement cannot be measured for any of the
                            ${pulse.headcount_insufficient} awaiting a second one`
                         : ''}.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={pulse.headcount_movers.slice(0, 8)}
                            layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" fontSize={11} />
                    <YAxis type="category" dataKey="vendor" width={110}
                           fontSize={11} interval={0} />
                    <Tooltip formatter={(v: number, _n, p: any) =>
                      [`${v > 0 ? '+' : ''}${v} staff (${p.payload.pct}%)`, 'change']} />
                    <Bar dataKey="delta" radius={[0, 3, 3, 0]} cursor="pointer"
                         onClick={(d: any) => {
                           const hit = vendors?.find(v => v.display_name === d?.vendor);
                           if (hit) openVendorPage(hit.brand_id);
                         }}>
                      {pulse.headcount_movers.slice(0, 8).map((m, i) => (
                        <Cell key={i} fill={m.delta >= 0 ? cc(isDark, '#30a46c', '#4ade80') : cc(isDark, '#e5484d', '#f87171')} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {headcountConfidence.ok && (
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  Headcount, market-wide
                </div>
                <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                  Average % change against each vendor&apos;s own baseline, as
                  of each week — not a sum of headcounts, which would read as
                  growth purely from more vendors gaining a first reading.
                </p>
                <ResponsiveContainer width="100%" height={200}>
                  <RLineChart data={headcountTrend!.points}
                             margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={cc(isDark, '#e2e8f0', '#374151')} />
                    <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip formatter={(v: number, _n, p: any) =>
                      [`${v}% (${p.payload.n_vendors} of ${headcountTrend!.watching} watched vendors read)`, 'avg vs baseline']} />
                    <Line type="monotone" dataKey="avg_pct_vs_baseline"
                          stroke={cc(isDark, '#475569', '#9ca3af')} strokeWidth={2} dot={{ r: 3 }}
                          connectNulls={false} />
                  </RLineChart>
                </ResponsiveContainer>
                <p className="text-xs text-slate-400 -mt-1 dark:text-gray-500">
                  {headcountConfidence.withData.length} of {headcountTrend!.points.length} weeks
                  since this market started tracking have a reading. Thin
                  weeks (fewer than half of watched vendors read as of that
                  week) are the least trustworthy points on it.
                </p>
              </div>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {momentumConfidence.ok && (
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  Overall market momentum, by month
                </div>
                <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                  How much attention and predicted growth this whole market is
                  getting on average, month by month. Updates slowly on
                  purpose — the underlying data is only checked about once a
                  week.
                </p>
                <ResponsiveContainer width="100%" height={200}>
                  <RLineChart data={fundingMomentum!.by_month}
                             margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={cc(isDark, '#e2e8f0', '#374151')} />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="avg_heat_score" name="Crunchbase Heat"
                          stroke={cc(isDark, '#0369a1', '#38bdf8')} strokeWidth={2} dot={{ r: 3 }}
                          connectNulls={false} />
                    <Line type="monotone" dataKey="avg_growth_score" name="Crunchbase Growth"
                          stroke={cc(isDark, '#b45309', '#fbbf24')} strokeWidth={2} dot={{ r: 3 }}
                          connectNulls={false} />
                  </RLineChart>
                </ResponsiveContainer>
                <p className="text-xs text-slate-400 -mt-1 dark:text-gray-500">
                  {momentumConfidence.withData.length} of {fundingMomentum!.by_month.length}{' '}
                  months since this market started tracking have a
                  Crunchbase reading.
                </p>
              </div>
            )}

            <div className={`border rounded-lg p-4 bg-white dark:bg-gray-800 ${
                              momentumConfidence.ok ? '' : 'lg:col-span-2'}`}>
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                Who's getting more attention or momentum
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Companies whose Crunchbase Growth or Heat score moved since
                the last check. Both are Crunchbase's own scores and we cannot
                reproduce how either is calculated, so treat a move as a change
                in what Crunchbase reports rather than a measured change in the
                company. Only real changes are listed — nothing here means the
                score held steady.
              </p>
              {!fundingMomentum?.momentum_events?.length ? (
                <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                  Nothing has changed since the last check.
                </p>
              ) : (
                <div className="divide-y">
                  {fundingMomentum.momentum_events.slice(0, 8).map((e, i) => (
                    <button key={i} onClick={() => {
                              const hit = vendors?.find(v => v.display_name === e.vendor);
                              if (hit) openVendorPage(hit.brand_id);
                            }}
                            className="w-full flex items-center justify-between
                                       py-1.5 text-sm hover:bg-slate-50 text-left dark:hover:bg-gray-700">
                      <span className="min-w-0">
                        <span className="text-slate-700 dark:text-gray-300">{e.vendor}</span>
                        <div className="text-xs text-slate-400 dark:text-gray-500">
                          {(e.observed_at ?? '').slice(0, 10)}
                          {e.prev_observed_at
                            ? ` (was ${e.prev_observed_at.slice(0, 10)})` : ''}
                        </div>
                      </span>
                      <span className="tabular-nums shrink-0">
                        {e.heat_delta !== null && (
                          <span className={deltaTextClass(e.heat_delta)}
                                title="Source: Crunchbase's Heat score, its 0-100 measure of attention/buzz. This is the change since the last reading, not the score itself.">
                            {fmtScoreDelta('Attention', e.heat_delta)}
                          </span>
                        )}
                        {e.heat_delta !== null && e.growth_delta !== null &&
                          <span className="text-slate-400 dark:text-gray-500"> · </span>}
                        {e.growth_delta !== null && (
                          <span className={deltaTextClass(e.growth_delta)}
                                title="Source: Crunchbase's Growth score, its 0-100 measure of predicted growth. This is the change since the last reading, not the score itself.">
                            {fmtScoreDelta('Growth outlook', e.growth_delta)}
                          </span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <ConfidenceGate panels={pulseThinPanels} />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
              {/* Named for what it is. "Coverage by week" was doing double
                  duty for content volume and for collection completeness, so a
                  low bar could mean either "little was published" or "we
                  collected almost nothing that week" and the chart could not
                  say which. Volume lives here; completeness is the Collection
                  state panel. */}
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                Content observed by week
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Articles matching the market&apos;s phrases, by publication week.
                A bar is how much we observed that week, which is a floor for
                how much was published, not a measure of it.
              </p>
              {!overview.corpus?.by_week?.length ? (
                <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                  Nothing matched yet. Run a scan from the Coverage view.
                </p>
              ) : (
                <>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={overview.corpus.by_week}>
                    {/* Hatch for the bars that are still filling. Without it
                        the newest bar reads as a collapse in coverage when it
                        is really three and a half days of a seven-day week. */}
                    <defs>
                      <pattern id="mm-partial" width="6" height="6"
                               patternUnits="userSpaceOnUse"
                               patternTransform="rotate(45)">
                        <rect width="6" height="6"
                              fill={cc(isDark, '#cbd5e1', '#4b5563')} />
                        <line x1="0" y1="0" x2="0" y2="6" strokeWidth="3"
                              stroke={cc(isDark, '#94a3b8', '#6b7280')} />
                      </pattern>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={cc(isDark, '#e2e8f0', '#374151')} />
                    <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip formatter={(v: any, _n: any, p: any) => [
                      p?.payload?.partial
                        ? `${v} so far — ${p.payload.partial_reason}`
                        : v,
                      'Articles',
                    ]} />
                    {/* Clicking a week opens the articles it counted. A bar
                        that names a number without offering the rows behind it
                        is a dead end. */}
                    {/* The clicked week is passed through as the server's own
                        filter rather than being turned into a date range here,
                        so the list cannot bound the week differently from the
                        bar. */}
                    <Bar dataKey="n" fill={cc(isDark, '#475569', '#9ca3af')} name="Articles"
                         cursor="pointer"
                         onClick={(d: any) => setRecords({
                           kind: 'coverage',
                           title: `Content observed, week of ${d?.week ?? ''}`,
                           week: d?.week, expectedTotal: d?.n,
                         })}>
                      {overview.corpus.by_week.map((w) => (
                        <Cell key={w.week}
                              fill={w.partial ? 'url(#mm-partial)'
                                              : cc(isDark, '#475569', '#9ca3af')} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-xs text-slate-400 text-center -mt-1 dark:text-gray-500">
                  Click a bar to open the articles.
                  {overview.corpus.by_week.some(w => w.partial) && (
                    <> Hatched bars are still filling and will rise.</>
                  )}
                </p>
                </>
              )}
            </div>

            <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  LinkedIn post volume
                </div>
                <button
                  onClick={() => setRecords({
                    kind: 'posts',
                    title: `Vendor posts, last ${periodDays} days`,
                    days: periodDays, ownership: 'owned',
                  })}
                  className="text-xs text-sky-700 dark:text-sky-400 hover:underline">
                  All posts
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Posts published in the selected window. Click a bar for that
                vendor&apos;s posts.
              </p>
              {!pulse || pulse.loudest_vendors.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                  No posts in this window.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={pulse.loudest_vendors.slice(0, 8)}
                            layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" fontSize={11} allowDecimals={false} />
                    <YAxis type="category" dataKey="vendor" width={110}
                           fontSize={11} interval={0} />
                    <Tooltip />
                    {/* Opens the posts, not the vendor page. The bar states a
                        post count, so the records behind it are the posts —
                        sending the reader to a profile instead is the dead end
                        this whole layer exists to remove. */}
                    <Bar dataKey="posts" fill="#d6409f" cursor="pointer"
                         onClick={(d: any) => {
                           const hit = vendors?.find(v => v.display_name === d?.vendor);
                           if (hit) setRecords({
                             kind: 'posts',
                             title: `${hit.display_name}: posts, last ${periodDays} days`,
                             days: periodDays, vendorId: hit.brand_id,
                             ownership: 'owned', expectedTotal: d?.posts,
                           });
                         }} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
            {/* Not "largest raise". These are cumulative totals, and there is
                no round-level amount or date in the data, so naming a single
                raise would be a claim nothing supports. */}
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                Largest disclosed total funding
              </div>
              <button
                onClick={() => setRecords({
                  kind: 'funding',
                  title: 'Funding by vendor',
                })}
                className="text-xs text-sky-700 dark:text-sky-400 hover:underline">
                All vendors
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
              Cumulative total raised, from the imported registry — not a single
              round. Vendors that never disclosed a figure are absent rather
              than shown as zero.
            </p>
            <div className="divide-y max-h-[420px] overflow-y-auto pr-1">
              {overview.top_funded.map(v => (
                <button key={v.brand_id}
                        onClick={() => openVendorPage(v.brand_id)}
                        className="w-full flex items-center justify-between
                                   py-1.5 text-sm hover:bg-slate-50 text-left dark:hover:bg-gray-700">
                  <span className="text-slate-700 dark:text-gray-300">{v.vendor}</span>
                  <span className="text-slate-500 tabular-nums dark:text-gray-400">
                    ${v.musd?.toFixed(1)}M
                    {v.last_round ? ` · ${v.last_round}` : ''}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
            <div className="text-sm font-medium text-slate-800 mb-2 dark:text-gray-100">
              Events
            </div>
            {!pulse || pulse.events.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
                No events in this window.
              </p>
            ) : (
              <ol className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                {pulse.events.map(e => (
                  <WireEventCard key={e.id} event={e} onVendor={openVendorPage} />
                ))}
              </ol>
            )}
          </div>

          <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Top posts, articles &amp; news
            </div>
            <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
              Everything matched to this market in the window, most engaged
              first. Click a vendor badge to open its page.
            </p>
            {!pulse || topArticles === null ? (
              <div className="py-8 text-center text-slate-400 dark:text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin mx-auto" />
              </div>
            ) : topArticles.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
                Nothing matched this market in this window.
              </p>
            ) : (
              <div className="divide-y max-h-[420px] overflow-y-auto pr-1">
                {topArticles.map(a => (
                  <div key={a.uri} className="py-2 text-sm">
                    <a href={a.uri} target="_blank" rel="noreferrer"
                       className="text-slate-800 hover:underline font-medium dark:text-gray-100">
                      {a.title}
                    </a>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span className="text-xs text-slate-400 dark:text-gray-500">
                        {a.news_source ?? 'unknown source'}
                        {a.publication_date ? ` · ${a.publication_date.slice(0, 10)}` : ''}
                      </span>
                      {a.vendors.map(v => (
                        <button key={v.brand_id} onClick={() => openVendorPage(v.brand_id)}
                                className="text-xs px-1.5 py-0.5 rounded border
                                           bg-sky-50 text-sky-700 border-sky-200
                                           hover:bg-sky-100 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                          {v.vendor}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      )}

      {view === 'findings' && marketId !== null && (
        <MarketAnalysisView marketId={marketId} onVendor={openVendorPage}
                            onRecords={setRecords}
                            days={periodDays}
                            onDrill={(kind, value) => {
                              if (kind === 'founded') {
                                setSearch('');
                                setView('vendors');
                                setSegment('all');
                                setFoundedFilter(value);
                              }
                            }} />
      )}

      {/* ---- Collection ---- */}
      {view === 'collection' && (
        <div className="space-y-4">
          <div className="flex gap-1 p-0.5 bg-slate-100 rounded-md w-fit dark:bg-gray-700">
            {([
              ['overview', 'Overview'],
              ['health', 'Sources & Health'],
              ['coverage', 'Coverage'],
              ['wire', 'Wire'],
              ['data', 'Data'],
              ['sourcemap', 'Data Map'],
            ] as [CollectionSubView, string][]).map(([id, label]) => (
              <button key={id} onClick={() => setCollectionSubView(id)}
                className={`text-sm px-3 py-1 rounded ${
                  collectionSubView === id
                    ? 'bg-white shadow-sm text-slate-900 dark:bg-gray-800 dark:text-gray-100'
                    : 'text-slate-600 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-100'}`}>
                {label}
              </button>
            ))}
          </div>

          {collectionSubView === 'overview' && overview && (
            <div className="space-y-4">
              {/* The registry's own count vs. the header's — the two are
                  allowed to differ (this includes excluded vendors, the
                  header doesn't) but the gap should be visible, not silent. */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ['Vendors', market?.vendors ?? 0],
                  ['Collecting', market?.collecting ?? 0],
                  ['Open reviews', tasks?.length ?? 0],
                  ['No LinkedIn', health?.coverage?.without_linkedin ?? 0],
                ].map(([label, value]) => (
                  <div key={String(label)} className="border rounded-lg p-3 bg-white dark:bg-gray-800">
                    <div className="text-2xl font-semibold text-slate-800 dark:text-gray-100">{value}</div>
                    <div className="text-xs text-slate-500 mt-0.5 dark:text-gray-400">{label}</div>
                  </div>
                ))}
              </div>

              <div className="border rounded-lg bg-white overflow-x-auto dark:bg-gray-800">
                <div className="px-3 pt-3 pb-1 text-sm font-medium text-slate-800 dark:text-gray-100">
                  Count reconciliation
                </div>
                <p className="px-3 text-xs text-slate-500 mb-2 dark:text-gray-400">
                  The same market, counted by each surface that reports it.
                </p>
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                      {['Surface', 'Reports', 'Basis'].map(h => (
                        <th key={h} className="text-left font-medium px-3 py-2">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-t">
                      <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">Header / Vendors tab count</td>
                      <td className="px-3 py-1.5 tabular-nums">{overview.coverage.vendors}</td>
                      <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">watching + paused, excludes excluded</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">Registry (all rows)</td>
                      <td className="px-3 py-1.5 tabular-nums">{overview.coverage.registry}</td>
                      <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">every row ever added, including excluded</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">Excluded</td>
                      <td className="px-3 py-1.5 tabular-nums">{overview.coverage.excluded}</td>
                      <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">marked out of scope, kept for un-excluding later</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">Collecting</td>
                      <td className="px-3 py-1.5 tabular-nums">{overview.coverage.watching}</td>
                      <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">collection switched on</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">Observed at least once</td>
                      <td className="px-3 py-1.5 tabular-nums">{overview.coverage.observed}</td>
                      <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">any reading, all time</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                {pulse && pulse.open_questions.length > 0 && (
                  <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                    <div className="text-sm font-medium text-slate-800 mb-2 dark:text-gray-100">
                      Open review tasks
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {pulse.open_questions.map((q, i) => (
                        <span key={i} className={`text-xs px-2 py-1 rounded border ${
                          SEVERITY_TONE[q.severity] ?? SEVERITY_TONE.low}`}>
                          {q.n} {q.kind.replace(/_/g, ' ')} ({q.severity})
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                  <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                    Last run per source
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                    State of the most recent run, not a 30-day history.
                  </p>
                  <div className="divide-y max-h-[320px] overflow-y-auto pr-1">
                    {overview.last_runs.map(r => (
                      <div key={r.source}
                           className="flex items-center justify-between py-1.5 text-sm">
                        <span className="text-slate-700 dark:text-gray-300">{r.source}</span>
                        <span className="flex items-center gap-2">
                          <span className="text-slate-500 tabular-nums dark:text-gray-400">
                            {r.records_received} records
                          </span>
                          <span className={`text-xs px-1.5 py-0.5 rounded border ${
                            r.status === 'succeeded'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800'
                              : r.status === 'partial'
                              ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800'
                              : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'}`}>
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

      {collectionSubView === 'coverage' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-slate-600 max-w-2xl dark:text-gray-400">
              Articles already in the database that match this market&apos;s
              phrases. Brand classification matches vendor names, so an article
              about the category that names no vendor never reaches it. This
              does.
            </p>
            <div className="flex-1" />
            <a href={feedUrl(marketId!)} target="_blank" rel="noreferrer"
               className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
              RSS feed
            </a>
            <button onClick={runCorpusScan} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50
                               inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Search className="w-4 h-4" />}
              Rescan corpus
            </button>
            <button onClick={runPostReview} disabled={busy}
                    className="text-sm px-3 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50
                               inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Play className="w-4 h-4" />}
              Review vendor posts
            </button>
          </div>

          {scanResult && (
            <div className="text-sm px-3 py-2 rounded-md bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-300">
              {scanResult}
            </div>
          )}

          {corpus && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="Matched articles (all time)" value={String(corpus.total)}
                    hint={`Last scan ${corpus.last_scan
                      ? new Date(corpus.last_scan).toLocaleString() : 'never'}`} />
              <Stat label="From other topics (all time)" value={String(corpus.corpus)}
                    hint="Collected for something else, relevant here" />
              <Stat label={`Published in ${corpus.recent_days} days`}
                    value={String(corpus.recent)}
                    hint="By publication date, not collection date — the only one of these three scoped to the period selector above" />
            </div>
          )}

          {leaderboards && (
            <div className="space-y-4">
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                  Most popular, last {periodDays} days
                </div>
                <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                  Ranked by reactions on the post itself — likes, comments and
                  reposts, owned or earned. Only posts a platform reports
                  engagement for are ranked; most news and vendor-blog
                  coverage carries none.
                </p>
                {(() => {
                  const top = leaderboards.networks
                    .flatMap(n => n.top_posts.map(p => ({ ...p, platform: n.platform })))
                    .sort((a, b) => b.engagement - a.engagement)
                    .slice(0, 5);
                  if (top.length === 0) {
                    return (
                      <p className="text-sm text-slate-500 py-4 text-center dark:text-gray-400">
                        No engagement data on any matched post yet.
                      </p>
                    );
                  }
                  return (
                    <div className="divide-y">
                      {top.map(p => (
                        <a key={p.uri} href={p.uri} target="_blank" rel="noreferrer"
                           className="flex items-center gap-2 py-1.5 text-sm
                                      hover:bg-slate-50 -mx-1 px-1 rounded dark:hover:bg-gray-700">
                          <span className={`text-xs px-1.5 py-0.5 rounded border shrink-0 ${
                            p.is_owned ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800'
                                       : 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800'}`}>
                            {p.platform}
                          </span>
                          <span className="text-slate-800 truncate flex-1 dark:text-gray-100">{p.title}</span>
                          <span className="text-slate-500 tabular-nums shrink-0 dark:text-gray-400">
                            {p.engagement} reactions
                          </span>
                        </a>
                      ))}
                    </div>
                  );
                })()}
              </div>

              <p className="text-xs text-slate-500 -mt-1 dark:text-gray-400">
                Career moves and Crunchbase score changes for this market are
                on the{' '}
                <button onClick={() => setView('findings')}
                        className="underline hover:text-slate-700 dark:hover:text-gray-300">
                  Findings tab
                </button>
                {' '}— not repeated here to avoid showing the same two lists twice.
              </p>

              <div>
                <div className="text-sm font-medium text-slate-800 mb-0.5 dark:text-gray-100">
                  By network
                </div>
                <p className="text-xs text-slate-500 mb-2 dark:text-gray-400">
                  &quot;Most discussed&quot; and &quot;most shared&quot; only
                  count posts tagged to a specific vendor. That tagging barely
                  reaches practitioner posts on Twitter, Reddit or Bluesky
                  today — a real gap in the data, not a quiet market. Where a
                  network shows nothing here, that is what it means.
                </p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {leaderboards.networks.map(n => (
                    <div key={n.platform} className="border rounded-lg p-3 bg-white dark:bg-gray-800">
                      <div className="text-sm font-medium text-slate-800 capitalize mb-1.5 dark:text-gray-100">
                        {n.platform}
                      </div>

                      <div className="text-xs text-slate-500 uppercase tracking-wide mb-0.5 dark:text-gray-400">
                        Most discussed
                      </div>
                      {n.most_discussed.length === 0 ? (
                        <p className="text-xs text-slate-400 mb-2 dark:text-gray-500">Not enough tagged posts yet.</p>
                      ) : (
                        <div className="mb-2">
                          {n.most_discussed.map(v => (
                            <button key={v.brand_id}
                                    onClick={() => openVendorPage(v.brand_id)}
                                    className="flex items-center justify-between w-full
                                               text-sm hover:bg-slate-50 rounded px-1 -mx-1 dark:hover:bg-gray-700">
                              <span className="text-slate-700 truncate dark:text-gray-300">{v.vendor}</span>
                              <span className="text-slate-500 tabular-nums shrink-0 dark:text-gray-400">
                                {v.mentions}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}

                      <div className="text-xs text-slate-500 uppercase tracking-wide mb-0.5 dark:text-gray-400">
                        Most shared
                      </div>
                      {n.most_shared.length === 0 ? (
                        <p className="text-xs text-slate-400 mb-2 dark:text-gray-500">Not enough tagged posts yet.</p>
                      ) : (
                        <div className="mb-2">
                          {n.most_shared.map(v => (
                            <button key={v.brand_id}
                                    onClick={() => openVendorPage(v.brand_id)}
                                    className="flex items-center justify-between w-full
                                               text-sm hover:bg-slate-50 rounded px-1 -mx-1 dark:hover:bg-gray-700">
                              <span className="text-slate-700 truncate dark:text-gray-300">{v.vendor}</span>
                              <span className="text-slate-500 tabular-nums shrink-0 dark:text-gray-400">
                                {v.shares}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}

                      <div className="text-xs text-slate-500 uppercase tracking-wide mb-0.5 dark:text-gray-400">
                        Top post
                      </div>
                      {n.top_posts.length === 0 ? (
                        <p className="text-xs text-slate-400 dark:text-gray-500">No engagement data.</p>
                      ) : (
                        <a href={n.top_posts[0].uri} target="_blank" rel="noreferrer"
                           className="text-sm text-slate-700 hover:underline line-clamp-2 dark:text-gray-300">
                          {n.top_posts[0].title}
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {corpus && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="text-sm font-medium text-slate-800 mb-2 dark:text-gray-100">
                  Phrases that matched
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {corpus.top_terms.map(t => (
                    <span key={t.term}
                          className="text-xs px-2 py-0.5 rounded border
                                     bg-slate-50 text-slate-700 dark:bg-gray-700 dark:text-gray-300">
                      {t.term} <span className="text-slate-400 dark:text-gray-500">{t.n}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
                <div className="text-sm font-medium text-slate-800 mb-2 dark:text-gray-100">
                  Sources
                </div>
                <div className="divide-y">
                  {corpus.top_sources.map(t => (
                    <div key={t.source}
                         className="flex justify-between py-1 text-sm">
                      <span className="text-slate-700 dark:text-gray-300">{t.source}</span>
                      <span className="text-slate-500 tabular-nums dark:text-gray-400">{t.n}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {corpus?.signal_kinds && corpus.signal_kinds.length > 0 && (
            <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                What vendors announced
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
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
                  <button key={k.kind} onClick={() => setGroupMode('kind')}
                          title={`Show articles grouped by kind — click to see what was announced under "${k.kind}"`}
                          className="text-xs px-2 py-0.5 rounded border
                                     bg-emerald-50 text-emerald-700 border-emerald-200
                                     hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800">
                    {k.kind} <span className="text-emerald-500">{k.n}</span>
                  </button>
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
                          : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
                {label}
              </button>
            ))}
            <span className="w-3" />
            {([['', 'Any kind'], ['news', 'News'], ['vendor', 'Vendor blogs'],
               ['social', 'Vendor posts'], ['discussion', 'Practitioners'],
               ['research', 'Research']] as const)
              .map(([id, label]) => (
              <button key={id} onClick={() => setCorpusClass(id)}
                      className={`text-sm px-3 py-1 rounded-md border ${
                        corpusClass === id
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
                {label}
                {id && corpus?.by_class
                  ? ` (${corpus.by_class[id as ArticleClass] ?? 0})` : ''}
              </button>
            ))}
            <span className="w-3" />
            <label className="text-sm text-slate-600 inline-flex items-center gap-1.5 dark:text-gray-400">
              <input type="checkbox" checked={allPosts}
                     onChange={e => setAllPosts(e.target.checked)} />
              Include posts judged noise
            </label>
            {vendorFilter !== null && (
              <button onClick={() => setVendorFilter(null)}
                      className="text-sm px-2 py-1 rounded border bg-slate-800
                                 text-white inline-flex items-center gap-1.5">
                {vendors?.find(v => v.brand_id === vendorFilter)?.display_name
                  ?? `vendor ${vendorFilter}`}
                <X className="w-3 h-3" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-sm text-slate-500 mr-1 dark:text-gray-400">Group by</span>
            {([['vendor', 'Vendor'], ['day', 'Day'], ['kind', 'Kind'],
               ['timeline', 'Timeline']] as const).map(([id, label]) => (
              <button key={id} onClick={() => setGroupMode(id)}
                      className={`text-sm px-3 py-1 rounded-md border ${
                        groupMode === id
                          ? 'bg-slate-800 text-white border-slate-800'
                          : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
                {label}
              </button>
            ))}
            {groupMode !== 'timeline' && (
              <>
                <span className="w-3" />
                <span className="text-sm text-slate-500 mr-1 dark:text-gray-400">Sort by</span>
                {([['newest', 'Newest'], ['popular', 'Most reactions']] as const)
                  .map(([id, label]) => (
                  <button key={id} onClick={() => setSortMode(id)}
                          className={`text-sm px-3 py-1 rounded-md border ${
                            sortMode === id
                              ? 'bg-slate-800 text-white border-slate-800'
                              : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
                    {label}
                  </button>
                ))}
              </>
            )}
          </div>

          {corpusArticles === null ? (
            <div className="py-12 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : corpusArticles.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
              Nothing matched. Run a scan, or widen the market&apos;s phrases in
              Settings.
            </p>
          ) : (
            <>
            {(() => {
              // The server already returns newest-first; "popular" is a
              // client-side re-sort of the same loaded set, not a second
              // fetch — reactions aren't a query the corpus scan indexes on,
              // and the loaded window (up to 500) is plenty to rank within.
              const ordered = sortMode === 'popular'
                ? [...corpusArticles].sort((a, b) => engagementOf(b) - engagementOf(a))
                : corpusArticles;
              if (groupMode === 'timeline') {
                return <CoverageTimeline articles={corpusArticles} />;
              }
              const groups = groupMode === 'vendor' ? groupByVendor(ordered)
                : groupMode === 'kind' ? groupByKind(ordered)
                : groupByDay(ordered);
              return (
                <CoverageGrouped
                  groups={groups}
                  expandedGroups={expandedGroups} setExpandedGroups={setExpandedGroups}
                  vendorFilter={vendorFilter} setVendorFilter={setVendorFilter}
                  openCluster={openCluster} setOpenCluster={setOpenCluster} />
              );
            })()}

            {/* A flat fetch of 900 rows is not something anybody reads either
                way, so this widens the window on request instead of paging
                through it — grouped views read as one continuous browse, not
                as pages. */}
            <div className="flex items-center gap-2 pt-1">
              <span className="text-sm text-slate-500 dark:text-gray-400">
                Showing {corpusArticles.length}{coverageMore ? '+' : ''} matched
              </span>
              {coverageMore && coverageLimit < COVERAGE_MAX && (
                <button disabled={busy}
                  onClick={() => setCoverageLimit(
                    l => Math.min(COVERAGE_MAX, l + COVERAGE_STEP))}
                  className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                             disabled:opacity-40 dark:hover:bg-gray-700">
                  Load {Math.min(COVERAGE_STEP, COVERAGE_MAX - coverageLimit)} more
                </button>
              )}
              {coverageMore && coverageLimit >= COVERAGE_MAX && (
                <span className="text-xs text-slate-400 dark:text-gray-500">
                  More than {COVERAGE_MAX} matched — narrow with a filter to see the rest.
                </span>
              )}
            </div>
            </>
          )}
        </div>
      )}

          {collectionSubView === 'health' && health && (
            <div className="space-y-3">
              <CollectionStatePanel state={collectionState} />
              <HealthPanel health={health} runs={runs} />
            </div>
          )}
        </div>
      )}

      {/* ---- Briefings ---- */}
      {view === 'briefings' && marketId !== null && (
        <MarketBriefingsView marketId={marketId} />
      )}

      {/* ---- Data (Collection sub-view) ---- */}
      {view === 'collection' && collectionSubView === 'data' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 max-w-3xl dark:text-gray-400">
            Everything this market has stored. Click a dataset to see its rows;
            the CSV is the whole table, the on-screen preview is the first 200.
          </p>

          {health && health.sources.length > 0 && (
            <div className="border rounded-lg bg-white overflow-hidden dark:bg-gray-800">
              <div className="px-3 pt-3 pb-1 text-sm font-medium text-slate-800 dark:text-gray-100">
                Fetched by source, last 30 days
              </div>
              <p className="px-3 text-xs text-slate-500 mb-2 dark:text-gray-400">
                What each provider returned before dedup, and how much of that
                was new. A source with a high received count and few new
                records is mostly re-fetching what it already sent.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                      {['Source', 'Provider', 'Received', 'New', 'Runs', 'Last success']
                        .map(h => (
                        <th key={h} className="text-left font-medium px-3 py-2">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {health.sources.map(s => (
                      <tr key={`${s.source}:${s.provider}`} className="border-t">
                        <td className="px-3 py-1.5 text-slate-800 dark:text-gray-100">{s.source}</td>
                        <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">{s.provider}</td>
                        <td className="px-3 py-1.5 tabular-nums">
                          {(s.records_received ?? 0).toLocaleString()}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">
                          {(s.records_new ?? 0).toLocaleString()}
                        </td>
                        <td className="px-3 py-1.5 text-slate-500 tabular-nums dark:text-gray-400">
                          {s.succeeded}/{s.runs}
                        </td>
                        <td className="px-3 py-1.5 text-slate-500 dark:text-gray-400">
                          {s.last_success
                            ? new Date(s.last_success).toLocaleString() : 'never'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {inventory === null ? (
            <div className="py-12 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : (
            <div className="border rounded-lg bg-white divide-y dark:bg-gray-800">
              {inventory.map(d => (
                <div key={d.dataset}>
                  <div className="flex items-center gap-3 p-3">
                    <button
                      onClick={() => setOpenDataset(
                        openDataset === d.dataset ? null : d.dataset)}
                      className="flex items-center gap-2 text-left flex-1 min-w-0">
                      {openDataset === d.dataset
                        ? <ChevronDown className="w-4 h-4 shrink-0 text-slate-400 dark:text-gray-500" />
                        : <ChevronRight className="w-4 h-4 shrink-0 text-slate-400 dark:text-gray-500" />}
                      <span className="text-sm font-medium text-slate-800 w-24 shrink-0 dark:text-gray-100">
                        {d.dataset}
                      </span>
                      <span className="text-sm text-slate-500 truncate dark:text-gray-400">
                        {d.description}
                      </span>
                    </button>
                    <span className="text-sm tabular-nums text-slate-700 shrink-0 dark:text-gray-300">
                      {d.rows.toLocaleString()}
                    </span>
                    <span className="text-xs text-slate-400 tabular-nums shrink-0
                                     hidden sm:inline w-32 text-right dark:text-gray-500">
                      {d.last_updated
                        ? new Date(d.last_updated).toLocaleString() : 'never'}
                    </span>
                    <a href={datasetCsvDownloadUrl(marketId!, d.dataset)}
                       className="text-xs px-2 py-1 border rounded
                                  hover:bg-slate-50 shrink-0 dark:hover:bg-gray-700">
                      CSV
                    </a>
                  </div>

                  {openDataset === d.dataset && (
                    <div className="border-t bg-slate-50 p-3 dark:bg-gray-700">
                      {datasetRows === null ? (
                        <div className="py-6 text-center text-slate-400 dark:text-gray-500">
                          <Loader2 className="w-4 h-4 animate-spin mx-auto" />
                        </div>
                      ) : datasetRows.rows.length === 0 ? (
                        <p className="text-sm text-slate-500 py-4 text-center dark:text-gray-400">
                          Nothing stored yet.
                        </p>
                      ) : (
                        <>
                          <div className="text-xs text-slate-500 mb-2 dark:text-gray-400">
                            Showing {datasetRows.rows.length} of{' '}
                            {datasetRows.total.toLocaleString()} rows.
                          </div>
                          {/* Wide tables scroll inside their own box rather
                              than pushing the page sideways. */}
                          <div className="overflow-x-auto border rounded bg-white dark:bg-gray-800">
                            <table className="text-xs min-w-full">
                              <thead className="bg-slate-100 dark:bg-gray-700">
                                <tr>
                                  {Object.keys(datasetRows.rows[0]).map(col => (
                                    <th key={col}
                                        className="px-2 py-1.5 text-left font-medium
                                                   text-slate-600 whitespace-nowrap dark:text-gray-400">
                                      {col}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y">
                                {datasetRows.rows.map((row, i) => (
                                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-gray-700">
                                    {Object.keys(datasetRows.rows[0]).map(col => (
                                      <td key={col}
                                          className="px-2 py-1 text-slate-700
                                                     max-w-xs truncate dark:text-gray-300"
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

      {/* ---- Data Map (Collection sub-view) ---- */}
      {view === 'collection' && collectionSubView === 'sourcemap' && (
        <div className="space-y-4 max-w-5xl">
          <p className="text-sm text-slate-600 dark:text-gray-400">
            What each source collects, where it lands, and what a vendor
            needs on file before it can run at all. Cost and cadence come
            from the schedule in Settings → Sources &amp; schedules; a source
            missing the identifier it needs closes out as a quiet no-op for
            that vendor rather than an error.
          </p>

          <div className="border rounded-lg bg-white overflow-hidden dark:bg-gray-800">
            <div className="px-3 pt-3 pb-1 text-sm font-medium text-slate-800 dark:text-gray-100">
              One-time only: the vendor registry import
            </div>
            <p className="px-3 pb-3 text-xs text-slate-500 dark:text-gray-400">
              Country, founding year, headcount, funding total and category
              for the original vendor list came from a one-time CSV import,
              not an ongoing collector — nothing refreshes it on a schedule.
              Ongoing collection only fills in a field the import left
              blank; it never overwrites a value the import set.
            </p>
          </div>

          {sources === null ? (
            <div className="py-12 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mx-auto" />
            </div>
          ) : (
            <div className="border rounded-lg bg-white overflow-x-auto dark:bg-gray-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                  <tr>{['Source', 'What it collects', 'Where it lands', 'Requires', 'Cost', 'Cadence']
                    .map(h => (
                    <th key={h} className="text-left font-medium px-3 py-2">{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {SOURCE_MAP.map(info => {
                    const s = sources.find(x => x.source === info.source);
                    return (
                      <tr key={info.source} className="border-t align-top">
                        <td className="px-3 py-2 text-slate-800 font-medium whitespace-nowrap dark:text-gray-100">
                          {info.label}
                        </td>
                        <td className="px-3 py-2 text-slate-600 dark:text-gray-400">{info.collects}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-gray-400">{info.landsIn}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-gray-400">{info.requires}</td>
                        <td className="px-3 py-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded border whitespace-nowrap ${
                            s?.paid ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800'
                                    : 'bg-slate-50 text-slate-500 dark:bg-gray-700 dark:text-gray-400'}`}>
                            {s?.paid ? 'per record' : 'free'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-500 whitespace-nowrap dark:text-gray-400">
                          {info.manualOnly
                            ? 'manual only'
                            : s
                              ? (s.enabled ? `every ${s.effective_interval_hours}h` : 'off')
                              : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---- Timeline (Collection sub-view) ---- */}
      {view === 'collection' && collectionSubView === 'wire' && (
        <div className="space-y-3 max-w-4xl">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600 dark:text-gray-400">
              Market-level events extracted from collected articles, newest
              first — most recent 50 within the period selected above, no
              significance filter yet.
            </p>
            <button disabled={busy || !plan?.topic_name} onClick={buildTimeline}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50 shrink-0">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Build from the last 7 days
            </button>
          </div>

          {events === null && (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-6 h-6 animate-spin text-slate-400 dark:text-gray-500" />
            </div>
          )}
          {events?.length === 0 && (
            <p className="text-sm text-slate-500 py-6 text-center dark:text-gray-400">
              No events. Extraction runs daily for the previous full day.
            </p>
          )}
          {events && events.length > 0 && (
            <>
            <ol className="space-y-2">
              {events.map(e => (
                <WireEventCard key={e.id} event={e} onVendor={openVendorPage} />
              ))}
            </ol>
            {events.length >= 50 && (
              <p className="text-xs text-slate-400 text-center dark:text-gray-500">
                Showing the 50 most recent events. Older ones aren&apos;t
                reachable from this list yet.
              </p>
            )}
            </>
          )}
        </div>
      )}

      {/* ---- Vendors ---- */}
      {view === 'vendors' && (
        <div className="space-y-3">
          {/* Where the vendors are, before the list of who they are. Country
              level only — the registry records a country, not a city. */}
          {marketId != null && <MarketGeographyMap marketId={marketId} />}

          {/* Segments filter the same vendor set. */}
          <div className="flex gap-1 p-0.5 bg-slate-100 rounded-md w-fit dark:bg-gray-700">
            {([
              ['all', `All (${vendors?.length ?? 0})`],
              ['review', `Needs review${tasks?.length ? ` (${tasks.length})` : ''}`],
              ['entrants', 'New entrants'],
            ] as [Segment, string][]).map(([id, label]) => (
              <button key={id} onClick={() => setSegment(id)}
                className={`text-sm px-3 py-1 rounded ${
                  segment === id ? 'bg-white shadow-sm text-slate-900 dark:bg-gray-800 dark:text-gray-100'
                                 : 'text-slate-600 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-100'}`}>
                {label}
              </button>
            ))}
          </div>

          {segment === 'all' && (
          <>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400 dark:text-gray-500" />
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
            {/* An arrived-from-a-chart filter has to be visible and
                removable, or the table looks wrong and nobody can tell why. */}
            {foundedFilter && (
              <button onClick={() => setFoundedFilter('')}
                      className="text-sm px-2 py-1 rounded border bg-slate-800
                                 text-white inline-flex items-center gap-1.5">
                Founded {foundedFilter}
                <X className="w-3 h-3" />
              </button>
            )}
            <div className="flex-1" />
            <span className="text-sm text-slate-500 dark:text-gray-400">
              {shown.length} of {vendors?.length ?? 0} shown
            </span>
          </div>

          {/* A company that shows up in the market's own coverage without
              being a tracked vendor — the way Intezer did — needs one row
              added, not a workbook re-import. */}
          <div className="flex flex-wrap items-center gap-2">
            {addVendorOpen ? (
              <>
                <input autoFocus value={newVendorName}
                       onChange={e => setNewVendorName(e.target.value)}
                       onKeyDown={e => e.key === 'Enter' && addVendorNow()}
                       placeholder="Vendor name"
                       className="text-sm px-2 py-1.5 border rounded-md w-48" />
                <input value={newVendorWebsite}
                       onChange={e => setNewVendorWebsite(e.target.value)}
                       onKeyDown={e => e.key === 'Enter' && addVendorNow()}
                       placeholder="Website (optional)"
                       className="text-sm px-2 py-1.5 border rounded-md w-48" />
                <button onClick={addVendorNow}
                        disabled={addingVendor || !newVendorName.trim()}
                        className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                                   disabled:opacity-50 inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
                  {addingVendor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Add'}
                </button>
                <button onClick={() => { setAddVendorOpen(false); setNewVendorName(''); }}
                        className="text-sm text-slate-500 hover:text-slate-700 dark:text-gray-400 dark:hover:text-gray-300">
                  Cancel
                </button>
              </>
            ) : (
              <button onClick={() => setAddVendorOpen(true)}
                      className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 dark:hover:bg-gray-700">
                + Add vendor
              </button>
            )}
          </div>

          {/* Bulk selection. Two switches, stated separately, because they are
              independent and cost different things: collection spends on
              fetching a vendor, brand monitoring puts it in Brand Watcher. */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="border rounded-lg p-3 bg-white dark:bg-gray-800">
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">Collection</div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Watch the vendor&apos;s website and LinkedIn.{' '}
                {vendors ? `${vendors.filter(v => v.collection_enabled).length} on.` : ''}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, true, false)}
                  className={BULK_BTN}>Select all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, false, false)}
                  className={BULK_BTN}>Remove all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] },
                                                   true, false)}
                  className={BULK_BTN}>Select funded</button>
              </div>
            </div>

            <div className="border rounded-lg p-3 bg-white dark:bg-gray-800">
              <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
                Brand monitoring
              </div>
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                Also track as a brand, with its own sentiment and alerts.{' '}
                {vendors
                  ? `${vendors.filter(v => v.brand_monitoring_enabled).length} on.`
                  : ''}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, true, false,
                                                   'brand_monitoring')}
                  className={BULK_BTN}>Select all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, false, false,
                                                   'brand_monitoring')}
                  className={BULK_BTN}>Remove all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] },
                                                   true, false, 'brand_monitoring')}
                  className={BULK_BTN}>Select funded</button>
              </div>
            </div>
          </div>

          <div className="overflow-x-auto border rounded-lg bg-white dark:bg-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                <tr>
                  {['Vendor', 'Sub-category', 'Country', 'Founded', 'LinkedIn headcount',
                    'Funding', 'Links', 'Collecting', 'Brand'].map(h => (
                    <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map(v => (
                  <tr key={v.brand_id}
                      onClick={() => openVendorPage(v.brand_id)}
                      className="border-t hover:bg-slate-50 cursor-pointer dark:hover:bg-gray-700">
                    <td className="px-3 py-2">
                      <div className="font-medium text-slate-800 hover:underline dark:text-gray-100">
                        {v.display_name}</div>
                      {v.role === 'excluded' && (
                        <span className="text-xs text-slate-500 dark:text-gray-400">out of scope</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap dark:text-gray-400">
                      {v.baseline?.taxonomy?.sub_category ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap dark:text-gray-400">
                      {v.baseline?.hq_country ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-gray-400">
                      {v.baseline?.founded_year ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-gray-400">
                      {v.baseline?.metrics?.employee_count ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap dark:text-gray-400">
                      {fundingLabel(v)}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5 text-slate-400 dark:text-gray-500">
                        {v.identifiers?.some(i => i.kind === 'website_url') && (
                          <Globe className="w-4 h-4" aria-label="website" />)}
                        {v.identifiers?.some(i => i.kind === 'linkedin_company_url') && (
                          <Linkedin className="w-4 h-4" aria-label="LinkedIn" />)}
                      </div>
                    </td>
                    {/* Both switches, per vendor. Clicking one toggles just
                        that vendor, so a single exception does not need a
                        filter rule written for it. */}
                    <td className="px-3 py-2">
                      <button disabled={busy}
                        title={v.collection_enabled
                          ? 'Stop collecting for this vendor'
                          : 'Collect for this vendor'}
                        onClick={e => {
                          e.stopPropagation();
                          applyFilterToggle({ brand_ids: [v.brand_id] },
                                            !v.collection_enabled, false);
                        }}>
                        {v.collection_enabled
                          ? <ToggleRight className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                          : <ToggleLeft className="w-5 h-5 text-slate-300 dark:text-gray-600" />}
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      <button disabled={busy}
                        title={v.brand_monitoring_enabled
                          ? 'Stop monitoring as a brand'
                          : 'Monitor as a brand'}
                        onClick={e => {
                          e.stopPropagation();
                          applyFilterToggle({ brand_ids: [v.brand_id] },
                                            !v.brand_monitoring_enabled, false,
                                            'brand_monitoring');
                        }}>
                        {v.brand_monitoring_enabled
                          ? <ToggleRight className="w-5 h-5 text-sky-600 dark:text-sky-400" />
                          : <ToggleLeft className="w-5 h-5 text-slate-300 dark:text-gray-600" />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500 dark:text-gray-400">
            Showing {shown.length} of {vendors?.length ?? 0}. Select a row for
            vendor detail.
          </p>
          </>
          )}

          {segment === 'review' && (
            <div className="space-y-2 max-w-4xl">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-slate-600 flex-1 dark:text-gray-400">
                  Questions the import raised where it would not guess. Correct
                  the value, or accept the question as unanswerable — a company
                  founded in 2026 cannot have a year-on-year figure and no
                  correction will make one exist.
                </p>
                <button disabled={busy} onClick={async () => {
                  if (marketId === null) return;
                  setBusy(true);
                  try {
                    const r = await autoCloseReviewTasks(marketId);
                    setToggleResult(r.closed
                      ? `${r.closed} of ${r.checked} closed — collection has since answered them.`
                      : `Checked ${r.checked}; none has been answered by collection yet.`);
                    reload();
                  } finally { setBusy(false); }
                }}
                  className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50
                             disabled:opacity-50 shrink-0 dark:hover:bg-gray-700">
                  Close answered questions
                </button>
              </div>

              {!tasks?.length && (
                <p className="text-sm text-slate-500 py-6 text-center dark:text-gray-400">
                  No open review tasks.
                </p>
              )}
              {tasks?.map(t => (
                <div key={t.id} className="border rounded-lg p-3 bg-white dark:bg-gray-800">
                  <div className="flex items-start gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${
                      SEVERITY_TONE[t.severity] ?? SEVERITY_TONE.low}`}>
                      {t.severity}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-slate-800 dark:text-gray-100">{t.message}</div>
                      <div className="text-xs text-slate-500 mt-1 dark:text-gray-400">
                        {t.brand_id ? (
                          <button onClick={() => openVendorPage(t.brand_id!)}
                            className="hover:underline">{t.vendor ?? 'vendor'}</button>
                        ) : 'market'} · {t.kind}
                        {t.target_field ? ` · ${t.target_field}` : ''}
                        {t.current_value !== null && t.current_value !== undefined
                          ? ` · currently ${t.current_value}` : ''}
                      </div>
                    </div>
                    <div className="flex gap-1.5 shrink-0">
                      {t.target_field && (
                        <button onClick={() => setFixing(
                                  fixing?.id === t.id ? null
                                    : { id: t.id, value: t.current_value ?? '',
                                        source: '' })}
                          className="text-xs px-2 py-1 border rounded hover:bg-slate-50 dark:hover:bg-gray-700">
                          Correct it
                        </button>
                      )}
                      <button disabled={busy} onClick={async () => {
                        if (marketId === null) return;
                        await closeReviewTask(marketId, t.id, 'accepted');
                        reload();
                      }}
                        title="The question has no answer; stop asking it."
                        className="text-xs px-2 py-1 border rounded hover:bg-slate-50 dark:hover:bg-gray-700">
                        Accept
                      </button>
                      <button disabled={busy} onClick={async () => {
                        if (marketId === null) return;
                        await closeReviewTask(marketId, t.id, 'dismissed');
                        reload();
                      }}
                        title="The flag was wrong."
                        className="text-xs px-2 py-1 border rounded hover:bg-slate-50 dark:hover:bg-gray-700">
                        Dismiss
                      </button>
                    </div>
                  </div>

                  {fixing?.id === t.id && (
                    <div className="mt-3 pt-3 border-t flex flex-wrap items-end gap-2">
                      <label className="text-xs text-slate-500 dark:text-gray-400">
                        <div className="mb-0.5">New {t.target_field}</div>
                        <input value={fixing.value}
                          onChange={e => setFixing({ ...fixing, value: e.target.value })}
                          className="px-2 py-1 text-sm border rounded-md w-32" />
                      </label>
                      <label className="text-xs text-slate-500 flex-1 min-w-[220px] dark:text-gray-400">
                        {/* Required. A corrected figure with no source is the
                            same problem moved one step later. */}
                        <div className="mb-0.5">Source (required)</div>
                        <input value={fixing.source} placeholder="where this came from"
                          onChange={e => setFixing({ ...fixing, source: e.target.value })}
                          className="px-2 py-1 text-sm border rounded-md w-full" />
                      </label>
                      <button disabled={busy || !fixing.source.trim()}
                        onClick={async () => {
                          if (marketId === null) return;
                          setBusy(true);
                          try {
                            await fixReviewTask(marketId, t.id, {
                              value: fixing.value, source: fixing.source });
                            setFixing(null);
                            setToggleResult(`${t.vendor}: ${t.target_field} set to ${fixing.value}.`);
                            reload();
                          } catch (e: any) {
                            setToggleResult(`Failed: ${e.message ?? e}`);
                          } finally { setBusy(false); }
                        }}
                        className="text-sm px-3 py-1.5 border rounded-md
                                   hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-gray-700">
                        Save
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {segment === 'entrants' && (
            <div className="space-y-3 max-w-4xl">
              <div className="border rounded-lg p-4 bg-white space-y-2 dark:bg-gray-800">
                <div className="font-medium text-slate-800 dark:text-gray-100">New entrants</div>
                <p className="text-sm text-slate-600 dark:text-gray-400">
                  Scans collected funding articles for companies not in the
                  registry. Results are proposals for review, not additions.
                </p>
                <button disabled={busy} onClick={runDiscovery}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  Scan the last 30 days
                </button>
                {discovery && !discovery.error && (
                  <p className="text-xs text-slate-500 dark:text-gray-400">
                    Scanned {discovery.scanned} articles
                    {discovery.below_alignment_floor ? `, skipped ${discovery.below_alignment_floor} below the relevance floor` : ''}.
                  </p>
                )}
                {discovery?.error && (
                  <div className="text-sm border border-amber-200 bg-amber-50 rounded-md p-2.5 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20">
                    {discovery.error}
                  </div>
                )}
              </div>
              {discovery && discovery.proposals.length > 0 && (
                <div className="border rounded-lg bg-white overflow-x-auto dark:bg-gray-800">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                      <tr>{['Company', 'Raised', 'Round', 'Seen in', 'Source'].map(h => (
                        <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
                    </thead>
                    <tbody>
                      {discovery.proposals.map(c => (
                        <tr key={c.name} className="border-t">
                          <td className="px-3 py-2 font-medium text-slate-800 dark:text-gray-100">{c.name}</td>
                          <td className="px-3 py-2 text-slate-600 dark:text-gray-400">
                            {c.amount_musd !== null ? `$${c.amount_musd}M` : '—'}</td>
                          <td className="px-3 py-2 text-slate-600 dark:text-gray-400">{c.round ?? '—'}</td>
                          <td className="px-3 py-2 text-slate-500 dark:text-gray-400">
                            {c.mentions} article{c.mentions === 1 ? '' : 's'}</td>
                          <td className="px-3 py-2 text-slate-500 max-w-xs truncate dark:text-gray-400"
                              title={c.article_title ?? ''}>
                            {c.news_source ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {discovery && !discovery.proposals.length && !discovery.error && (
                <p className="text-sm text-slate-500 py-4 dark:text-gray-400">
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
          <div className="relative bg-slate-50 w-full max-w-3xl h-full overflow-y-auto shadow-xl dark:bg-gray-700"
               onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b px-4 py-3 flex items-center gap-3 dark:bg-gray-800">
              <div className="font-medium text-slate-800 dark:text-gray-100">Market settings</div>
              <div className="flex gap-1 p-0.5 bg-slate-100 rounded-md dark:bg-gray-700">
                {([
                  // Labeled "Search terms" here, not "Collection" — this
                  // edits what gets collected; the Collection *mode* (the
                  // main tab bar) is a different, read-only concept, and
                  // sharing a name with it read as the same thing.
                  ['collection', 'Search terms'],
                  ['sources', 'Sources & schedules'],
                  ['health', 'Health'],
                  ['scope', 'Scope'],
                ] as [SettingsPanel, string][]).map(([id, label]) => (
                  <button key={id} onClick={() => setSettingsOpen(id)}
                    className={`text-sm px-3 py-1 rounded ${
                      settingsOpen === id ? 'bg-white shadow-sm text-slate-900 dark:bg-gray-800 dark:text-gray-100'
                                          : 'text-slate-600 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-100'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex-1" />
              <button onClick={() => setSettingsOpen(null)}
                className="text-slate-400 hover:text-slate-700 dark:text-gray-500 dark:hover:text-gray-300">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4">

      {settingsOpen === 'scope' && (
        <div className="space-y-4 max-w-3xl">
          <div className="border rounded-lg p-4 bg-white space-y-3 dark:bg-gray-800">
            <div>
              <div className="font-medium text-slate-800 dark:text-gray-100">Market scope</div>
              <p className="text-sm text-slate-600 mt-1 dark:text-gray-400">
                What the tracked vendor cohort actually covers. The investor
                report states this verbatim when set, and says plainly that
                scope was never defined when it isn&apos;t — it never infers
                a boundary from who happens to be in the registry.
              </p>
            </div>

            <div>
              <label className="text-sm text-slate-700 dark:text-gray-300">Scope description</label>
              <textarea
                value={scopeDraft}
                onChange={e => setScopeDraft(e.target.value)}
                rows={4}
                placeholder="The tracked vendor cohort covers companies for which AI-led investigation, triage or response automation is a material part of the product proposition. Broader security vendors may appear in market coverage without being included in the tracked cohort."
                className="mt-1 w-full text-sm border rounded-md px-2 py-1.5" />
            </div>

            <div>
              <label className="text-sm text-slate-700 dark:text-gray-300">
                Inclusion criteria <span className="text-slate-400 dark:text-gray-500">(optional)</span>
              </label>
              <textarea
                value={inclusionDraft}
                onChange={e => setInclusionDraft(e.target.value)}
                rows={2}
                className="mt-1 w-full text-sm border rounded-md px-2 py-1.5" />
            </div>

            <div>
              <label className="text-sm text-slate-700 dark:text-gray-300">
                Exclusion criteria <span className="text-slate-400 dark:text-gray-500">(optional)</span>
              </label>
              <textarea
                value={exclusionDraft}
                onChange={e => setExclusionDraft(e.target.value)}
                rows={2}
                className="mt-1 w-full text-sm border rounded-md px-2 py-1.5" />
            </div>

            <div className="flex items-center gap-2">
              <button disabled={busy} onClick={saveScope}
                className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-gray-700">
                Save scope
              </button>
              {toggleResult && (
                <span className="text-xs text-slate-500 dark:text-gray-400">{toggleResult}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {settingsOpen === 'collection' && plan && (
        <div className="space-y-4 max-w-3xl">
          <div className="border rounded-lg p-4 bg-white space-y-3 dark:bg-gray-800">
            <div>
              <div className="font-medium text-slate-800 dark:text-gray-100">What this market collects</div>
              <p className="text-sm text-slate-600 mt-1 dark:text-gray-400">
                Search terms for the category. Vendor names are added separately
                below.
              </p>
            </div>

            <div>
              <label className="text-sm text-slate-700 dark:text-gray-300">
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
                  className="text-sm px-3 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-gray-700">
                  Save terms
                </button>
                <span className="text-xs text-slate-500 dark:text-gray-400">
                  {plan.market_terms.length} saved · 30 characters max
                </span>
              </div>
              {plan.truncated && plan.truncated.length > 0 && (
                <div className="text-xs border border-amber-200 bg-amber-50 rounded-md p-2 mt-2 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20">
                  {plan.truncated.length} term
                  {plan.truncated.length === 1 ? ' is' : 's are'} over 30
                  characters and will be searched as the shorter, broader form:
                  <ul className="mt-1 space-y-0.5">
                    {plan.truncated.map(x => (
                      <li key={x.term}>
                        <code className="bg-white border px-1 rounded dark:bg-gray-800">{x.term}</code>
                        {' → '}
                        <code className="bg-white border px-1 rounded dark:bg-gray-800">{x.searched_as}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="pt-1">
              <div className="text-sm text-slate-700 dark:text-gray-300">Also search vendors by name</div>
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
                          : 'hover:bg-slate-50 dark:hover:bg-gray-700'}`}>
                      {label}
                    </button>
                  ))}
              </div>
              <p className="text-xs text-slate-500 mt-1.5 dark:text-gray-400">
                Adds vendor names to the search. Short or ambiguous names are
                qualified with
                <code className="mx-1 bg-slate-100 px-1 rounded dark:bg-gray-700">{plan.qualifier}</code>
                to reduce false matches.
              </p>
            </div>

            {plan.error && (
              <div className="text-sm border border-amber-200 bg-amber-50 rounded-md p-2.5 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20">
                {plan.error}
              </div>
            )}

            <div className="text-sm text-slate-700 space-y-1 border-t pt-3 dark:text-gray-300">
              <div>Group: <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded dark:bg-gray-700">{plan.group_name}</code></div>
              <div>Topic: <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded dark:bg-gray-700">{plan.topic_name}</code></div>
              <div>{plan.keywords.length} search terms in total</div>
            </div>

            {plan.keywords.length > 0 && (
              <>
                <button onClick={() => setShowKeywords(s => !s)}
                  className="text-sm text-slate-600 flex items-center gap-1 dark:text-gray-400">
                  {showKeywords ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  {showKeywords ? 'Hide' : 'Show'} the full search list
                </button>
                {showKeywords && (
                  <div className="flex flex-wrap gap-1">
                    {plan.keywords.map(k => (
                      <span key={k} className={`text-xs border rounded px-1.5 py-0.5 ${
                        plan.vendor_keywords.includes(k)
                          ? 'bg-white text-slate-500 dark:bg-gray-800 dark:text-gray-400' : 'bg-slate-100 dark:bg-gray-700'}`}>{k}</span>
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
                <span className="text-sm text-emerald-700 flex items-center gap-1 dark:text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" /> Live
                </span>
              )}
            </div>
          </div>

          <div className="border rounded-lg p-4 bg-white space-y-3 dark:bg-gray-800">
            <div className="font-medium text-slate-800 dark:text-gray-100">Vendor selection</div>

            <div>
              <div className="text-sm text-slate-700 dark:text-gray-300">Collection</div>
              <p className="text-xs text-slate-500 mb-1.5 dark:text-gray-400">
                Whether we spend on watching a vendor's website and LinkedIn.
                Vendors marked out of scope are never included unless a rule
                names their role.
              </p>
              <div className="flex flex-wrap gap-2">
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, true, false)}
                  className={BULK_BTN}>Select all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, false, false)}
                  className={BULK_BTN}>Remove all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] }, true, false)}
                  className={BULK_BTN}>Select funded</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle(
                    { funding_status: ['Undisclosed', 'Bootstrapped'] }, false, false)}
                  className={BULK_BTN}>Remove unfunded</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle({ has_linkedin: false }, false, false)}
                  className={BULK_BTN}>Remove those with no LinkedIn</button>
              </div>
            </div>

            <div className="pt-1 border-t">
              <div className="text-sm text-slate-700 pt-2 dark:text-gray-300">Brand monitoring</div>
              <p className="text-xs text-slate-500 mb-1.5 dark:text-gray-400">
                Whether a vendor also appears in Brand Watcher as a brand of its
                own, with sentiment, alerts and its own dashboard. Separate from
                collection, and off by default — 83 vendors would swamp a brand
                dashboard. Switching it on rewrites keywords that are ordinary
                words, so "Variance" is searched as "Variance security".
              </p>
              <div className="flex flex-wrap gap-2">
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, true, false,
                                                   'brand_monitoring')}
                  className={BULK_BTN}>Select all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle(ALL_IN_SCOPE, false, false,
                                                   'brand_monitoring')}
                  className={BULK_BTN}>Remove all</button>
                <button disabled={busy}
                  onClick={() => applyFilterToggle({ funding_status: ['Disclosed'] },
                                                   true, false, 'brand_monitoring')}
                  className={BULK_BTN}>Select funded</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---- Settings: health ---- */}
      {settingsOpen === 'health' && health && (
        <HealthPanel health={health} runs={runs} />
      )}

      {/* ---- Settings: sources and schedules ---- */}
      {settingsOpen === 'sources' && sources && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-gray-400">
            Collection sources and intervals. Sources marked "per record" are
            billed by the provider. Minimum interval is {minInterval} hours.
          </p>
          <div className="border rounded-lg bg-white overflow-x-auto dark:bg-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                <tr>{['Source', 'Cost', 'On', 'Every', 'Last success'].map(h => (
                  <th key={h} className="text-left font-medium px-3 py-2">{h}</th>))}</tr>
              </thead>
              <tbody>
                {sources.map(s => (
                  <tr key={s.source} className="border-t">
                    <td className="px-3 py-2 text-slate-800 dark:text-gray-100">
                      {s.source.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        s.paid ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800'
                               : 'bg-slate-50 text-slate-500 dark:bg-gray-700 dark:text-gray-400'}`}>
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
                          ? <ToggleRight className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                          : <ToggleLeft className="w-5 h-5 text-slate-300 dark:text-gray-600" />}
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
                      <span className="text-xs text-slate-500 ml-1 dark:text-gray-400">h</span>
                      {s.interval_hours && (
                        <span className="text-xs text-slate-400 ml-1 dark:text-gray-500">
                          (default {s.default_interval_hours}h)</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-500 text-xs dark:text-gray-400">
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
      {/* The records behind whichever figure was clicked. A dialog rather than
          an inline panel: the list can be long, and it belongs to the figure
          that opened it rather than to the section it happens to sit in. */}
      {records && marketId !== null && (
        <div className="fixed inset-0 z-50 flex items-start justify-center
                        overflow-y-auto bg-black/40 p-4 sm:p-8"
             role="dialog" aria-modal="true"
             aria-label={records.title}
             onClick={() => setRecords(null)}>
          <div className="w-full max-w-6xl" onClick={e => e.stopPropagation()}>
            <DrilldownHost marketId={marketId} spec={records}
                           onClose={() => setRecords(null)}
                           onVendor={openVendorPage} />
          </div>
        </div>
      )}
    </div>
  );
}
