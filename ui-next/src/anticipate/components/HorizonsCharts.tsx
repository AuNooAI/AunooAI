import { Stack, Text } from '@aunoo/ui';
import { stripCitations } from './CitedText';
import type { Band, Scenario } from '../lib/model';
import './horizonsCharts.css';

/*
 * The Three Horizons chart the old page drew (ui/src/components/foresight/HorizonsView.tsx, ported from
 * the saas renderer): three curves over time, Horizon 1 declining, Horizon 2 peaking mid-way and
 * Horizon 3 rising, with each scenario placed on its horizon's curve at its middle year. The old chart
 * wrote each scenario's title on the curve in a hover card; here each scenario is a numbered marker
 * and the list below spells out its title and years, so nothing overlaps or hides behind a hover.
 */

const VW = 1000;
const VH = 300;
const L = 24;
const R = 976;
const TOP = 18;
const BOT = 280;
const NSEG = 120;
const SPAN = R - L;
const HGT = BOT - TOP;

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const ss = (x: number) => {
  const c = clamp01(x);
  return c * c * (3 - 2 * c);
};

const CURVES: Record<Band, (t: number) => number> = {
  h1: (t) => 0.06 + 0.74 * (1 - ss((t - 0.05) / 0.75)),
  h2: (t) => (t < 0.38 ? 0.42 + 0.2 * ss(t / 0.38) : 0.62 - 0.48 * ss((t - 0.38) / 0.62)),
  h3: (t) => 0.05 + 0.81 * ss((t - 0.28) / 0.78),
};

const X = (t: number) => L + t * SPAN;
const Y = (v: number) => BOT - v * HGT;
const PHASES = ['Present', 'Short-term', 'Mid-term', 'Long-term', 'Horizon'];

export const BAND_META: Record<Band, { label: string; short: string; color: string }> = {
  h1: { label: 'Horizon 1: current, declining', short: 'Current', color: 'var(--viz-series-1)' },
  h2: { label: 'Horizon 2: transition, innovation', short: 'Transition', color: 'var(--viz-series-2)' },
  h3: { label: 'Horizon 3: future, emerging vision', short: 'Future', color: 'var(--viz-series-3)' },
};

function path(f: (t: number) => number, closed: boolean) {
  const pts: string[] = [];
  for (let i = 0; i <= NSEG; i++) pts.push(`${i === 0 ? 'M' : 'L'} ${X(i / NSEG).toFixed(1)} ${Y(f(i / NSEG)).toFixed(1)}`);
  return closed ? `M ${X(0)} ${BOT} ${pts.join(' ').replace(/^M/, 'L')} L ${X(1)} ${BOT} Z` : pts.join(' ');
}

const BANDS: Band[] = ['h1', 'h2', 'h3'];

export function ThreeHorizonsChart({ scenarios }: { scenarios: Scenario[] }) {
  const years = scenarios.flatMap((s) => (s.years ? [s.years.start, s.years.end] : []));
  const now = new Date().getFullYear();
  const lo = years.length ? Math.max(Math.min(...years), now) : now;
  const hi = years.length ? Math.max(Math.max(...years), lo + 1) : now + 15;
  // Scenarios without years sit in the middle of their curve, as on the old chart
  const tOf = (s: Scenario) => (s.years ? clamp01(((s.years.start + s.years.end) / 2 - lo) / Math.max(hi - lo, 1)) : 0.5);
  const numbered = BANDS.flatMap((b) => scenarios.filter((s) => s.band === b)).map((s, i) => ({ s, n: i + 1, t: tOf(s) }));
  // Nudge markers on the same curve apart so their numbers stay readable
  const placed = numbered.map((m, i, all) => {
    const same = all.slice(0, i).filter((o) => o.s.band === m.s.band && Math.abs(o.t - m.t) < 0.05).length;
    const t = clamp01(m.t + same * 0.05);
    return { ...m, x: X(t), y: Y(CURVES[m.s.band](t)) };
  });
  const ticks = [0, 1, 2, 3, 4].map((i) => ({ year: Math.round(lo + ((hi - lo) * i) / 4), phase: PHASES[i] }));
  return (
    <Stack gap="md">
      <figure className="h3-chart" aria-label={`Three Horizons chart, ${lo}–${hi}: Horizon 1 declines, Horizon 2 peaks mid-way and Horizon 3 rises. ${numbered.length} scenarios placed on their curves.`}>
        <div className="h3-chart__stage" aria-hidden="true">
          <svg viewBox={`0 0 ${VW} ${VH}`} preserveAspectRatio="none" className="h3-chart__svg">
            {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={X(i / 4)} y1={TOP} x2={X(i / 4)} y2={BOT} className="h3-chart__grid" />)}
            {(['h3', 'h2', 'h1'] as Band[]).map((b) => <path key={`a${b}`} d={path(CURVES[b], true)} fill={BAND_META[b].color} fillOpacity={0.22} />)}
            {(['h3', 'h2', 'h1'] as Band[]).map((b) => <path key={`l${b}`} d={path(CURVES[b], false)} fill="none" stroke={BAND_META[b].color} strokeWidth={2.5} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />)}
          </svg>
          {placed.map((m) => (
            <span key={m.n} className="h3-chart__mark" style={{ left: `${(m.x / VW) * 100}%`, top: `${(m.y / VH) * 100}%`, borderColor: BAND_META[m.s.band].color }}>
              {m.n}
            </span>
          ))}
        </div>
        <div className="h3-chart__axis" aria-hidden="true">
          {ticks.map((t, i) => (
            <span key={i} style={{ left: `${(X(i / 4) / VW) * 100}%` }}>
              <strong>{t.year}</strong>
              <small>{t.phase}</small>
            </span>
          ))}
        </div>
        <figcaption className="h3-chart__key">
          {BANDS.map((b) => <span key={b}><i style={{ background: BAND_META[b].color }} />{BAND_META[b].label}</span>)}
        </figcaption>
      </figure>
      {numbered.length > 0 && (
        <ol className="h3-chart__list" aria-label="Scenarios on the chart">
          {numbered.map((m) => (
            <li key={m.n}>
              <span className="h3-chart__num" style={{ borderColor: BAND_META[m.s.band].color }} aria-hidden="true">{m.n}</span>
              <Text as="span" variant="caption">
                <strong>{stripCitations(m.s.title)}</strong>
                {` · ${BAND_META[m.s.band].short}${m.s.years ? ` · ${m.s.years.start === m.s.years.end ? m.s.years.start : `${m.s.years.start}–${m.s.years.end}`}` : m.s.timeframe ? ` · ${m.s.timeframe}` : ''}`}
              </Text>
            </li>
          ))}
        </ol>
      )}
    </Stack>
  );
}
