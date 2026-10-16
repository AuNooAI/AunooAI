import { useId } from 'react';
import './ScatterChart.css';

export interface ScatterPoint {
  id: string;
  /** Written next to the dot, and in the data table. */
  label: string;
  x: number;
  y: number;
  /** Categorical slot (--viz-series-N). */
  color: 1 | 2 | 3 | 4 | 5;
}

export interface ScatterChartProps {
  title: string;
  xLabel: string;
  yLabel: string;
  points: ScatterPoint[];
  /** Both axes run 0 to this (default 100). */
  max?: number;
  formatValue?: (value: number) => string;
  emptyText?: string;
  className?: string;
}

const TICKS = [0, 0.25, 0.5, 0.75, 1];
// Plot box inside the 100 × 70 viewBox, leaving room for tick labels
const X0 = 12;
const X1 = 96;
const Y0 = 60;
const Y1 = 4;

/** Labelled dots on two 0–max axes. Each dot carries its name; a data table has the values. */
export function ScatterChart({ title, xLabel, yLabel, points, max = 100, formatValue = String, emptyText = 'No data to chart yet.', className }: ScatterChartProps) {
  const id = useId();
  if (points.length === 0) return <p className={['scatter-chart__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  const sx = (v: number) => X0 + (Math.min(max, Math.max(0, v)) / max) * (X1 - X0);
  const sy = (v: number) => Y0 - (Math.min(max, Math.max(0, v)) / max) * (Y0 - Y1);

  return (
    <figure className={['scatter-chart', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <div className="scatter-chart__plot">
        <svg className="scatter-chart__svg" viewBox="0 0 100 70" aria-hidden="true">
          {TICKS.map((t) => (
            <line key={t} className="scatter-chart__grid" x1={X0} x2={X1} y1={sy(t * max)} y2={sy(t * max)} />
          ))}
          <line className="scatter-chart__axis" x1={X0} x2={X1} y1={Y0} y2={Y0} />
          <line className="scatter-chart__axis" x1={X0} x2={X0} y1={Y0} y2={Y1} />
          {points.map((p) => (
            <circle key={p.id} className={`scatter-chart__dot scatter-chart__dot--${p.color}`} cx={sx(p.x)} cy={sy(p.y)} r="1.6" />
          ))}
        </svg>
        {/* Text is HTML over the plot (x in % of width, y in % of the 70-unit height) */}
        <div aria-hidden="true">
          {TICKS.map((t) => (
            <span key={`y${t}`} className="scatter-chart__tick scatter-chart__tick--y" style={{ left: `${X0 - 1.5}%`, top: `${(sy(t * max) / 70) * 100}%` }}>
              {formatValue(t * max)}
            </span>
          ))}
          {TICKS.map((t) => (
            <span key={`x${t}`} className="scatter-chart__tick scatter-chart__tick--x" style={{ left: `${sx(t * max)}%`, top: `${((Y0 + 2) / 70) * 100}%` }}>
              {formatValue(t * max)}
            </span>
          ))}
          {points.map((p) => {
            const right = sx(p.x) > 80;
            return (
              <span
                key={p.id}
                className={`scatter-chart__name${right ? ' scatter-chart__name--left' : ''}`}
                style={{ left: `${sx(p.x) + (right ? -2.4 : 2.4)}%`, top: `${(sy(p.y) / 70) * 100}%` }}
              >
                {p.label}
              </span>
            );
          })}
        </div>
      </div>
      <div className="scatter-chart__axes" aria-hidden="true">
        <span>↑ {yLabel}</span>
        <span>{xLabel} →</span>
      </div>
      {/* Wrapped: a table ignores the 1px box of .visually-hidden and would widen the page */}
      <div className="visually-hidden">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr><th scope="col">Name</th><th scope="col">{xLabel}</th><th scope="col">{yLabel}</th></tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.id}><th scope="row">{p.label}</th><td>{formatValue(p.x)}</td><td>{formatValue(p.y)}</td></tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
