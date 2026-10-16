import { useId } from 'react';
import { chartColorClass, type ChartColor } from './chartColors';
import './DonutChart.css';

export interface DonutSegment {
  id: string;
  label: string;
  value: number;
  color: ChartColor;
}

export interface DonutChartProps {
  title: string;
  segments: DonutSegment[];
  /** In the hole, e.g. the total. */
  centerLabel?: React.ReactNode;
  emptyText?: string;
  className?: string;
}

const R = 15.9155; // circumference 100, so dash lengths are percentages
const RING = 6; // ring thickness in the 42-unit viewBox

/** Share of a whole. The legend lists every segment with its count and percentage. */
export function DonutChart({ title, segments, centerLabel, emptyText = 'No data to chart yet.', className }: DonutChartProps) {
  const id = useId();
  const total = segments.reduce((s, x) => s + x.value, 0);
  if (total === 0) return <p className={['donut-chart__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  let offset = 25; // start at 12 o'clock
  const pct = (v: number) => Math.round((v / total) * 1000) / 10;
  return (
    <figure className={['donut-chart', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">
        {title}: {segments.map((s) => `${s.label} ${s.value} (${pct(s.value)}%)`).join(', ')}
      </figcaption>
      <div className="donut-chart__plot" aria-hidden="true">
        <svg viewBox="0 0 42 42" className="donut-chart__svg">
          <circle className="donut-chart__track" cx="21" cy="21" r={R} strokeWidth={RING} />
          {segments.map((s) => {
            const len = (s.value / total) * 100;
            const el = (
              <circle
                key={s.id}
                className={`donut-chart__segment ${chartColorClass(s.color)}`}
                cx="21"
                cy="21"
                r={R}
                strokeWidth={RING}
                strokeDasharray={`${len} ${100 - len}`}
                strokeDashoffset={offset}
              />
            );
            offset -= len;
            return el;
          })}
        </svg>
        {centerLabel !== undefined && <div className="donut-chart__center">{centerLabel}</div>}
      </div>
      <ul className="donut-chart__legend" aria-hidden="true">
        {segments.map((s) => (
          <li key={s.id}>
            <span className={`donut-chart__key ${chartColorClass(s.color)}`} />
            <span className="donut-chart__label">{s.label}</span>
            <span className="donut-chart__value">{s.value} · {pct(s.value)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
