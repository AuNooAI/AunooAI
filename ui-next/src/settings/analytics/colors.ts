import type { ChartColor } from '@aunoo/ui';

/*
 * Chart colours from the design system's slots. Sentiments keep the old page's meaning (green for
 * positive, red for critical, amber for cautious), everything else takes the categorical slots in turn.
 */

const SENTIMENT: Record<string, ChartColor> = {
  positive: 'positive', optimistic: 'positive',
  negative: 'negative', critical: 'negative', pessimistic: 'negative',
  neutral: 'neutral', hyperbolic: 0,
  mixed: 'caution', cautious: 'caution', concerned: 'caution',
};

const TIME: Record<string, ChartColor> = { immediate: 'negative', 'short-term': 'caution', 'mid-term': 'positive', 'long-term': 1 };

const SLOTS: (1 | 2 | 3 | 4 | 5)[] = [1, 2, 3, 4, 5];
export const slot = (i: number): 1 | 2 | 3 | 4 | 5 => SLOTS[i % SLOTS.length];
export const stackSlot = (i: number): 0 | 1 | 2 | 3 | 4 | 5 => ([1, 2, 3, 4, 5, 0] as const)[i % 6];

export const sentimentColor = (label: string, i: number): ChartColor => SENTIMENT[label.toLowerCase()] ?? slot(i);
export const timeColor = (label: string, i: number): ChartColor => TIME[label.toLowerCase()] ?? slot(i);

/** LineChart takes no "caution" role, so caution sentiments use a categorical slot */
export function lineColor(label: string, i: number): 1 | 2 | 3 | 4 | 5 | 'positive' | 'negative' | 'neutral' {
  const c = sentimentColor(label, i);
  if (c === 'positive' || c === 'negative' || c === 'neutral') return c;
  if (c === 'caution') return 3;
  return c === 0 ? 'neutral' : (c as 1 | 2 | 3 | 4 | 5);
}

/** Put the known values first, in the topic's own order, then anything else the data holds */
export function ordered(labels: string[], known: string[]) {
  const first = known.filter((k) => labels.includes(k));
  return [...first, ...labels.filter((l) => !first.includes(l))];
}
