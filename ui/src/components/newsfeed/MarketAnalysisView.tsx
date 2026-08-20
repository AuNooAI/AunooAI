/**
 * Market Analysis — four cross-sectional reads on a tracked market.
 *
 * Every panel prints its own coverage line. That is not decoration: most of
 * these rest on a subset of the registry, and a chart without its denominator
 * invites the wrong conclusion. "One shared investor" reads as a fragmented
 * market when what it means is that half the Crunchbase pages are unread.
 */

import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts';
import {
  getAnalyses, getChannelMix, getJobPostings, getTopVoices,
  type ChannelMix, type Coverage, type JobPosting, type MarketAnalyses,
  type TopVoices,
} from '../../services/marketMonitorApi';
import { DataTable, type Column } from './DataTable';

const GRID = '#e2e8f0';
const INK = '#475569';
const SIGNAL = '#30a46c';
const COMMENTARY = '#8b93a1';
const NOISE = '#d4d8de';

function CoverageLine({ coverage, note }: { coverage: Coverage; note?: string }) {
  return (
    <p className="text-xs text-slate-500 mt-0.5 mb-2">
      {note ? `${note} ` : ''}
      <span className={coverage.complete ? '' : 'text-amber-700'}>
        Based on {coverage.label}.
      </span>
    </p>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="text-sm font-medium text-slate-800">{title}</div>
      {children}
    </div>
  );
}

export function MarketAnalysisView({ marketId, onVendor, onDrill }: {
  marketId: number;
  onVendor: (brandId: number) => void;
  /** Open a filtered list for a chart segment. Optional so the view still
   *  renders where no drilldown target exists. */
  onDrill?: (kind: string, value: string) => void;
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

  useEffect(() => {
    let live = true;
    setData(null);
    getAnalyses(marketId)
      .then(d => { if (live) setData(d); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId]);

  useEffect(() => {
    let live = true;
    Promise.all([getTopVoices(marketId, undefined, 20), getChannelMix(marketId)])
      .then(([v, m]) => { if (live) { setVoices(v); setMix(m); } })
      .catch(() => {});
    return () => { live = false; };
  }, [marketId]);

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
                           bg-red-50">{error}</div>;
  }
  if (!data) {
    return <div className="py-16 text-center text-slate-400">
      <Loader2 className="w-5 h-5 animate-spin mx-auto" />
    </div>;
  }

  const f = data.formation;
  const sn = data.signal_noise;
  const fu = data.funding;
  const sov = data.share_of_voice;
  const hi = data.hiring;

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
              note={`${f.founded_since_2023} of ${f.vendors_in_scope} were founded in 2023 or later.`} />
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
                    className="text-xs px-2 py-1 border rounded hover:bg-slate-50 shrink-0">
              {sortByShare ? 'Sort by count' : 'Sort by share'}
            </button>
          </div>
          {sortByShare && (
            <p className="text-xs text-slate-500 mb-2">
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
                               text-emerald-700 border-emerald-200">
                {k.kind} <span className="text-emerald-500">{k.n}</span>
              </span>
            ))}
          </div>
        </Panel>
      )}

      {/* ---- Share of voice ---- */}
      {sov && !sov.error && sov.vendors.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Share of voice">
            <CoverageLine
              coverage={sov.coverage}
              note={`Of ${sov.earned_total} mentions by somebody other than the vendor.`} />
            <p className="text-xs text-slate-500 mb-2">
              Share of what <em>other people</em> said. A vendor's own posts are
              not counted here at all — they are volume, not voice, and they are
              in the panel below.
            </p>
            {sov.earned_total === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">
                Nobody outside the vendors has mentioned any of them yet.
              </p>
            ) : (
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
            )}
          </Panel>

          <Panel title="Who shouts loudest, and who is heard">
            <p className="text-xs text-slate-500 mt-0.5 mb-2">
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
                                offset: -12, fontSize: 11, fill: '#64748b' }} />
                <YAxis type="number" dataKey="reactions_per_post"
                       name="Reactions per post" tick={{ fontSize: 11 }}
                       label={{ value: 'reactions per post', angle: -90,
                                position: 'insideLeft', fontSize: 11,
                                fill: '#64748b' }} />
                <ZAxis range={[90, 90]} />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  content={({ payload }) => {
                    const p: any = payload?.[0]?.payload;
                    if (!p) return null;
                    return (
                      <div className="bg-white border rounded px-2 py-1 text-xs shadow">
                        <div className="font-medium">{p.vendor}</div>
                        <div className="text-slate-600">
                          {p.own_posts} posts · {p.reactions_per_post} reactions each
                        </div>
                        <div className="text-slate-500">
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
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <p className="text-xs text-slate-400">
              Vendors with fewer than five measured posts are absent: an average
              over two posts is not an average.
            </p>
          </Panel>

          <Panel title="Top voices">
            {voices ? (
              <>
                <CoverageLine
                  coverage={voices.coverage}
                  note="Accounts posting about the market. Vendors' own company posts are excluded — they are counted as owned above." />
                <DataTable
                  rows={voices.voices} dense
                  rowKey={v => `${v.platform}:${v.author}`}
                  initialSort="posts" initialDir="desc"
                  columns={[
                    { key: 'author', label: 'Account', groupable: false,
                      render: v => `@${v.author}` },
                    { key: 'platform', label: 'Platform', groupable: true },
                    // A ranked list of handles with no subject is a list of
                    // strangers. What they talk about is the useful part.
                    { key: 'about', label: 'Talking about', sortable: false,
                      render: v => (
                        <span className="flex flex-wrap gap-1">
                          {v.terms.length === 0 && (
                            <span className="text-slate-400">—</span>)}
                          {v.terms.map(t => (
                            <span key={t.term}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-slate-50 text-slate-600">
                              {t.term}
                            </span>
                          ))}
                          {v.vendors.map(x => (
                            <span key={x.vendor}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-sky-50 text-sky-700 border-sky-200">
                              {x.vendor}
                            </span>
                          ))}
                        </span>
                      ) },
                    { key: 'posts', label: 'Posts', align: 'right' },
                    { key: 'engagement', label: 'Reactions', align: 'right' },
                  ]} />
              </>
            ) : (
              <div className="py-10 text-center text-slate-400">
                <Loader2 className="w-4 h-4 animate-spin mx-auto" />
              </div>
            )}
          </Panel>

          {mix && mix.by_month.length > 0 && (
            <Panel title="Where the coverage comes from">
              <p className="text-xs text-slate-500 mt-0.5 mb-2">
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
                  <Bar dataKey="news" stackId="c" fill="#475569" name="News" />
                  <Bar dataKey="vendor" stackId="c" fill="#d6409f" name="Vendor blogs" />
                  <Bar dataKey="social" stackId="c" fill="#f5a524" name="Vendor posts" />
                  <Bar dataKey="discussion" stackId="c" fill="#0ea5e9" name="Practitioners" />
                  <Bar dataKey="research" stackId="c" fill="#6366f1" name="Research" />
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          )}
        </div>
      )}

      {/* ---- Funding ---- */}
      {fu && !fu.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Funding stage across the market">
            <CoverageLine coverage={fu.coverage} />
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

          <Panel title="Growth against attention">
            <CoverageLine
              coverage={fu.coverage}
              note="Both scores are Crunchbase's own, 0-100. Crunchbase rank is in the tooltip, not the dot size — it spans 5,900 to 4.4 million and would make every dot the same." />
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
                      <div className="bg-white border rounded px-2 py-1 text-xs shadow">
                        <div className="font-medium">{p.vendor}</div>
                        <div className="text-slate-600">
                          growth {p.growth_score ?? '—'} · attention {p.heat_score ?? '—'}
                        </div>
                        {p.cb_rank !== null && (
                          <div className="text-slate-500">
                            Crunchbase rank {Number(p.cb_rank).toLocaleString()}
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
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Investors backing more than one vendor">
            <CoverageLine
              coverage={fu.coverage}
              note="Overlap can only appear among the pages we have read." />
            {fu.shared_investors.length === 0 ? (
              <p className="text-sm text-slate-500 py-6 text-center">
                None among the vendors read so far.
              </p>
            ) : (
              <div className="divide-y">
                {fu.shared_investors.map(inv => (
                  <div key={inv.investor} className="py-1.5">
                    <div className="text-sm text-slate-800">{inv.investor}</div>
                    <div className="text-xs text-slate-500">
                      {inv.backing.join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {/* ---- Hiring ---- */}
      {hi && !hi.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="What the market is hiring for">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <CoverageLine
                  coverage={hi.coverage}
                  note={`${hi.openings} open listings. Engineering-heavy hiring says a vendor is still building; sales-heavy says it has started selling.`} />
              </div>
              <div className="flex gap-1 shrink-0">
                {(['role', 'function', 'region', 'seniority'] as const).map(k => (
                  <button key={k} onClick={() => setHiringCut(k)}
                          className={`text-xs px-2 py-1 rounded border ${
                            hiringCut === k
                              ? 'bg-slate-800 text-white border-slate-800'
                              : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
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
                <p className="text-xs text-slate-500 mt-2 mb-1">
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
                      className="text-xs px-2 py-1 border rounded hover:bg-slate-50 shrink-0">
                {showJobs ? 'Show the counts' : 'Show the postings'}
              </button>
            </div>
            {showJobs ? (
              jobs === null ? (
                <div className="py-8 text-center text-slate-400">
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
                            ? <ChevronDown className="w-3 h-3 text-slate-400" />
                            : <ChevronRight className="w-3 h-3 text-slate-400" />}
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
                    <div className="border rounded-lg p-3 bg-slate-50 mt-2">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium text-slate-800">
                          {v.vendor}
                        </span>
                        <span className="text-xs text-slate-500">
                          {v.openings} open
                        </span>
                        <div className="flex-1" />
                        <button onClick={() => onVendor(v.brand_id)}
                                className="text-xs px-2 py-1 border rounded
                                           bg-white hover:bg-slate-50">
                          Open vendor
                        </button>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <div className="text-xs text-slate-500 mb-1">By function</div>
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(v.by_function)
                              .sort((a, b) => b[1] - a[1])
                              .map(([k, n]) => (
                              <span key={k}
                                    className="text-xs px-1.5 py-0.5 rounded border
                                               bg-white text-slate-700">
                                {k} <span className="text-slate-400">{n}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500 mb-1">By role</div>
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(v.by_role)
                              .sort((a, b) => b[1] - a[1])
                              .map(([k, n]) => (
                              <span key={k}
                                    className="text-xs px-1.5 py-0.5 rounded border
                                               bg-white text-slate-700">
                                {k} <span className="text-slate-400">{n}</span>
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
    </div>
  );
}
