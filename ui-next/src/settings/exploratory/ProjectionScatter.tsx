import { useMemo, useState } from 'react';
import { Text } from '@aunoo/ui';
import type { ProjectionPoint } from './api';
import './exploratory.css';

/*
 * The map of articles: each article is a dot placed by meaning (UMAP, t-SNE or PCA over the
 * embeddings), so articles about the same thing sit close together. The axes have no units, which is
 * why none are drawn. Each axis is scaled to its own range: projections give negative and uneven
 * coordinates, which the design system's 0–100 scatter can't show.
 */

const W = 640;
const H = 420;
const PAD = 12;

export function ProjectionScatter({ points, colourOf, onSelect }: {
  points: ProjectionPoint[];
  colourOf: (p: ProjectionPoint) => string;
  onSelect: (p: ProjectionPoint) => void;
}) {
  const [active, setActive] = useState<ProjectionPoint | null>(null);
  const scale = useMemo(() => {
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    const sx = (v: number) => PAD + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * PAD);
    const sy = (v: number) => H - PAD - ((v - y0) / (y1 - y0 || 1)) * (H - 2 * PAD);
    return { sx, sy };
  }, [points]);
  if (!points.length) return null;
  const r = points.length > 1500 ? 2.5 : points.length > 500 ? 3.5 : 5;

  return (
    <figure className="xa-map">
      <div className="xa-map__scroll">
        <svg className="xa-map__svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Map of ${points.length} articles, grouped by meaning`}>
          <rect className="xa-map__frame" x={0.5} y={0.5} width={W - 1} height={H - 1} />
          {points.map((p) => (
            <circle
              key={p.id}
              className={`xa-map__dot${active?.id === p.id ? ' xa-map__dot--active' : ''}`}
              cx={scale.sx(p.x)}
              cy={scale.sy(p.y)}
              r={active?.id === p.id ? r + 2 : r}
              style={{ fill: colourOf(p) }}
              onMouseEnter={() => setActive(p)}
              onClick={() => onSelect(p)}
            >
              <title>{p.title || p.id}</title>
            </circle>
          ))}
        </svg>
      </div>
      <Text variant="caption" as="div">
        {active ? `${active.title || 'Untitled'} · cluster ${active.cluster}${active.category ? ` · ${active.category}` : ''}${active.sentiment ? ` · ${active.sentiment}` : ''}. Click to open it.` : 'Point at a dot to see the article; click it to open its details. The articles are also listed under Results.'}
      </Text>
    </figure>
  );
}
