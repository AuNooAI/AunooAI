import './charts.css';

/*
 * Small charts the old Brand Watcher tab drew by hand and the rebuild had reduced to text or plain
 * meters: a sentiment split bar, a rating bar with the competitor-average tick, and grouped bars.
 */

/**
 * Positive / neutral / negative as one bar. `scale` (0 to 1) shortens the bar, so rows of different
 * volume compare at a glance, as the old Fans & Critics list did.
 */
export function SplitBar({ pos, neu, neg, scale = 1, label }: { pos: number; neu: number; neg: number; scale?: number; label: string }) {
  const total = pos + neu + neg;
  const text = `${label}: ${pos} positive, ${neu} neutral, ${neg} negative`;
  if (!total) return <span className="bw-split bw-split--empty" role="img" aria-label={`${label}: nothing scored`} />;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <span className="bw-split" role="img" aria-label={text} title={`${pos} positive · ${neu} neutral · ${neg} negative`}>
      <span className="bw-split__track" style={{ width: `${Math.max(scale, 0.08) * 100}%` }}>
        {pos > 0 && <span className="bw-split__seg bw-split__seg--pos" style={{ width: w(pos) }} />}
        {neu > 0 && <span className="bw-split__seg bw-split__seg--neu" style={{ width: w(neu) }} />}
        {neg > 0 && <span className="bw-split__seg bw-split__seg--neg" style={{ width: w(neg) }} />}
      </span>
    </span>
  );
}

/**
 * A 0-to-max rating as a bar, coloured by score (3.5 and up good, under 3 poor, as the old page),
 * with a dark tick at the competitors' average.
 */
export function RatingBar({ label, value, avg, max = 5 }: { label: string; value: number; avg?: number | null; max?: number }) {
  const tone = value >= 3.5 ? 'good' : value < 3 ? 'poor' : 'mid';
  const at = (v: number) => `${(Math.min(Math.max(v, 0), max) / max) * 100}%`;
  return (
    <div className="bw-rating">
      <span className="bw-rating__label">{label}</span>
      <span className="bw-rating__track" role="img" aria-label={`${label}: ${value.toFixed(1)} of ${max}${avg != null ? `, competitors ${avg.toFixed(1)}` : ''}`}>
        <span className={`bw-rating__fill bw-rating__fill--${tone}`} style={{ width: at(value) }} />
        {avg != null && <span className="bw-rating__tick" style={{ left: at(avg) }} title={`Competitor average ${avg.toFixed(1)}`} />}
      </span>
      <span className="bw-rating__value">{value.toFixed(1)}</span>
    </div>
  );
}

export interface GroupedSeries { id: string; label: string; color: string }

/**
 * Vertical bars grouped by category (e.g. one group per sub-rating, one bar per brand). The design
 * system's bar charts stack; side-by-side comparison of a few brands needs groups.
 */
export function GroupedBars({ title, groups, series, values, max, format = (v) => v.toFixed(1) }: {
  title: string;
  groups: { id: string; label: string }[];
  series: GroupedSeries[];
  /** values[s][g], null where a brand has no reading */
  values: (number | null)[][];
  max: number;
  format?: (v: number) => string;
}) {
  return (
    <figure className="bw-grouped" aria-label={title}>
      <div className="bw-grouped__scroll">
        <div className="bw-grouped__plot" style={{ minWidth: `${groups.length * Math.max(series.length * 1.1, 3)}rem` }}>
          {groups.map((g, gi) => (
            <div key={g.id} className="bw-grouped__group" role="group" aria-label={`${g.label}: ${series.map((s, si) => `${s.label} ${values[si]?.[gi] != null ? format(values[si][gi]!) : 'no reading'}`).join(', ')}`}>
              <div className="bw-grouped__bars" aria-hidden="true">
                {series.map((s, si) => {
                  const v = values[si]?.[gi];
                  return (
                    <span key={s.id} className="bw-grouped__bar" title={`${s.label}: ${v != null ? format(v) : 'no reading'}`}
                      style={{ height: v != null ? `${(Math.min(v, max) / max) * 100}%` : '0', background: s.color }} />
                  );
                })}
              </div>
              <span className="bw-grouped__label" aria-hidden="true">{g.label}</span>
            </div>
          ))}
        </div>
      </div>
      <figcaption className="bw-grouped__legend">
        {series.map((s) => (
          <span key={s.id}><i style={{ background: s.color }} />{s.label}</span>
        ))}
      </figcaption>
    </figure>
  );
}
