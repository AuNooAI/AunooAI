import { useEffect, useState } from 'react';
import { Grid, LineChart, Panel, SegmentedControl, StackedBarChart, Stack, Text } from '@aunoo/ui';
import { niceTicks } from '../api';
import { BarList, LoadFailed, Loading } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyThemesTab: themes, how they moved month by month, the institutions named, places
 * named, and escalation language. All of it is keyword matching on the server, not the AI. Each view
 * loads when picked and again when the period changes.
 */

type View = 'themes' | 'evolution' | 'entities' | 'geography' | 'escalation';

export function Themes({ pt }: { pt: PolicyTracker }) {
  const [view, setView] = useState<View>('themes');
  const { themes, loadThemes, entities, loadEntities, geography, loadGeography, escalation, loadEscalation } = pt;

  useEffect(() => {
    if (view === 'themes' || view === 'evolution') void loadThemes();
  }, [view, loadThemes]);
  useEffect(() => {
    if (view === 'entities') void loadEntities();
  }, [view, loadEntities]);
  useEffect(() => {
    if (view === 'geography') void loadGeography();
  }, [view, loadGeography]);
  useEffect(() => {
    if (view === 'escalation') void loadEscalation();
  }, [view, loadEscalation]);

  const current = view === 'themes' || view === 'evolution' ? themes : view === 'entities' ? entities : view === 'geography' ? geography : escalation;
  const retry = view === 'themes' || view === 'evolution' ? loadThemes : view === 'entities' ? loadEntities : view === 'geography' ? loadGeography : loadEscalation;

  return (
    <Panel
      title="Themes and language"
      headingLevel={3}
      description="Counted by matching keywords in each article, so a theme here is a word list, not a judgement."
      headerAside={
        <SegmentedControl className="policy-segmented"
          label="View"
          value={view}
          onValueChange={(v) => setView(v as View)}
          options={[
            { value: 'themes', label: 'Themes' },
            { value: 'evolution', label: 'Over time' },
            { value: 'entities', label: 'Institutions' },
            { value: 'geography', label: 'Places' },
            { value: 'escalation', label: 'Escalation' },
          ]}
        />
      }
    >
      {current.loading ? <Loading /> : current.failed ? <LoadFailed what={view === 'evolution' ? 'themes' : view} onRetry={() => void retry()} /> : (
        <>
          {view === 'themes' && (
            <BarList
              title="Articles per theme"
              items={themes.data.themes.map((t) => ({ id: t.theme, label: t.theme, value: t.article_count, note: `${t.percentage}%`, detail: t.keywords_matched.length ? `Matched on: ${t.keywords_matched.slice(0, 8).join(', ')}` : undefined }))}
            />
          )}
          {view === 'evolution' && <Evolution pt={pt} />}
          {view === 'entities' && (
            <BarList title="Government bodies and institutions mentioned" unit="mentions" items={entities.data.slice(0, 12).map((e) => ({ id: e.entity, label: e.entity, value: e.mention_count, note: `${e.percentage}%` }))} />
          )}
          {view === 'geography' && (
            <Grid columns={2} gap="md">
              <Stack gap="sm">
                <Text variant="label">In the United States</Text>
                <BarList title="US places mentioned" unit="mentions" items={geography.data.filter((g) => g.location_type === 'domestic').slice(0, 8).map((g) => ({ id: g.location, label: g.location, value: g.mention_count }))} />
              </Stack>
              <Stack gap="sm">
                <Text variant="label">Elsewhere</Text>
                <BarList title="Places abroad mentioned" unit="mentions" items={geography.data.filter((g) => g.location_type === 'international').slice(0, 8).map((g) => ({ id: g.location, label: g.location, value: g.mention_count }))} />
              </Stack>
            </Grid>
          )}
          {view === 'escalation' && <Escalation pt={pt} />}
        </>
      )}
    </Panel>
  );
}

function Evolution({ pt }: { pt: PolicyTracker }) {
  const { themes, evolution } = pt.themes.data;
  // The design system's stacked bars carry five colours, so the five largest themes are shown (the old chart showed six)
  const top = [...themes].sort((a, b) => b.article_count - a.article_count).slice(0, 5).map((t) => t.theme);
  return (
    <StackedBarChart
      title="The five largest themes, month by month"
      categories={evolution.map((e) => e.month)}
      series={top.map((t, i) => ({ id: t, label: t, color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: evolution.map((e) => e.by_theme[t] ?? 0) }))}
      emptyText="No monthly theme figures for this period."
    />
  );
}

function Escalation({ pt }: { pt: PolicyTracker }) {
  const { markers, trends } = pt.escalation.data;
  const ticks = niceTicks(Math.max(0, ...trends.map((t) => t.total_escalation_articles)));
  return (
    <Stack gap="lg">
      <Text variant="caption">Language that signals intensification: threats, military language, emergency powers, defiance of courts and violent imagery.</Text>
      <BarList title="Articles with escalation language" items={markers.map((m) => ({ id: m.marker_type, label: m.marker_type, value: m.article_count, note: `${m.percentage}%`, detail: m.keywords_matched.length ? `Matched on: ${m.keywords_matched.slice(0, 8).join(', ')}` : undefined }))} />
      {trends.length > 1 && (
        <LineChart
          title="Articles with any escalation language, per period"
          categories={trends.map((t) => t.period)}
          series={[{ id: 'total', label: 'Articles with escalation language', color: 'negative', markers: true, values: trends.map((t) => t.total_escalation_articles) }]}
          yDomain={ticks.domain}
          yTicks={ticks.ticks}
        />
      )}
    </Stack>
  );
}
