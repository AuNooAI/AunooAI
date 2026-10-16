import { StackedBarChart, Text, type StackedSeries } from '@aunoo/ui';
import type { Timeline } from './api';

/*
 * Results per day, stacked by category, as the old page's Data Points chart (a stacked Chart.js bar
 * chart), so each column shows both the day's total and its mix. The five biggest categories get
 * their own colour and the rest are stacked together as "Other", so the day's total stays exact.
 */
export function TimelineChart({ timeline }: { timeline: Timeline }) {
  const cats = Object.entries(timeline)
    .map(([c, days]) => ({ c, days, n: Object.values(days).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.n - a.n);
  const top = cats.slice(0, 5);
  const rest = cats.slice(5);
  const days = [...new Set(cats.flatMap((x) => Object.keys(x.days)))].sort();
  if (!days.length) return <Text variant="caption">No dated results to chart.</Text>;
  const series: StackedSeries[] = top.map((x, i) => ({ id: x.c, label: x.c, color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: days.map((d) => x.days[d] ?? 0) }));
  if (rest.length) {
    series.push({ id: '__other', label: `Other (${rest.length} categories)`, color: 0, values: days.map((d) => rest.reduce((a, x) => a + (x.days[d] ?? 0), 0)) });
  }
  return (
    <>
      <StackedBarChart title="Results per day, by category" categories={days.map((d) => d.slice(5))} series={series} maxLabels={10} emptyText="No dated results to chart." />
      <Text variant="caption">Each column is one day; its height is the day’s number of results, split by category.</Text>
    </>
  );
}
