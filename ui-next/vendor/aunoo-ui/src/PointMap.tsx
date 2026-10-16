import { useId } from 'react';
import './PointMap.css';

export interface MapGroup {
  id: string;
  label: string;
  /** Categorical slot (--viz-series-N), or 0 for the grey "Other" groups. */
  color: 0 | 1 | 2 | 3 | 4 | 5;
}

export interface MapPoint {
  id: string;
  /** Position, any range — the map fits the points to its box. */
  x: number;
  y: number;
  group: string;
  /** Shown on hover. */
  label: string;
}

export interface PointMapProps {
  /** Names the map. */
  title: string;
  groups: MapGroup[];
  points: MapPoint[];
  /** Legend chips to show before folding the rest into "+N more". */
  maxLegend?: number;
  /** e.g. "Showing 500 of 10,000 points". */
  caption?: React.ReactNode;
  emptyText?: string;
  className?: string;
}

/**
 * Many small dots (an embedding projection). The picture is for overview only — the legend counts
 * points per group, and each dot names itself on hover. Pair it with a list for exact reading.
 */
export function PointMap({ title, groups, points, maxLegend = 8, caption, emptyText = 'No points to plot yet.', className }: PointMapProps) {
  const id = useId();
  if (points.length === 0) return <p className={['point-map__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v: number) => 2 + ((v - x0) / (x1 - x0 || 1)) * 96;
  const sy = (v: number) => 2 + ((y1 - v) / (y1 - y0 || 1)) * 56;
  const color = Object.fromEntries(groups.map((g) => [g.id, g.color]));
  const counts = groups.map((g) => ({ ...g, n: points.filter((p) => p.group === g.id).length })).filter((g) => g.n > 0);
  const shown = counts.slice(0, maxLegend);

  return (
    <figure className={['point-map', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <svg className="point-map__svg" viewBox="0 0 100 60" role="img" aria-label={`${title}: ${points.length} points in ${counts.length} groups`}>
        {points.map((p) => (
          <circle key={p.id} className={`point-map__dot point-map__dot--${color[p.group] ?? 0}`} cx={sx(p.x)} cy={sy(p.y)} r="0.55">
            <title>{p.label}</title>
          </circle>
        ))}
      </svg>
      <ul className="point-map__legend">
        {shown.map((g) => (
          <li key={g.id}>
            <span className={`point-map__key point-map__dot--${g.color}`} aria-hidden="true" />
            {g.label} ({g.n})
          </li>
        ))}
        {counts.length > shown.length && <li>+{counts.length - shown.length} more</li>}
      </ul>
      {caption && <p className="point-map__caption">{caption}</p>}
    </figure>
  );
}
