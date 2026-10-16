import { useMemo, useState } from 'react';
import { Text } from '@aunoo/ui';
import './swimlane.css';

/*
 * One row per lane (a vendor, a brand, an account), with each item placed on a shared date axis.
 * The design system has no such chart, so this is a small SVG. Dots are sized by weight, can be
 * reached with the keyboard, and name themselves on hover or focus in the line under the chart.
 * The chart keeps a minimum width and scrolls sideways inside its own box on a phone.
 */

export interface SwimlaneLane { id: string; label: string; color?: string }
export interface SwimlaneItem {
  id: string;
  lane: string;
  /** ISO date or date-time */
  date: string;
  /** Read out and shown on hover/focus */
  label: string;
  tone?: 'neutral' | 'positive' | 'negative' | 'accent';
  /** Size hint, e.g. engagement; optional */
  weight?: number;
  onSelect?: () => void;
}
export interface SwimlaneProps {
  title: string;
  lanes: SwimlaneLane[];
  items: SwimlaneItem[];
  /** Axis bounds; default to the items' own range */
  from?: string;
  to?: string;
  caption?: React.ReactNode;
  emptyText?: string;
}

const DAY = 86_400_000;
const LABEL_W = 150;
const PLOT_W = 640;
const ROW_H = 32;
const TOP = 8;
const AXIS_H = 26;

const TONE_FILL: Record<NonNullable<SwimlaneItem['tone']>, string> = {
  neutral: 'var(--viz-neutral)',
  positive: 'var(--success)',
  negative: 'var(--error)',
  accent: 'var(--accent)',
};

const dayOf = (iso: string) => {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor(t / DAY);
};
const fmt = (day: number) => new Date(day * DAY).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

export function Swimlane({ title, lanes, items, from, to, caption, emptyText = 'Nothing with a date to place on the timeline.' }: SwimlaneProps) {
  const [active, setActive] = useState<SwimlaneItem | null>(null);

  const placed = useMemo(() => {
    const laneIndex = new Map(lanes.map((l, i) => [l.id, i]));
    return items
      .map((it) => ({ it, day: dayOf(it.date), row: laneIndex.get(it.lane) }))
      .filter((p): p is { it: SwimlaneItem; day: number; row: number } => p.day !== null && p.row !== undefined);
  }, [items, lanes]);

  if (!lanes.length || !placed.length) return <Text variant="caption">{emptyText}</Text>;

  const days = placed.map((p) => p.day);
  const lo = (from ? dayOf(from) : null) ?? Math.min(...days);
  const hi = Math.max((to ? dayOf(to) : null) ?? Math.max(...days), lo + 1);
  const x = (day: number) => LABEL_W + 10 + ((day - lo) / (hi - lo)) * (PLOT_W - 20);
  const maxW = Math.max(1, ...placed.map((p) => p.it.weight ?? 0));
  const r = (w?: number) => (w && w > 0 ? 4 + 5 * Math.sqrt(w / maxW) : 5);
  const height = TOP + lanes.length * ROW_H + AXIS_H;
  const width = LABEL_W + PLOT_W;
  const ticks = Array.from({ length: 6 }, (_, i) => Math.round(lo + ((hi - lo) * i) / 5));
  const laneColor = new Map(lanes.map((l) => [l.id, l.color]));

  return (
    <figure className="swimlane">
      <div className="swimlane__scroll" tabIndex={-1}>
        <svg className="swimlane__svg" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="group" aria-label={title}>
          {lanes.map((l, i) => {
            const y = TOP + i * ROW_H + ROW_H / 2;
            return (
              <g key={l.id}>
                <line className="swimlane__lane" x1={LABEL_W} x2={width} y1={y} y2={y} />
                <text className="swimlane__label" x={LABEL_W - 8} y={y} dominantBaseline="middle" textAnchor="end">
                  {l.label.length > 22 ? `${l.label.slice(0, 21)}…` : l.label}
                  <title>{l.label}</title>
                </text>
              </g>
            );
          })}
          {ticks.map((t) => (
            <g key={t}>
              <line className="swimlane__grid" x1={x(t)} x2={x(t)} y1={TOP} y2={TOP + lanes.length * ROW_H} />
              <text className="swimlane__tick" x={x(t)} y={height - 8} textAnchor="middle">{fmt(t)}</text>
            </g>
          ))}
          {placed.map(({ it, day, row }) => {
            const cy = TOP + row * ROW_H + ROW_H / 2;
            const fill = it.tone ? TONE_FILL[it.tone] : laneColor.get(it.lane) ?? 'var(--viz-series-1)';
            const pick = it.onSelect;
            return (
              <circle
                key={it.id}
                className={`swimlane__dot${pick ? ' swimlane__dot--pick' : ''}${active?.id === it.id ? ' swimlane__dot--active' : ''}`}
                cx={x(day)}
                cy={cy}
                r={r(it.weight)}
                style={{ fill }}
                tabIndex={0}
                role={pick ? 'button' : 'img'}
                aria-label={`${it.label}, ${fmt(day)}`}
                onMouseEnter={() => setActive(it)}
                onFocus={() => setActive(it)}
                onClick={() => pick?.()}
                onKeyDown={(e) => {
                  if (pick && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    pick();
                  }
                }}
              >
                <title>{`${it.label} · ${fmt(day)}`}</title>
              </circle>
            );
          })}
        </svg>
      </div>
      <Text variant="caption" as="div">
        {active ? `${lanes.find((l) => l.id === active.lane)?.label ?? ''}: ${active.label} (${fmt(dayOf(active.date)!)})` : 'Point at a dot, or move to it with Tab, to see what it is.'}
      </Text>
      {caption && <Text variant="caption" as="div">{caption}</Text>}
    </figure>
  );
}
