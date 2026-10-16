import { useEffect, useState } from 'react';
import { ImagePanel } from '../common/ImagePanel';
import { Banner, EmptyState, Grid, LineChart, SegmentedControl, Skeleton, StackedBars, Stat, Text } from '@aunoo/ui';
import { getDailyIntensity, getDayOfWeek, type DailyIntensityData, type DayOfWeekData, type TemporalData } from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { fmtDate, HOW_DATA_ARRIVES, periodText, SCIENCE_TOPIC, ticks } from './labels';
import './science.css';

/*
 * Timeline: when the coverage happened, as the old ScienceTimelineTab. Daily counts with a running
 * average (the server skips days with no articles, so it isn't a calendar 7-day average), the spread over the days of the week, and the monthly totals. It loads while open and
 * reloads when the period changes (the old tab loaded once and kept showing the first period).
 */

type View = 'daily' | 'week' | 'monthly';
const VIEWS = [
  { value: 'daily', label: 'Daily' },
  { value: 'week', label: 'Day of week' },
  { value: 'monthly', label: 'Monthly' },
];

export function Timeline({ daysBack, temporal, reloadKey }: { daysBack: number; temporal: TemporalData[] | null; reloadKey: number }) {
  const [view, setView] = useState<View>('daily');
  const [data, setData] = useState<{ week: DayOfWeekData[]; daily: DailyIntensityData[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    Promise.all([getDayOfWeek(SCIENCE_TOPIC, daysBack), getDailyIntensity(SCIENCE_TOPIC, daysBack)]).then(
      ([week, daily]) => live && setData({ week, daily }),
      (e) => {
        if (!live) return;
        setError(errorText(e));
        setData({ week: [], daily: [] });
      },
    );
    return () => {
      live = false;
    };
  }, [daysBack, reloadKey]);

  if (!data) return <Skeleton variant="block" size="card" />;
  const daily = data.daily.slice(-90);
  const total = data.daily.reduce((s, d) => s + d.count, 0);
  const peakDay = data.week.length ? data.week.reduce((m, d) => (d.article_count > m.article_count ? d : m)) : null;
  const peakDaily = data.daily.length ? data.daily.reduce((m, d) => (d.count > m.count ? d : m)) : null;
  const dailyTicks = ticks(Math.max(0, ...daily.map((d) => Math.max(d.count, d.rolling_avg_7day))));
  const monthTicks = ticks(Math.max(0, ...(temporal ?? []).map((t) => t.total)));

  return (
    <>
      {error && <Banner tone="error" title="The timeline didn’t load" description={error} />}
      <ImagePanel
        filename="science-temporal-analysis"
        title="When the coverage happened"
        description={`Articles in ${periodText(daysBack)}.`}
        headerAside={<SegmentedControl className="science-segmented" label="View" options={VIEWS} value={view} onValueChange={(v) => setView(v as View)} />}
      >
        {total === 0 && !(view === 'monthly' && (temporal?.length ?? 0) > 0) ? (
          <EmptyState icon="ClockCounterClockwise" title="Nothing to plot yet">{HOW_DATA_ARRIVES}</EmptyState>
        ) : (
          <>
            {view === 'daily' && (daily.length > 1 ? (
              <LineChart
                title="Articles per day, with a running average"
                categories={daily.map((d) => d.date)}
                categoryLabels={daily.map((d) => fmtDate(d.date, false))}
                series={[
                  { id: 'count', label: 'Articles that day', color: 1, values: daily.map((d) => d.count) },
                  { id: 'avg', label: 'Average of the last 7 days with articles', color: 2, dashed: true, values: daily.map((d) => d.rolling_avg_7day) },
                ]}
                yDomain={dailyTicks.domain}
                yTicks={dailyTicks.ticks}
                summary={`Days with no articles are left out, so the running average covers the last seven days that had any, which can stretch over more than a week.${data.daily.length > 90 ? ' Shows the last 90 days with articles.' : ''}`}
              />
            ) : <Text>Daily counts need at least two days with articles.</Text>)}
            {view === 'week' && (
              <StackedBars
                title="Articles by day of the week"
                series={[{ id: 'n', label: 'Articles', color: 1 }]}
                rows={[...data.week].sort((a, b) => a.day_number - b.day_number).map((d) => ({ id: d.day, label: `${d.day} (${d.percentage}%)`, values: [d.article_count] }))}
                emptyText="No articles by weekday for this period."
              />
            )}
            {view === 'monthly' && ((temporal?.length ?? 0) > 1 ? (
              <LineChart
                title="Articles per month"
                categories={(temporal ?? []).map((t) => t.month)}
                series={[{ id: 'total', label: 'Articles', color: 1, markers: true, values: (temporal ?? []).map((t) => t.total) }]}
                yDomain={monthTicks.domain}
                yTicks={monthTicks.ticks}
              />
            ) : <Text>A monthly trend needs at least two months of articles.</Text>)}
          </>
        )}
      </ImagePanel>
      <Grid columns={3} gap="md">
        <Stat label="Busiest weekday" value={peakDay && peakDay.article_count > 0 ? peakDay.day : 'None yet'} meta={peakDay && peakDay.article_count > 0 ? `${peakDay.article_count} articles` : undefined} />
        <Stat label="Average per day" value={data.daily.length ? (total / data.daily.length).toFixed(1) : 'None yet'} meta="Across the days that had articles" />
        <Stat label="Busiest day" value={peakDaily && peakDaily.count > 0 ? String(peakDaily.count) : 'None yet'} meta={peakDaily && peakDaily.count > 0 ? fmtDate(peakDaily.date) : undefined} />
      </Grid>
    </>
  );
}
