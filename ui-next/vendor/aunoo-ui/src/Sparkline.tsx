import './Sparkline.css';

export interface SparklineProps {
  /** Accessible name and summary, e.g. "30-day trend: 467 articles, rising". */
  label: string;
  /** One value per point, oldest first. */
  values: number[];
  /** Categorical slot (proposed --viz-series-N tokens), as in LineChart. */
  color?: 1 | 2 | 3;
  /** Area wash under the line. */
  fill?: boolean;
  className?: string;
}

const W = 100;
const H = 40;

/**
 * Tiny trend line for cards: no axes, ticks or tooltip — the shape only. Stretches to its
 * container's width at --sparkline-h. Pair it with the figure it summarises in text.
 */
export function Sparkline({ label, values, color = 1, fill = true, className }: SparklineProps) {
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = values.length > 1 ? W / (values.length - 1) : 0;
  const points = values.map((v, i) => [i * step, H - ((v - min) / span) * H] as const);
  const line = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  return (
    <svg
      className={['sparkline', `sparkline--${color}`, className].filter(Boolean).join(' ')}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      {fill && values.length > 1 && <path className="sparkline__area" d={`${line} L${W},${H} L0,${H} Z`} />}
      {values.length > 1 && <path className="sparkline__line" d={line} />}
    </svg>
  );
}
