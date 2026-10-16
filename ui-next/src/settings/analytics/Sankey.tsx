import { useState } from 'react';
import { Text } from '@aunoo/ui';

/*
 * A small left-to-right flow chart: columns of nodes (source, category, sentiment), each sized by how
 * many articles pass through it, joined by bands whose width is the article count of that pair.
 * Replaces the old page's Plotly Sankey.
 */

export interface SankeyNode { id: string; label: string; column: number; color: string }
export interface SankeyLink { source: string; target: string; value: number; color: string }

const W = 960;
const PAD = 10;
const NODE_W = 14;
const LABEL_W = 170;

export function Sankey({ title, nodes, links, height = 620 }: { title: string; nodes: SankeyNode[]; links: SankeyLink[]; height?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  if (!links.length) return <Text>No articles match these filters.</Text>;

  const columns = Math.max(...nodes.map((n) => n.column)) + 1;
  const total = (id: string) => Math.max(
    links.filter((l) => l.source === id).reduce((a, l) => a + l.value, 0),
    links.filter((l) => l.target === id).reduce((a, l) => a + l.value, 0),
  );
  const colX = (c: number) => LABEL_W + (c * (W - 2 * LABEL_W - NODE_W)) / Math.max(1, columns - 1);

  // Lay out each column top to bottom, biggest first, with one scale shared by all columns
  const byCol = Array.from({ length: columns }, (_, c) => nodes.filter((n) => n.column === c).sort((a, b) => total(b.id) - total(a.id)));
  const scale = Math.min(...byCol.map((col) => {
    const sum = col.reduce((a, n) => a + total(n.id), 0);
    return sum ? (height - PAD * (col.length + 1)) / sum : Infinity;
  }));
  const pos = new Map<string, { x: number; y: number; h: number; outY: number; inY: number }>();
  byCol.forEach((col) => {
    let y = PAD;
    col.forEach((n) => {
      const h = Math.max(2, total(n.id) * scale);
      pos.set(n.id, { x: colX(n.column), y, h, outY: y, inY: y });
      y += h + PAD;
    });
  });

  const paths = [...links].sort((a, b) => b.value - a.value).map((l, i) => {
    const s = pos.get(l.source)!;
    const t = pos.get(l.target)!;
    const w = Math.max(1, l.value * scale);
    const y0 = s.outY + w / 2;
    const y1 = t.inY + w / 2;
    s.outY += w;
    t.inY += w;
    const x0 = s.x + NODE_W;
    const x1 = t.x;
    const mx = (x0 + x1) / 2;
    return { key: `${l.source}>${l.target}-${i}`, d: `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}`, w, l };
  });
  const label = (id: string) => nodes.find((n) => n.id === id)?.label ?? id;
  const active = hover ? paths.find((p) => p.key === hover) : null;

  return (
    <figure className="an-figure">
      <div className="an-scroll">
        <svg className="an-sankey" viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label={title}>
          {paths.map((p) => (
            <path
              key={p.key}
              className="an-sankey__link"
              d={p.d}
              stroke={p.l.color}
              strokeWidth={p.w}
              tabIndex={0}
              aria-label={`${label(p.l.source)} to ${label(p.l.target)}: ${p.l.value} articles`}
              onMouseEnter={() => setHover(p.key)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(p.key)}
              onBlur={() => setHover(null)}
            />
          ))}
          {nodes.map((n) => {
            const p = pos.get(n.id);
            if (!p) return null;
            const left = n.column === 0;
            return (
              <g key={n.id}>
                <rect className="an-sankey__node" x={p.x} y={p.y} width={NODE_W} height={p.h} fill={n.color} />
                <text className="an-sankey__label" x={left ? p.x - 6 : p.x + NODE_W + 6} y={p.y + p.h / 2} dy="0.35em" textAnchor={left ? 'end' : 'start'}>
                  {n.label.length > 26 ? `${n.label.slice(0, 25)}…` : n.label}
                  <tspan className="an-sankey__count">{` ${total(n.id)}`}</tspan>
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <Text variant="caption" aria-live="polite">
        {active ? `${label(active.l.source)} → ${label(active.l.target)}: ${active.l.value} articles` : 'Point at a band to see how many articles it carries.'}
      </Text>
    </figure>
  );
}
