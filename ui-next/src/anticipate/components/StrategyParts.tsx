import './strategyParts.css';

/*
 * The horizon colour coding of the old Strategic Recommendations view (ui/src/App.tsx and
 * TimelineBar.tsx): green near-term, amber mid-term, rose long-term, on the card's icon and its
 * timeline bar, which the rebuild had reduced to one neutral range bar.
 */

export type HorizonTone = 'near' | 'mid' | 'long';

/** The horizon's years on the shared axis, in its own colour, with the axis ends labelled */
export function HorizonBar({ label, start, end, min, max, tone }: { label: string; start: number; end: number; min: number; max: number; tone: HorizonTone }) {
  const span = Math.max(max - min, 1);
  const left = ((Math.max(start, min) - min) / span) * 100;
  const width = Math.max(((Math.min(end, max) - Math.max(start, min)) / span) * 100, 3);
  return (
    <figure className="strat-bar" aria-label={`${label}: ${start === end ? start : `${start}–${end}`}, on an axis from ${min} to ${max}`}>
      <div className="strat-bar__track" aria-hidden="true">
        <span className={`strat-bar__fill strat-bar__fill--${tone}`} style={{ left: `${left}%`, width: `${width}%` }} />
      </div>
      <figcaption className="strat-bar__ends" aria-hidden="true">
        <span>{min}</span>
        <span>{max}{max >= 2040 ? '+' : ''}</span>
      </figcaption>
    </figure>
  );
}

/** An icon in the horizon's colour (the card titles) */
export function HorizonIcon({ tone, children }: { tone: HorizonTone; children: React.ReactNode }) {
  return <span className={`strat-icon strat-icon--${tone}`}>{children}</span>;
}
