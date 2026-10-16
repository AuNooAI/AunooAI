import { useId } from 'react';
import { chartColorClass, type ChartColor } from './chartColors';
import './RadarChart.css';

export interface RadarSeries {
  id: string;
  label: string;
  /** Categorical slot (--viz-series-N) or a sentiment role. Keep it fixed per entity across charts. */
  color: ChartColor;
  /** Dashed outline, e.g. the benchmark. */
  dashed?: boolean;
  /** One value per axis, 0–100. */
  values: number[];
}

export interface RadarChartProps {
  /** Names the chart and its data table. */
  title: string;
  /** Axis names, clockwise from the top. */
  axes: string[];
  series: RadarSeries[];
  /** e.g. `(v) => `${v}%`` */
  formatValue?: (value: number) => string;
  /** Shown instead of the chart when there's nothing to plot. */
  emptyText?: string;
  className?: string;
}

const R = 38;
const RINGS = [25, 50, 75, 100];

/**
 * Spider chart for comparing a few series across the same axes (0–100). The legend names every
 * series and a data table carries the exact values for screen readers.
 */
export function RadarChart({ title, axes, series, formatValue = String, emptyText = 'No data to chart yet.', className }: RadarChartProps) {
  const id = useId();
  if (series.length === 0 || axes.length < 3) {
    return <p className={['radar-chart__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  }
  const point = (axis: number, value: number) => {
    const a = (axis / axes.length) * 2 * Math.PI - Math.PI / 2;
    const r = (Math.max(0, Math.min(100, value)) / 100) * R;
    return [50 + r * Math.cos(a), 50 + r * Math.sin(a)] as const;
  };

  return (
    <figure className={['radar-chart', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <div className="radar-chart__plot">
        <svg className="radar-chart__svg" viewBox="0 0 100 100" aria-hidden="true">
          {RINGS.map((ring) => (
            <polygon key={ring} className="radar-chart__ring" points={axes.map((_, i) => point(i, ring).join(',')).join(' ')} />
          ))}
          {axes.map((_, i) => {
            const [x, y] = point(i, 100);
            return <line key={i} className="radar-chart__spoke" x1="50" y1="50" x2={x} y2={y} />;
          })}
          {series.map((s) => (
            <polygon
              key={s.id}
              className={['radar-chart__area', chartColorClass(s.color), s.dashed && 'radar-chart__area--dashed'].filter(Boolean).join(' ')}
              points={s.values.map((v, i) => point(i, v).join(',')).join(' ')}
            />
          ))}
        </svg>
        {axes.map((name, i) => {
          const [x, y] = point(i, 116);
          const align = x < 45 ? 'end' : x > 55 ? 'start' : 'middle';
          return (
            <span key={name} className={`radar-chart__axis radar-chart__axis--${align}`} style={{ left: `${x}%`, top: `${y}%` }} aria-hidden="true">
              {name}
            </span>
          );
        })}
      </div>
      <ul className="radar-chart__legend" aria-hidden="true">
        {series.map((s) => (
          <li key={s.id}>
            <span className={['radar-chart__key', chartColorClass(s.color), s.dashed && 'radar-chart__key--dashed'].filter(Boolean).join(' ')} />
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
            <th scope="col">Series</th>
            {axes.map((a) => <th key={a} scope="col">{a}</th>)}
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.id}>
              <th scope="row">{s.label}</th>
              {s.values.map((v, i) => <td key={i}>{formatValue(v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
