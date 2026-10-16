import { useEffect, useState } from 'react';
import { Banner, Grid, LineChart, Panel, SegmentedControl, Skeleton, StackedBarChart, Text, type StackedSeries } from '@aunoo/ui';
import {
  getActors, getCategoriesData, getCategoryTrends, getCountriesData, getEscalationMarkers,
  type ActorData, type CategoryData, type CategoryTrendPeriod, type CountryStats, type EscalationData,
} from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { BarList } from '../BarList';
import { cap, shortDate, ticksFor } from '../labels';

/*
 * Themes in the coverage, as the old Themes tab: every category, how the top categories moved week
 * by week, the countries with most hotspots and most coverage, the actors named, and escalation
 * signals. Each view loads when first opened. Categories and countries cover every hotspot on file;
 * trends, actors and escalation follow the period. The old tab's Regions view repeated the Regions
 * tab and is left out here.
 */

type View = 'categories' | 'trends' | 'countries' | 'actors' | 'escalation';
const VIEWS = [
  { value: 'categories', label: 'Categories' },
  { value: 'trends', label: 'Trends' },
  { value: 'countries', label: 'Countries' },
  { value: 'actors', label: 'Actors' },
  { value: 'escalation', label: 'Escalation' },
];
const ACTOR_TYPE: Record<string, string> = { state: 'state', non_state: 'non-state group', organization: 'organisation', location: 'place' };

function useLoad<T>(enabled: boolean, load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setData(null);
    setError(null);
    load().then((d) => live && setData(d), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [enabled, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error };
}

export function Themes({ daysBack, onCategory }: { daysBack: number; onCategory: (c: string) => void }) {
  const [view, setView] = useState<View>('categories');
  const [seen, setSeen] = useState<Set<View>>(new Set(['categories']));
  const pick = (v: View) => {
    setView(v);
    setSeen((s) => new Set(s).add(v));
  };
  // Weekly buckets need a few weeks to show a trend; a year reads better by month
  const trendDays = Math.max(daysBack, 28);
  const granularity = daysBack > 180 ? 'monthly' : 'weekly';

  const cats = useLoad<CategoryData[]>(seen.has('categories'), () => getCategoriesData(), []);
  const trends = useLoad<CategoryTrendPeriod[]>(seen.has('trends'), () => getCategoryTrends(undefined, trendDays, granularity), [trendDays, granularity]);
  const countries = useLoad<CountryStats[]>(seen.has('countries'), () => getCountriesData(), []);
  const actors = useLoad<ActorData[]>(seen.has('actors'), () => getActors(undefined, daysBack), [daysBack]);
  const escalation = useLoad<EscalationData>(seen.has('escalation'), () => getEscalationMarkers(undefined, daysBack), [daysBack]);

  const body = () => {
    if (view === 'categories') {
      if (cats.error) return <Banner tone="error" title="Categories didn’t load" description={cats.error} />;
      if (!cats.data) return <Skeleton variant="text" lines={8} />;
      const list = cats.data.filter((c) => c.count > 0).sort((a, b) => b.count - a.count);
      const total = list.reduce((s, c) => s + c.count, 0);
      return (
        <Panel title="All threat categories" description="Every category with its hotspots, articles and average intensity (out of 100), across all hotspots on file. Click one to see its articles.">
          <BarList
            rows={list.map((c) => ({
              id: c.category, label: cap(c.category), value: c.count,
              valueText: `${c.count} hotspots (${total ? ((c.count / total) * 100).toFixed(1) : 0}%) · ${c.total_articles} articles · intensity ${c.avg_intensity.toFixed(0)}`,
              tone: c.avg_intensity >= 60 ? 'error' : c.avg_intensity >= 40 ? 'warning' : 'neutral',
            }))}
            onPick={onCategory}
            pickLabel={(l) => `Show ${l} articles`}
            empty="No categories yet."
          />
        </Panel>
      );
    }
    if (view === 'trends') {
      if (trends.error) return <Banner tone="error" title="Trends didn’t load" description={trends.error} />;
      if (!trends.data) return <Skeleton variant="block" size="card" />;
      const totals: Record<string, number> = {};
      for (const p of trends.data) for (const [c, n] of Object.entries(p.by_category)) totals[c] = (totals[c] || 0) + n;
      const top = Object.entries(totals).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([c]) => c);
      const colours = [1, 2, 3, 4, 5] as const;
      const series: StackedSeries[] = top.map((c, i) => ({ id: c, label: cap(c), color: colours[i], values: trends.data!.map((p) => p.by_category[c] || 0) }));
      const other = trends.data.map((p) => Object.entries(p.by_category).filter(([c]) => !top.includes(c)).reduce((s, [, n]) => s + n, 0));
      if (other.some((n) => n > 0)) series.push({ id: 'other', label: 'Other categories', color: 0, values: other });
      return (
        <Panel title="How the categories moved" description={`Articles per ${granularity === 'weekly' ? 'week' : 'month'} over the last ${trendDays} days, for the five biggest categories and the rest together.`}>
          <StackedBarChart
            title="Articles by category over time"
            categories={trends.data.map((p) => shortDate(p.period))}
            series={series}
            emptyText="No trend data for this period."
          />
        </Panel>
      );
    }
    if (view === 'countries') {
      if (countries.error) return <Banner tone="error" title="Countries didn’t load" description={countries.error} />;
      if (!countries.data) return <Skeleton variant="text" lines={8} />;
      const name = (c: CountryStats) => c.country_name || c.country_code;
      const byHotspots = [...countries.data].sort((a, b) => b.total_hotspots - a.total_hotspots).slice(0, 10);
      const byArticles = [...countries.data].sort((a, b) => b.total_articles - a.total_articles).slice(0, 10);
      return (
        <Grid columns={2} gap="md">
          <Panel title="Most hotspots" description="The ten countries with the most hotspots, all on file.">
            <BarList rows={byHotspots.map((c) => ({ id: c.country_code, label: name(c), value: c.total_hotspots, valueText: `${c.total_hotspots} hotspots · ${c.total_articles} articles` }))} empty="No country figures yet." />
          </Panel>
          <Panel title="Most coverage" description="The ten countries with the most linked articles.">
            <BarList rows={byArticles.map((c) => ({ id: c.country_code, label: name(c), value: c.total_articles, valueText: `${c.total_articles} articles · ${c.total_hotspots} hotspots` }))} empty="No country figures yet." />
          </Panel>
        </Grid>
      );
    }
    if (view === 'actors') {
      if (actors.error) return <Banner tone="error" title="Actors didn’t load" description={actors.error} />;
      if (!actors.data) return <Skeleton variant="text" lines={8} />;
      return (
        <Panel title="Actors named" description={`States, groups, organisations and places named in the last ${daysBack} days of hotspot coverage, top 15.`}>
          <BarList
            rows={actors.data.slice(0, 15).map((a) => ({ id: a.actor, label: a.actor, value: a.mention_count, valueText: `${a.mention_count} mentions (${a.percentage}%) · ${ACTOR_TYPE[a.actor_type] ?? a.actor_type}` }))}
            empty="No actors found for this period."
          />
        </Panel>
      );
    }
    if (escalation.error) return <Banner tone="error" title="Escalation signals didn’t load" description={escalation.error} />;
    if (!escalation.data) return <Skeleton variant="block" size="card" />;
    const t = escalation.data.trends;
    const maxCount = Math.max(1, ...t.map((p) => Math.max(p.total_articles, p.escalating_count)));
    const label = (p: (typeof t)[number]) => (p.period_date ? shortDate(p.period_date) : p.period);
    return (
      <>
        <Panel title="Escalation signals" description={`Kinds of escalation the article analysis found in the last ${daysBack} days, by number of articles.`}>
          <BarList rows={escalation.data.markers.map((m) => ({ id: m.marker_type, label: m.marker_type, value: m.article_count, valueText: `${m.article_count} articles (${m.percentage}%)` }))} empty="No escalation signals found." />
        </Panel>
        {t.length > 0 ? (
          <Grid columns={2} gap="md">
            <Panel title="Articles and escalating articles" description="Per week.">
              <LineChart
                title="Articles and escalating articles per week"
                categories={t.map(label)}
                series={[
                  { id: 'a', label: 'Articles', color: 1, values: t.map((p) => p.total_articles) },
                  { id: 'e', label: 'Escalating', color: 'negative', values: t.map((p) => p.escalating_count) },
                ]}
                yDomain={[0, ticksFor(maxCount).at(-1)!]}
                yTicks={ticksFor(maxCount)}
              />
            </Panel>
            <Panel title="Average intensity" description="Per week, out of 100.">
              <LineChart
                title="Average intensity per week"
                categories={t.map(label)}
                series={[{ id: 'i', label: 'Average intensity', color: 'negative', values: t.map((p) => Math.round(p.avg_intensity * 10) / 10) }]}
                yDomain={[0, 100]}
                yTicks={[0, 25, 50, 75, 100]}
              />
            </Panel>
          </Grid>
        ) : <Text variant="caption">No weekly escalation figures for this period.</Text>}
      </>
    );
  };

  return (
    <>
      <SegmentedControl label="Theme view" options={VIEWS} value={view} onValueChange={(v) => pick(v as View)} />
      {body()}
    </>
  );
}
