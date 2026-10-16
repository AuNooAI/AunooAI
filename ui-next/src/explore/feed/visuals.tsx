import './visuals.css';

/*
 * Small visuals the old News Feed drew by hand and the rebuild had reduced to text: the incident
 * timeline ruler (ui/src/components/newsfeed/incidentUtils.tsx TimelineRuler) and the sentiment
 * spread across a story's coverage (ArticleDetailPanel's "Sentiment across coverage").
 */

const fmt = (t: number) => new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

/** Every date an incident's timeline names, as a dot on a bar from the first to the last */
export function TimelineRuler({ dates, label }: { dates: number[]; label: string }) {
  const ds = [...new Set(dates)].filter((d) => Number.isFinite(d)).sort((a, b) => a - b);
  if (ds.length < 2) return null;
  const min = ds[0];
  const range = Math.max(1, ds[ds.length - 1] - min);
  return (
    <figure className="feed-ruler" aria-label={`${label}: ${ds.length} dates from ${fmt(min)} to ${fmt(ds[ds.length - 1])}`}>
      <div className="feed-ruler__bar" aria-hidden="true">
        {ds.map((d) => (
          <span key={d} className="feed-ruler__dot" style={{ left: `${Math.max(2, Math.min(98, ((d - min) / range) * 100))}%` }} title={new Date(d).toLocaleDateString('en-GB')} />
        ))}
      </div>
      <figcaption className="feed-ruler__ends" aria-hidden="true">
        <span>{fmt(min)}</span>
        <span>{`${ds.length} dates`}</span>
        <span>{fmt(ds[ds.length - 1])}</span>
      </figcaption>
    </figure>
  );
}

/** Every date an incident record names: its timeline (dates or text such as "reported 2026-10-12"), first and last seen */
export function incidentDates(i: { timeline?: unknown; first_seen?: string | null; last_seen?: string | null }): number[] {
  const parts = [...(Array.isArray(i.timeline) ? i.timeline : [i.timeline ?? '']), i.first_seen ?? '', i.last_seen ?? ''].map(String);
  const out: number[] = [];
  for (const p of parts) {
    const found = p.match(/\d{4}-\d{2}-\d{2}/g);
    if (found) found.forEach((d) => out.push(Date.parse(d)));
    else if (p && !Number.isNaN(Date.parse(p))) out.push(Date.parse(p));
  }
  return out.filter((t) => Number.isFinite(t));
}

/** Positive, neutral and negative shares of a story's coverage as one stacked bar, with the counts */
export function SentimentSpread({ positive, neutral, negative }: { positive: number; neutral: number; negative: number }) {
  const total = positive + neutral + negative;
  if (total < 2) return null;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="feed-spread" role="img" aria-label={`Sentiment across coverage: ${positive} positive, ${neutral} neutral, ${negative} negative`}>
      <span className="feed-spread__label" aria-hidden="true">Sentiment across coverage</span>
      <span className="feed-spread__bar" aria-hidden="true">
        {positive > 0 && <span className="feed-spread__seg feed-spread__seg--pos" style={{ width: w(positive) }} />}
        {neutral > 0 && <span className="feed-spread__seg feed-spread__seg--neu" style={{ width: w(neutral) }} />}
        {negative > 0 && <span className="feed-spread__seg feed-spread__seg--neg" style={{ width: w(negative) }} />}
      </span>
      <span className="feed-spread__counts" aria-hidden="true">{`${positive} positive · ${neutral} neutral · ${negative} negative`}</span>
    </div>
  );
}

/** Chip tone for an article's sentiment, so it reads at a glance as the old coloured dot did */
export const sentimentTone = (s?: string | null): 'success' | 'error' | 'warning' | 'muted' => {
  const v = (s ?? '').toLowerCase();
  if (v.startsWith('pos')) return 'success';
  if (v.startsWith('neg') || v.startsWith('crit')) return 'error';
  if (v.startsWith('mix')) return 'warning';
  return 'muted';
};
