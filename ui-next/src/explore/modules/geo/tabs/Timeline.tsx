import { useEffect, useState } from 'react';
import { ImagePanel } from '../../common/ImagePanel';
import { Banner, EmptyState, Grid, LineChart, Panel, Skeleton, Stat, Text } from '@aunoo/ui';
import {
  getDailyCounts, getDayOfWeekDistribution, getTimelineData,
  type DailyCount, type DayOfWeekData, type TimelineDataPoint,
} from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { BarList } from '../BarList';
import { shortDate, ticksFor } from '../labels';

/*
 * Coverage over time, as the old Timeline: daily articles with a 7-day average, the day of the week
 * they arrive, and article count, average intensity and active hotspots by day. The old page read the
 * daily and day-of-week figures over a fixed 30 days whatever period was picked; these follow the
 * period.
 */

export function Timeline({ daysBack }: { daysBack: number }) {
  const [timeline, setTimeline] = useState<TimelineDataPoint[] | null>(null);
  const [daily, setDaily] = useState<DailyCount[] | null>(null);
  const [weekdays, setWeekdays] = useState<DayOfWeekData[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setTimeline(null);
    setDaily(null);
    setWeekdays(null);
    setError(null);
    getTimelineData(undefined, daysBack).then((d) => live && setTimeline(d), (e) => { if (live) { setTimeline([]); setError(errorText(e)); } });
    getDailyCounts(undefined, daysBack).then((d) => live && setDaily(d), () => live && setDaily([]));
    getDayOfWeekDistribution(undefined, daysBack).then((d) => live && setWeekdays(d), () => live && setWeekdays([]));
    return () => {
      live = false;
    };
  }, [daysBack]);

  if (error) return <Banner tone="error" title="The timeline didn’t load" description={error} />;
  if (!timeline) return <Skeleton variant="block" size="card" />;
  if (timeline.length === 0 && daily?.length === 0) {
    return (
      <Panel title="Timeline">
        <EmptyState icon="ClockCounterClockwise" title="No timeline yet">Figures appear once articles have been read and linked to hotspots.</EmptyState>
      </Panel>
    );
  }

  const total = timeline.reduce((s, d) => s + d.article_count, 0);
  const peak = timeline.reduce<TimelineDataPoint | null>((m, d) => (!m || d.article_count > m.article_count ? d : m), null);
  const avgDaily = timeline.length ? Math.round(total / timeline.length) : 0;
  const avgIntensity = timeline.length ? timeline.reduce((s, d) => s + d.avg_intensity, 0) / timeline.length : 0;
  const peakIntensity = timeline.length ? Math.max(...timeline.map((d) => d.avg_intensity)) : 0;
  const busiest = weekdays?.length ? weekdays.reduce((m, d) => (d.article_count > m.article_count ? d : m), weekdays[0]) : null;

  const cats = timeline.map((d) => shortDate(d.date));
  const longCats = timeline.map((d) => new Date(d.date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }));
  const maxArticles = Math.max(1, ...timeline.map((d) => d.article_count));
  const maxHotspots = Math.max(1, ...timeline.map((d) => d.hotspot_count));
  const maxDaily = Math.max(1, ...(daily ?? []).map((d) => Math.max(d.article_count, d.rolling_avg)));

  return (
    <>
      <Grid columns={4} gap="sm">
        <Stat label="Articles" value={total.toLocaleString()} meta={`in the last ${daysBack} days`} />
        <Stat label="Busiest day" value={peak ? peak.article_count.toLocaleString() : '—'} meta={peak ? shortDate(peak.date) : undefined} />
        <Stat label="Daily average" value={avgDaily.toLocaleString()} meta={busiest ? `${busiest.day} is the busiest weekday (${busiest.article_count})` : undefined} />
        <Stat label="Average intensity" value={avgIntensity.toFixed(1)} meta={`out of 100; peak ${peakIntensity.toFixed(1)}`} />
      </Grid>

      {daily && daily.length > 0 && (
        <ImagePanel filename="geohotspots-daily-articles" title="Daily articles" description={`Articles per day, with the 7-day average. The daily average over the period is ${avgDaily}.`}>
          <LineChart
            title="Daily articles linked to hotspots"
            categories={daily.map((d) => shortDate(d.date))}
            series={[
              { id: 'n', label: 'Articles', color: 1, markers: true, values: daily.map((d) => d.article_count) },
              { id: 'avg', label: '7-day average', color: 2, dashed: true, values: daily.map((d) => Math.round(d.rolling_avg * 10) / 10) },
            ]}
            yDomain={[0, ticksFor(maxDaily).at(-1)!]}
            yTicks={ticksFor(maxDaily)}
          />
        </ImagePanel>
      )}

      {weekdays && weekdays.length > 0 && (
        <ImagePanel filename="geohotspots-articles-by-day-of-the-week" title="Articles by day of the week" description="Over the picked period.">
          <BarList rows={[...weekdays].sort((a, b) => a.day_num - b.day_num).map((d) => ({ id: d.day, label: d.day, value: d.article_count }))} />
        </ImagePanel>
      )}

      {timeline.length > 0 && (
        <Grid columns={2} gap="md">
          <ImagePanel filename="geohotspots-articles-over-time" title="Articles over time">
            <LineChart
              title="Articles over time"
              categories={cats}
              categoryLabels={longCats}
              series={[{ id: 'a', label: 'Articles', color: 1, fill: true, values: timeline.map((d) => d.article_count) }]}
              yDomain={[0, ticksFor(maxArticles).at(-1)!]}
              yTicks={ticksFor(maxArticles)}
            />
          </ImagePanel>
          <ImagePanel filename="geohotspots-active-hotspots-over-time" title="Active hotspots over time" description="Hotspots with at least one article that day.">
            <LineChart
              title="Active hotspots over time"
              categories={cats}
              categoryLabels={longCats}
              series={[{ id: 'h', label: 'Active hotspots', color: 3, fill: true, values: timeline.map((d) => d.hotspot_count) }]}
              yDomain={[0, ticksFor(maxHotspots).at(-1)!]}
              yTicks={ticksFor(maxHotspots)}
            />
          </ImagePanel>
          <ImagePanel filename="geohotspots-average-intensity" title="Average intensity" description="The average intensity score of that day’s hotspots, out of 100.">
            <LineChart
              title="Average intensity over time"
              categories={cats}
              categoryLabels={longCats}
              series={[{ id: 'i', label: 'Average intensity', color: 'negative', values: timeline.map((d) => Math.round(d.avg_intensity * 10) / 10) }]}
              yDomain={[0, 100]}
              yTicks={[0, 25, 50, 75, 100]}
            />
          </ImagePanel>
        </Grid>
      )}
      {timeline.length === 0 && <Text variant="caption">No per-day figures for this period.</Text>}
    </>
  );
}
