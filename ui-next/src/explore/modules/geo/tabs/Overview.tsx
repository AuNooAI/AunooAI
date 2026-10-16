import { Chip, DonutChart, EmptyState, Grid, Panel, Skeleton, Stack, Stat, Text, type ChartColor } from '@aunoo/ui';
import { ImagePanel } from '../../common/ImagePanel';
import type { Hotspot, OverviewStats, RiskLevel } from '@monolith/geopoliticalHotspotsApi';
import { BarList } from '../BarList';
import { MapViews } from '../MapViews';
import { HotspotRow } from './HotspotRow';
import { RISK_LABEL, RISK_ORDER, RISK_TONE, cap } from '../labels';

/*
 * The one-look state, as the old Overview: headline figures, risk levels (each opens its articles),
 * the map, the most intense hotspots, and how hotspots split by risk and by category.
 */

const RISK_CHART: Record<RiskLevel, ChartColor> = { critical: 'negative', high: 'caution', medium: 3, low: 'positive', info: 1 };

export function Overview({ stats, hotspots, daysBack, olderExists = false, onHotspot, onRisk, onCategory }: {
  stats: OverviewStats | null;
  hotspots: Hotspot[] | null;
  daysBack: number;
  /** Older hotspots exist outside this period (the frame shows how to see them) */
  olderExists?: boolean;
  onHotspot: (h: Hotspot) => void;
  onRisk: (r: RiskLevel) => void;
  onCategory: (c: string) => void;
}) {
  if (!stats || !hotspots) return <Skeleton variant="block" size="card" />;
  if (stats.total_hotspots === 0) {
    return (
      <Panel title="Overview">
        <EmptyState icon="Globe" title={olderExists ? `Nothing in the last ${daysBack} days` : 'No hotspots yet'}>
          {olderExists
            ? 'Older hotspots exist; pick a longer period above, or use “Update hotspots” to read recent articles.'
            : 'Hotspots appear once articles have been read for places. Use “Update hotspots” to read the curated articles of a topic.'}
        </EmptyState>
      </Panel>
    );
  }

  const categoryTotal = Object.values(stats.by_category).reduce((a, b) => a + b, 0);
  const categories = Object.entries(stats.by_category).sort((a, b) => b[1] - a[1]);
  const top = categories[0];
  const byId = new Map(hotspots.map((h) => [h.id, h]));

  return (
    <>
      <Grid columns={4} gap="sm">
        <Stat label="Hotspots" value={stats.total_hotspots.toLocaleString()} meta={`seen in the last ${daysBack} days`} />
        <Stat label="Countries" value={stats.countries_affected.toLocaleString()} />
        <Stat label="Articles" value={stats.total_articles.toLocaleString()} meta={`${stats.recent_articles.toLocaleString()} in the last 7 days`} />
        <Stat
          label="Escalating"
          value={stats.escalating_count.toLocaleString()}
          tone={stats.escalating_count > 0 ? 'error' : 'default'}
          meta={`${stats.de_escalating_count.toLocaleString()} de-escalating`}
        />
      </Grid>
      <Text variant="caption">
        A hotspot is escalating when the tone of its last 7 days of coverage turned clearly more negative than over the previous 30 days, or its
        coverage jumped by half again with a negative tone. De-escalating is the reverse. Trends are recalculated every 6 hours.
        {top ? ` The most common category is ${cap(top[0])}, with ${top[1]} hotspots (${Math.round((top[1] / Math.max(1, categoryTotal)) * 100)}%).` : ''}
      </Text>

      <Panel title="Risk levels" description="Each level opens its articles.">
        <Stack direction="row" gap="sm">
          {RISK_ORDER.map((r) => (
            <Chip key={r} tone={RISK_TONE[r]} onClick={() => onRisk(r)} label={`Show articles at ${RISK_LABEL[r].toLowerCase()} risk`}>
              {`${RISK_LABEL[r]}: ${(stats.by_risk_level[r] || 0).toLocaleString()}`}
            </Chip>
          ))}
        </Stack>
      </Panel>

      <Grid columns="main-aside" gap="md">
        <Panel title="Map" description="Click a hotspot to see its articles.">
          <MapViews hotspots={hotspots} onHotspot={onHotspot} title="Overview map of hotspots" labelTop={8} />
        </Panel>
        <Panel title="Most intense hotspots">
          {stats.top_hotspots.length === 0 ? <Text>No hotspots found.</Text> : (
            <Stack as="ul" gap="sm" label="Most intense hotspots">
              {stats.top_hotspots.map((h, i) => {
                const full = byId.get(h.id);
                return <li key={h.id}><HotspotRow rank={i + 1} hotspot={h} onOpen={full ? () => onHotspot(full) : undefined} /></li>;
              })}
            </Stack>
          )}
        </Panel>
      </Grid>

      <Grid columns={2} gap="md">
        <ImagePanel filename="geohotspots-hotspots-by-risk-level" title="Hotspots by risk level">
          <DonutChart
            title="Hotspots by risk level"
            segments={RISK_ORDER.filter((r) => (stats.by_risk_level[r] || 0) > 0).map((r) => ({ id: r, label: RISK_LABEL[r], value: stats.by_risk_level[r], color: RISK_CHART[r] }))}
            centerLabel={`${stats.total_hotspots} hotspots`}
          />
        </ImagePanel>
        <Panel title="Hotspots by category" description="Click a category to see its articles.">
          <BarList
            rows={categories.map(([c, n]) => ({ id: c, label: cap(c), value: n, valueText: `${n} hotspots (${((n / Math.max(1, categoryTotal)) * 100).toFixed(1)}%)` }))}
            onPick={onCategory}
            pickLabel={(l) => `Show ${l} articles`}
            empty="No categories yet."
          />
        </Panel>
      </Grid>
    </>
  );
}
