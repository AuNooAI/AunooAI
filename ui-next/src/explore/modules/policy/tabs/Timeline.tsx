import { useEffect, useState } from 'react';
import { Grid, LineChart, Panel, SegmentedControl, Stat, Text } from '@aunoo/ui';
import { fmtDate, niceTicks } from '../api';
import { BarList, LoadFailed, Loading } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyTimelineTab: articles per day with a 7-day average, by day of the week, and per
 * month. It loads when opened and again when the period changes (the old one kept the first
 * period's figures until the page was reloaded).
 */
export function Timeline({ pt }: { pt: PolicyTracker }) {
  const [view, setView] = useState<'daily' | 'weekday' | 'monthly'>('daily');
  const { timeline, loadTimeline, temporal } = pt;
  useEffect(() => {
    void loadTimeline();
  }, [loadTimeline]);

  const { dayOfWeek, daily } = timeline.data;
  if (timeline.loading && !daily.length) return <Loading />;
  if (timeline.failed) return <LoadFailed what="timeline" onRetry={() => void loadTimeline()} />;

  const last90 = daily.slice(-90);
  const dailyTicks = niceTicks(Math.max(0, ...last90.map((d) => Math.max(d.count, d.rolling_avg_7day))));
  const monthTicks = niceTicks(Math.max(0, ...temporal.map((t) => t.total)));
  const peakDay = dayOfWeek.length ? dayOfWeek.reduce((m, d) => (d.article_count > m.article_count ? d : m)) : null;
  const peakDaily = daily.length ? daily.reduce((m, d) => (d.count > m.count ? d : m)) : null;
  const avg = daily.length ? daily.reduce((s, d) => s + d.count, 0) / daily.length : null;

  return (
    <>
      <Panel
        title="When articles appear"
        headingLevel={3}
        headerAside={
          <SegmentedControl className="policy-segmented"
            label="View"
            value={view}
            onValueChange={(v) => setView(v as typeof view)}
            options={[{ value: 'daily', label: 'Per day' }, { value: 'weekday', label: 'Day of the week' }, { value: 'monthly', label: 'Per month' }]}
          />
        }
      >
        {view === 'daily' && (last90.length < 2 ? <Text variant="caption">Not enough days with articles to draw a line.</Text> : (
          <LineChart
            title="Articles per day, with the 7-day average (last 90 days of the period)"
            categories={last90.map((d) => d.date)}
            categoryLabels={last90.map((d) => fmtDate(d.date))}
            series={[
              { id: 'count', label: 'Articles that day', color: 2, values: last90.map((d) => d.count) },
              { id: 'avg', label: '7-day average', color: 1, values: last90.map((d) => d.rolling_avg_7day) },
            ]}
            yDomain={dailyTicks.domain}
            yTicks={dailyTicks.ticks}
          />
        ))}
        {view === 'weekday' && (
          <BarList title="Articles by day of the week" items={[...dayOfWeek].sort((a, b) => a.day_number - b.day_number).map((d) => ({ id: d.day, label: d.day, value: d.article_count, note: `${d.percentage}%` }))} />
        )}
        {view === 'monthly' && (temporal.length < 2 ? <Text variant="caption">A monthly line needs at least two months of articles.</Text> : (
          <LineChart
            title="Articles per month"
            categories={temporal.map((t) => t.month)}
            series={[{ id: 'total', label: 'Articles', color: 1, markers: true, values: temporal.map((t) => t.total) }]}
            yDomain={monthTicks.domain}
            yTicks={monthTicks.ticks}
          />
        ))}
      </Panel>

      <Grid columns={3} gap="sm" as="ul" label="Timeline figures">
        <Stat as="li" label="Busiest day of the week" value={peakDay?.day ?? 'none yet'} meta={peakDay ? `${peakDay.article_count} articles` : undefined} />
        <Stat as="li" label="Average per day" value={avg !== null ? avg.toFixed(1) : 'none yet'} meta="articles, counting days with none" />
        <Stat as="li" label="Busiest single day" value={peakDaily ? String(peakDaily.count) : 'none yet'} meta={peakDaily ? fmtDate(peakDaily.date) : undefined} />
      </Grid>
    </>
  );
}
