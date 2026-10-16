import { useState } from 'react';
import { Text } from '@aunoo/ui';
import './mm.css';

/*
 * A scatter chart with its own scale on each axis, for two measures with very different ranges
 * (posts published against reactions per post). The design system's scatter puts both axes on one
 * 0–100 scale, which flattens one of them. Dots are buttons; the busiest few are named on the chart.
 */

export interface ScatterDot { id: string; label: string; x: number; y: number; color?: string }

const W = 560;
const H = 300;
const L = 48;
const B = 36;
const T = 12;
const R = 16;

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

export function DualScatter({ title, dots, xLabel, yLabel, onSelect, nameTop = 6 }: {
  title: string;
  dots: ScatterDot[];
  xLabel: string;
  yLabel: string;
  onSelect?: (id: string) => void;
  /** How many of the furthest-out dots get a name on the chart */
  nameTop?: number;
}) {
  const [active, setActive] = useState<ScatterDot | null>(null);
  if (!dots.length) return null;
  const xMax = niceMax(Math.max(...dots.map((d) => d.x)));
  const yMax = niceMax(Math.max(...dots.map((d) => d.y)));
  const sx = (v: number) => L + (v / xMax) * (W - L - R);
  const sy = (v: number) => H - B - (v / yMax) * (H - B - T);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  // Name the dots furthest from the origin in either direction, so both the loud and the heard stand out
  const named = new Set([...dots].sort((a, b) => b.x / xMax + b.y / yMax - (a.x / xMax + a.y / yMax)).slice(0, nameTop).map((d) => d.id));
  const fmt = (v: number) => (v >= 100 ? Math.round(v).toLocaleString() : String(Math.round(v * 10) / 10));

  return (
    <figure className="mm-vbars">
      <div className="mm-vbars__scroll">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label={title} className="mm-vbars__svg">
          {ticks.map((t) => (
            <g key={t}>
              <line className="mm-scatter__grid" x1={L} x2={W - R} y1={sy(t * yMax)} y2={sy(t * yMax)} />
              <text className="mm-vbars__tick" x={L - 6} y={sy(t * yMax)} textAnchor="end" dominantBaseline="middle">{fmt(t * yMax)}</text>
              <line className="mm-scatter__grid" x1={sx(t * xMax)} x2={sx(t * xMax)} y1={T} y2={H - B} />
              <text className="mm-vbars__tick" x={sx(t * xMax)} y={H - B + 14} textAnchor="middle">{fmt(t * xMax)}</text>
            </g>
          ))}
          <text className="mm-scatter__axis" x={(L + W - R) / 2} y={H - 4} textAnchor="middle">{xLabel}</text>
          <text className="mm-scatter__axis" x={12} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(T + H - B) / 2})`}>{yLabel}</text>
          {dots.map((d) => (
            <g key={d.id}>
              <circle
                className={`mm-scatter__dot${active?.id === d.id ? ' mm-scatter__dot--active' : ''}${onSelect ? ' mm-scatter__dot--pick' : ''}`}
                cx={sx(d.x)}
                cy={sy(d.y)}
                r={6}
                style={{ fill: d.color }}
                tabIndex={0}
                role={onSelect ? 'button' : 'img'}
                aria-label={`${d.label}: ${xLabel.toLowerCase()} ${fmt(d.x)}, ${yLabel.toLowerCase()} ${fmt(d.y)}`}
                onMouseEnter={() => setActive(d)}
                onFocus={() => setActive(d)}
                onClick={() => onSelect?.(d.id)}
                onKeyDown={(e) => {
                  if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    onSelect(d.id);
                  }
                }}
              >
                <title>{d.label}</title>
              </circle>
              {named.has(d.id) && <text className="mm-scatter__name" x={sx(d.x) + 8} y={sy(d.y) - 8}>{d.label}</text>}
            </g>
          ))}
        </svg>
      </div>
      <Text variant="caption" as="div">
        {active ? `${active.label}: ${fmt(active.x)} ${xLabel.toLowerCase()}, ${fmt(active.y)} ${yLabel.toLowerCase()}.` : `Each dot is one vendor. Point at a dot, or move to it with Tab${onSelect ? '; select it to open the vendor' : ''}.`}
      </Text>
    </figure>
  );
}
