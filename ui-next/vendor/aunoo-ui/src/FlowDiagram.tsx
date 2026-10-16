import { useId } from 'react';
import { chartColorClass, type ChartColor } from './chartColors';
import './FlowDiagram.css';

export interface FlowNode {
  id: string;
  label: string;
  /** Column index into `stages`. */
  stage: number;
  color: ChartColor;
}

export interface FlowLink {
  source: string;
  target: string;
  value: number;
}

export interface FlowDiagramProps {
  /** Names the diagram and its table, e.g. "Article flow: source → category → sentiment". */
  title: string;
  /** Column headings, left to right. */
  stages: string[];
  nodes: FlowNode[];
  /** Between nodes in neighbouring stages. */
  links: FlowLink[];
  /** e.g. "articles" in "Reuters → Military Activity: 12 articles". */
  unit?: string;
  emptyText?: string;
  className?: string;
}

const NODE_W = 1.6; // node width in the 100-unit-wide viewBox
const GAP = 2.5; // vertical gap between nodes, in the 100-unit-high viewBox

/**
 * Sankey-style flow between stages. Node height and ribbon width follow the count; each ribbon
 * names itself on hover, and a table lists every flow for screen readers.
 */
export function FlowDiagram({ title, stages, nodes, links, unit = 'items', emptyText = 'No flow to show yet.', className }: FlowDiagramProps) {
  const id = useId();
  if (nodes.length === 0 || links.length === 0) return <p className={['flow-diagram__empty', className].filter(Boolean).join(' ')}>{emptyText}</p>;

  const inSum = (n: string) => links.filter((l) => l.target === n).reduce((s, l) => s + l.value, 0);
  const outSum = (n: string) => links.filter((l) => l.source === n).reduce((s, l) => s + l.value, 0);
  const size = Object.fromEntries(nodes.map((n) => [n.id, Math.max(inSum(n.id), outSum(n.id))]));
  const byStage = stages.map((_, i) => nodes.filter((n) => n.stage === i));
  // One scale for every column, so heights compare across stages
  const k = Math.min(...byStage.filter((col) => col.length).map((col) => (100 - GAP * (col.length - 1)) / col.reduce((s, n) => s + size[n.id], 0)));
  const x = (stage: number) => (stages.length === 1 ? 0 : (stage / (stages.length - 1)) * (100 - NODE_W));
  const pos: Record<string, { x: number; y: number; h: number }> = {};
  byStage.forEach((col) => {
    let y = 0;
    col.forEach((n) => {
      pos[n.id] = { x: x(n.stage), y, h: size[n.id] * k };
      y += size[n.id] * k + GAP;
    });
  });

  const outOffset: Record<string, number> = {};
  const inOffset: Record<string, number> = {};
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const ribbons = links.map((l, i) => {
    const s = pos[l.source];
    const t = pos[l.target];
    const w = l.value * k;
    const y0 = s.y + (outOffset[l.source] ?? 0);
    const y1 = t.y + (inOffset[l.target] ?? 0);
    outOffset[l.source] = (outOffset[l.source] ?? 0) + w;
    inOffset[l.target] = (inOffset[l.target] ?? 0) + w;
    const xs = s.x + NODE_W;
    const xt = t.x;
    const xm = (xs + xt) / 2;
    const d = `M${xs},${y0} C${xm},${y0} ${xm},${y1} ${xt},${y1} L${xt},${y1 + w} C${xm},${y1 + w} ${xm},${y0 + w} ${xs},${y0 + w} Z`;
    return (
      <path key={i} className={`flow-diagram__link ${chartColorClass(byId[l.source].color)}`} d={d}>
        <title>{`${byId[l.source].label} → ${byId[l.target].label}: ${l.value} ${unit}`}</title>
      </path>
    );
  });

  return (
    <figure className={['flow-diagram', className].filter(Boolean).join(' ')} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="visually-hidden">{title}</figcaption>
      <div className="flow-diagram__stages" aria-hidden="true">
        {stages.map((s) => <span key={s}>{s}</span>)}
      </div>
      <div className="flow-diagram__plot" aria-hidden="true">
        <svg className="flow-diagram__svg" viewBox="0 0 100 100" preserveAspectRatio="none">
          {ribbons}
          {nodes.map((n) => (
            <rect key={n.id} className={`flow-diagram__node ${chartColorClass(n.color)}`} x={pos[n.id].x} y={pos[n.id].y} width={NODE_W} height={Math.max(0.4, pos[n.id].h)} />
          ))}
        </svg>
        {nodes.map((n) => {
          const last = n.stage === stages.length - 1;
          return (
            <span
              key={n.id}
              className={`flow-diagram__label${last ? ' flow-diagram__label--end' : ''}`}
              style={{ left: `${last ? pos[n.id].x : pos[n.id].x + NODE_W}%`, top: `${pos[n.id].y + pos[n.id].h / 2}%` }}
            >
              {n.label} <span className="flow-diagram__count">{size[n.id]}</span>
            </span>
          );
        })}
      </div>
      <div className="visually-hidden">
        <table>
          <caption>{title}</caption>
          <thead>
            <tr><th scope="col">From</th><th scope="col">To</th><th scope="col">Count</th></tr>
          </thead>
          <tbody>
            {links.map((l, i) => (
              <tr key={i}><td>{byId[l.source].label}</td><td>{byId[l.target].label}</td><td>{l.value}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
