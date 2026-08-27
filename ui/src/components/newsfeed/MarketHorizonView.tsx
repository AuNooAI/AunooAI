/**
 * Market Horizon: every rated vendor on a map of scale against momentum.
 *
 * Not a quadrant of judgement. Both axes are weighted percentile ranks of
 * readings we collect, the weights are printed under the chart, and a vendor
 * is on the map only when every required input was measured. The rest are
 * listed with the reading each one lacks, which is also the collection
 * to-do. Each computation is stored, so the page can say who moved.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import {
  computeMarketHorizon, getMarketHorizon,
  type HorizonVendor, type MarketHorizon,
} from '../../services/marketMonitorApi';
import { Panel } from './MarketAnalysisView';

const TIER_ORDER = ['executors', 'innovators', 'established', 'emerging'] as const;
const TIER_COLOUR: Record<string, string> = {
  executors: '#0f766e', innovators: '#b45309', established: '#1d4ed8', emerging: '#6b7280',
};

/** Every input behind a dot, shown on hover. */
function InputsTable({ v }: { v: HorizonVendor }) {
  return (
    <table className="mt-1">
      <tbody>
        {Object.entries(v.inputs).map(([k, i]) => (
          <tr key={k}>
            <td className="pr-2 text-slate-500 dark:text-gray-400">{k.replace(/_/g, ' ')}</td>
            <td className="pr-2 text-right">{Number.isInteger(i.value) ? i.value : i.value.toFixed(1)}</td>
            <td className="text-right text-slate-500 dark:text-gray-400">p{Math.round(i.percentile)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The horizon. Distance from the base is the overall position (the mean of
 * scale and momentum); the angle is the balance between them — scale-heavy
 * to the left, momentum-heavy to the right, balanced up the middle. The
 * concentric arcs are the horizons. Same geometry as the report's SVG.
 */
function HorizonArc({ rated, onVendor }: {
  rated: HorizonVendor[]; onVendor?: (brandId: number) => void;
}) {
  const [hover, setHover] = useState<HorizonVendor | null>(null);
  const W = 760, H = 440, cx = W / 2, cy = H - 44, R = 350;
  // The angle is the balance between the axes, scaled to the rated set's own
  // spread so the horizon is used whatever the market looks like: the most
  // lopsided vendor sits 80 degrees off the vertical.
  const widest = Math.max(20, ...rated.map(v => Math.abs(v.scale - v.momentum)));
  const perPoint = 80 / widest;
  const place = (v: HorizonVendor) => {
    const pos = (v.scale + v.momentum) / 2;
    const theta = (Math.PI / 180) * (90 + (v.scale - v.momentum) * perPoint);
    const d = R * pos / 100;
    return { x: cx + d * Math.cos(theta), y: cy - d * Math.sin(theta) };
  };
  const arc = (f: number) => {
    const d = R * f;
    return `M ${cx - d} ${cy} A ${d} ${d} 0 0 1 ${cx + d} ${cy}`;
  };
  // Labels, nudged down when they would sit on one already placed.
  const placed: { x: number; y: number; w: number }[] = [];
  const labels = [...rated]
    .sort((a, b) => (b.scale + b.momentum) - (a.scale + a.momentum))
    .map(v => {
      const { x, y } = place(v);
      let lx = x + 7, ly = y + 4;
      const w = 5.5 * v.vendor.length + 4;
      for (let i = 0; i < 4; i++) {
        if (placed.some(p => Math.abs(ly - p.y) < 11 && lx < p.x + p.w && p.x < lx + w)) ly += 11;
        else break;
      }
      placed.push({ x: lx, y: ly, w });
      return { v, x, y, lx, ly };
    });
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[760px]" role="img"
           aria-label="Market Horizon: position and balance">
        <path d={`${arc(1)} Z`} fill="#f8fafc" stroke="#e2e8f0" className="dark:fill-gray-900" />
        {[0.25, 0.5, 0.75].map((f, i) => (
          <g key={f}>
            <path d={arc(f)} fill="none" stroke="#cbd5e1" strokeDasharray="4 4" />
            <text x={cx + R * f + 4} y={cy - 4} fontSize={9} fill="#94a3b8">horizon {i + 1}</text>
          </g>
        ))}
        <text x={cx} y={cy - R - 12} textAnchor="middle" fontSize={11} fill="#64748b">Executors — growing, and already large</text>
        <text x={cx - R + 4} y={cy - 60} fontSize={11} fill="#64748b">Established</text>
        <text x={cx + R - 4} y={cy - 60} textAnchor="end" fontSize={11} fill="#64748b">Innovators</text>
        <text x={cx} y={cy + 16} textAnchor="middle" fontSize={11} fill="#64748b">Emerging — near the base</text>
        <text x={cx - R} y={cy + 30} fontSize={10} fill="#94a3b8">← scale-heavy</text>
        <text x={cx + R} y={cy + 30} textAnchor="end" fontSize={10} fill="#94a3b8">momentum-heavy →</text>
        {labels.map(({ v, x, y, lx, ly }) => (
          <g key={v.brand_id}
             onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)}
             onClick={() => onVendor?.(v.brand_id)}
             style={{ cursor: onVendor ? 'pointer' : 'default' }}>
            <circle cx={x} cy={y} r={hover?.brand_id === v.brand_id ? 7 : 5}
                    fill={TIER_COLOUR[v.tier] ?? '#6b7280'} fillOpacity={0.85} />
            <text x={lx} y={ly} fontSize={10} fill="#0f172a" className="dark:fill-gray-200">{v.vendor}</text>
          </g>
        ))}
      </svg>
      {hover && (
        <div className="absolute top-2 right-2 bg-white dark:bg-gray-800 border rounded shadow p-2 text-xs max-w-[18rem] pointer-events-none">
          <div className="font-medium text-slate-800 dark:text-gray-100">{hover.vendor}</div>
          <div className="text-slate-500 dark:text-gray-400">
            scale {hover.scale} · momentum {hover.momentum} · {hover.tier}
          </div>
          <InputsTable v={hover} />
        </div>
      )}
    </div>
  );
}

export function MarketHorizonView({ marketId, onVendor }: {
  marketId: number;
  onVendor?: (brandId: number) => void;
}) {
  const [horizon, setHorizon] = useState<MarketHorizon | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [computing, setComputing] = useState(false);

  useEffect(() => {
    let live = true;
    setHorizon(undefined); setError(null);
    getMarketHorizon(marketId)
      .then(h => { if (live) setHorizon(h); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId]);

  const compute = async () => {
    setComputing(true); setError(null);
    try {
      setHorizon(await computeMarketHorizon(marketId));
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setComputing(false);
    }
  };

  // The not-rated list, grouped by what is missing, so the collection to-do
  // reads as "47 lack a disclosed funding total" rather than 47 lines.
  const gaps = useMemo(() => {
    const by: Record<string, { label: string; vendors: string[] }> = {};
    for (const nr of horizon?.not_rated ?? []) {
      for (const g of nr.missing) {
        (by[g.key] ??= { label: g.label, vendors: [] }).vendors.push(nr.vendor);
      }
    }
    return Object.values(by).sort((a, b) => b.vendors.length - a.vendors.length);
  }, [horizon]);

  if (error) return <div className="text-sm text-red-600 dark:text-red-400">{error}</div>;
  if (horizon === undefined) {
    return <div className="py-10 text-center text-slate-400"><Loader2 className="w-4 h-4 animate-spin mx-auto" /></div>;
  }

  const cuts = horizon?.config.tiers ?? { scale_cut: 50, momentum_cut: 50 };

  return (
    <div className="space-y-4">
      <Panel title="Market Horizon">
        <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">
          A map of scale against momentum from readings we collect. It does not rate
          product quality, customer satisfaction or strategy. A vendor is on the map only
          when every required input was measured.
        </p>
        <div className="flex flex-wrap items-center gap-2 my-3">
          <button onClick={compute} disabled={computing}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border
                       bg-white hover:bg-slate-50 disabled:opacity-50
                       dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
            {computing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {horizon ? 'Recompute from today\'s readings' : 'Compute the first map'}
          </button>
          {horizon && (
            <span className="text-xs text-slate-500 dark:text-gray-400">
              Computed {horizon.computed_at.slice(0, 10)} over the last {horizon.days} days ·{' '}
              {horizon.counts.rated} of {horizon.counts.eligible} vendors rated
              {horizon.previous_at ? ` · previous map ${horizon.previous_at.slice(0, 10)}` : ''}
            </span>
          )}
        </div>

        {!horizon && (
          <p className="text-sm text-slate-600 dark:text-gray-300">No map yet for this market.</p>
        )}

        {horizon && horizon.rated.length > 0 && (
          <HorizonArc rated={horizon.rated} onVendor={onVendor} />
        )}

        {horizon && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
            {TIER_ORDER.map(tier => {
              const info = horizon.tiers[tier];
              const rows = horizon.rated.filter(r => r.tier === tier);
              return (
                <div key={tier} className="border rounded-md p-3 dark:border-gray-700">
                  <div className="flex items-baseline gap-2">
                    <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: TIER_COLOUR[tier] }} />
                    <span className="text-sm font-medium text-slate-800 dark:text-gray-100">{info?.label ?? tier}</span>
                    <span className="text-xs text-slate-500 dark:text-gray-400">({rows.length}) — {info?.means}</span>
                  </div>
                  {rows.length === 0 ? (
                    <div className="text-xs text-slate-400 mt-1">none</div>
                  ) : (
                    <ul className="mt-1 text-sm space-y-0.5">
                      {rows.map(r => (
                        <li key={r.brand_id} className="flex items-baseline gap-2">
                          {onVendor ? (
                            <button onClick={() => onVendor(r.brand_id)}
                                    className="text-sky-700 dark:text-sky-400 hover:underline">{r.vendor}</button>
                          ) : <span>{r.vendor}</span>}
                          <span className="text-xs text-slate-500 dark:text-gray-400">
                            {Math.round(r.scale)} / {Math.round(r.momentum)}
                          </span>
                          {r.moved && r.previous && (
                            <span className="text-xs text-amber-700 dark:text-amber-400"
                                  title={`Was ${r.previous.tier} (${Math.round(r.previous.scale)} / ${Math.round(r.previous.momentum)}) on the previous map`}>
                              moved from {r.previous.tier}
                            </span>
                          )}
                          {!r.previous && horizon.previous_at && (
                            <span className="text-xs text-slate-400" title="Not rated on the previous map">new</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {horizon && horizon.not_rated.length > 0 && (
          <div className="mt-4">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Not rated ({horizon.not_rated.length})
            </div>
            <p className="text-xs text-slate-500 dark:text-gray-400">
              Each of these lacks at least one required reading. This is the collection to-do.
            </p>
            <ul className="mt-1 space-y-1 text-sm">
              {gaps.map(g => (
                <li key={g.label}>
                  <span className="font-medium text-slate-700 dark:text-gray-200">{g.vendors.length}</span>
                  <span className="text-slate-600 dark:text-gray-300"> lack {g.label.toLowerCase()}: </span>
                  <span className="text-xs text-slate-500 dark:text-gray-400">{g.vendors.join(', ')}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {horizon && (
          <div className="mt-4">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">Weights</div>
            <p className="text-xs text-slate-500 dark:text-gray-400">
              Each input is a percentile rank among the rated vendors; an axis is the weighted mean
              of its inputs. On the map, distance from the base is the mean of the two axes and the
              angle is their balance. At or above {cuts.scale_cut} on scale and {cuts.momentum_cut} on
              momentum is an Executor; high on one only is Established (scale) or an Innovator
              (momentum); below both is Emerging. Edit <code>app/config/market_horizon.json</code> to
              change them.
            </p>
            <table className="mt-1 text-xs">
              <tbody>
                {Object.entries(horizon.config.inputs).map(([k, i]) => (
                  <tr key={k}>
                    <td className="pr-3 py-0.5 text-slate-700 dark:text-gray-200">
                      {i.label}{i.optional ? <span className="text-slate-400"> (optional)</span> : null}
                      {i.note ? <span className="text-slate-400"> — {i.note}</span> : null}
                    </td>
                    <td className="pr-3 text-slate-500 dark:text-gray-400">{i.axis}</td>
                    <td className="text-right text-slate-500 dark:text-gray-400">{i.weight.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
