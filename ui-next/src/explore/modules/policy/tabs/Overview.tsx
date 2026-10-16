import { useState } from 'react';
import { Grid, LineChart, Panel, SegmentedControl, StackedBarChart, Stat, Stack, Text, TextLink } from '@aunoo/ui';
import { CATEGORY_DESCRIPTIONS, CATEGORY_SHORT_NAMES } from '@monolith/policyTrackerApi';
import { fmtDate, niceTicks } from '../api';
import { BarList, Loading, NoData } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyOverviewTab: four figures and the category chart, with a monthly trend and the top
 * five categories month by month.
 */
export function Overview({ pt, period, onUpdate }: { pt: PolicyTracker; period: string; onUpdate: () => void }) {
  const [view, setView] = useState<'categories' | 'trend' | 'stacked'>('categories');
  const { stats, categories, temporal, loadingOverview } = pt;
  if (loadingOverview && !stats) return <Loading />;
  if (stats && stats.total_articles === 0) return <NoData onUpdate={onUpdate} period={period} />;

  const top5 = [...categories].sort((a, b) => b.article_count - a.article_count).slice(0, 5).map((c) => c.category);
  const months = temporal.map((t) => t.month);
  const trend = niceTicks(Math.max(0, ...temporal.map((t) => t.total)));
  const range = stats?.date_range_start && stats.date_range_end ? `${fmtDate(stats.date_range_start)} to ${fmtDate(stats.date_range_end)}` : 'none yet';

  return (
    <>
      <Grid columns={4} gap="sm" as="ul" label="Tracker figures">
        <Stat as="li" label="Articles" value={(stats?.total_articles ?? 0).toLocaleString()} meta={`in ${period}`} />
        <Stat as="li" label="Date range" value={range} wrapValue size="compact" />
        <Stat as="li" label="Most active category" value={stats?.most_active_category ?? 'none yet'} wrapValue size="compact" />
        <Stat as="li" label="Articles in three or more categories" value={(stats?.multi_category_count ?? 0).toLocaleString()} />
      </Grid>

      <Panel
        title="Policy categories"
        headingLevel={3}
        description="How many articles fall in each of the ten categories. One article can sit in several."
        headerAside={
          <SegmentedControl className="policy-segmented"
            label="Chart"
            value={view}
            onValueChange={(v) => setView(v as typeof view)}
            options={[{ value: 'categories', label: 'By category' }, { value: 'trend', label: 'By month' }, { value: 'stacked', label: 'Top five by month' }]}
          />
        }
      >
        {view === 'categories' && (
          <BarList
            title="Articles per category"
            items={[...categories].sort((a, b) => b.article_count - a.article_count).map((c) => ({
              id: c.category, label: c.category, value: c.article_count, note: `${c.percentage}%`, detail: CATEGORY_DESCRIPTIONS[c.category],
            }))}
          />
        )}
        {view === 'trend' && (temporal.length < 2 ? <Text variant="caption">A monthly trend needs at least two months of articles.</Text> : (
          <LineChart
            title="Articles per month"
            categories={months}
            series={[{ id: 'total', label: 'Articles', color: 1, markers: true, values: temporal.map((t) => t.total) }]}
            yDomain={trend.domain}
            yTicks={trend.ticks}
          />
        ))}
        {view === 'stacked' && (
          <StackedBarChart
            title="The five largest categories, month by month"
            categories={months}
            series={top5.map((c, i) => ({ id: c, label: CATEGORY_SHORT_NAMES[c] ?? c, color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: temporal.map((t) => t.by_category[c] ?? 0) }))}
            emptyText="No monthly figures for this period."
          />
        )}
      </Panel>

      <Stack direction="row" justify="end">
        <TextLink href="https://www.trumpactiontracker.info/about" external>Where the category list comes from</TextLink>
      </Stack>
    </>
  );
}
