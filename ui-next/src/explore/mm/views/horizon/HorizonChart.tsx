import { useId, useState } from 'react';
import { ICONS, Text, type IconName } from '@aunoo/ui';
import type { HorizonCuts, HorizonVendor } from '@monolith/marketMonitorApi';
import { labelSpots, labelWidth, spreadDots } from './labels';
import './horizon.css';

/*
 * The map itself, in two shapes over the same dots, as the old MarketHorizonView's HorizonArc and
 * HorizonGrid (the same geometry as the report's SVG in app/services/market_report_html.py).
 *
 * Arc: the angle is the stage, by scale, smallest on the left, so a vendor's life runs left to
 * right; the distance from the base is momentum. Grid: scale across, momentum up, with the stage
 * cuts as vertical lines and the band cuts as horizontal ones.
 */

export type MarkerKey = 'innovating' | 'hiring' | 'funded';
export const MARKER_KEYS: MarkerKey[] = ['innovating', 'hiring', 'funded'];
export const STAGE_KEYS = ['emerging', 'established', 'innovators', 'executors'] as const;
// One icon per stage, standing in for the old sprout, building blocks, rising chart and target
const STAGE_ICON: Record<string, IconName> = { emerging: 'Sparkle', established: 'Buildings', innovators: 'TrendUp', executors: 'Target' };

interface Props {
  shape: 'arc' | 'grid';
  rated: HorizonVendor[];
  cuts: HorizonCuts;
  stageNames: Record<string, string>;
  bandNames: Record<string, string>;
  largeShift: number;
  highlight: MarkerKey | null;
  onVendor: (brandId: number) => void;
}

type Pt = { x: number; y: number };
type Box = { x: number; y: number; w: number; h: number };
const clamp = (n: number) => Math.max(0, Math.min(100, n));
// The largest ring a dot carries, so labels keep clear of it
const ring = (v: HorizonVendor) => (v.funded ? 10.5 : v.hiring ? 9 : v.innovating ? 7.5 : 6);

function StageIcon({ stage, cx, cy, size = 16 }: { stage: string; cx: number; cy: number; size?: number }) {
  const C = ICONS[STAGE_ICON[stage] ?? 'Sparkle'];
  return <C className="hz-stage-icon" x={cx - size / 2} y={cy - size / 2} width={size} height={size} weight="regular" color="currentColor" aria-hidden />;
}

export function HorizonChart({ shape, rated, cuts, stageNames, bandNames, largeShift, highlight, onVendor }: Props) {
  const [hover, setHover] = useState<HorizonVendor | null>(null);
  const arrowId = `hz-arrow-${useId().replace(/:/g, '')}`;
  const rimId = `hz-rim-${useId().replace(/:/g, '')}`;
  const [c1, c2, c3] = [...(cuts.stage_cuts ?? [25, 50, 75])].sort((a, b) => a - b);
  const [b1, b2] = [...(cuts.band_cuts ?? [33, 67])].sort((a, b) => a - b);
  const edges = [0, c1, c2, c3, 100];
  const ordered = [...rated].sort((a, b) => b.scale + b.momentum - (a.scale + a.momentum));

  // ---- Geometry for the chosen shape ----
  let W: number, H: number, place: (v: { scale: number; momentum: number }) => Pt;
  let background: React.ReactNode, labelMaxX: number, labelMaxY: number, legendY: number, legendX: number;
  let obstacles: Box[] = [];
  let bandMarks: (Box & { key: string; word: string; tx: number; anchor: 'middle' | 'end' })[] = [];

  if (shape === 'arc') {
    W = 760; H = 478;
    const cx = W / 2, cy = H - 78, R = 350;
    const angle = (scale: number) => (Math.PI / 180) * (180 - 1.8 * clamp(scale));
    place = (v) => {
      const t = angle(v.scale), d = (R * clamp(v.momentum)) / 100;
      return { x: cx + d * Math.cos(t), y: cy - d * Math.sin(t) };
    };
    const arc = (f: number) => `M ${cx - R * f} ${cy} A ${R * f} ${R * f} 0 0 1 ${cx + R * f} ${cy}`;
    background = (
      <>
        <path d={`${arc(1)} Z`} className="hz-plot" />
        {[b1 / 100, b2 / 100].map((f) => <path key={f} d={arc(f)} className="hz-cut" />)}
        {[c1, c2, c3].map((c) => {
          const t = angle(c);
          return <line key={c} x1={cx} y1={cy} x2={cx + R * Math.cos(t)} y2={cy - R * Math.sin(t)} className="hz-cut" />;
        })}
        <path id={rimId} d={`M ${cx - R - 9} ${cy} A ${R + 9} ${R + 9} 0 0 1 ${cx + R + 9} ${cy}`} fill="none" stroke="none" />
        {STAGE_KEYS.map((key, k) => {
          const t = angle((edges[k] + edges[k + 1]) / 2);
          return (
            <g key={key}>
              <text className="hz-stage"><textPath href={`#${rimId}`} startOffset={`${(edges[k] + edges[k + 1]) / 2}%`} textAnchor="middle">{stageNames[key] ?? key}</textPath></text>
              <StageIcon stage={key} cx={cx + (R + 32) * Math.cos(t)} cy={cy - (R + 32) * Math.sin(t)} />
            </g>
          );
        })}
        {[c1, c2, c3].map((c) => <text key={`a${c}`} className="hz-arrow-text"><textPath href={`#${rimId}`} startOffset={`${c}%`} textAnchor="middle">→</textPath></text>)}
        <text x={cx - R} y={cy + 16} className="hz-caption">← smaller by scale</text>
        <text x={cx + R} y={cy + 16} textAnchor="end" className="hz-caption">larger by scale →</text>
        <text x={cx} y={cy + 16} textAnchor="middle" className="hz-caption">further from the base = more momentum</text>
      </>
    );
    labelMaxX = W;
    labelMaxY = cy + 26;
    legendX = cx - 250;
    legendY = cy + 44;
    const cap = (t: string) => labelWidth(t) * 1.1;
    obstacles = [
      { x: cx - R, y: cy + 6, w: cap('← smaller by scale'), h: 12 },
      { x: cx + R - cap('larger by scale →'), y: cy + 6, w: cap('larger by scale →'), h: 12 },
      { x: cx - cap('further from the base = more momentum') / 2, y: cy + 6, w: cap('further from the base = more momentum'), h: 12 },
    ];
    // Each band name sits on its arc at the top, or at the nearest angle to the top that's clear of dots
    const pre = ordered.map((v) => place(v));
    bandMarks = ([['holding', b1 / 100], ['growing', b2 / 100], ['accelerating', 1]] as [string, number][]).map(([key, f]) => {
      const word = (bandNames[key] ?? key).toLowerCase(), bw = labelWidth(word) * 1.1;
      let best = { px: cx, py: cy - R * f + 6 }, bestGap = -1;
      for (const deg of [90, 100, 80, 110, 70, 120, 60, 130, 50]) {
        const t = (deg * Math.PI) / 180;
        const px = cx + (R * f - 6) * Math.cos(t), py = cy - (R * f - 6) * Math.sin(t);
        const gap = Math.min(999, ...pre.map((d) => Math.hypot(px - d.x, py - d.y)));
        if (gap > bestGap) { best = { px, py }; bestGap = gap; }
        if (gap >= 28) break;
      }
      return { key, word, tx: best.px, anchor: 'middle' as const, x: best.px - bw / 2, y: best.py - 6, w: bw, h: 12 };
    });
  } else {
    W = 760; H = 480;
    const x0 = 50, x1 = 716, y0 = 34, y1 = 406;
    // The momentum axis starts a little below the lowest dot (a multiple of 5, never above 20), so the
    // plot isn't a fifth empty when nobody is near zero. The bottom tick names the floor.
    const lows = rated.map((v) => v.momentum).concat(rated.filter((v) => v.big_move && v.previous).map((v) => v.previous!.momentum));
    const floor = lows.length ? Math.max(0, Math.min(20, 5 * Math.floor((Math.min(...lows) - 3) / 5))) : 0;
    const sx = (s: number) => x0 + ((x1 - x0) * clamp(s)) / 100;
    const sy = (m: number) => y1 - ((y1 - y0) * (clamp(m) - floor)) / (100 - floor);
    place = (v) => ({ x: sx(v.scale), y: sy(v.momentum) });
    background = (
      <>
        <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} className="hz-plot" />
        {([[floor, b1], [b2, 100]] as [number, number][]).map(([lo, hi]) => <rect key={lo} x={x0} y={sy(hi)} width={x1 - x0} height={sy(lo) - sy(hi)} className="hz-band" />)}
        {[b1, b2].map((c) => <line key={`b${c}`} x1={x0} y1={sy(c)} x2={x1} y2={sy(c)} className="hz-cut" />)}
        {[c1, c2, c3].map((c) => <line key={`c${c}`} x1={sx(c)} y1={y0} x2={sx(c)} y2={y1} className="hz-cut" />)}
        {STAGE_KEYS.map((key, k) => {
          const name = stageNames[key] ?? key, mx = (sx(edges[k]) + sx(edges[k + 1])) / 2;
          return (
            <g key={key}>
              <text x={mx + 10} y={y0 - 11} textAnchor="middle" className="hz-stage">{name}</text>
              <StageIcon stage={key} cx={mx + 10 - labelWidth(name) * 0.68 - 14} cy={y0 - 15.5} />
            </g>
          );
        })}
        {[c1, c2, c3].map((c) => <text key={`a${c}`} x={sx(c)} y={y0 - 11} textAnchor="middle" className="hz-arrow-text">→</text>)}
        {[0, c1, c2, c3, 100].map((v) => <text key={`x${v}`} x={sx(v)} y={y1 + 13} textAnchor="middle" className="hz-tick">{v}</text>)}
        {[floor, b1, b2, 100].map((v) => <text key={`y${v}`} x={x0 - 7} y={sy(v) + 3.5} textAnchor="end" className="hz-tick">{v}</text>)}
        <text x={x0} y={y1 + 30} className="hz-caption">← smaller by scale</text>
        <text x={x1} y={y1 + 30} textAnchor="end" className="hz-caption">larger by scale →</text>
        <text x={13} y={(y0 + y1) / 2} textAnchor="middle" className="hz-caption" transform={`rotate(-90 13 ${(y0 + y1) / 2})`}>more momentum →</text>
      </>
    );
    labelMaxX = x1 + 2;
    labelMaxY = y1 + 2;
    legendX = x0 + 20;
    legendY = y1 + 50;
    // Labels stay inside the plot: the gutters around it are obstacles
    obstacles = [{ x: 0, y: 0, w: x0 - 2, h: H }, { x: 0, y: 0, w: W, h: y0 - 2 }, { x: 0, y: y1 + 2, w: W, h: H - y1 }];
    bandMarks = ([['holding', b1], ['growing', b2], ['accelerating', 100]] as [string, number][]).map(([key, top]) => {
      const word = (bandNames[key] ?? key).toLowerCase(), bw = labelWidth(word) * 1.1;
      const px = x1 - 8, py = sy(top) + 8;
      return { key, word, tx: px, anchor: 'end' as const, x: px - bw, y: py - 6, w: bw, h: 12 };
    });
  }

  // Dots closer than 13px are nudged apart (at most 10px) so each one shows
  const spreadPos = spreadDots(ordered.map((v) => place(v)));
  const spread = new Map(ordered.map((v, i) => [v.brand_id, spreadPos[i]]));
  // A large move since the previous map draws a trail from where the vendor was
  const trails = rated.filter((v) => v.big_move && v.previous).map((v) => ({ v, from: place(v.previous!), to: spread.get(v.brand_id)! }));
  const dots = ordered.map((v) => ({ v, ...spread.get(v.brand_id)! }));
  const spots = labelSpots(
    dots.map((d) => ({ x: d.x, y: d.y, ring: ring(d.v), width: labelWidth(d.v.vendor) * 1.1 })),
    12, labelMaxX, labelMaxY, [...bandMarks.map((b) => ({ x: b.x, y: b.y, w: b.w, h: b.h })), ...obstacles],
  );

  // The legend under the plot: the three rings and, when there are any, the trail
  const legendStep = shape === 'arc' ? [0, 220, 440] : [0, 224, 466];
  const legend: [MarkerKey, string][] = [
    ['innovating', 'innovating: top third by product work'],
    ['hiring', 'hiring: top third by open roles per head'],
    ['funded', 'funded: a round in the last year'],
  ];

  return (
    <div className="hz-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="hz-svg" role="img" aria-label={shape === 'arc' ? 'Market Maturity Map: stage by scale, distance by momentum' : 'Market Maturity Map: scale against momentum'}>
        <defs>
          <marker id={arrowId} viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 Z" className="hz-arrowhead" />
          </marker>
        </defs>
        {background}
        {legend.map(([k, text], i) => (
          <g key={k}>
            <circle cx={legendX + legendStep[i]} cy={legendY} r={6} className={`hz-ring-${k}`} />
            <text x={legendX + legendStep[i] + 10} y={legendY + 4} className="hz-legend">{text}</text>
          </g>
        ))}
        {trails.length > 0 && (
          <>
            <line x1={legendX} y1={legendY + 14} x2={legendX + 18} y2={legendY + 14} className="hz-trail" markerEnd={`url(#${arrowId})`} />
            <text x={legendX + 24} y={legendY + 17} className="hz-legend">trail: moved {largeShift} or more points on an axis since the previous map</text>
          </>
        )}
        {trails.map(({ v, from, to }) => (
          <g key={`t${v.brand_id}`}>
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="hz-trail" markerEnd={`url(#${arrowId})`} />
            <circle cx={from.x} cy={from.y} r={3} className="hz-trail" />
          </g>
        ))}
        {dots.map(({ v, x, y }, i) => {
          const s = spots[i];
          const on = !!highlight && !!v[highlight];
          return (
            <g
              key={v.brand_id}
              className={`hz-dot${highlight && !on ? ' hz-dot--dim' : ''}`}
              tabIndex={0}
              role="link"
              aria-label={`${v.vendor}: scale ${Math.round(v.scale)}, momentum ${Math.round(v.momentum)}, ${stageNames[v.tier] ?? v.tier}. Opens the vendor page.`}
              onMouseEnter={() => setHover(v)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(v)}
              onBlur={() => setHover(null)}
              onClick={() => onVendor(v.brand_id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onVendor(v.brand_id); } }}
            >
              {s?.leader && (
                <>
                  <line x1={s.leader.x1} y1={s.leader.y1} x2={s.leader.x2} y2={s.leader.y2} className="hz-leader" />
                  <circle cx={s.leader.x2} cy={s.leader.y2} r={1.8} className="hz-leader-dot" />
                </>
              )}
              {v.innovating && <circle cx={x} cy={y} r={7.5} className="hz-ring-innovating" />}
              {v.hiring && <circle cx={x} cy={y} r={9} className="hz-ring-hiring" />}
              {v.funded && <circle cx={x} cy={y} r={10.5} className="hz-ring-funded" />}
              <circle cx={x} cy={y} r={hover?.brand_id === v.brand_id ? 7 : 5} className={`hz-core ${on ? `hz-fill-${highlight}` : `hz-tier-${v.tier}`}`} />
              {s && <text x={s.tx} y={s.by + 10} textAnchor={s.anchor} className={`hz-label${on ? ' hz-label--on' : ''}`}>{v.vendor}</text>}
            </g>
          );
        })}
        {bandMarks.map((b) => <text key={b.key} x={b.tx} y={b.y + 10} textAnchor={b.anchor} className="hz-bandname">{b.word}</text>)}
      </svg>
      {hover && <Detail v={hover} stageNames={stageNames} />}
    </div>
  );
}

/** Beside the map, for the dot under the pointer: scores, stage, markers, inputs and any analyst weights */
function Detail({ v, stageNames }: { v: HorizonVendor; stageNames: Record<string, string> }) {
  const sign = (n: number) => `${n > 0 ? '+' : ''}${n}`;
  return (
    <div className="hz-detail" aria-hidden>
      <Text variant="label">{v.vendor}</Text>
      <Text variant="caption">
        scale {v.scale} · momentum {v.momentum} · {stageNames[v.tier] ?? v.tier}{v.band ? ` · ${v.band}` : ''}
        {v.innovation != null ? ` · innovation ${v.innovation}${v.innovating ? ' (innovating)' : ''}` : ''}
      </Text>
      {v.shift && (Math.abs(v.shift.scale) >= 1 || Math.abs(v.shift.momentum) >= 1) && (
        <Text variant="caption">Since the previous map: {sign(v.shift.scale)} scale, {sign(v.shift.momentum)} momentum{v.big_move ? ' (a large move)' : ''}</Text>
      )}
      {v.hiring && v.hiring_detail && <Text variant="caption">Hiring: {v.hiring_detail.open_roles} open roles, {Math.round(v.hiring_detail.per_100)} per 100 staff</Text>}
      {v.funded && <Text variant="caption">Funded: {v.funded.round ?? 'round not stated'}, {v.funded.date.slice(0, 7)} ({v.funded.source})</Text>}
      <table>
        <tbody>
          {Object.entries(v.inputs).map(([k, i]) => (
            <tr key={k}>
              <td>{k.replace(/_/g, ' ')}</td>
              <td className="hz-num">{Number.isInteger(i.value) ? i.value : i.value.toFixed(1)}</td>
              <td className="hz-num">p{Math.round(i.percentile)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {v.multipliers && <Text variant="caption">Analyst weights: {Object.entries(v.multipliers).map(([k, m]) => `${k} ×${m}`).join(', ')}</Text>}
      {v.analyst_note && <Text variant="caption">Note: {v.analyst_note}</Text>}
    </div>
  );
}
