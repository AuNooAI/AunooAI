/*
 * Colours for the map of articles. Five design-system series colours first, then evenly spaced hues,
 * because a map can hold 30 or more clusters and the design system only defines five.
 */
const SERIES = ['var(--viz-series-1)', 'var(--viz-series-2)', 'var(--viz-series-3)', 'var(--viz-series-4)', 'var(--viz-series-5)'];

export function palette(n: number): string[] {
  const out = SERIES.slice(0, n);
  for (let i = SERIES.length; i < n; i++) out.push(`hsl(${Math.round((i * 137.5) % 360)} 55% 52%)`);
  return out;
}

/** Fixed colours where the value itself has a meaning */
export const SENTIMENT_COLOUR: Record<string, string> = {
  positive: 'var(--success)',
  negative: 'var(--error)',
  neutral: 'var(--viz-neutral)',
  mixed: 'var(--warning)',
};
