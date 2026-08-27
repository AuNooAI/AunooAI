/**
 * Findings — what changed in this market, as a list a reader can act on.
 *
 * The findings endpoint has carried deduplicated, evidence-backed changes since
 * the findings service shipped, and until this view nothing on the page read
 * it: the tab called "Findings" rendered the analysis dashboard. This view is
 * the list. The dashboard is now the Analysis tab.
 *
 * Two things are kept visible on every row because they are what a reader
 * needs to weigh a finding and what the rest of the page tends to hide:
 * who is saying it (the vendor about itself, or somebody else), and how much
 * it matters. Neither is colour-coded red or green; a launch is not good news
 * and a hiring spike is not bad news.
 */

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink, Loader2 } from 'lucide-react';
import {
  getMarketFindings,
  type MarketFinding, type MarketFindings, type MarketOverview, type MarketPulse,
} from '../../services/marketMonitorApi';
import { DataStateBadge, UnmeasuredNotice } from './MarketMetric';

interface Props {
  marketId: number;
  days: number;
  onVendor: (brandId: number) => void;
  /** Already loaded by the tab for the same period; the strip at the top
   *  reads them rather than fetching twice. */
  overview?: MarketOverview | null;
  pulse?: MarketPulse | null;
}

/** "Vendor: the rest" → the rest, when the prefix is one of the finding's
 *  vendors. The vendor is shown as a chip beside it, so repeating it in the
 *  headline made every row start with the same word twice. */
function headlineOf(f: MarketFinding): string {
  let h = (f.headline || '').trim();
  for (const v of f.vendors) {
    const prefix = `${v.vendor}:`;
    if (h.toLowerCase().startsWith(prefix.toLowerCase())) {
      const rest = h.slice(prefix.length).trim();
      if (rest) { h = rest; break; }
    }
  }
  // A LinkedIn post with no first sentence of its own — "Kamal Shah: Prophet
  // Security's Post", "Full announcement: https://lnkd.in/…" — is not a
  // headline. The first sentence of the body is, when there is one.
  const junk = /(’s|'s) Post$|https?:\/\/|^Full announcement/i;
  if (junk.test(h) && f.summary) {
    const first = f.summary.replace(/\s+/g, ' ').trim()
      .split(/(?<=[.!?])\s+/)[0] || '';
    if (first && first.length >= 12 && !/https?:\/\//.test(first)) {
      return first.length > 160 ? `${first.slice(0, 157)}…` : first;
    }
  }
  return h;
}

/** Who is saying this, in words. */
function saidBy(f: MarketFinding): { label: string; independent: boolean } {
  if (f.non_vendor_source_count > 0) {
    const n = f.non_vendor_source_count;
    return { label: n === 1 ? 'Reported by one outside source'
                            : `Reported by ${n} outside sources`,
             independent: true };
  }
  if (f.corroboration === 'vendor_claim' || f.vendor_voiced) {
    return { label: "The vendor's own claim", independent: false };
  }
  if (f.corroboration === 'single_source') {
    return { label: 'One source', independent: false };
  }
  return { label: f.corroboration.replace(/_/g, ' '), independent: false };
}

function whenOf(f: MarketFinding): string {
  const stamp = f.occurred_at || f.first_observed_at;
  if (!stamp) return 'date unknown';
  const d = new Date(stamp);
  if (Number.isNaN(d.getTime())) return 'date unknown';
  if (f.date_precision === 'month') {
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' });
  }
  const text = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  return f.occurred_at ? text : `first seen ${text}`;
}

function hostOf(uri: string | null): string {
  if (!uri) return '';
  try {
    const h = new URL(uri).hostname;
    return h.startsWith('www.') ? h.slice(4) : h;
  } catch {
    return '';
  }
}

const MATERIALITY_LABEL: Record<string, string> = {
  high: 'Material', medium: 'Notable', low: 'Minor',
};

function MaterialityBadge({ level, reason }: { level: string; reason: string | null }) {
  const weight = level === 'high' ? 'font-semibold text-slate-900 dark:text-gray-100 border-slate-500'
    : level === 'medium' ? 'font-medium text-slate-700 dark:text-gray-200 border-slate-300 dark:border-gray-600'
    : 'text-slate-500 dark:text-gray-400 border-slate-200 dark:border-gray-700';
  return (
    <span className={`text-[11px] px-1.5 py-0.5 rounded border ${weight}`}
          title={reason ?? undefined}>
      {MATERIALITY_LABEL[level] ?? level}
    </span>
  );
}

function FindingRow({ f, onVendor, open, onToggle }: {
  f: MarketFinding; onVendor: (id: number) => void; open: boolean; onToggle: () => void;
}) {
  const by = saidBy(f);
  const evidence = f.strongest_evidence;
  const host = hostOf(evidence?.uri ?? null);
  return (
    <div className="border-b last:border-b-0 dark:border-gray-700">
      <button onClick={onToggle}
              className="w-full text-left px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-gray-700/40">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 text-slate-400 dark:text-gray-500">
            {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              {f.vendors.map(v => (
                <span key={v.brand_id}
                      role="link"
                      onClick={e => { e.stopPropagation(); onVendor(v.brand_id); }}
                      className="text-xs px-1.5 py-0.5 rounded border cursor-pointer
                                 bg-sky-50 text-sky-700 border-sky-200 hover:bg-sky-100
                                 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                  {v.vendor}
                </span>
              ))}
              <span className="text-sm text-slate-900 dark:text-gray-100">
                {headlineOf(f)}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-gray-400">
              <MaterialityBadge level={f.materiality} reason={f.materiality_reason} />
              <span className={by.independent ? 'text-slate-700 dark:text-gray-200' : ''}>
                {by.label}
              </span>
              <span>·</span>
              <span>{whenOf(f)}</span>
              {f.status === 'watch' && (<><span>·</span><span>Watching</span></>)}
              {f.has_contradiction && (<><span>·</span><span>Sources disagree</span></>)}
              {f.evidence_count > 1 && (
                <><span>·</span><span>{f.evidence_count} pieces of evidence</span></>
              )}
            </div>
          </div>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pl-9 space-y-2 text-sm">
          {f.why_it_matters && (
            <p className="text-slate-800 dark:text-gray-200">{f.why_it_matters}</p>
          )}
          {f.summary && (
            <p className="text-slate-600 whitespace-pre-line dark:text-gray-300 max-h-48 overflow-y-auto">
              {f.summary}
            </p>
          )}
          {evidence?.uri && (
            <a href={evidence.uri} target="_blank" rel="noreferrer"
               className="inline-flex items-center gap-1 text-xs text-sky-700 hover:underline dark:text-sky-400">
              <ExternalLink className="w-3 h-3" />
              {host ? `Strongest evidence on ${host}` : 'Strongest evidence'}
            </a>
          )}
          {f.limitations.length > 0 && (
            <ul className="text-xs text-slate-500 list-disc pl-4 dark:text-gray-400">
              {f.limitations.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function MarketFindingsView({ marketId, days, onVendor, overview, pulse }: Props) {
  const [data, setData] = useState<MarketFindings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<string>('all');
  const [onlyIndependent, setOnlyIndependent] = useState(false);
  const [materiality, setMateriality] = useState<string>('all');
  const [open, setOpen] = useState<Set<number>>(new Set());

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getMarketFindings(marketId, { days, pageSize: 500 })
      .then(r => { if (live) setData(r); })
      .catch(e => { if (live) setError(String(e.message ?? e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [marketId, days]);

  const all = data?.data ?? [];
  const themes = useMemo(() => Object.keys(data?.by_theme ?? {}), [data]);

  const shown = useMemo(() => all.filter(f =>
    (theme === 'all' || f.theme === theme)
    && (!onlyIndependent || f.non_vendor_source_count > 0)
    && (materiality === 'all' || f.materiality === materiality)),
    [all, theme, onlyIndependent, materiality]);

  const grouped = useMemo(() => {
    const order = themes.length ? themes : Array.from(new Set(shown.map(f => f.theme)));
    return order
      .map(t => [t, shown.filter(f => f.theme === t)] as [string, MarketFinding[]])
      .filter(([, rows]) => rows.length > 0);
  }, [shown, themes]);

  const independent = all.filter(f => f.non_vendor_source_count > 0).length;
  const material = all.filter(f => f.materiality === 'high').length;
  // The rest of the strip: what the collected channels recorded in the same
  // period. Sums over the measured vendors, so a channel that was not
  // measured for a vendor contributes nothing rather than a zero.
  const totals = (overview?.most_active ?? []).reduce(
    (acc, v) => ({ posts: acc.posts + (v.posts || 0), jobs: acc.jobs + (v.jobs || 0),
                   earned: acc.earned + (v.earned || 0) }),
    { posts: 0, jobs: 0, earned: 0 });
  const metric = data?.meta.metric;
  const synthesis = data?.meta.synthesis;

  const toggle = (id: number) => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  if (loading && !data) {
    return <div className="flex justify-center p-8">
      <Loader2 className="w-6 h-6 animate-spin text-slate-400 dark:text-gray-500" /></div>;
  }
  if (error) {
    return <div className="text-sm text-red-700 dark:text-red-400 p-3 border rounded-lg">{error}</div>;
  }
  if (!data) return null;

  if (metric && !metric.measured) {
    return <UnmeasuredNotice meta={metric} />;
  }

  const executive = data.executive.filter(f => f.non_vendor_source_count > 0 || f.materiality === 'high');

  return (
    <div className="space-y-4">
      {/* The count line: what is here, and how much of it anyone other than
          the vendor has said. */}
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700 dark:text-gray-300">
        <span>
          <span className="font-medium text-slate-900 dark:text-gray-100">{all.length}</span>
          {' '}finding{all.length === 1 ? '' : 's'} in the last {days} days
        </span>
        <span>·</span>
        <span>
          <span className="font-medium text-slate-900 dark:text-gray-100">{independent}</span>
          {' '}reported by someone other than the vendor
        </span>
        <span>·</span>
        <span>
          <span className="font-medium text-slate-900 dark:text-gray-100">{material}</span>
          {' '}material
        </span>
        {metric && <DataStateBadge meta={metric} className="ml-1" />}
      </div>
      {overview && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-gray-400">
          <span><strong className="text-slate-800 dark:text-gray-200">{totals.posts}</strong> posts the vendors published</span>
          <span><strong className="text-slate-800 dark:text-gray-200">{totals.earned}</strong> articles about them by somebody else</span>
          <span><strong className="text-slate-800 dark:text-gray-200">{totals.jobs}</strong> open roles observed</span>
          {pulse && (
            <span><strong className="text-slate-800 dark:text-gray-200">{pulse.headcount_movers.length}</strong> headcount move{pulse.headcount_movers.length === 1 ? '' : 's'} with two readings</span>
          )}
          <span><strong className="text-slate-800 dark:text-gray-200">{overview.quiet_vendors}</strong> of {overview.coverage.vendors} vendors with nothing observed</span>
        </div>
      )}
      {synthesis && synthesis.state !== 'ready' && synthesis.detail && (
        <p className="text-xs text-slate-500 dark:text-gray-400">{synthesis.detail}</p>
      )}
      {all.length > 0 && independent === 0 && (
        <p className="text-xs text-slate-500 dark:text-gray-400">
          Every finding in this period comes from a vendor describing itself.
          That is what the collected evidence contains, not a verdict on the
          vendors. Third-party coverage is attributed to vendors on each corpus
          scan, and findings drawn from it appear once they are synthesised.
        </p>
      )}

      {executive.length > 0 && (
        <div className="border rounded-lg bg-white dark:bg-gray-800">
          <div className="px-3 py-2 border-b text-sm font-medium text-slate-800 dark:text-gray-100 dark:border-gray-700">
            Needs attention
          </div>
          {executive.map(f => (
            <FindingRow key={`x-${f.finding_id}`} f={f} onVendor={onVendor}
                        open={open.has(-f.finding_id)} onToggle={() => toggle(-f.finding_id)} />
          ))}
        </div>
      )}

      {/* Filters. Theme chips carry their counts so an empty theme is visible
          as empty rather than absent. */}
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setTheme('all')}
                className={`text-xs px-2 py-1 rounded border ${theme === 'all'
                  ? 'bg-slate-800 text-white border-slate-800 dark:bg-gray-200 dark:text-gray-900'
                  : 'hover:bg-slate-50 dark:hover:bg-gray-700'}`}>
          All ({all.length})
        </button>
        {themes.map(t => (
          <button key={t} onClick={() => setTheme(t)}
                  className={`text-xs px-2 py-1 rounded border ${theme === t
                    ? 'bg-slate-800 text-white border-slate-800 dark:bg-gray-200 dark:text-gray-900'
                    : 'hover:bg-slate-50 dark:hover:bg-gray-700'}`}>
            {t} ({data.by_theme[t]?.length ?? 0})
          </button>
        ))}
        <div className="flex-1" />
        <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-gray-400">
          <input type="checkbox" checked={onlyIndependent}
                 onChange={e => setOnlyIndependent(e.target.checked)} />
          Only findings someone other than the vendor reported
        </label>
        <select value={materiality} onChange={e => setMateriality(e.target.value)}
                className="text-xs border rounded px-1.5 py-1 bg-white dark:bg-gray-800">
          <option value="all">Any materiality</option>
          <option value="high">Material only</option>
          <option value="medium">Notable and above</option>
        </select>
      </div>

      {shown.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-gray-400 border rounded-lg p-4">
          {all.length === 0
            ? 'Collection succeeded and nothing in the period met the bar for a finding.'
            : 'Nothing matches these filters.'}
        </p>
      ) : grouped.map(([t, rows]) => (
        <div key={t} className="border rounded-lg bg-white dark:bg-gray-800">
          <div className="px-3 py-2 border-b flex items-center justify-between dark:border-gray-700">
            <span className="text-sm font-medium text-slate-800 dark:text-gray-100">{t}</span>
            <span className="text-xs text-slate-500 dark:text-gray-400">
              {rows.length} · {rows.filter(f => f.non_vendor_source_count > 0).length} independently reported
            </span>
          </div>
          {rows.map(f => (
            <FindingRow key={f.finding_id} f={f} onVendor={onVendor}
                        open={open.has(f.finding_id)} onToggle={() => toggle(f.finding_id)} />
          ))}
        </div>
      ))}
    </div>
  );
}
