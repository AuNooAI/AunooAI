/**
 * Vendor detail page.
 *
 * Addressable by URL (?vendor=<brand_id>) so it can be linked. All data comes
 * from a single request; the page needs everything at once.
 */

import { useEffect, useState } from 'react';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts';
import {
  AlertTriangle, ArrowLeft, Briefcase, Check, ExternalLink, FileText, Globe,
  Linkedin, Loader2, ToggleLeft, ToggleRight,
} from 'lucide-react';
import { getVendorDetail, type VendorDetail } from '../../services/marketMonitorApi';

const SEVERITY_TONE: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-slate-50 text-slate-600 border-slate-200',
};

const KIND_ICON: Record<string, typeof Globe> = {
  website_url: Globe, domain: Globe,
  linkedin_company_url: Linkedin, crunchbase_url: FileText,
};

function Panel({ title, hint, children }: {
  title: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="text-sm font-medium text-slate-800">{title}</div>
      {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

const VERDICT_WORD: Record<string, string> = {
  signal: 'announcements', commentary: 'opinion', noise: 'promotion',
};

export function MarketVendorPage({ marketId, brandId, onBack }: {
  marketId: number; brandId: number; onBack: () => void;
}) {
  const [v, setV] = useState<VendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSuperseded, setShowSuperseded] = useState(false);

  useEffect(() => {
    setV(null); setError(null);
    getVendorDetail(marketId, brandId)
      .then(setV)
      .catch(e => setError(String(e.message ?? e)));
  }, [marketId, brandId]);

  if (error) {
    return (
      <div className="p-6">
        <button onClick={onBack} className="text-sm text-slate-600 flex items-center gap-1 mb-3">
          <ArrowLeft className="w-4 h-4" /> Back to vendors
        </button>
        <div className="text-red-600 flex items-start gap-2">
          <AlertTriangle className="w-5 h-5 mt-0.5" />{error}
        </div>
      </div>
    );
  }
  if (!v) {
    return <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>;
  }

  const base = v.baseline ?? {};
  const tax = base.taxonomy ?? {};
  const fund = base.funding_baseline ?? {};
  const metrics = base.metrics ?? {};
  const cb = v.funding ?? {};
  const live = v.identifiers.filter(i => i.live);
  const superseded = v.identifiers.filter(i => !i.live);
  const latest = v.profile_series[v.profile_series.length - 1];

  // The imported baseline is a different measurement, taken at a different
  // time, so it is a reference line rather than the first point of the series.
  const series = v.profile_series
    .filter(p => p.employee_count !== null)
    .map(p => ({
      date: p.observed_at.slice(0, 10),
      staff: Number(p.employee_count),
    }));
  const baselineStaff = metrics.employee_count ?? null;

  return (
    <div className="p-4 space-y-4">
      <button onClick={onBack}
        className="text-sm text-slate-600 flex items-center gap-1 hover:text-slate-900">
        <ArrowLeft className="w-4 h-4" /> Back to vendors
      </button>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">{v.display_name}</h2>
          <p className="text-sm text-slate-600 mt-0.5">
            {[tax.sub_category, base.hq_country,
              base.founded_year ? `founded ${base.founded_year}` : null]
              .filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs px-2 py-1 rounded border bg-slate-50 text-slate-600">
            {v.role}
          </span>
          <span className={`text-xs px-2 py-1 rounded border flex items-center gap-1 ${
            v.collection_enabled
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
              : 'bg-slate-50 text-slate-500'}`}>
            {v.collection_enabled
              ? <ToggleRight className="w-3.5 h-3.5" />
              : <ToggleLeft className="w-3.5 h-3.5" />}
            {v.collection_enabled ? 'watched' : 'not watched'}
          </span>
          {v.is_public && (
            <span className="text-xs px-2 py-1 rounded border bg-blue-50 text-blue-700 border-blue-200">
              published
            </span>
          )}
        </div>
      </div>

      {v.review_tasks.length > 0 && (
        <div className="space-y-2">
          {v.review_tasks.map(t => (
            <div key={t.id} className={`text-sm border rounded-lg p-3 flex items-start gap-2 ${
              SEVERITY_TONE[t.severity] ?? SEVERITY_TONE.low}`}>
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{t.message}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Headcount: LinkedIn readings only, workbook as a reference line. */}
        <Panel title="Headcount" hint="LinkedIn employee count. Dashed line is the imported baseline.">
          {series.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">
              No LinkedIn reading yet.
            </p>
          ) : series.length === 1 ? (
            <div className="py-2">
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-semibold text-slate-800">
                  {series[0].staff}
                </span>
                <span className="text-sm text-slate-500">on {series[0].date}</span>
              </div>
              {baselineStaff != null && (
                <p className="text-sm text-slate-600 mt-2">
                  Baseline {baselineStaff}
                  {Number(baselineStaff) !== series[0].staff && (
                    <> · delta {series[0].staff > Number(baselineStaff) ? '+' : ''}
                      {series[0].staff - Number(baselineStaff)}</>
                  )}
                </p>
              )}
              {/* One point is not a trend. Say when the next one lands rather
                  than drawing a flat line through it. */}
              <p className="text-xs text-slate-500 mt-2">
                1 reading. Collected weekly.
              </p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={series} margin={{ left: 4, right: 12, top: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={11} />
                <YAxis fontSize={11} domain={['auto', 'auto']} />
                <Tooltip />
                {baselineStaff != null && (
                  <ReferenceLine y={Number(baselineStaff)} stroke="#8b8d98"
                    strokeDasharray="4 4"
                    label={{ value: `registry: ${baselineStaff}`, position: 'right',
                             fontSize: 10, fill: '#65636d' }} />
                )}
                <Line type="monotone" dataKey="staff" stroke="#d6409f"
                      strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
          {latest?.followers != null && (
            <p className="text-xs text-slate-500 mt-2">
              Followers: {Number(latest.followers).toLocaleString()}
            </p>
          )}
        </Panel>

        <Panel title="Funding" hint="Source: Crunchbase. Round amounts not available from this dataset.">
          <dl className="text-sm space-y-1.5">
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Registry status</dt>
              <dd className="text-slate-800">
                {fund.status ?? '—'}
                {fund.total_musd != null && ` · $${fund.total_musd}M`}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Rounds</dt>
              <dd className="text-slate-800">{cb.num_funding_rounds ?? '—'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Last round</dt>
              <dd className="text-slate-800">
                {cb.last_funding_type?.replace(/_/g, ' ') ?? '—'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Status</dt>
              <dd className="text-slate-800">
                {[cb.operating_status, cb.ipo_status].filter(Boolean).join(' · ') || '—'}</dd>
            </div>
            {(cb.growth_score != null || cb.cb_rank != null) && (
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Crunchbase</dt>
                <dd className="text-slate-800">
                  {/* growth_trend and heat_trend are also stored, and are
                      numbers rather than a direction — 19, 2, 37. Crunchbase
                      does not document what they count, so they are left out:
                      a figure nobody can read is worse than no figure. */}
                  {cb.growth_score != null && `growth ${cb.growth_score}`}
                  {cb.heat_score != null && ` · heat ${cb.heat_score}`}
                  {cb.cb_rank != null
                    && ` · rank ${Number(cb.cb_rank).toLocaleString()}`}
                </dd>
              </div>
            )}
            {Array.isArray(cb.founders) && cb.founders.length > 0 && (
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Founders</dt>
                <dd className="text-slate-800 text-right">
                  {cb.founders.join(', ')}</dd>
              </div>
            )}
            {cb.acquired_by && (
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Acquired by</dt>
                <dd className="text-slate-800">{cb.acquired_by}</dd>
              </div>
            )}
          </dl>
          {(cb.lead_investors?.length ?? 0) > 0 && (
            <div className="mt-3">
              <div className="text-xs text-slate-500 mb-1">Lead investors</div>
              <div className="flex flex-wrap gap-1">
                {cb.lead_investors.map((i: string) => (
                  <span key={i} className="text-xs bg-slate-100 border rounded px-1.5 py-0.5">
                    {i}
                  </span>
                ))}
              </div>
            </div>
          )}
          {/* The full list, distinct from the leads above. Stored since the
              first Crunchbase run and never shown until now. */}
          {(cb.investors?.length ?? 0) > 0 && (
            <div className="mt-3">
              <div className="text-xs text-slate-500 mb-1">
                All investors ({cb.investors.length})
              </div>
              <div className="flex flex-wrap gap-1">
                {cb.investors.map((i: string) => (
                  <span key={i}
                        className="text-xs bg-white border rounded px-1.5 py-0.5
                                   text-slate-600">
                    {i}
                  </span>
                ))}
              </div>
            </div>
          )}
          {Array.isArray(cb.recent_news) && cb.recent_news.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-slate-500 mb-1">
                Recent news, per Crunchbase
              </div>
              <div className="space-y-1">
                {cb.recent_news.slice(0, 6).map((n: any, i: number) => (
                  <div key={i} className="text-xs">
                    <span className="text-slate-700">{n.title}</span>
                    <span className="text-slate-400">
                      {n.publisher ? ` · ${n.publisher}` : ''}
                      {n.date ? ` · ${String(n.date).slice(0, 10)}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Identifiers" hint="Used to match this vendor across sources.">
        <div className="space-y-1.5">
          {live.map(i => {
            const Icon = KIND_ICON[i.kind] ?? FileText;
            return (
              <div key={i.kind + i.normalized_value}
                   className="flex items-center gap-2 text-sm">
                <Icon className="w-4 h-4 text-slate-400 shrink-0" />
                <span className="text-slate-500 w-36 shrink-0">
                  {i.kind.replace(/_/g, ' ')}</span>
                <a href={i.display_value ?? undefined} target="_blank" rel="noreferrer"
                   className="text-slate-800 truncate hover:underline flex-1">
                  {i.display_value}</a>
                {i.verified ? (
                  <span className="text-xs text-emerald-700 flex items-center gap-0.5 shrink-0">
                    <Check className="w-3 h-3" /> verified</span>
                ) : (
                  <span className="text-xs text-slate-400 shrink-0">unverified</span>
                )}
              </div>
            );
          })}
        </div>
        {superseded.length > 0 && (
          <>
            <button onClick={() => setShowSuperseded(s => !s)}
              className="text-xs text-slate-500 mt-2 hover:text-slate-700">
              {showSuperseded ? 'Hide' : 'Show'} {superseded.length} corrected
            </button>
            {showSuperseded && (
              <div className="mt-2 space-y-1">
                {superseded.map(i => (
                  <div key={i.normalized_value} className="text-xs text-slate-500">
                    <span className="line-through">{i.display_value}</span>
                    {' · '}{String((i.provenance as any)?.superseded_reason ?? 'corrected')}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Panel>

      <Panel title="Announcements"
             hint="Posts naming something that happened — a launch, a raise, a customer, a hire. Everything else this vendor posted is below.">
        {v.announcements.length === 0 ? (
          <p className="text-sm text-slate-500">
            {Object.keys(v.post_verdicts ?? {}).length === 0
              ? 'No posts have been read yet.'
              : 'Nothing this vendor posted stated a fact.'}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5 mb-2 text-xs">
              {(['signal', 'commentary', 'noise'] as const).map(k => (
                v.post_verdicts?.[k] ? (
                  <span key={k} className="px-2 py-0.5 rounded border bg-slate-50
                                           text-slate-600">
                    {VERDICT_WORD[k]} {v.post_verdicts[k]}
                  </span>
                ) : null
              ))}
            </div>
            <div className="space-y-2">
              {v.announcements.map(a => (
                <div key={a.uri}
                     className="text-sm border-b last:border-0 pb-2 last:pb-0">
                  <div className="flex items-start gap-2">
                    <a href={a.url ?? a.uri} target="_blank" rel="noreferrer"
                       className="text-slate-800 hover:underline flex-1">
                      {a.title}
                    </a>
                    <span className="text-xs text-slate-400 tabular-nums shrink-0">
                      {a.publication_date?.slice(0, 10) ?? '—'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    {a.review_kind && (
                      <span className="text-xs px-1.5 py-0.5 rounded border
                                       bg-emerald-50 text-emerald-700
                                       border-emerald-200">
                        {a.review_kind}
                      </span>
                    )}
                    {a.review_reason && (
                      <span className="text-xs text-slate-500">
                        {a.review_reason}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Site changes" hint="Monitored pages and their most recent diff.">
          {v.pages.length === 0 ? (
            <p className="text-sm text-slate-500">No monitored pages.</p>
          ) : (
            <div className="space-y-2">
              {v.pages.map(p => (
                <div key={p.url} className="text-sm border-b last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center justify-between gap-2">
                    <a href={p.url} target="_blank" rel="noreferrer"
                       className="text-slate-800 hover:underline flex items-center gap-1 truncate">
                      {p.title || p.kind || 'page'}
                      <ExternalLink className="w-3 h-3 shrink-0" />
                    </a>
                    <span className="text-xs text-slate-500 shrink-0">
                      {p.observed_at.slice(0, 10)}</span>
                  </div>
                  {p.diff && p.diff.material && (
                    <div className="mt-1 text-xs">
                      {/* The counts say how much moved; the lines are a sample
                          of it. Showing only three added lines without the
                          count reads as a three-line change. */}
                      <div className="text-slate-500 mb-0.5">
                        {p.diff.added_count ?? p.diff.added.length} lines added,{' '}
                        {p.diff.removed_count ?? p.diff.removed.length} removed
                      </div>
                      {p.diff.added.slice(0, 3).map((l, i) => (
                        <div key={`a${i}`} className="text-emerald-700 truncate">+ {l}</div>
                      ))}
                      {p.diff.removed.slice(0, 2).map((l, i) => (
                        <div key={`r${i}`} className="text-red-700 truncate">− {l}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Job postings" hint="Open roles from LinkedIn. Collected twice weekly.">
          {v.jobs.length === 0 ? (
            <p className="text-sm text-slate-500 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-slate-400" />
              No postings collected.
            </p>
          ) : (
            <div className="space-y-1.5">
              {v.jobs.slice(0, 10).map((j, i) => (
                <div key={i} className="text-sm flex items-baseline justify-between gap-3">
                  <span className="text-slate-800 truncate">{j.title}</span>
                  <span className="text-xs text-slate-500 shrink-0">
                    {[j.seniority, j.location].filter(Boolean).join(' · ')}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="LinkedIn posts" hint="Most recent 10.">
          {v.posts.length === 0 ? (
            <p className="text-sm text-slate-500">No posts collected.</p>
          ) : (
            <ol className="space-y-2">
              {v.posts.map(p => (
                <li key={p.uri} className="text-sm">
                  <a href={p.url ?? p.uri} target="_blank" rel="noreferrer"
                     className="text-slate-800 hover:underline">{p.title}</a>
                  <div className="text-xs text-slate-500">
                    {p.publication_date?.slice(0, 10)}</div>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel title="Coverage" hint="Third-party articles attributed to this vendor.">
          {v.coverage_by_category.length === 0 ? (
            <p className="text-sm text-slate-500">No articles attributed.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {v.coverage_by_category.map(c => (
                <span key={c.category}
                      className="text-xs bg-slate-100 border rounded px-1.5 py-0.5">
                  {c.category} · {c.n}
                </span>
              ))}
            </div>
          )}
          {v.recent_coverage.length > 0 && (
            <ol className="space-y-1.5 mt-3">
              {v.recent_coverage.slice(0, 5).map(a => (
                <li key={a.uri} className="text-sm">
                  <a href={a.url ?? a.uri} target="_blank" rel="noreferrer"
                     className="text-slate-800 hover:underline">{a.title}</a>
                  <div className="text-xs text-slate-500">
                    {a.news_source} · {a.publication_date?.slice(0, 10)}</div>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  );
}
