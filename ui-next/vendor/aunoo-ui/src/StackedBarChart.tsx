import { useId } from 'react';
import './StackedBarChart.css';

export interface StackedSeries {
  id: string;
  label: string;
  /** Categorical slot (--viz-series-N), or 0 for the grey "Other" remainder. */
  color: 0 | 1 | 2 | 3 | 4 | 5;
  /** One value per category (x position). */
  values: number[];
}

export interface StackedBarChartProps {
  /** Names the chart and its data table. */
  title: string;
  /** Short x labels, e.g. "2026-07-24". */
  categories: string[];
  /** Bottom of the stack first. Keep it to five named series plus "Other". */
  series: StackedSeries[];
  /** Most x labels to print; the rest are skipped evenly. */
  maxLabels?: number;
  emptyText?: string;
  className?: string;
}

const W = 100;
const H = 60;

/** Top of the scale: four equal whole steps of 1, 2 or 5 × 10ⁿ. */
const niceMax = (v: number) => {
  const raw = Math.max(1, v / 4);
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p * 4;
};

/**
 * Vertical stacked bars over time (e.g. articles per day by category). A legend names every
 * series; a data table carries the exact numbers for screen readers. Hover a bar for its total.
 */
export function StackedBarChart({ title, categories, series, maxLabels = 8, emptyText = 'No data to chart yet.', className }: StackedBarChartProps) {
  const id = useId();
  const totals = categories.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0));
  if (categories.length === 0 || totals.every((t) => t === 0)) {
    return <p className={['stacked-bar-chart__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  }
  const max = niceMax(Math.max(...totals));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const slot = W / categories.length;
  const barW = slot * 0.72;
  const every = Math.max(1, Math.ceil(categories.length / maxLabels));

  return (
    <figure className={['stacked-bar-chart', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <div className="stacked-bar-chart__body">
        <div className="stacked-bar-chart__y" aria-hidden="true">
          {[...ticks].reverse().map((t) => <span key={t}>{Math.round(t)}</span>)}
        </div>
        <div className="stacked-bar-chart__plot">
          <svg className="stacked-bar-chart__svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
            {ticks.map((t) => (
              <line key={t} className="stacked-bar-chart__grid" x1="0" x2={W} y1={H - (t / max) * H} y2={H - (t / max) * H} />
            ))}
            {categories.map((cat, i) => {
              let y = H;
              return (
                <g key={cat}>
                  <title>{`${cat}: ${totals[i]}`}</title>
                  {series.map((s) => {
                    const h = ((s.values[i] ?? 0) / max) * H;
                    y -= h;
                    return h > 0 ? <rect key={s.id} className={`stacked-bar-chart__bar stacked-bar-chart__bar--${s.color}`} x={i * slot + (slot - barW) / 2} y={y} width={barW} height={h} /> : null;
                  })}
                </g>
              );
            })}
          </svg>
          <div className="stacked-bar-chart__x" aria-hidden="true">
            {categories.map((cat, i) =>
              i % every === 0 ? (
                <span key={cat} style={{ left: `${(i + 0.5) * slot}%` }}>{cat}</span>
              ) : null,
            )}
          </div>
        </div>
      </div>
      <ul className="stacked-bar-chart__legend" aria-hidden="true">
        {series.map((s) => (
          <li key={s.id}>
            <span className={`stacked-bar-chart__key stacked-bar-chart__bar--${s.color}`} />
            {s.label}
          </li>
        ))}
      </ul>
      {/* Wrapped: a table ignores the 1px box of .visually-hidden and would widen the page */}
      <div className="visually-hidden">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            {series.map((s) => <th key={s.id} scope="col">{s.label}</th>)}
            <th scope="col">Total</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((cat, i) => (
            <tr key={cat}>
              <th scope="row">{cat}</th>
              {series.map((s) => <td key={s.id}>{s.values[i] ?? 0}</td>)}
              <td>{totals[i]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
