import { useEffect, useState } from 'react';
import { Banner, Button, DonutChart, EmptyState, Grid, Icon, LineChart, Meter, Panel, Skeleton, Stack, Stat, Table, Text } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { getCategories, getCategoryTrends, type CategoryData, type CategoryTrendPeriod } from '../api';
import type { ThreatCtx } from '../context';
import { categoryLabel, fmtDay, scoreBand, severityLabel } from '../labels';
import { LinkButton } from '../parts';

/*
 * Threat types across everything filed (not just the header period), as the old ThreatCategoriesTab:
 * how many threats of each type, their average severity, and how many articles a picked type drew
 * each week.
 *
 * The old trend chart never drew: it sent the picked type as the topic filter and read fields the
 * server doesn't return. This reads the weekly counts per type and picks the one asked for.
 */

const DONUT_COLORS = [1, 2, 3, 4, 5] as const;

function meterTone(score: number): 'error' | 'warning' | 'neutral' | 'success' {
  if (score >= 80) return 'error';
  if (score >= 60) return 'warning';
  if (score >= 20) return 'neutral';
  return 'success';
}

export function Categories(ctx: ThreatCtx) {
  const [cats, setCats] = useState<CategoryData[] | null>(null);
  const [trends, setTrends] = useState<CategoryTrendPeriod[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getCategories().then((c) => {
      if (!live) return;
      const sorted = [...c].sort((a, b) => b.count - a.count);
      setCats(sorted);
      setPicked((p) => p ?? sorted[0]?.category ?? null);
    }, (e) => live && setError(errorText(e)));
    getCategoryTrends(90).then((t) => live && setTrends(t), () => live && setTrends([]));
    return () => {
      live = false;
    };
  }, []);

  if (error) return <Banner tone="error" title="Categories didn’t load" description={error} />;
  if (!cats) return <Skeleton variant="block" size="card" />;
  if (!cats.length) return <Panel title="Threat types"><EmptyState icon="Tag" title="No threats filed yet">Run “Update” to have the AI read collected articles and file threats by type.</EmptyState></Panel>;

  const sel = cats.find((c) => c.category === picked) ?? null;
  const total = cats.reduce((s, c) => s + c.count, 0);
  const top = cats.slice(0, 5);
  const rest = cats.slice(5).reduce((s, c) => s + c.count, 0);
  const series = sel && trends ? trends.map((t) => t.by_type?.[sel.category] ?? 0) : [];
  const trendMax = Math.max(0, ...series);
  const trendTop = trendMax <= 5 ? 5 : Math.ceil(trendMax / 5) * 5;

  return (
    <>
      <Grid columns={2}>
        <Panel title="Threat types" description={`${total} threat${total === 1 ? '' : 's'} filed across ${cats.length} type${cats.length === 1 ? '' : 's'}, all time.`}>
          <DonutChart
            title="Threats by type"
            segments={[
              ...top.map((c, i) => ({ id: c.category, label: categoryLabel(c.category), value: c.count, color: DONUT_COLORS[i] })),
              ...(rest ? [{ id: 'other', label: 'Other types', value: rest, color: 0 as const }] : []),
            ]}
            centerLabel={String(total)}
          />
        </Panel>
        <Panel title="By volume" description="Average severity is the mean score (0 to 100) of the type’s threats. Pick a type for its detail.">
          <Table
            caption="Threat types by volume"
            hideCaption
            rows={cats}
            rowKey={(c) => c.category}
            columns={[
              { key: 'category', header: 'Type', rowHeader: true, wrap: true, render: (c) => <LinkButton onClick={() => setPicked(c.category)}>{categoryLabel(c.category)}</LinkButton> },
              { key: 'count', header: 'Threats', align: 'end' },
              { key: 'total_articles', header: 'Articles', align: 'end' },
              { key: 'avg_severity', header: 'Average severity', render: (c) => <Meter label={`${categoryLabel(c.category)} average severity`} value={Math.round(c.avg_severity)} tone={meterTone(c.avg_severity)} /> },
            ]}
          />
        </Panel>
      </Grid>

      {sel && (
        <Panel
          title={categoryLabel(sel.category)}
          description={`${sel.count} threat${sel.count === 1 ? '' : 's'} of this type.`}
          headerAside={<Button variant="secondary" iconStart={<Icon name="Newspaper" size="sm" />} onClick={() => ctx.showArticles({ threatType: sel.category })}>Show the articles</Button>}
        >
          <Stack gap="md">
            <Grid columns={3}>
              <Stat label="Average severity" value={String(Math.round(sel.avg_severity))} meta={`Rated ${severityLabel(scoreBand(sel.avg_severity)).toLowerCase()}`} />
              <Stat label="Articles" value={sel.total_articles.toLocaleString()} />
              <Stat label="Share of all threats" value={`${total ? Math.round((sel.count / total) * 100) : 0}%`} />
            </Grid>
            {!trends ? <Skeleton variant="block" size="card" /> : !trends.length ? <Text variant="caption">No weekly counts for the last 90 days.</Text> : (
              <LineChart
                title={`${categoryLabel(sel.category)}: articles by week`}
                summary="Articles linked to threats of this type each week, by when the AI filed them, over the last 90 days."
                categories={trends.map((t) => t.period)}
                categoryLabels={trends.map((t) => fmtDay(t.period))}
                series={[{ id: 'n', label: 'Articles', color: 1, markers: true, values: series }]}
                yDomain={[0, trendTop]}
                yTicks={Array.from({ length: 6 }, (_, i) => Math.round((trendTop / 5) * i))}
              />
            )}
          </Stack>
        </Panel>
      )}
    </>
  );
}
