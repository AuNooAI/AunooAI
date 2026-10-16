import { useId } from 'react';
import { chartColorClass, type ChartColor } from './chartColors';
import './StackedBars.css';

export interface StackedBarsSeries {
  id: string;
  label: string;
  color: ChartColor;
}

export interface StackedBarsRow {
  id: string;
  /** Wraps — long category names are never clipped. */
  label: string;
  /** One value per series, in `series` order. */
  values: number[];
}

export interface StackedBarsProps {
  title: string;
  series: StackedBarsSeries[];
  rows: StackedBarsRow[];
  emptyText?: string;
  className?: string;
}

/** Horizontal stacked bars, one row per item (e.g. sentiment within each category), scaled to the largest total. */
export function StackedBars({ title, series, rows, emptyText = 'No data to chart yet.', className }: StackedBarsProps) {
  const id = useId();
  const totals = rows.map((r) => r.values.reduce((a, b) => a + b, 0));
  const max = Math.max(0, ...totals);
  if (rows.length === 0 || max === 0) return <p className={['stacked-bars__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  return (
    <figure className={['stacked-bars', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <ul className="stacked-bars__legend" aria-hidden="true">
        {series.map((s) => (
          <li key={s.id}><span className={`stacked-bars__key ${chartColorClass(s.color)}`} />{s.label}</li>
        ))}
      </ul>
      <div className="stacked-bars__rows" aria-hidden="true">
        {rows.map((r, i) => (
          <div key={r.id} className="stacked-bars__row">
            <span className="stacked-bars__label">{r.label}</span>
            <span className="stacked-bars__track">
              {r.values.map((v, j) =>
                v > 0 ? (
                  <span key={series[j].id} className={`stacked-bars__segment ${chartColorClass(series[j].color)}`} style={{ width: `${(v / max) * 100}%` }} title={`${series[j].label}: ${v}`} />
                ) : null,
              )}
            </span>
            <span className="stacked-bars__total">{totals[i]}</span>
          </div>
        ))}
      </div>
      <div className="visually-hidden">
        <table>
          <caption>{title}</caption>
          <thead>
            <tr><th scope="col">Item</th>{series.map((s) => <th key={s.id} scope="col">{s.label}</th>)}<th scope="col">Total</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id}><th scope="row">{r.label}</th>{r.values.map((v, j) => <td key={j}>{v}</td>)}<td>{totals[i]}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
