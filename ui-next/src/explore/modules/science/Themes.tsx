import { useEffect, useState } from 'react';
import { ImagePanel } from '../common/ImagePanel';
import { Banner, EmptyState, Grid, LineChart, SegmentedControl, Skeleton, Stack, StackedBarChart, StackedBars, Text } from '@aunoo/ui';
import {
  getEntities, getEscalationMarkers, getEscalationTrends, getGeography, getThemes, getThemesEvolution,
  type EntityData, type EscalationMarkerData, type EscalationTrend, type GeographyData, type ThemeData, type ThemeEvolution,
} from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { HOW_DATA_ARRIVES, periodText, SCIENCE_TOPIC, ticks } from './labels';
import './science.css';

/*
 * Themes: what the coverage is about, as the old ScienceThemesTab. Five views, each found by
 * matching keyword lists in the article text (not by the AI): themes, how themes changed by month,
 * institutions named, places named, and escalation language. Each view loads the first time it is
 * opened for the current period (the old tab kept the first period's data after a period change).
 */

type View = 'themes' | 'evolution' | 'entities' | 'geography' | 'escalation';
const VIEWS = [
  { value: 'themes', label: 'Themes' },
  { value: 'evolution', label: 'Over time' },
  { value: 'entities', label: 'Institutions' },
  { value: 'geography', label: 'Places' },
  { value: 'escalation', label: 'Escalation' },
];

interface Loaded {
  themes?: { themes: ThemeData[]; evolution: ThemeEvolution[] };
  entities?: EntityData[];
  geography?: GeographyData[];
  escalation?: { markers: EscalationMarkerData[]; trends: EscalationTrend[] };
}
const groupOf = (v: View): keyof Loaded => (v === 'evolution' ? 'themes' : v);

export function Themes({ daysBack, reloadKey }: { daysBack: number; reloadKey: number }) {
  const [view, setView] = useState<View>('themes');
  const [loaded, setLoaded] = useState<Loaded>({});
  const [error, setError] = useState<string | null>(null);

  // A new period or a refresh starts over
  useEffect(() => {
    setLoaded({});
    setError(null);
  }, [daysBack, reloadKey]);

  const group = groupOf(view);
  useEffect(() => {
    if (loaded[group] !== undefined) return;
    let live = true;
    const t = SCIENCE_TOPIC;
    const load: Promise<Partial<Loaded>> =
      group === 'themes' ? Promise.all([getThemes(t, daysBack), getThemesEvolution(t, daysBack)]).then(([themes, evolution]) => ({ themes: { themes, evolution } }))
        : group === 'entities' ? getEntities(t, daysBack).then((entities) => ({ entities }))
          : group === 'geography' ? getGeography(t, daysBack).then((geography) => ({ geography }))
            : Promise.all([getEscalationMarkers(t, daysBack), getEscalationTrends(t, daysBack)]).then(([markers, trends]) => ({ escalation: { markers, trends } }));
    load.then(
      (patch) => live && setLoaded((l) => ({ ...l, ...patch })),
      (e) => {
        if (!live) return;
        setError(errorText(e));
        // An empty result so the view stops loading; Refresh tries again
        setLoaded((l) => ({ ...l, [group]: group === 'themes' ? { themes: [], evolution: [] } : group === 'escalation' ? { markers: [], trends: [] } : [] }));
      },
    );
    return () => {
      live = false;
    };
  }, [group, loaded, daysBack]);

  const body = () => {
    if (view === 'themes' || view === 'evolution') {
      const d = loaded.themes;
      if (!d) return <Skeleton variant="block" size="card" />;
      if (!d.themes.length) return <EmptyState icon="Tag" title="No themes found">{HOW_DATA_ARRIVES}</EmptyState>;
      if (view === 'themes') {
        return (
          <StackedBars
            title="Articles per theme"
            series={[{ id: 'n', label: 'Articles', color: 1 }]}
            rows={[...d.themes].sort((a, b) => b.article_count - a.article_count).map((x) => ({ id: x.theme, label: `${x.theme} (${x.percentage}%)`, values: [x.article_count] }))}
          />
        );
      }
      const top = [...d.themes].sort((a, b) => b.article_count - a.article_count).slice(0, 5).map((x) => x.theme);
      return (
        <StackedBarChart
          title="The five biggest themes, month by month"
          categories={d.evolution.map((m) => m.month)}
          series={top.map((th, i) => ({ id: th, label: th, color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: d.evolution.map((m) => m.by_theme?.[th] ?? 0) }))}
          emptyText="No monthly theme counts for this period."
        />
      );
    }
    if (view === 'entities') {
      const d = loaded.entities;
      if (!d) return <Skeleton variant="block" size="card" />;
      if (!d.length) return <EmptyState icon="Buildings" title="No institutions named">{HOW_DATA_ARRIVES}</EmptyState>;
      return (
        <StackedBars
          title="Institutions and organisations named most often (top 12)"
          series={[{ id: 'n', label: 'Mentions', color: 2 }]}
          rows={d.slice(0, 12).map((x) => ({ id: x.entity, label: `${x.entity} (${x.percentage}%)`, values: [x.mention_count] }))}
        />
      );
    }
    if (view === 'geography') {
      const d = loaded.geography;
      if (!d) return <Skeleton variant="block" size="card" />;
      if (!d.length) return <EmptyState icon="Globe" title="No places named">{HOW_DATA_ARRIVES}</EmptyState>;
      const part = (type: GeographyData['location_type'], title: string, color: 1 | 3) => {
        const rows = d.filter((g) => g.location_type === type).slice(0, 8);
        return (
          <StackedBars
            title={title}
            series={[{ id: 'n', label: 'Mentions', color }]}
            rows={rows.map((g) => ({ id: g.location, label: g.location, values: [g.mention_count] }))}
            emptyText="None named in this period."
          />
        );
      };
      return (
        <Grid columns={2} gap="md">
          {part('domestic', 'US states (top 8)', 1)}
          {part('international', 'Other countries (top 8)', 3)}
        </Grid>
      );
    }
    const d = loaded.escalation;
    if (!d) return <Skeleton variant="block" size="card" />;
    if (!d.markers.length) return <EmptyState icon="Warning" title="No escalation language found">{HOW_DATA_ARRIVES}</EmptyState>;
    const tt = ticks(Math.max(0, ...d.trends.map((x) => x.total_escalation_articles)));
    return (
      <Stack gap="lg">
        <StackedBars
          title="Articles using each kind of escalation language"
          series={[{ id: 'n', label: 'Articles', color: 'negative' }]}
          rows={d.markers.map((m) => ({ id: m.marker_type, label: `${m.marker_type} (${m.percentage}%)`, values: [m.article_count] }))}
        />
        {d.trends.length > 1 ? (
          <LineChart
            title="Articles with escalation language, by period"
            categories={d.trends.map((x) => x.period)}
            series={[{ id: 'total', label: 'Articles with escalation language', color: 'negative', markers: true, values: d.trends.map((x) => x.total_escalation_articles) }]}
            yDomain={tt.domain}
            yTicks={tt.ticks}
          />
        ) : <Text variant="caption">A trend over time needs at least two periods.</Text>}
      </Stack>
    );
  };

  return (
    <>
      {error && <Banner tone="error" title="Part of this view didn’t load" description={error} />}
      <ImagePanel
        filename="science-thematic-analysis"
        title="What the coverage is about"
        description={`Found by matching fixed lists of words and names against article titles and summaries, in ${periodText(daysBack)}, not by the AI. An article can match several themes.`}
        headerAside={<SegmentedControl className="science-segmented" label="View" options={VIEWS} value={view} onValueChange={(v) => setView(v as View)} />}
      >
        {body()}
      </ImagePanel>
    </>
  );
}
