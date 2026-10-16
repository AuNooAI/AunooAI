import { DonutChart, Stack, Text } from '@aunoo/ui';
import type { Payload } from '../lib/model';
import './consensusCharts.css';

/*
 * The consensus card's charts, as the old page drew them (ui/src/components/TimelineVisualization.tsx
 * and SentimentChart.tsx), which the design template had reduced to meter bars and a range bar.
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

/**
 * Where the consensus sits in time: the window as a band on a year axis, with the optimistic and
 * pessimistic outliers as markers. The axis is shared by every theme on the page so they compare.
 * Each marker's year and share of sources is written out, not only shown on hover.
 */
export function ConsensusTimeline({ title, window, peak, optimistic, pessimistic, axis }: {
  title: string;
  window?: { start: number; end: number; label?: string };
  /** The year inside the window where sources expect the change to peak (as the old page marked it) */
  peak?: number;
  optimistic?: Payload;
  pessimistic?: Payload;
  axis: { min: number; max: number };
}) {
  const marks = [
    optimistic && Number(optimistic.year) ? { kind: 'optimistic' as const, year: Number(optimistic.year), share: optimistic.source_percentage, scenario: String(optimistic.scenario ?? '') } : null,
    pessimistic && Number(pessimistic.year) ? { kind: 'pessimistic' as const, year: Number(pessimistic.year), share: pessimistic.source_percentage, scenario: String(pessimistic.scenario ?? '') } : null,
  ].filter(Boolean) as { kind: 'optimistic' | 'pessimistic'; year: number; share?: number; scenario: string }[];
  const summary = [
    window ? `Consensus ${window.start === window.end ? window.start : `${window.start}–${window.end}`}` : null,
    peak ? `peak ${peak}` : null,
    ...marks.map((m) => `${m.kind} outlier ${m.year}${m.share != null ? ` (${m.share}% of sources)` : ''}`),
  ].filter(Boolean).join('; ');
  return (
    <figure className="cons-timeline" aria-label={`${title}: ${summary}`}>
      <div className="cons-timeline__track" aria-hidden="true">
        {window && (
          <div className="cons-timeline__band" style={{ left: `${pct(window.start, axis.min, axis.max)}%`, width: `${Math.max(pct(window.end, axis.min, axis.max) - pct(window.start, axis.min, axis.max), 3)}%` }}>
            <span>Consensus</span>
          </div>
        )}
        <div className="cons-timeline__line">
          {peak != null && <span className="cons-timeline__peak" style={{ left: `${pct(peak, axis.min, axis.max)}%` }} title={`Peak ${peak}`} />}
          {marks.map((m) => (
            <span key={m.kind} className={`cons-timeline__mark cons-timeline__mark--${m.kind}`} style={{ left: `${pct(m.year, axis.min, axis.max)}%` }} title={`${m.scenario} (${m.year})`} />
          ))}
        </div>
        <div className="cons-timeline__ticks">
          {ticksFor(axis.min, axis.max).map((y) => (
            <span key={y} style={{ left: `${pct(y, axis.min, axis.max)}%` }}>{y === axis.max && axis.max >= 2050 ? `${y}+` : y}</span>
          ))}
        </div>
      </div>
      <figcaption className="cons-timeline__legend">
        {window && <span><i className="cons-key cons-key--band" />{`Consensus ${window.label || `${window.start}–${window.end}`}`}</span>}
        {peak != null && <span><i className="cons-key cons-key--peak" />{`Peak ${peak}`}</span>}
        {marks.map((m) => (
          <span key={m.kind}>
            <i className={`cons-key cons-key--${m.kind}`} />
            {`${m.kind === 'optimistic' ? 'Optimistic' : 'Pessimistic'} outlier ${m.year}${m.share != null ? ` · ${m.share}% of sources` : ''}`}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

/**
 * Sentiment as a pie (donut), with the largest share in the middle. The donut's legend prints a count
 * beside each percentage, so the shares are turned into approximate article counts when the theme's
 * article total is known ("23 · 70%"), rather than printing the percentage twice.
 */
export function SentimentPie({ title, sentiment, articles = 0 }: { title: string; sentiment: { positive: number; neutral: number; critical: number }; articles?: number }) {
  const total = sentiment.positive + sentiment.neutral + sentiment.critical;
  // The model sends percentages, fractions or raw counts; work in shares of the whole
  const share = (v: number) => (total > 0 ? v / total : 0);
  const amount = (v: number) => (articles > 0 ? Math.round(share(v) * articles) : Math.round(share(v) * 100));
  const segs = [
    { id: 'positive', label: 'Positive', value: amount(sentiment.positive), color: 'positive' as const },
    { id: 'neutral', label: 'Neutral', value: amount(sentiment.neutral), color: 'neutral' as const },
    { id: 'critical', label: 'Critical', value: amount(sentiment.critical), color: 'negative' as const },
  ];
  const top = [
    { label: 'positive', s: share(sentiment.positive) }, { label: 'neutral', s: share(sentiment.neutral) }, { label: 'critical', s: share(sentiment.critical) },
  ].sort((a, b) => b.s - a.s)[0];
  return (
    <Stack gap="sm">
      <DonutChart title={title} segments={segs} centerLabel={total > 0 ? `${Math.round(top.s * 100)}% ${top.label}` : undefined} emptyText="No sentiment recorded." />
      {articles > 0 && <Text variant="caption">{`Counts are approximate articles, out of ${articles}.`}</Text>}
    </Stack>
  );
}

/** When sources expect it: one column per period, in time order, with the consensus period marked */
export function TimingColumns({ title, buckets, consensusLabel }: { title: string; buckets: { label: string; pct: number }[]; consensusLabel?: string }) {
  const firstYear = (l: string) => Number((l.match(/\d{4}/) ?? ['9999'])[0]);
  const ordered = [...buckets].sort((a, b) => firstYear(a.label) - firstYear(b.label));
  const max = Math.max(1, ...ordered.map((b) => b.pct));
  const name = (l: string) => l.replace(/\s*\(.*\)\s*$/, '');
  const years = (l: string) => (l.match(/\(([^)]*)\)/) ?? [])[1] ?? '';
  const isConsensus = (l: string) => !!consensusLabel && name(l).toLowerCase() === name(consensusLabel).toLowerCase();
  return (
    <Stack gap="sm">
      <div className="cons-cols" role="list" aria-label={title}>
        {ordered.map((b) => (
          <div key={b.label} role="listitem" className={`cons-cols__col${isConsensus(b.label) ? ' cons-cols__col--consensus' : ''}`} aria-label={`${b.label}: ${b.pct}% of sources${isConsensus(b.label) ? ', the consensus period' : ''}`}>
            <span className="cons-cols__value" aria-hidden="true">{`${b.pct}%`}</span>
            <span className="cons-cols__bar" aria-hidden="true" style={{ height: `${(b.pct / max) * 100}%` }} />
            <span className="cons-cols__label" aria-hidden="true">{name(b.label)}<br /><small>{years(b.label)}</small></span>
          </div>
        ))}
      </div>
      {consensusLabel && <Text variant="caption">The highlighted column is the consensus period.</Text>}
    </Stack>
  );
}
