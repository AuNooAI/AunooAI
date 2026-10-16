import { Stack, Text } from '@aunoo/ui';
import './impactTimeline.css';

/*
 * One impact on a year axis, as the old ImpactTimelineCard drew it: the window of impact as a coloured
 * band, and each milestone as a numbered marker at its year. The old card wrote the milestone labels on
 * the track and shuffled them into rows to avoid collisions; here each marker carries a number and the
 * list under the bar spells out its year and label, so nothing overlaps at any width.
 */

const pct = (v: number, min: number, max: number) => ((Math.min(Math.max(v, min), max) - min) / Math.max(max - min, 1)) * 100;

function ticksFor(min: number, max: number): number[] {
  const span = max - min;
  const step = span <= 6 ? 1 : span <= 15 ? 5 : 10;
  const out = [min];
  for (let y = Math.ceil((min + 1) / step) * step; y < max; y += step) out.push(y);
  out.push(max);
  return [...new Set(out)];
}

export interface Milestone {
  year: number;
  label: string;
}

export function ImpactTimelineChart({ name, start, end, milestones, axis, color }: {
  name: string;
  start: number;
  end: number;
  milestones: Milestone[];
  axis: { min: number; max: number };
  /** 1 to 5: the design system's chart series colours, so neighbouring rows differ */
  color: number;
}) {
  const marks = [...milestones].filter((m) => Number.isFinite(m.year)).sort((a, b) => a.year - b.year);
  const series = `var(--viz-series-${((color - 1) % 5) + 1})`;
  return (
    <Stack gap="sm">
      <figure className="impact-tl" aria-label={`${name}: impact ${start === end ? start : `${start}–${end}`}${marks.length ? `, milestones ${marks.map((m) => `${m.year} ${m.label}`).join('; ')}` : ''}`}>
        <div className="impact-tl__track" aria-hidden="true">
          <div className="impact-tl__base" />
          <div className="impact-tl__band" style={{ left: `${pct(start, axis.min, axis.max)}%`, width: `${Math.max(pct(end, axis.min, axis.max) - pct(start, axis.min, axis.max), 2)}%`, background: series }} />
          {marks.map((m, i) => (
            <span key={`${m.year}-${i}`} className="impact-tl__mark" style={{ left: `${pct(m.year, axis.min, axis.max)}%`, borderColor: series }} title={`${m.year}: ${m.label}`}>
              {i + 1}
            </span>
          ))}
          <div className="impact-tl__ticks">
            {ticksFor(axis.min, axis.max).map((y) => <span key={y} style={{ left: `${pct(y, axis.min, axis.max)}%` }}>{y}</span>)}
          </div>
        </div>
      </figure>
      {marks.length > 0 && (
        <ol className="impact-tl__legend" aria-label={`${name} milestones`}>
          {marks.map((m, i) => (
            <li key={`${m.year}-${i}`}>
              <span className="impact-tl__num" style={{ borderColor: series }} aria-hidden="true">{i + 1}</span>
              <Text as="span" variant="caption"><strong>{m.year}</strong>{` ${m.label}`}</Text>
            </li>
          ))}
        </ol>
      )}
    </Stack>
  );
}
