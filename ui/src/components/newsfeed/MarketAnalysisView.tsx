/**
 * Market Analysis — four cross-sectional reads on a tracked market.
 *
 * Every panel prints its own coverage line. That is not decoration: most of
 * these rest on a subset of the registry, and a chart without its denominator
 * invites the wrong conclusion. "One shared investor" reads as a fragmented
 * market when what it means is that half the Crunchbase pages are unread.
 */

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, Pie,
  PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
  ZAxis,
} from 'recharts';
import {
  getAnalyses, getChannelMix, getJobPostings, getTopVoices,
  type ChannelMix, type Coverage, type JobPosting, type MarketAnalyses,
  type TopVoices, type VoiceRow,
} from '../../services/marketMonitorApi';
import { DataTable, type Column } from './DataTable';
import { MarketThemesPanel } from './MarketThemesPanel';
import { ConfidenceGate, type ThinPanel } from './ConfidenceGate';
import type { DrilldownSpec } from './MarketDrilldownHost';

// SVG stroke/fill props take a literal color, not a Tailwind class, so every
// chart color needs a light/dark pair picked at render time (see `cc` below).
const GRID_L = '#e2e8f0', GRID_D = '#374151';
const INK_L = '#475569', INK_D = '#9ca3af';
const SIGNAL_L = '#30a46c', SIGNAL_D = '#4ade80';
const COMMENTARY_L = '#8b93a1', COMMENTARY_D = '#a1a1aa';
const NOISE_L = '#d4d8de', NOISE_D = '#4b5563';
const SOCIAL_L = '#f5a524', SOCIAL_D = '#fbbf24';
const DISCUSSION_L = '#0ea5e9', DISCUSSION_D = '#38bdf8';
const RESEARCH_L = '#6366f1', RESEARCH_D = '#818cf8';
const AXIS_LABEL_L = '#64748b', AXIS_LABEL_D = '#94a3b8';

// Share-of-voice pie: only the first three categorical slots clear the
// colorblind-safe all-pairs check (a pie is compared slice-to-slice, not just
// adjacent-to-adjacent) — past three, everyone else folds into a neutral
// "Other" wedge rather than a fourth hue that can't be told apart reliably.
// The dark set reuses this app's own Radix blue-8/amber-7/green-8 steps, so
// the pie stays on-brand rather than picking arbitrary lighter tones.
const SOV_PIE_COLORS_L = ['#2a78d6', '#eb6834', '#1baf7a'];
const SOV_PIE_COLORS_D = ['#5eb0ef', '#f3ba63', '#5bb98c'];
const SOV_PIE_OTHER_L = '#94a3b8', SOV_PIE_OTHER_D = '#6b7280';

function cc(isDark: boolean, light: string, dark: string): string {
  return isDark ? dark : light;
}

function CoverageLine({ coverage, note }: { coverage: Coverage; note?: string }) {
  // coverage.label is already a full clause ("81 of 83 vendors have a
  // founding year") — prefixing "Based on " onto it stacked two subjects in
  // one sentence and stopped parsing as English.
  const label = coverage.label
    ? coverage.label[0].toUpperCase() + coverage.label.slice(1)
    : coverage.label;
  return (
    <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
      {note ? `${note} ` : ''}
      <span className={coverage.complete ? '' : 'text-amber-700 dark:text-amber-400'}>
        {label}.
      </span>
    </p>
  );
}

function Panel({ title, children, full }: {
  title: string; children: React.ReactNode;
  /** Spans both grid columns — for a panel left alone in a 2-column row,
   *  either because its sibling collapsed into the "not enough data" strip
   *  or because a third panel shares the row with two others. */
  full?: boolean;
}) {
  return (
    <div className={`border rounded-lg p-4 bg-white dark:bg-gray-800 ${full ? 'lg:col-span-2' : ''}`}>
      <div className="text-sm font-medium text-slate-800 dark:text-gray-100">{title}</div>
      {children}
    </div>
  );
}

export function MarketAnalysisView({ marketId, onVendor, onDrill, onRecords,
                                     days }: {
  marketId: number;
  onVendor: (brandId: number) => void;
  /** Open a filtered list for a chart segment. Optional so the view still
   *  renders where no drilldown target exists. */
  onDrill?: (kind: string, value: string) => void;
  /** Open the records behind a figure — the posts, listings or funding rows
   *  themselves, as opposed to onDrill's list of vendors. */
  onRecords?: (spec: DrilldownSpec) => void;
  /** The shared period, same as Pulse and Coverage. Only reaches the panels
   *  where a window has a real meaning — signal/noise, hiring, share of
   *  voice, top voices, channel mix. Formation and funding describe the
   *  market's current state, not activity in a window, and stay unwindowed
   *  regardless of this value (see market_analysis.run). */
  days?: number;
}) {
  const [data, setData] = useState<MarketAnalyses | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortByShare, setSortByShare] = useState(false);
  const [jobs, setJobs] = useState<JobPosting[] | null>(null);
  const [showJobs, setShowJobs] = useState(false);
  const [voices, setVoices] = useState<TopVoices | null>(null);
  const [mix, setMix] = useState<ChannelMix | null>(null);
  const [hiringCut, setHiringCut] =
    useState<'role' | 'function' | 'region' | 'seniority'>('role');
  const [openVendorRow, setOpenVendorRow] = useState<number | null>(null);
  const [sovChart, setSovChart] = useState<'bar' | 'pie'>('bar');
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const GRID = cc(isDark, GRID_L, GRID_D);
  const INK = cc(isDark, INK_L, INK_D);
  const SIGNAL = cc(isDark, SIGNAL_L, SIGNAL_D);
  const COMMENTARY = cc(isDark, COMMENTARY_L, COMMENTARY_D);
  const NOISE = cc(isDark, NOISE_L, NOISE_D);
  const SOCIAL = cc(isDark, SOCIAL_L, SOCIAL_D);
  const DISCUSSION = cc(isDark, DISCUSSION_L, DISCUSSION_D);
  const RESEARCH = cc(isDark, RESEARCH_L, RESEARCH_D);
  const AXIS_LABEL = cc(isDark, AXIS_LABEL_L, AXIS_LABEL_D);
  const SOV_PIE_COLORS = isDark ? SOV_PIE_COLORS_D : SOV_PIE_COLORS_L;
  const SOV_PIE_OTHER = cc(isDark, SOV_PIE_OTHER_L, SOV_PIE_OTHER_D);

  useEffect(() => {
    let live = true;
    setData(null);
    getAnalyses(marketId, days)
      .then(d => { if (live) setData(d); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, days]);

  useEffect(() => {
    let live = true;
    Promise.all([getTopVoices(marketId, days, 20), getChannelMix(marketId, days)])
      .then(([v, m]) => { if (live) { setVoices(v); setMix(m); } })
      .catch(() => {});
    return () => { live = false; };
  }, [marketId, days]);

  useEffect(() => {
    if (!showJobs || jobs) return;
    let live = true;
    getJobPostings(marketId)
      .then(r => { if (live) setJobs(r.postings); })
      .catch(() => { if (live) setJobs([]); });
    return () => { live = false; };
  }, [showJobs, jobs, marketId]);

  if (error) {
    return <div className="text-sm text-red-700 p-3 border rounded-md
                           bg-red-50 dark:text-red-400 dark:bg-red-900/20">{error}</div>;
  }
  if (!data) {
    return <div className="py-16 text-center text-slate-400 dark:text-gray-500">
      <Loader2 className="w-5 h-5 animate-spin mx-auto" />
    </div>;
  }

  const f = data.formation;
  const sn = data.signal_noise;
  const fu = data.funding;
  const sov = data.share_of_voice;
  const hi = data.hiring;

  // A confirmed zero ("nobody has mentioned any of them") is its own
  // informative state, rendered inline where it already was. What routes
  // into the shared strip below is the middle case: some data, not enough
  // of it for a percentage or a network to mean anything.
  const sovThin = !!sov && !sov.error && sov.earned_total > 0 && !sov.earned_share_reliable;
  const investorsThin = !!fu && !fu.error && fu.shared_investors.length > 0
    && fu.shared_investors.length < 2;
  const analysisThinPanels: ThinPanel[] = [];
  if (sovThin) {
    analysisThinPanels.push({
      id: 'share-of-voice',
      title: 'Share of voice',
      why: 'Share of what other people said about each vendor, among vendors with any earned coverage.',
      need: `${sov!.earned_total} of ${sov!.min_earned_for_share} minimum earned mentions`,
    });
  }
  if (investorsThin) {
    analysisThinPanels.push({
      id: 'investor-overlap',
      title: 'Investors backing more than one vendor',
      why: 'Investors whose portfolio includes more than one tracked vendor.',
      need: fu!.coverage.label,
    });
  }

  // Founding years and announcement months share no x-axis, so they are two
  // charts side by side rather than one composed chart pretending otherwise.
  const snRows = sn?.vendors ? [...sn.vendors] : [];
  if (sortByShare) {
    snRows.sort((a, b) => (b.signal_share ?? -1) - (a.signal_share ?? -1));
  }

  return (
    <div className="space-y-4">
      {/* ---- Formation ---- */}
      {f && !f.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="When these vendors were founded">
            <CoverageLine
              coverage={f.coverage}
              note={`${f.founded_since_2023} of ${f.vendors_in_scope} were founded in 2023 or later. Current registry — not scoped to the period selector above.`} />
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={f.founded_by_year}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                {/* Clicking a year opens the vendors founded in it. */}
                <Bar dataKey="vendors" fill={INK} name="Vendors founded"
                     cursor={onDrill ? 'pointer' : undefined}
                     onClick={(d: any) => onDrill?.('founded', String(d?.year))} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="When they started announcing">
            <CoverageLine
              coverage={f.announcement_coverage}
              note="Vendor posts by month. The line is announcements — posts naming something that happened." />
            <ResponsiveContainer width="100%" height={230}>
              <ComposedChart data={f.announcements_by_month}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="posts" fill={NOISE} name="All posts" />
                <Line type="monotone" dataKey="signal" stroke={SIGNAL}
                      strokeWidth={2} dot={{ r: 2 }} name="Announcements" />
              </ComposedChart>
            </ResponsiveContainer>
          </Panel>
        </div>
      )}

      {/* ---- Signal to noise ---- */}
      {sn && !sn.error && (
        <Panel title="What each vendor's posts actually contain">
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <CoverageLine
                coverage={sn.coverage}
                note={`${sn.totals.signal} of ${sn.totals.signal + sn.totals.commentary + sn.totals.noise} vendor posts announce something.`} />
            </div>
            <button onClick={() => setSortByShare(v => !v)}
                    className="text-xs px-2 py-1 border rounded hover:bg-slate-50 shrink-0 dark:hover:bg-gray-700">
              {sortByShare ? 'Sort by count' : 'Sort by share'}
            </button>
          </div>
          {sortByShare && (
            <p className="text-xs text-slate-500 mb-2 dark:text-gray-400">
              Share is only computed for vendors with at least{' '}
              {sn.min_posts_for_ratio} posts. A vendor with three posts, all
              announcements, is not the most substantive vendor in the market.
            </p>
          )}
          <ResponsiveContainer width="100%" height={Math.max(240, snRows.length * 26)}>
            <BarChart data={snRows} layout="vertical"
                      margin={{ left: 10, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
              <YAxis type="category" dataKey="vendor" width={130}
                     tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="signal" stackId="a" fill={SIGNAL} name="Announcement"
                   cursor="pointer"
                   onClick={(d: any) => d?.brand_id && onVendor(d.brand_id)} />
              <Bar dataKey="commentary" stackId="a" fill={COMMENTARY} name="Opinion" />
              <Bar dataKey="noise" stackId="a" fill={NOISE} name="Promotion" />
            </BarChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {sn.signal_kinds.map(k => (
              <span key={k.kind}
                    className="text-xs px-2 py-0.5 rounded border bg-emerald-50
                               text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800">
                {k.kind} <span className="text-emerald-500">{k.n}</span>
              </span>
            ))}
          </div>
        </Panel>
      )}

      {/* ---- Share of voice ---- */}
      {sov && !sov.error && sov.vendors.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {!sovThin && (
          <Panel title="Share of voice">
            <div className="flex items-start justify-between gap-2">
              <CoverageLine
                coverage={sov.coverage}
                note={`Of ${sov.earned_total} mentions by somebody other than the vendor.`} />
              {sov.earned_total > 0 && (
                <div className="flex gap-1 shrink-0 text-xs">
                  {(['bar', 'pie'] as const).map(k => (
                    <button key={k} onClick={() => setSovChart(k)}
                            className={`px-2 py-0.5 rounded border capitalize ${
                              sovChart === k
                                ? 'bg-slate-800 text-white border-slate-800'
                                : 'text-slate-600 border-slate-200 hover:bg-slate-50 dark:text-gray-400 dark:border-gray-700 dark:hover:bg-gray-700'
                            }`}>
                      {k}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="text-xs text-slate-500 mb-2 dark:text-gray-400">
              Share of what <em>other people</em> said. A vendor's own posts are
              not counted here at all — they are volume, not voice, and they are
              in the panel below.
            </p>
            {sov.earned_total === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center dark:text-gray-400">
                Nobody outside the vendors has mentioned any of them yet.
              </p>
            ) : sovChart === 'bar' ? (
              <ResponsiveContainer width="100%"
                height={Math.max(180, sov.vendors.filter(v => v.earned > 0).length * 26)}>
                <BarChart layout="vertical"
                          data={sov.vendors.filter(v => v.earned > 0)}
                          margin={{ left: 10, right: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis type="number" tick={{ fontSize: 11 }}
                         tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                         domain={[0, 'dataMax']} />
                  <YAxis type="category" dataKey="vendor" width={130}
                         tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(v: any, _n: any, p: any) =>
                      [`${(Number(v) * 100).toFixed(1)}% — ${p?.payload?.earned} of ${sov.earned_total} mentions`,
                       'Share of voice']} />
                  <Bar dataKey="earned_share" fill={SIGNAL} name="Share of voice"
                       cursor="pointer"
                       onClick={(d: any) => d?.brand_id && onVendor(d.brand_id)} />
                </BarChart>
              </ResponsiveContainer>
            ) : (() => {
              // Only the top 3 get a named hue — that's as many as a pie can
              // carry while staying colorblind-safe slice-to-slice (every
              // slice can be next to every other, not just its neighbors).
              // Everyone else folds into one neutral "Other" wedge.
              const ranked = [...sov.vendors].filter(v => v.earned > 0)
                .sort((a, b) => (b.earned_share ?? 0) - (a.earned_share ?? 0));
              const top = ranked.slice(0, 3);
              const rest = ranked.slice(3);
              const otherShare = rest.reduce((s, v) => s + (v.earned_share ?? 0), 0);
              const otherEarned = rest.reduce((s, v) => s + v.earned, 0);
              const pieData = [
                ...top.map(v => ({ name: v.vendor, share: v.earned_share ?? 0,
                                    earned: v.earned, brand_id: v.brand_id })),
                ...(rest.length > 0
                  ? [{ name: `Other (${rest.length})`, share: otherShare,
                       earned: otherEarned, brand_id: null }]
                  : []),
              ];
              return (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" outerRadius={100}
                         dataKey="share" nameKey="name"
                         label={({ name, percent }: any) =>
                           percent > 0.05 ? `${name} ${(percent * 100).toFixed(0)}%` : ''}
                         labelLine={false}>
                      {pieData.map((p, i) => (
                        <Cell key={p.name}
                              fill={p.brand_id === null ? SOV_PIE_OTHER : SOV_PIE_COLORS[i]}
                              cursor={p.brand_id ? 'pointer' : 'default'}
                              onClick={() => p.brand_id && onVendor(p.brand_id)} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(v: any, _n: any, p: any) =>
                        [`${(Number(v) * 100).toFixed(1)}% — ${p?.payload?.earned} of ${sov.earned_total} mentions`,
                         p?.payload?.name]} />
                  </PieChart>
                </ResponsiveContainer>
              );
            })()}
          </Panel>
          )}

          <Panel title="Who shouts loudest, and who is heard" full={sovThin}>
            <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
              Each dot is a vendor. Further right means it posts more; higher
              means each post gets more reaction. The two are not the same
              thing, and the gap between them is the finding —{' '}
              {sov.reactions_total.toLocaleString()} reactions measured.
            </p>
            <ResponsiveContainer width="100%" height={280}>
              <ScatterChart margin={{ left: 4, right: 16, top: 8, bottom: 22 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" dataKey="own_posts" name="Posts"
                       tick={{ fontSize: 11 }}
                       label={{ value: 'posts published', position: 'insideBottom',
                                offset: -12, fontSize: 11, fill: AXIS_LABEL }} />
                <YAxis type="number" dataKey="reactions_per_post"
                       name="Reactions per post" tick={{ fontSize: 11 }}
                       label={{ value: 'reactions per post', angle: -90,
                                position: 'insideLeft', fontSize: 11,
                                fill: AXIS_LABEL }} />
                <ZAxis range={[90, 90]} />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  content={({ payload }) => {
                    const p: any = payload?.[0]?.payload;
                    if (!p) return null;
                    return (
                      <div className="bg-white border rounded px-2 py-1 text-xs shadow dark:bg-gray-800">
                        <div className="font-medium">{p.vendor}</div>
                        <div className="text-slate-600 dark:text-gray-400">
                          {p.own_posts} posts · {p.reactions_per_post} reactions each
                        </div>
                        <div className="text-slate-500 dark:text-gray-400">
                          {p.earned} mention{p.earned === 1 ? '' : 's'} by others
                        </div>
                      </div>
                    );
                  }} />
                <Scatter
                  data={sov.vendors.filter(v => v.reactions_per_post !== null)}
                  fill="#d6409f">
                  {sov.vendors.filter(v => v.reactions_per_post !== null).map(v => (
                    <Cell key={v.brand_id} cursor="pointer"
                          onClick={() => onVendor(v.brand_id)} />
                  ))}
                  <LabelList dataKey="vendor" position="top"
                             style={{ fontSize: 9, fill: AXIS_LABEL }} />
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <p className="text-xs text-slate-400 dark:text-gray-500">
              Vendors with fewer than five measured posts are absent: an average
              over two posts is not an average.
            </p>
            {sov.loudest.length >= 4 && (() => {
              const top = sov.loudest.slice(0, 10);
              const Row = (v: VoiceRow) => (
                <button key={v.brand_id} onClick={() => onVendor(v.brand_id)}
                        className="w-full flex items-center justify-between
                                   py-1.5 text-sm hover:bg-slate-50 text-left dark:hover:bg-gray-700">
                  <span className="text-slate-700 dark:text-gray-300">{v.vendor}</span>
                  <span className="text-slate-500 tabular-nums dark:text-gray-400"
                        title="Own posts about itself, in this window">
                    {v.own_posts} post{v.own_posts === 1 ? '' : 's'}
                  </span>
                </button>
              );
              return (
                <div className="grid gap-4 sm:grid-cols-2 mt-3 pt-3 border-t">
                  <div>
                    <div className="text-xs font-medium text-slate-600 mb-1 dark:text-gray-400">
                      Loudest — most own posts
                    </div>
                    <div className="divide-y">{top.map(Row)}</div>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-slate-600 mb-1 dark:text-gray-400">
                      Quietest — collected, and said nothing
                    </div>
                    {/* Two conditions, both required. Zero own posts in the
                        window, *and* a successful collection for that vendor.
                        Without the second, this list was accusing 57 companies
                        of silence when nothing had ever been collected from
                        them — the vendors below the split are that group, kept
                        separate because "we did not look" is not a finding
                        about the company.

                        The date shown is the vendor's last post at any time,
                        not inside the window. A vendor quiet this month may
                        have posted in March, and "never" would be a lie the
                        window told. */}
                    <div className="divide-y">
                      {sov.quietest.slice(0, 10).map(v => (
                        <button key={v.brand_id} onClick={() => onVendor(v.brand_id)}
                                className="w-full py-1.5 text-sm text-left flex items-baseline
                                           justify-between gap-2
                                           text-slate-700 hover:bg-slate-50
                                           dark:text-gray-300 dark:hover:bg-gray-700">
                          <span>{v.vendor}</span>
                          <span className="text-xs text-slate-400 dark:text-gray-500 shrink-0">
                            {v.last_posted_at
                              ? `last posted ${String(v.last_posted_at).slice(0, 10)}`
                              : 'no post on record'}
                          </span>
                        </button>
                      ))}
                    </div>
                    {sov.quietest_total > 10 && (
                      <div className="text-xs text-slate-400 dark:text-gray-500 pt-1">
                        {sov.quietest_total - 10} more of {sov.quietest_total} total
                      </div>
                    )}

                    {sov.unmeasured_total > 0 && (
                      <div className="mt-3 pt-2 border-t border-dashed">
                        <div className="text-xs font-medium text-amber-700 dark:text-amber-400 mb-1">
                          Unmeasured — {sov.unmeasured_total} not collected
                        </div>
                        <p className="text-xs text-slate-500 dark:text-gray-400 mb-1">
                          Post collection has never succeeded for these, so we
                          cannot say whether they are quiet.
                        </p>
                        <div className="divide-y">
                          {sov.unmeasured.slice(0, 10).map(v => (
                            <button key={v.brand_id} onClick={() => onVendor(v.brand_id)}
                                    className="w-full py-1.5 text-sm text-left
                                               text-slate-700 hover:bg-slate-50
                                               dark:text-gray-300 dark:hover:bg-gray-700">
                              {v.vendor}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
          </Panel>

          {mix && mix.by_month.length > 0 && (
            <Panel title="Where the coverage comes from">
              <p className="text-xs text-slate-500 mt-0.5 mb-2 dark:text-gray-400">
                {mix.total} items by month and kind. Vendor posts dominate by
                volume throughout, which is why they are shown apart from
                everything else rather than summed with it.
              </p>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={mix.by_month}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="news" stackId="c" fill={INK} name="News" />
                  <Bar dataKey="vendor" stackId="c" fill="#d6409f" name="Vendor blogs" />
                  <Bar dataKey="social" stackId="c" fill={SOCIAL} name="Vendor posts" />
                  <Bar dataKey="discussion" stackId="c" fill={DISCUSSION} name="Practitioners" />
                  <Bar dataKey="research" stackId="c" fill={RESEARCH} name="Research" />
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          )}
        </div>
      )}

      {/* ---- Top voices ---- */}
      {sov && !sov.error && sov.vendors.length > 0 && (
        <Panel title="Top voices">
          {voices ? (
            <>
              <CoverageLine
                coverage={voices.coverage}
                note="Accounts posting about the market. Vendors' own company posts are excluded — they are counted as owned above." />
              <DataTable
                rows={voices.voices}
                rowKey={v => `${v.platform}:${v.author}`}
                initialSort="engagement" initialDir="desc"
                columns={[
                  { key: 'author', label: 'Account', groupable: false,
                    // Opens every relevant post by this account. A ranked
                    // handle whose posts cannot be read is an assertion.
                    render: v => onRecords ? (
                      <button
                        onClick={e => { e.stopPropagation();
                                        onRecords({
                                          kind: 'voice',
                                          title: `@${v.author}: posts about this market`,
                                          author: v.author, days,
                                          expectedTotal: v.posts,
                                        }); }}
                        className="text-sky-700 dark:text-sky-400 hover:underline">
                        @{v.author}
                      </button>
                    ) : `@${v.author}` },
                  { key: 'platform', label: 'Platform', groupable: true },
                  // A ranked list of handles with no subject is a list of
                  // strangers. What they talk about is the useful part.
                  { key: 'about', label: 'Talking about', sortable: false,
                    // Capped, or an account naming a dozen terms and
                    // vendors pushes its row tall enough that the table
                    // becomes an endless scroll instead of a scan.
                    render: v => {
                      const terms = v.terms.slice(0, 4);
                      const vendors = v.vendors.slice(0, 3);
                      const extra = (v.terms.length - terms.length)
                        + (v.vendors.length - vendors.length);
                      return (
                        <span className="flex flex-wrap gap-1">
                          {terms.length === 0 && vendors.length === 0 && (
                            <span className="text-slate-400 dark:text-gray-500">—</span>)}
                          {terms.map(t => (
                            <span key={t.term}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                              {t.term}
                            </span>
                          ))}
                          {vendors.map(x => (
                            <span key={x.vendor}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                              {x.vendor}
                            </span>
                          ))}
                          {extra > 0 && (
                            <span className="text-xs text-slate-400 dark:text-gray-500">+{extra} more</span>
                          )}
                        </span>
                      );
                    } },
                  { key: 'posts', label: 'Posts', align: 'right' },
                  { key: 'engagement', label: 'Reactions', align: 'right' },
                  { key: 'last_seen', label: 'Last seen', align: 'right',
                    render: v => (v.last_seen ?? '').slice(0, 10) || '—' },
                ]} />
            </>
          ) : (
            <div className="py-10 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            </div>
          )}
        </Panel>
      )}

      {/* ---- Funding ---- */}
      {fu && !fu.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Funding stage across the market">
            <CoverageLine coverage={fu.coverage}
              note="Latest Crunchbase reading per vendor — not scoped to the period selector above." />
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={fu.stages}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="stage" tick={{ fontSize: 10 }} angle={-20}
                       textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="vendors" fill={INK} name="Vendors" />
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Crunchbase Growth vs Heat">
            <CoverageLine
              coverage={fu.coverage}
              note="Growth and Heat are Crunchbase's own scores, 0-100. We do not compute them, cannot reproduce how they are calculated, and neither is a forecast: Heat is how much attention a company is getting now, not a prediction about it. A company's Crunchbase rank is in the tooltip rather than the dot size, which would make every dot look the same." />
            <ResponsiveContainer width="100%" height={230}>
              <ScatterChart margin={{ left: 4, right: 12, top: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis type="number" dataKey="growth_score" name="Growth"
                       domain={[0, 100]} tick={{ fontSize: 11 }} />
                <YAxis type="number" dataKey="heat_score" name="Attention"
                       domain={[0, 100]} tick={{ fontSize: 11 }} />
                <ZAxis range={[70, 70]} />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  content={({ payload }) => {
                    const p: any = payload?.[0]?.payload;
                    if (!p) return null;
                    return (
                      <div className="bg-white border rounded px-2 py-1 text-xs shadow dark:bg-gray-800">
                        <div className="font-medium">{p.vendor}</div>
                        <div className="text-slate-600 dark:text-gray-400">
                          growth {p.growth_score ?? '—'} · attention {p.heat_score ?? '—'}
                        </div>
                        {p.cb_rank !== null && (
                          <div className="text-slate-500 dark:text-gray-400">
                            Investor-database rank {Number(p.cb_rank).toLocaleString()}
                          </div>
                        )}
                      </div>
                    );
                  }} />
                <Scatter data={fu.momentum} fill={INK}>
                  {fu.momentum.map(m => (
                    <Cell key={m.brand_id} cursor="pointer"
                          onClick={() => onVendor(m.brand_id)} />
                  ))}
                  <LabelList dataKey="vendor" position="top"
                             style={{ fontSize: 9, fill: AXIS_LABEL }} />
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            {(() => {
              // Ranked by the two scores averaged — both already share the
              // 0-100 scale the panel's own caption points out, so this
              // needs no separate normalization step.
              const ranked = fu.momentum
                .filter(m => m.growth_score !== null || m.heat_score !== null)
                .map(m => ({
                  ...m,
                  combined: ((m.growth_score ?? 0) + (m.heat_score ?? 0)) / 2,
                }))
                .sort((a, b) => b.combined - a.combined);
              if (ranked.length < 4) return null;
              const top = ranked.slice(0, 5);
              const bottom = ranked.slice(-5).reverse();
              const Row = (m: typeof ranked[number]) => (
                <button key={m.brand_id} onClick={() => onVendor(m.brand_id)}
                        className="w-full flex items-center justify-between
                                   py-1.5 text-sm hover:bg-slate-50 text-left dark:hover:bg-gray-700">
                  <span className="text-slate-700 dark:text-gray-300">{m.vendor}</span>
                  <span className="text-slate-500 tabular-nums dark:text-gray-400">
                    <span title="Crunchbase Growth, their own score, 0-100. Not ours and not a forecast.">
                      growth {m.growth_score ?? '—'}
                    </span>
                    {' · '}
                    <span title="Crunchbase Heat, their own score, 0-100. Attention now, not a prediction.">
                      attention {m.heat_score ?? '—'}
                    </span>
                  </span>
                </button>
              );
              return (
                <div className="grid gap-4 sm:grid-cols-2 mt-3 pt-3 border-t">
                  <div>
                    <div className="text-xs font-medium text-slate-600 mb-1 dark:text-gray-400">
                      Growing fast and getting noticed — outreach candidates
                    </div>
                    <div className="divide-y">{top.map(Row)}</div>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-slate-600 mb-1 dark:text-gray-400">
                      Slowing down and going quiet
                    </div>
                    <div className="divide-y">{bottom.map(Row)}</div>
                  </div>
                </div>
              );
            })()}
          </Panel>

          {!investorsThin && (
          // Spans the full row on its own rather than sharing a 2-column
          // grid with the two panels above it — a 3rd panel dropped into
          // `grid-cols-2` otherwise leaves an empty cell beside it.
          <Panel title="Investors backing more than one vendor" full>
            <CoverageLine
              coverage={fu.coverage}
              note="Overlap can only appear among the pages we have read." />
            {fu.shared_investors.length === 0 ? (
              <p className="text-sm text-slate-500 py-6 text-center dark:text-gray-400">
                None among the vendors read so far.
              </p>
            ) : (
              <div className="divide-y">
                {onRecords && (
                  <div className="pb-1.5">
                    <button
                      onClick={() => onRecords({
                        kind: 'investors',
                        title: 'Investors backing more than one vendor',
                        expectedTotal: fu.shared_investors.length,
                      })}
                      className="text-xs text-sky-700 dark:text-sky-400 hover:underline">
                      Open the full list, with the evidence behind each
                    </button>
                  </div>
                )}
                {fu.shared_investors.map(inv => (
                  <div key={inv.investor} className="py-1.5">
                    <div className="text-sm text-slate-800 dark:text-gray-100">{inv.investor}</div>
                    <div className="text-xs text-slate-500 dark:text-gray-400">
                      {inv.backing.join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          )}
        </div>
      )}

      <ConfidenceGate panels={analysisThinPanels} />

      {/* ---- Hiring ---- */}
      {hi && !hi.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Observed hiring">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <p className="text-sm text-slate-700 dark:text-gray-300">
                  {hi.openings} open roles were observed across {hi.by_vendor.length} vendors.
                  {hi.by_vendor.length > 0 && (
                    <> Hiring is concentrated: {hi.by_vendor[0].vendor} accounts for{' '}
                      {hi.by_vendor[0].openings} of them{hi.by_vendor.length > 1
                        ? `, with ${hi.by_vendor[1].vendor} accounting for another ${hi.by_vendor[1].openings}.`
                        : '.'}</>
                  )}
                </p>
                <p className="text-xs text-slate-500 mt-1 dark:text-gray-400">
                  The mix of roles can indicate where companies are investing,
                  but is not a direct measure of product maturity or commercial
                  traction.
                </p>
                <CoverageLine coverage={hi.coverage} />
              </div>
              <div className="flex gap-1 shrink-0">
                {(['role', 'function', 'region', 'seniority'] as const).map(k => (
                  <button key={k} onClick={() => setHiringCut(k)}
                          className={`text-xs px-2 py-1 rounded border ${
                            hiringCut === k
                              ? 'bg-slate-800 text-white border-slate-800'
                              : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
                    {k}
                  </button>
                ))}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={
                hiringCut === 'role' ? hi.by_role.slice(0, 12)
                : hiringCut === 'function' ? hi.by_function
                : hiringCut === 'region' ? hi.by_region : hi.by_seniority}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey={hiringCut} tick={{ fontSize: 9 }}
                       angle={hiringCut === 'role' ? -30 : 0}
                       textAnchor={hiringCut === 'role' ? 'end' : 'middle'}
                       height={hiringCut === 'role' ? 80 : 30} interval={0} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="openings" fill={INK} name="Openings" />
              </BarChart>
            </ResponsiveContainer>
            {hiringCut === 'region' && hi.function_by_region.length > 0 && (
              <>
                <p className="text-xs text-slate-500 mt-2 mb-1 dark:text-gray-400">
                  Function within each region. Engineering in one place and
                  sales in another is a company expanding, not simply hiring.
                </p>
                <DataTable
                  rows={hi.function_by_region as any[]} dense
                  rowKey={r => String(r.region)}
                  columns={[
                    { key: 'region', label: 'Region' },
                    { key: 'engineering', label: 'Eng', align: 'right' },
                    { key: 'sales', label: 'Sales', align: 'right' },
                    { key: 'marketing', label: 'Marketing', align: 'right' },
                    { key: 'operations', label: 'Ops', align: 'right' },
                  ]} />
              </>
            )}
          </Panel>

          <Panel title="Openings per vendor">
            <div className="flex items-start gap-2">
              <div className="flex-1"><CoverageLine coverage={hi.coverage} /></div>
              <button onClick={() => setShowJobs(v => !v)}
                      className="text-xs px-2 py-1 border rounded hover:bg-slate-50 shrink-0 dark:hover:bg-gray-700">
                {showJobs ? 'Show the counts' : 'Show the postings'}
              </button>
            </div>
            {showJobs ? (
              jobs === null ? (
                <div className="py-8 text-center text-slate-400 dark:text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin mx-auto" />
                </div>
              ) : (
                <DataTable<JobPosting>
                  rows={jobs} dense rowKey={j => j.url ?? `${j.vendor}-${j.title}`}
                  initialSort="vendor"
                  columns={[
                    { key: 'vendor', label: 'Vendor', groupable: true },
                    { key: 'title', label: 'Role', href: j => j.url,
                      groupable: false },
                    { key: 'function_group', label: 'Function', groupable: true },
                    { key: 'seniority', label: 'Level', groupable: true },
                    { key: 'location', label: 'Location', groupable: true },
                    { key: 'posted_date', label: 'Posted' },
                  ]} />
              )
            ) : (
              <>
                <DataTable
                  rows={hi.by_vendor} dense rowKey={v => v.brand_id}
                  initialSort="openings" initialDir="desc"
                  onRowClick={v => setOpenVendorRow(
                    openVendorRow === v.brand_id ? null : v.brand_id)}
                  columns={[
                    { key: 'vendor', label: 'Vendor',
                      render: v => (
                        <span className="inline-flex items-center gap-1">
                          {openVendorRow === v.brand_id
                            ? <ChevronDown className="w-3 h-3 text-slate-400 dark:text-gray-500" />
                            : <ChevronRight className="w-3 h-3 text-slate-400 dark:text-gray-500" />}
                          {v.vendor}
                        </span>
                      ) },
                    { key: 'openings', label: 'Open', align: 'right' },
                    { key: 'engineering', label: 'Eng', align: 'right' },
                    { key: 'sales', label: 'Sales', align: 'right' },
                  ]} />
                {/* Expanding a vendor shows what those openings actually are.
                    A count of twenty says a company is hiring; the split says
                    whether it is building or selling. */}
                {openVendorRow !== null && (() => {
                  const v = hi.by_vendor.find(x => x.brand_id === openVendorRow);
                  if (!v) return null;
                  return (
                    <div className="border rounded-lg p-3 bg-slate-50 mt-2 dark:bg-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
                          {v.vendor}
                        </span>
                        <span className="text-xs text-slate-500 dark:text-gray-400">
                          {v.openings} open
                        </span>
                        <div className="flex-1" />
                        <button onClick={() => onVendor(v.brand_id)}
                                className="text-xs px-2 py-1 border rounded
                                           bg-white hover:bg-slate-50 dark:bg-gray-800 dark:hover:bg-gray-700">
                          Open vendor
                        </button>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <div className="text-xs text-slate-500 mb-1 dark:text-gray-400">By function</div>
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(v.by_function)
                              .sort((a, b) => b[1] - a[1])
                              .map(([k, n]) => (
                              <span key={k}
                                    className="text-xs px-1.5 py-0.5 rounded border
                                               bg-white text-slate-700 dark:bg-gray-800 dark:text-gray-300">
                                {k} <span className="text-slate-400 dark:text-gray-500">{n}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500 mb-1 dark:text-gray-400">By role</div>
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(v.by_role)
                              .sort((a, b) => b[1] - a[1])
                              .map(([k, n]) => (
                              <span key={k}
                                    className="text-xs px-1.5 py-0.5 rounded border
                                               bg-white text-slate-700 dark:bg-gray-800 dark:text-gray-300">
                                {k} <span className="text-slate-400 dark:text-gray-500">{n}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
          </Panel>
        </div>
      )}

      <MarketThemesPanel marketId={marketId} />
    </div>
  );
}
