import './RangeBar.css';

export interface RangeBarProps {
  /** Scale start and end, e.g. 2025 and 2040. */
  min: number;
  max: number;
  /** Highlighted range on the scale. Equal start and end draws a single mark. */
  start: number;
  end: number;
  /** What the range is, for screen readers, e.g. "Near term". */
  label: string;
  /** Data-viz slot for the segment (proposed --viz-series-N). */
  color?: 1 | 2 | 3;
  /** Show the scale ends under the bar. */
  showScale?: boolean;
  /** Extra tick labels between the ends, e.g. [2030, 2035]. */
  ticks?: number[];
  className?: string;
}

/** A highlighted span on a year (or any numeric) scale, e.g. "2027–2030 on 2025–2040". */
export function RangeBar({ min, max, start, end, label, color = 1, showScale = true, ticks = [], className }: RangeBarProps) {
  const span = max - min || 1;
  const pct = (v: number) => ((Math.min(max, Math.max(min, v)) - min) / span) * 100;
  const left = pct(Math.min(start, end));
  const width = Math.max(pct(Math.max(start, end)) - left, 0);
  const text = start === end ? `${label}: ${start}, on a ${min}–${max} scale` : `${label}: ${start}–${end}, on a ${min}–${max} scale`;
  return (
    <div className={['range-bar', `range-bar--${color}`, className].filter(Boolean).join(' ')} role="img" aria-label={text}>
      <div className="range-bar__track">
        <span className="range-bar__segment" style={{ insetInlineStart: `${left}%`, inlineSize: `${width}%` }} data-point={width === 0 ? '' : undefined} />
      </div>
      {showScale && (
        <div className="range-bar__scale" aria-hidden="true">
          <span>{min}</span>
          {ticks.map((t) => (
            <span key={t} className="range-bar__tick" style={{ insetInlineStart: `${pct(t)}%` }}>{t}</span>
          ))}
          <span>{max}</span>
        </div>
      )}
    </div>
  );
}
