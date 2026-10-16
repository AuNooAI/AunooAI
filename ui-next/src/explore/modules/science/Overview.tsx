import { useState } from 'react';
import { ImagePanel } from '../common/ImagePanel';
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Grid, LineChart, SegmentedControl, SettingRow, Skeleton,
  Stack, StackedBarChart, StackedBars, Stat, Text,
} from '@aunoo/ui';
import type { ScienceCategory, ScienceStats, TemporalData } from '@monolith/scienceFundingApi';
import { categoryColor, categoryDescription, fmtDate, HOW_DATA_ARRIVES, periodText, shortName, ticks } from './labels';
import './science.css';

/*
 * Overview: the four headline figures and the category chart, as the old ScienceOverviewTab with
 * ScienceFundingStats and ScienceFundingCharts. Three views of the same categorised articles:
 * how many fall in each category, the monthly total, and the five biggest categories month by month.
 */

type ChartView = 'categories' | 'trend' | 'stacked';
const VIEWS = [
  { value: 'categories', label: 'Categories' },
  { value: 'trend', label: 'Monthly total' },
  { value: 'stacked', label: 'Category trends' },
];

export function Overview({ stats, categories, temporal, loading, daysBack }: {
  stats: ScienceStats | null;
  categories: ScienceCategory[] | null;
  temporal: TemporalData[] | null;
  loading: boolean;
  daysBack: number;
}) {
  const [view, setView] = useState<ChartView>('categories');
  if (loading && !stats) return <Skeleton variant="block" size="card" />;

  const empty = !stats || stats.total_articles === 0;
  const sorted = [...(categories ?? [])].sort((a, b) => b.article_count - a.article_count);
  const top5 = sorted.slice(0, 5).map((c) => c.category);
  const months = (temporal ?? []).map((t) => t.month);
  const monthTicks = ticks(Math.max(0, ...(temporal ?? []).map((t) => t.total)));

  return (
    <>
      <Grid columns={4} gap="md">
        <Stat label="Articles" value={(stats?.total_articles ?? 0).toLocaleString()} meta={`Categorised, ${periodText(daysBack)}`} />
        <Stat
          label="Date range"
          size="compact"
          wrapValue
          value={stats?.date_range_start && stats?.date_range_end ? `${fmtDate(stats.date_range_start)} to ${fmtDate(stats.date_range_end)}` : 'None yet'}
        />
        <Stat label="Most active category" size="compact" wrapValue value={stats?.most_active_category ?? 'None yet'} />
        <Stat label="Multi-category articles" value={(stats?.multi_category_count ?? 0).toLocaleString()} meta="Articles in three or more categories" />
      </Grid>

      <ImagePanel
        filename="science-funding-analysis"
        title="Science funding by category"
        description="Each article can fall in more than one category, so the category counts add up to more than the article total."
        headerAside={<SegmentedControl className="science-segmented" label="Chart" options={VIEWS} value={view} onValueChange={(v) => setView(v as ChartView)} />}
      >
        {empty ? (
          <EmptyState icon="Flask" title="No categorised articles yet">{HOW_DATA_ARRIVES}</EmptyState>
        ) : (
          <Stack gap="md">
            {view === 'categories' && (
              <StackedBars
                title="Articles per category"
                series={[{ id: 'n', label: 'Articles', color: 1 }]}
                rows={sorted.map((c) => ({ id: c.category, label: `${shortName(c.category)} (${c.percentage}%)`, values: [c.article_count] }))}
                emptyText="No category counts for this period."
              />
            )}
            {view === 'trend' && (
              months.length > 1 ? (
                <LineChart
                  title="Articles per month"
                  categories={months}
                  series={[{ id: 'total', label: 'Articles', color: 1, markers: true, values: (temporal ?? []).map((t) => t.total) }]}
                  yDomain={monthTicks.domain}
                  yTicks={monthTicks.ticks}
                  summary="Monthly totals cover at least the last 90 days, whatever period is picked, so a short period still shows a trend."
                />
              ) : <Text>A trend needs at least two months of articles.</Text>
            )}
            {view === 'stacked' && (
              <StackedBarChart
                title="The five biggest categories, month by month"
                categories={months}
                series={top5.map((c, i) => ({ id: c, label: shortName(c), color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: (temporal ?? []).map((t) => t.by_category?.[c] ?? 0) }))}
                emptyText="No monthly category counts yet."
              />
            )}
            <Collapsible>
              <CollapsibleTrigger variant="ghost" size="sm" className="science-wrap-trigger">What each category covers</CollapsibleTrigger>
              <CollapsibleContent>
                <Stack as="ul" gap="sm" label="Category descriptions">
                  {sorted.map((c) => (
                    <li key={c.category}>
                      <SettingRow
                        title={<span><span className="science-dot" style={{ background: categoryColor(c.category) }} aria-hidden="true" />{c.category}</span>}
                        description={`${categoryDescription(c.category)}${categoryDescription(c.category) ? '. ' : ''}${c.article_count} articles, trend ${c.recent_trend === 'up' ? 'rising' : c.recent_trend === 'down' ? 'falling' : 'steady'}.`}
                      />
                    </li>
                  ))}
                </Stack>
              </CollapsibleContent>
            </Collapsible>
          </Stack>
        )}
      </ImagePanel>
    </>
  );
}
