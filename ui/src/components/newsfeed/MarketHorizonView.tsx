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
import { Blocks, ChartNoAxesCombined, Loader2, RefreshCw, Sprout, Target } from 'lucide-react';
import {
  computeMarketHorizon, getMarketHorizon, getHorizonControls, getVendors,
  saveHorizonControls,
  type HorizonVendor, type MarketHorizon, type Vendor,
} from '../../services/marketMonitorApi';
import { Panel } from './MarketAnalysisView';
import { labelSpots, labelWidth, spreadDots } from './horizonLabels';
import { useVendorColours, VendorSwatch } from './vendorColours';
import type { HorizonCuts } from '../../services/marketMonitorApi';

const TIER_ORDER = ['executors', 'innovators', 'established', 'emerging'] as const;
// One icon per stage: a sprout, building blocks, a rising chart, a target.
const STAGE_ICON: Record<string, typeof Sprout> = {
  emerging: Sprout, established: Blocks, innovators: ChartNoAxesCombined, executors: Target,
};
function StageIcon({ stage, cx, cy, size = 16 }: { stage: string; cx: number; cy: number; size?: number }) {
  const Icon = STAGE_ICON[stage] ?? Sprout;
  return <Icon x={cx - size / 2} y={cy - size / 2} width={size} height={size} stroke="#334155" strokeWidth={2} className="dark:stroke-gray-300" />;
}
// The three markers a reader can highlight, with the colour of their ring.
type MarkerKey = 'innovating' | 'hiring' | 'funded';
const MARKERS: { key: MarkerKey; colour: string }[] = [
  { key: 'innovating', colour: '#0f172a' }, { key: 'hiring', colour: '#b45309' }, { key: 'funded', colour: '#1d4ed8' },
];
// One slate tone per stage, light for Emerging through dark for Executing,
// so a dot shows its stage without a loud colour.
const TIER_COLOUR: Record<string, string> = {
  emerging: '#94a3b8', established: '#64748b', innovators: '#475569', executors: '#1e293b',
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
 * The horizon. The angle is the stage, by scale: the smallest vendors on the
 * left, the largest on the right, so a vendor's life runs left to right. The
 * distance from the base is momentum: the outer band is accelerating, the
 * inner band holding. Same geometry as the report's SVG.
 */
function HorizonArc({ rated, onVendor, largeShift = 10, cuts, stageNames, bandNames, highlight = null }: {
  rated: HorizonVendor[]; onVendor?: (brandId: number) => void; largeShift?: number;
  cuts: HorizonCuts; stageNames: Record<string, string>; bandNames: Record<string, string>;
  highlight?: MarkerKey | null;
}) {
  const [hover, setHover] = useState<HorizonVendor | null>(null);
  const W = 760, H = 478, cx = W / 2, cy = H - 78, R = 350;
  const clamp = (n: number) => Math.max(0, Math.min(100, n));
  const angle = (scale: number) => (Math.PI / 180) * (180 - 1.8 * clamp(scale));
  const place = (v: { scale: number; momentum: number }) => {
    const theta = angle(v.scale), d = R * clamp(v.momentum) / 100;
    return { x: cx + d * Math.cos(theta), y: cy - d * Math.sin(theta) };
  };
  const [c1, c2, c3] = [...(cuts.stage_cuts ?? [25, 50, 75])].sort((a, b) => a - b);
  const [b1, b2] = [...(cuts.band_cuts ?? [33, 67])].sort((a, b) => a - b);
  const edges = [0, c1, c2, c3, 100];
  const stageKeys = ['emerging', 'established', 'innovators', 'executors'];
  // Dots closer than 13 px are nudged apart so each is visible; the nudge
  // is capped at 10 px from where the scores put the dot.
  const ordered = [...rated].sort((a, b) => (b.scale + b.momentum) - (a.scale + a.momentum));
  const spreadPos = spreadDots(ordered.map(v => place(v)));
  const spread = new Map(ordered.map((v, i) => [v.brand_id, spreadPos[i]]));
  // A large move since the previous map: a trail from where the vendor was.
  const trails = rated.filter(v => v.big_move && v.previous)
    .map(v => ({ v, from: place(v.previous!), to: spread.get(v.brand_id)! }));
  const arc = (f: number) => {
    const d = R * f;
    return `M ${cx - d} ${cy} A ${d} ${d} 0 0 1 ${cx + d} ${cy}`;
  };
  // Labels must not sit on another label, on any dot or on a leader line;
  // see horizonLabels.ts. Labels stay above the axis captions.
  const dots = ordered.map(v => ({ v, ...spread.get(v.brand_id)! }));
  const ring = (v: HorizonVendor) => v.funded ? 10.5 : v.hiring ? 9 : v.innovating ? 7.5 : 6;
  // The band names sit on the centre line inside each arc, drawn after the
  // dots with a halo; the vendor labels keep off them.
  // Each sits on its arc at the top, or failing a clear spot there, at the
  // nearest angle to the top that is clear of dots.
  const bandMarks = ([['holding', b1 / 100], ['growing', b2 / 100], ['accelerating', 1]] as [string, number][])
    .map(([key, f]) => {
      const word = (bandNames[key] ?? key).toLowerCase(), bw = labelWidth(word) * 1.1;
      let best = { px: cx, py: cy - R * f + 6 }, bestGap = -1;
      for (const deg of [90, 100, 80, 110, 70, 120, 60, 130, 50]) {
        const t = deg * Math.PI / 180;
        const px = cx + (R * f - 6) * Math.cos(t), py = cy - (R * f - 6) * Math.sin(t);
        const gap = Math.min(999, ...dots.map(d => Math.hypot(px - d.x, py - d.y)));
        if (gap > bestGap) { best = { px, py }; bestGap = gap; }
        if (gap >= 28) break;
      }
      return { key, word, cx: best.px, x: best.px - bw / 2, y: best.py - 6, w: bw, h: 12 };
    });
  // The axis captions under the base are obstacles too, so a label that
  // drops below the base cannot land on them.
  const cap = (t: string) => labelWidth(t) * 1.1;
  const captions = [
    { x: cx - R, y: cy + 6, w: cap('← smaller by scale'), h: 12 },
    { x: cx + R - cap('larger by scale →'), y: cy + 6, w: cap('larger by scale →'), h: 12 },
    { x: cx - cap('further from the base = more momentum') / 2, y: cy + 6, w: cap('further from the base = more momentum'), h: 12 },
  ];
  const spots = labelSpots(dots.map(d => ({ x: d.x, y: d.y, ring: ring(d.v), width: labelWidth(d.v.vendor) * 1.1 })),
                           12, W, cy + 26, [...bandMarks.map(b => ({ x: b.x, y: b.y, w: b.w, h: b.h })), ...captions]);
  const labels = dots.map(({ v, x, y }, i) => {
    const s = spots[i]!;
    return { v, x, y, lx: s.tx, ly: s.by + 10, anchor: s.anchor, leader: s.leader };
  });
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[760px]" role="img"
           aria-label="Market Maturity Map: position and balance">
        <defs>
          <marker id="mm-hz-arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
          </marker>
        </defs>
        <path d={`${arc(1)} Z`} fill="#f8fafc" stroke="#e2e8f0" className="dark:fill-gray-900" />
        {[b1 / 100, b2 / 100].map(f => (
          <path key={f} d={arc(f)} fill="none" stroke="#cbd5e1" strokeDasharray="4 4" />
        ))}
        {[c1, c2, c3].map(c => {
          const t = angle(c);
          return <line key={c} x1={cx} y1={cy} x2={cx + R * Math.cos(t)} y2={cy - R * Math.sin(t)} stroke="#cbd5e1" strokeDasharray="4 4" />;
        })}
        <path id="mm-hz-rim" d={`M ${cx - R - 9} ${cy} A ${R + 9} ${R + 9} 0 0 1 ${cx + R + 9} ${cy}`} fill="none" stroke="none" />
        {stageKeys.map((key, k) => {
          const t = angle((edges[k] + edges[k + 1]) / 2);
          return (
            <g key={key}>
              <text fontSize={13} fontWeight={600} fill="#334155" letterSpacing={0.3} className="dark:fill-gray-300">
                <textPath href="#mm-hz-rim" startOffset={`${(edges[k] + edges[k + 1]) / 2}%`} textAnchor="middle">{stageNames[key] ?? key}</textPath>
              </text>
              <StageIcon stage={key} cx={cx + (R + 32) * Math.cos(t)} cy={cy - (R + 32) * Math.sin(t)} />
            </g>
          );
        })}
        {[c1, c2, c3].map(cut => (
          <text key={`arrow-${cut}`} fontSize={14} fill="#94a3b8">
            <textPath href="#mm-hz-rim" startOffset={`${cut}%`} textAnchor="middle">→</textPath>
          </text>
        ))}
        <text x={cx - R} y={cy + 16} fontSize={11} fill="#64748b">← smaller by scale</text>
        <text x={cx + R} y={cy + 16} textAnchor="end" fontSize={11} fill="#64748b">larger by scale →</text>
        <text x={cx} y={cy + 16} textAnchor="middle" fontSize={11} fill="#64748b">further from the base = more momentum</text>
        <circle cx={cx - 250} cy={cy + 44} r={6} fill="none" stroke="#0f172a" strokeWidth={1.2} strokeDasharray="2 2" />
        <text x={cx - 240} y={cy + 48} fontSize={10} fill="#64748b">innovating — top third by product work</text>
        <circle cx={cx - 30} cy={cy + 44} r={6} fill="none" stroke="#b45309" strokeWidth={1.6} strokeDasharray="1 2.2" />
        <text x={cx - 20} y={cy + 48} fontSize={10} fill="#64748b">hiring — top third by open roles per head</text>
        <circle cx={cx + 190} cy={cy + 44} r={6} fill="none" stroke="#1d4ed8" strokeWidth={1} />
        <text x={cx + 200} y={cy + 48} fontSize={10} fill="#64748b">funded — a round in the last year</text>
        {trails.length > 0 && (
          <>
            <line x1={cx - 250} y1={cy + 58} x2={cx - 232} y2={cy + 58} stroke="#94a3b8" strokeWidth={1.2} markerEnd="url(#mm-hz-arrow)" />
            <text x={cx - 226} y={cy + 61} fontSize={10} fill="#64748b">trail — moved {largeShift} or more points on an axis since the previous map</text>
          </>
        )}
        {trails.map(({ v, from, to }) => (
          <g key={`trail-${v.brand_id}`}>
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#94a3b8" strokeWidth={1.2} markerEnd="url(#mm-hz-arrow)" />
            <circle cx={from.x} cy={from.y} r={3} fill="none" stroke="#94a3b8" />
          </g>
        ))}
        {labels.map(({ v, x, y, lx, ly, anchor, leader }) => {
          const on = !!highlight && !!v[highlight];
          const hl = on ? MARKERS.find(m => m.key === highlight)!.colour : undefined;
          return (
          <g key={v.brand_id} opacity={highlight && !on ? 0.3 : 1}
             onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)}
             onClick={() => onVendor?.(v.brand_id)}
             style={{ cursor: onVendor ? 'pointer' : 'default' }}>
            {leader && (
              <>
                <line x1={leader.x1} y1={leader.y1} x2={leader.x2} y2={leader.y2} stroke="#64748b" strokeWidth={1} />
                <circle cx={leader.x2} cy={leader.y2} r={1.8} fill="#64748b" />
              </>
            )}
            {v.innovating && (
              <circle cx={x} cy={y} r={7.5} fill="none" stroke="#0f172a" strokeWidth={1.1} strokeDasharray="2 2" />
            )}
            {v.hiring && (
              <circle cx={x} cy={y} r={9} fill="none" stroke="#b45309" strokeWidth={1.4} strokeDasharray="1 2.2" />
            )}
            {v.funded && (
              <circle cx={x} cy={y} r={10.5} fill="none" stroke="#1d4ed8" strokeWidth={1} />
            )}
            <circle cx={x} cy={y} r={hover?.brand_id === v.brand_id ? 7 : 5}
                    fill={hl ?? TIER_COLOUR[v.tier] ?? '#475569'} fillOpacity={hl ? 1 : 0.9} />
            <text x={lx} y={ly} textAnchor={anchor} fontSize={11} fontWeight={on ? 600 : 400}
                  fill="#0f172a" className="dark:fill-gray-200">{v.vendor}</text>
          </g>
          );
        })}
        {bandMarks.map(b => (
          <text key={b.key} x={b.cx} y={b.y + 10} textAnchor="middle" fontSize={11} fontWeight={500} fill="#64748b"
                paintOrder="stroke" stroke="#f8fafc" strokeWidth={4} className="dark:stroke-gray-900">{b.word}</text>
        ))}
      </svg>
      <HoverPanel hover={hover} stageNames={stageNames} />
    </div>
  );
}

/** The panel beside the map for the dot under the pointer: the scores,
 * the stage and band, the markers and any analyst weights or note. */
function HoverPanel({ hover, stageNames }: { hover: HorizonVendor | null; stageNames: Record<string, string> }) {
  if (!hover) return null;
  return (
    <div className="absolute top-2 right-2 bg-white dark:bg-gray-800 border rounded shadow p-2 text-xs max-w-[18rem] pointer-events-none">
      <div className="font-medium text-slate-800 dark:text-gray-100">{hover.vendor}</div>
      <div className="text-slate-500 dark:text-gray-400">
    scale {hover.scale} · momentum {hover.momentum} · {stageNames[hover.tier] ?? hover.tier}{hover.band ? ` · ${hover.band}` : ''}
    {hover.innovation != null && <> · innovation {hover.innovation}{hover.innovating ? ' (innovating)' : ''}</>}
      </div>
      {hover.shift && (Math.abs(hover.shift.scale) >= 1 || Math.abs(hover.shift.momentum) >= 1) && (
    <div className={hover.big_move ? 'text-amber-700 dark:text-amber-400' : 'text-slate-500 dark:text-gray-400'}>
      since previous map: {hover.shift.scale > 0 ? '+' : ''}{hover.shift.scale} scale,{' '}
      {hover.shift.momentum > 0 ? '+' : ''}{hover.shift.momentum} momentum
    </div>
      )}
      {(hover.hiring || hover.funded) && (
    <div className="text-slate-600 dark:text-gray-300">
      {hover.hiring && hover.hiring_detail && (
        <div>hiring: {hover.hiring_detail.open_roles} open roles, {Math.round(hover.hiring_detail.per_100)} per 100 staff</div>
      )}
      {hover.funded && (
        <div>funded: {hover.funded.round ?? 'round not stated'}, {hover.funded.date.slice(0, 7)} ({hover.funded.source})</div>
      )}
    </div>
      )}
      <InputsTable v={hover} />
      {hover.multipliers && (
    <div className="mt-1 text-amber-700 dark:text-amber-400">
      analyst weights: {Object.entries(hover.multipliers).map(([k, m]) => `${k} ×${m}`).join(', ')}
    </div>
      )}
      {hover.analyst_note && (
    <div className="mt-1 text-slate-600 dark:text-gray-300">note: {hover.analyst_note}</div>
      )}
    </div>
  );
}

/**
 * The same vendors on plain axes: scale left to right, momentum bottom to
 * top. The stage cuts are vertical lines and the band cuts horizontal
 * ones. Same dots, rings, labels and hover as the arc; mirrors
 * `_horizon_grid_svg` in app/services/market_report_html.py.
 */
function HorizonGrid({ rated, onVendor, largeShift = 10, cuts, stageNames, bandNames, highlight = null }: {
  rated: HorizonVendor[]; onVendor?: (brandId: number) => void; largeShift?: number;
  cuts: HorizonCuts; stageNames: Record<string, string>; bandNames: Record<string, string>;
  highlight?: MarkerKey | null;
}) {
  const [hover, setHover] = useState<HorizonVendor | null>(null);
  const W = 760, H = 480, x0 = 50, x1 = 716, y0 = 34, y1 = 406;
  const clamp = (n: number) => Math.max(0, Math.min(100, n));
  // The momentum axis starts at a floor below the lowest dot (a multiple of
  // 5, at least 3 below it, never above 20), so the plot is not a fifth
  // empty when nobody is near zero. The tick names the floor.
  const lows = rated.map(v => v.momentum).concat(rated.filter(v => v.big_move && v.previous).map(v => v.previous!.momentum));
  const floor = lows.length ? Math.max(0, Math.min(20, 5 * Math.floor((Math.min(...lows) - 3) / 5))) : 0;
  const sx = (s: number) => x0 + (x1 - x0) * clamp(s) / 100;
  const sy = (m: number) => y1 - (y1 - y0) * (clamp(m) - floor) / (100 - floor);
  const place = (v: { scale: number; momentum: number }) => ({ x: sx(v.scale), y: sy(v.momentum) });
  const [c1, c2, c3] = [...(cuts.stage_cuts ?? [25, 50, 75])].sort((a, b) => a - b);
  const [b1, b2] = [...(cuts.band_cuts ?? [33, 67])].sort((a, b) => a - b);
  const edges = [0, c1, c2, c3, 100];
  const stageKeys = ['emerging', 'established', 'innovators', 'executors'];
  const ordered = [...rated].sort((a, b) => (b.scale + b.momentum) - (a.scale + a.momentum));
  const spreadPos = spreadDots(ordered.map(v => place(v)));
  const spread = new Map(ordered.map((v, i) => [v.brand_id, spreadPos[i]]));
  const trails = rated.filter(v => v.big_move && v.previous)
    .map(v => ({ v, from: place(v.previous!), to: spread.get(v.brand_id)! }));
  const dots = ordered.map(v => ({ v, ...spread.get(v.brand_id)! }));
  const ring = (v: HorizonVendor) => v.funded ? 10.5 : v.hiring ? 9 : v.innovating ? 7.5 : 6;
  // Band names inside their rows at the right edge, drawn after the dots.
  const bandMarks = ([['holding', b1], ['growing', b2], ['accelerating', 100]] as [string, number][])
    .map(([key, top]) => {
      const word = (bandNames[key] ?? key).toLowerCase(), bw = labelWidth(word) * 1.1;
      const px = x1 - 8, py = sy(top) + 8;
      return { key, word, px, x: px - bw, y: py - 6, w: bw, h: 12 };
    });
  // Labels stay inside the plot: the gutters around it are obstacles.
  const gutters = [
    { x: 0, y: 0, w: x0 - 2, h: H }, { x: 0, y: 0, w: W, h: y0 - 2 }, { x: 0, y: y1 + 2, w: W, h: H - y1 },
  ];
  const spots = labelSpots(dots.map(d => ({ x: d.x, y: d.y, ring: ring(d.v), width: labelWidth(d.v.vendor) * 1.1 })),
                           12, x1 + 2, y1 + 2, [...bandMarks.map(b => ({ x: b.x, y: b.y, w: b.w, h: b.h })), ...gutters]);
  const labels = dots.map(({ v, x, y }, i) => {
    const s = spots[i]!;
    return { v, x, y, lx: s.tx, ly: s.by + 10, anchor: s.anchor, leader: s.leader };
  });
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[760px]" role="img"
           aria-label="Market Maturity Map: scale against momentum">
        <defs>
          <marker id="mm-hz-arrow-grid" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
          </marker>
        </defs>
        <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill="#f8fafc" className="dark:fill-gray-900" />
        {([[floor, b1], [b2, 100]] as [number, number][]).map(([lo, hi]) => (
          <rect key={lo} x={x0} y={sy(hi)} width={x1 - x0} height={sy(lo) - sy(hi)} fill="#eef2f6" className="dark:fill-gray-800" />
        ))}
        {[b1, b2].map(cut => (
          <line key={cut} x1={x0} y1={sy(cut)} x2={x1} y2={sy(cut)} stroke="#cbd5e1" strokeDasharray="4 4" />
        ))}
        {[c1, c2, c3].map(cut => (
          <line key={cut} x1={sx(cut)} y1={y0} x2={sx(cut)} y2={y1} stroke="#cbd5e1" strokeDasharray="4 4" />
        ))}
        <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill="none" stroke="#e2e8f0" />
        {stageKeys.map((key, k) => {
          const name = stageNames[key] ?? key, mx = (sx(edges[k]) + sx(edges[k + 1])) / 2;
          return (
            <g key={key}>
              <text x={mx + 10} y={y0 - 11} textAnchor="middle"
                    fontSize={13} fontWeight={600} fill="#334155" letterSpacing={0.3} className="dark:fill-gray-300">
                {name}
              </text>
              <StageIcon stage={key} cx={mx + 10 - labelWidth(name) * 0.68 - 14} cy={y0 - 15.5} />
            </g>
          );
        })}
        {[c1, c2, c3].map(cut => (
          <text key={`arrow-${cut}`} x={sx(cut)} y={y0 - 11} textAnchor="middle" fontSize={14} fill="#94a3b8">→</text>
        ))}
        {[0, c1, c2, c3, 100].map(v => (
          <text key={v} x={sx(v)} y={y1 + 13} textAnchor="middle" fontSize={10} fill="#94a3b8">{v}</text>
        ))}
        {[floor, b1, b2, 100].map(v => (
          <text key={v} x={x0 - 7} y={sy(v) + 3.5} textAnchor="end" fontSize={10} fill="#94a3b8">{v}</text>
        ))}
        <text x={x0} y={y1 + 30} fontSize={11} fill="#64748b">← smaller by scale</text>
        <text x={x1} y={y1 + 30} textAnchor="end" fontSize={11} fill="#64748b">larger by scale →</text>
        <text x={13} y={(y0 + y1) / 2} textAnchor="middle" fontSize={11} fill="#64748b"
              transform={`rotate(-90 13 ${(y0 + y1) / 2})`}>more momentum →</text>
        <circle cx={x0 + 20} cy={y1 + 50} r={6} fill="none" stroke="#0f172a" strokeWidth={1.2} strokeDasharray="2 2" />
        <text x={x0 + 30} y={y1 + 54} fontSize={10} fill="#64748b">innovating — top third by product work</text>
        <circle cx={x0 + 244} cy={y1 + 50} r={6} fill="none" stroke="#b45309" strokeWidth={1.6} strokeDasharray="1 2.2" />
        <text x={x0 + 254} y={y1 + 54} fontSize={10} fill="#64748b">hiring — top third by open roles per head</text>
        <circle cx={x0 + 486} cy={y1 + 50} r={6} fill="none" stroke="#1d4ed8" strokeWidth={1} />
        <text x={x0 + 496} y={y1 + 54} fontSize={10} fill="#64748b">funded — a round in the last year</text>
        {trails.length > 0 && (
          <>
            <line x1={x0 + 38} y1={y1 + 64} x2={x0 + 56} y2={y1 + 64} stroke="#94a3b8" strokeWidth={1.2} markerEnd="url(#mm-hz-arrow-grid)" />
            <text x={x0 + 62} y={y1 + 67} fontSize={10} fill="#64748b">trail — moved {largeShift} or more points on an axis since the previous map</text>
          </>
        )}
        {trails.map(({ v, from, to }) => (
          <g key={`trail-${v.brand_id}`}>
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#94a3b8" strokeWidth={1.2} markerEnd="url(#mm-hz-arrow-grid)" />
            <circle cx={from.x} cy={from.y} r={3} fill="none" stroke="#94a3b8" />
          </g>
        ))}
        {labels.map(({ v, x, y, lx, ly, anchor, leader }) => {
          const on = !!highlight && !!v[highlight];
          const hl = on ? MARKERS.find(m => m.key === highlight)!.colour : undefined;
          return (
          <g key={v.brand_id} opacity={highlight && !on ? 0.3 : 1}
             onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)}
             onClick={() => onVendor?.(v.brand_id)}
             style={{ cursor: onVendor ? 'pointer' : 'default' }}>
            {leader && (
              <>
                <line x1={leader.x1} y1={leader.y1} x2={leader.x2} y2={leader.y2} stroke="#64748b" strokeWidth={1} />
                <circle cx={leader.x2} cy={leader.y2} r={1.8} fill="#64748b" />
              </>
            )}
            {v.innovating && (
              <circle cx={x} cy={y} r={7.5} fill="none" stroke="#0f172a" strokeWidth={1.1} strokeDasharray="2 2" />
            )}
            {v.hiring && (
              <circle cx={x} cy={y} r={9} fill="none" stroke="#b45309" strokeWidth={1.4} strokeDasharray="1 2.2" />
            )}
            {v.funded && (
              <circle cx={x} cy={y} r={10.5} fill="none" stroke="#1d4ed8" strokeWidth={1} />
            )}
            <circle cx={x} cy={y} r={hover?.brand_id === v.brand_id ? 7 : 5}
                    fill={hl ?? TIER_COLOUR[v.tier] ?? '#475569'} fillOpacity={hl ? 1 : 0.9} />
            <text x={lx} y={ly} textAnchor={anchor} fontSize={11} fontWeight={on ? 600 : 400}
                  fill="#0f172a" className="dark:fill-gray-200">{v.vendor}</text>
          </g>
          );
        })}
        {bandMarks.map(b => (
          <text key={b.key} x={b.px} y={b.y + 10} textAnchor="end" fontSize={11} fontWeight={500} fill="#64748b"
                paintOrder="stroke" stroke="#f8fafc" strokeWidth={4} className="dark:stroke-gray-900">{b.word}</text>
        ))}
      </svg>
      <HoverPanel hover={hover} stageNames={stageNames} />
    </div>
  );
}

/**
 * Acquired, closed and pivoted vendors: listed under the map, never placed on it.
 * The form here writes the same per-vendor status the vendor page's
 * controls do, then recomputes, so a sale recorded here shows at once.
 */
function AcquiredPanel({ marketId, horizon, onVendor, onChanged }: {
  marketId: number; horizon: MarketHorizon;
  onVendor?: (brandId: number) => void; onChanged: () => Promise<void>;
}) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [open, setOpen] = useState(false);
  const [brandId, setBrandId] = useState<number | ''>('');
  const [status, setStatus] = useState<'acquired' | 'closed' | 'pivoted'>('acquired');
  const [by, setBy] = useState('');
  const [date, setDate] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState<number | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || vendors.length) return;
    getVendors(marketId).then(setVendors).catch(e => setError(String(e.message ?? e)));
  }, [open, marketId, vendors.length]);

  const listed = new Set(horizon.acquired.map(a => a.brand_id));
  const choices = vendors.filter(v => !listed.has(v.brand_id))
    .sort((a, b) => a.display_name.localeCompare(b.display_name));

  // Keep the analyst's multipliers and note when only the status changes.
  const setStatusFor = async (bid: number, next: {
    status: 'active' | 'acquired' | 'closed' | 'pivoted'; acquired_by?: string | null;
    status_date?: string | null; note?: string | null;
  }) => {
    const cur = (await getHorizonControls(marketId, bid)).controls;
    await saveHorizonControls(marketId, bid, {
      ...cur,
      status: next.status,
      acquired_by: next.status === 'active' ? null : (next.acquired_by ?? cur.acquired_by),
      status_date: next.status === 'active' ? null : (next.status_date ?? cur.status_date),
      note: next.note === undefined ? cur.note : next.note,
    });
  };

  const add = async () => {
    if (brandId === '') return;
    setBusy('new'); setError(null);
    try {
      await setStatusFor(brandId, {
        status, acquired_by: status === 'acquired' ? (by.trim() || null) : null,
        status_date: date || null, note: note.trim() || null,
      });
      await onChanged();
      setBrandId(''); setBy(''); setDate(''); setNote(''); setOpen(false);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const reactivate = async (bid: number) => {
    setBusy(bid); setError(null);
    try {
      await setStatusFor(bid, { status: 'active' });
      await onChanged();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const input = 'text-xs px-2 py-1 rounded border bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-gray-200';
  return (
    <div className="mt-4 border rounded-md p-3 dark:border-gray-700">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
          Acquired, closed and pivoted ({horizon.acquired.length})
        </span>
        <span className="text-xs text-slate-500 dark:text-gray-400">— listed, not placed</span>
        <button onClick={() => setOpen(o => !o)}
                className="ml-auto text-xs px-2 py-1 rounded border bg-white hover:bg-slate-50
                           dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
          {open ? 'Cancel' : 'Mark a vendor acquired, closed or pivoted'}
        </button>
      </div>
      {horizon.acquired.length === 0 && !open && (
        <div className="text-xs text-slate-400 mt-1">none recorded</div>
      )}
      {horizon.acquired.length > 0 && (
        <ul className="text-sm mt-1 space-y-0.5">
          {horizon.acquired.map(a => (
            <li key={a.brand_id} className="flex flex-wrap items-baseline gap-1">
              {onVendor ? (
                <button onClick={() => onVendor(a.brand_id)}
                        className="text-sky-700 dark:text-sky-400 hover:underline">{a.vendor}</button>
              ) : a.vendor}
              <span className="text-xs text-slate-500 dark:text-gray-400">
                — {a.status === 'closed' ? 'closed' : a.status === 'pivoted' ? (a.note ? `pivoted: ${a.note}` : 'pivoted') : a.acquired_by ? `acquired by ${a.acquired_by}` : 'acquired'}
                {a.status_date ? `, ${a.status_date}` : ''}
                {a.note ? ` · ${a.note}` : ''}
              </span>
              <button onClick={() => reactivate(a.brand_id)} disabled={busy !== null}
                      className="text-xs text-slate-400 hover:text-slate-700 hover:underline disabled:opacity-50 dark:hover:text-gray-200"
                      title="Put the vendor back in the rated cohort">
                {busy === a.brand_id ? 'saving…' : 'mark active'}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-[minmax(0,1.4fr)_auto_minmax(0,1fr)_auto_auto] gap-2 items-end">
          <label className="text-xs text-slate-600 dark:text-gray-300">Vendor
            <select className={`${input} block w-full mt-0.5`} value={brandId}
                    onChange={e => setBrandId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">{vendors.length ? 'choose…' : 'loading…'}</option>
              {choices.map(v => (
                <option key={v.brand_id} value={v.brand_id}>
                  {v.display_name}{v.role !== 'vendor' ? ` (${v.role})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600 dark:text-gray-300">Status
            <select className={`${input} block mt-0.5`} value={status}
                    onChange={e => setStatus(e.target.value as 'acquired' | 'closed' | 'pivoted')}>
              <option value="acquired">acquired</option>
              <option value="closed">closed (dead)</option>
              <option value="pivoted">pivoted (left this market; say where in the note)</option>
            </select>
          </label>
          <label className="text-xs text-slate-600 dark:text-gray-300">Acquired by
            <input className={`${input} block w-full mt-0.5`} value={by} disabled={status !== 'acquired'}
                   onChange={e => setBy(e.target.value)} placeholder="acquirer" />
          </label>
          <label className="text-xs text-slate-600 dark:text-gray-300">Date
            <input type="date" className={`${input} block mt-0.5`} value={date}
                   onChange={e => setDate(e.target.value)} />
          </label>
          <button onClick={add} disabled={brandId === '' || busy !== null}
                  className="text-xs px-2.5 py-1.5 rounded-md border bg-slate-800 text-white hover:bg-slate-700
                             disabled:opacity-50 dark:bg-gray-200 dark:text-gray-900">
            {busy === 'new' ? 'Saving…' : 'Save and recompute'}
          </button>
          <label className="text-xs text-slate-600 dark:text-gray-300 md:col-span-5">Note
            <input className={`${input} block w-full mt-0.5`} value={note}
                   onChange={e => setNote(e.target.value)} placeholder="what was bought, or how the closure is known" />
          </label>
        </div>
      )}
      {error && <div className="text-xs text-red-600 dark:text-red-400 mt-1">{error}</div>}
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
  // Two shapes of the same map: the arc reads as a life cycle, the grid as
  // a chart with scale across and momentum up. The choice is remembered.
  const [view, setView] = useState<'arc' | 'grid'>(() => {
    try { return localStorage.getItem('mm-horizon-view') === 'grid' ? 'grid' : 'arc'; } catch { return 'arc'; }
  });
  const [highlight, setHighlight] = useState<MarkerKey | null>(null);
  const colours = useVendorColours(marketId);
  const pickView = (v: 'arc' | 'grid') => {
    setView(v);
    try { localStorage.setItem('mm-horizon-view', v); } catch { /* private mode */ }
  };

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

  const cuts: HorizonCuts = horizon?.config.tiers ?? { stage_cuts: [25, 50, 75], band_cuts: [33, 67] };
  const stageCuts = [...(cuts.stage_cuts ?? [25, 50, 75])].sort((a, b) => a - b);
  const bandCuts = [...(cuts.band_cuts ?? [33, 67])].sort((a, b) => a - b);

  return (
    <div className="space-y-4">
      <Panel title="Market Maturity Map">
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
          <>
            <div className="flex gap-1 mb-2" role="tablist" aria-label="Map shape">
              {(['arc', 'grid'] as const).map(v => (
                <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => pickView(v)}
                        className={`text-xs px-2.5 py-1 rounded-full border ${view === v
                          ? 'bg-slate-700 border-slate-700 text-white dark:bg-gray-200 dark:border-gray-200 dark:text-gray-900'
                          : 'bg-white border-slate-300 text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-300'}`}>
                  {v === 'arc' ? 'Arc' : 'Grid'}
                </button>
              ))}
              <span className="ml-3 text-[11px] text-slate-500 dark:text-gray-400 self-center">Highlight</span>
              {MARKERS.map(m => {
                const n = horizon.rated.filter(r => !!r[m.key]).length;
                const on = highlight === m.key;
                return (
                  <button key={m.key} type="button" aria-pressed={on} onClick={() => setHighlight(on ? null : m.key)}
                          style={on ? { background: m.colour, borderColor: m.colour } : undefined}
                          className={`text-[11px] px-2 py-0.5 rounded-full border ${on ? 'text-white'
                            : 'bg-white border-slate-300 text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-300'}`}>
                    {m.key} <b className="font-semibold">{n}</b>
                  </button>
                );
              })}
            </div>
            {view === 'arc' ? (
              <HorizonArc rated={horizon.rated} onVendor={onVendor} largeShift={horizon.large_shift ?? 10}
                          highlight={highlight}
                          cuts={cuts}
                          stageNames={Object.fromEntries(Object.entries(horizon.tiers).map(([k, v]) => [k, v.label]))}
                          bandNames={Object.fromEntries(Object.entries(horizon.bands ?? {}).map(([k, v]) => [k, v.label]))} />
            ) : (
              <HorizonGrid rated={horizon.rated} onVendor={onVendor} largeShift={horizon.large_shift ?? 10}
                           highlight={highlight}
                           cuts={cuts}
                           stageNames={Object.fromEntries(Object.entries(horizon.tiers).map(([k, v]) => [k, v.label]))}
                           bandNames={Object.fromEntries(Object.entries(horizon.bands ?? {}).map(([k, v]) => [k, v.label]))} />
            )}
          </>
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
                          <VendorSwatch color={colours.byId(r.brand_id)} className="self-center" />
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
                          {r.big_move && r.shift && (
                            <span className="text-xs text-amber-700 dark:text-amber-400"
                                  title="A large move since the previous map">
                              {r.shift.scale > 0 ? '▲' : r.shift.scale < 0 ? '▼' : ''}{Math.abs(r.shift.scale) >= 1 ? ` ${Math.abs(r.shift.scale)} scale ` : ''}
                              {r.shift.momentum > 0 ? '▲' : r.shift.momentum < 0 ? '▼' : ''}{Math.abs(r.shift.momentum) >= 1 ? ` ${Math.abs(r.shift.momentum)} momentum` : ''}
                            </span>
                          )}
                          {!r.previous && horizon.previous_at && (
                            <span className="text-xs text-slate-400" title="Not rated on the previous map">new</span>
                          )}
                          {r.innovating && <span className="text-xs text-slate-500" title="innovating">◌</span>}
                          {r.hiring && r.hiring_detail && (
                            <span className="text-xs text-amber-700 dark:text-amber-400"
                                  title={`${r.hiring_detail.open_roles} open roles, ${Math.round(r.hiring_detail.per_100)} per 100 staff`}>hiring</span>
                          )}
                          {r.funded && (
                            <span className="text-xs text-blue-700 dark:text-blue-400"
                                  title={`${r.funded.round ?? 'round not stated'}, ${r.funded.date} — ${r.funded.source}: ${r.funded.title}`}>funded</span>
                          )}
                          {(r.analyst_note || r.multipliers) && (
                            <span className="text-xs text-amber-700 dark:text-amber-400"
                                  title={[r.multipliers ? 'weights ' + Object.entries(r.multipliers).map(([k, m]) => `${k} ×${m}`).join(', ') : '', r.analyst_note ?? ''].filter(Boolean).join(' — ')}>
                              adjusted
                            </span>
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

        {horizon && horizon.innovating.length > 0 && (
          <div className="mt-4 border rounded-md p-3 dark:border-gray-700">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Innovating ({horizon.innovating.length})
              <span className="text-xs font-normal text-slate-500 dark:text-gray-400"> — a marker across every tier: the top third by launches, corroborated launches, research posts and engineering hiring</span>
            </div>
            <p className="text-sm mt-1">{horizon.innovating.join(', ')}</p>
          </div>
        )}

        {horizon && (horizon.moves?.length ?? 0) > 0 && (
          <div className="mt-4 border rounded-md p-3 border-amber-200 dark:border-amber-800">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Moved ({horizon.moves!.length})
              <span className="text-xs font-normal text-slate-500 dark:text-gray-400">
                {' '}— {horizon.large_shift ?? 10} or more points on an axis since the map of {horizon.previous_at?.slice(0, 10)}
              </span>
            </div>
            <ul className="text-sm mt-1 space-y-0.5">
              {horizon.moves!.map(m => (
                <li key={m.brand_id}>
                  {onVendor ? (
                    <button onClick={() => onVendor(m.brand_id)}
                            className="text-sky-700 dark:text-sky-400 hover:underline">{m.vendor}</button>
                  ) : m.vendor}
                  <span className="text-xs text-slate-500 dark:text-gray-400">
                    {' '}— {[['scale', m.scale], ['momentum', m.momentum]].filter(([, d]) => Math.abs(d as number) >= 1)
                      .map(([a, d]) => `${(d as number) > 0 ? '+' : ''}${d} ${a}`).join(', ')}
                    {m.previous_tier !== m.tier ? `; ${horizon.tiers[m.previous_tier]?.label ?? m.previous_tier} → ${horizon.tiers[m.tier]?.label ?? m.tier}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {horizon && (horizon.markers?.hiring.length ?? 0) > 0 && (
          <div className="mt-4 border rounded-md p-3 dark:border-gray-700">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Hiring ({horizon.markers!.hiring.length})
              <span className="text-xs font-normal text-slate-500 dark:text-gray-400">
                {' '}— a marker across every tier: the top third of rated vendors by open roles per 100 staff,
                with at least {horizon.markers!.min_open_roles} roles open
                {horizon.markers!.hiring_bar != null ? ` (bar: ${Math.round(horizon.markers!.hiring_bar)} per 100)` : ''}
              </span>
            </div>
            <ul className="text-sm mt-1 space-y-0.5">
              {horizon.markers!.hiring.map(h => (
                <li key={h.brand_id}>
                  {onVendor ? (
                    <button onClick={() => onVendor(h.brand_id)}
                            className="text-sky-700 dark:text-sky-400 hover:underline">{h.vendor}</button>
                  ) : h.vendor}
                  <span className="text-xs text-slate-500 dark:text-gray-400">
                    {' '}— {h.open_roles} open roles, {Math.round(h.per_100)} per 100 staff{h.rated ? '' : ' · not on the map'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {horizon && (horizon.markers?.funded.length ?? 0) > 0 && (
          <div className="mt-4 border rounded-md p-3 dark:border-gray-700">
            <div className="text-sm font-medium text-slate-800 dark:text-gray-100">
              Funded ({horizon.markers!.funded.length})
              <span className="text-xs font-normal text-slate-500 dark:text-gray-400">
                {' '}— a round dated inside the last {horizon.markers!.funded_days} days, from the vendor's
                own post, a matched news event or the Crunchbase news list
              </span>
            </div>
            <ul className="text-sm mt-1 space-y-0.5">
              {horizon.markers!.funded.map(f => (
                <li key={f.brand_id}>
                  {onVendor ? (
                    <button onClick={() => onVendor(f.brand_id)}
                            className="text-sky-700 dark:text-sky-400 hover:underline">{f.vendor}</button>
                  ) : f.vendor}
                  <span className="text-xs text-slate-500 dark:text-gray-400" title={f.title}>
                    {' '}— {f.round ?? 'round not stated'}, {f.date} · {f.source}{f.rated ? '' : ' · not on the map'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {horizon && (
          <AcquiredPanel marketId={marketId} horizon={horizon} onVendor={onVendor}
                         onChanged={compute} />
        )}

        {horizon && horizon.acquisition_hints.length > 0 && (
          <div className="mt-4 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md p-2 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800">
            Possibly acquired, not yet marked — confirm on the vendor page:{' '}
            {horizon.acquisition_hints.map((h, i) => (
              <span key={h.brand_id}>
                {i > 0 ? '; ' : ''}
                {onVendor ? (
                  <button onClick={() => onVendor(h.brand_id)} className="underline">{h.vendor}</button>
                ) : h.vendor}
                {' '}({h.why})
              </span>
            ))}
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
              of its inputs. On the map, the angle is the stage, by scale: Emerging under {stageCuts[0]},
              Building from {stageCuts[0]}, Scaling from {stageCuts[1]}, Executing from {stageCuts[2]}, left to
              right. The distance from the base is momentum: holding under {bandCuts[0]}, growing from{' '}
              {bandCuts[0]}, accelerating from {bandCuts[1]}. A vendor moves right as it grows and outward as
              it speeds up. Edit <code>app/config/market_horizon.json</code> to change the cuts.
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
