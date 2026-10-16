import { Grid, Panel, Stack, StackedBarChart } from '@aunoo/ui';
import { ClickableBars } from '../../../shared/ClickableBars';
import { CoverageLine, openFoundedYear, type PanelProps } from './common';

/*
 * When the vendors were founded, and when they started announcing things. The two share no x-axis,
 * so they are two charts side by side. Founding years describe the registry as it stands, so the
 * period selector doesn't apply to them.
 */
export function Formation({ ctx, data }: PanelProps) {
  const f = data.formation;
  if (!f || f.error) return null;
  const years = f.founded_by_year;
  const months = f.announcements_by_month;
  return (
    <Grid columns={2}>
      <Panel title="When these vendors were founded">
        <Stack gap="md">
          <CoverageLine
            coverage={f.coverage}
            note={`${f.founded_since_2023} of ${f.vendors_in_scope} were founded in 2023 or later. This is the current registry, not the period picked above.`}
          />
          <ClickableBars
            title="Vendors founded per year"
            bars={years.map((y) => ({ id: String(y.year), label: String(y.year), value: y.vendors }))}
            onSelect={(year) => openFoundedYear(ctx, year)}
            selectLabel={(b) => `Show the ${b.value} vendors founded in ${b.label}`}
            unit="vendors"
          />
        </Stack>
      </Panel>

      <Panel title="When they started announcing">
        <Stack gap="md">
          <CoverageLine coverage={f.announcement_coverage} note="Vendor posts by month. An announcement is a post that names something that happened." />
          <StackedBarChart
            title="Vendor posts per month, announcements and the rest"
            categories={months.map((m) => m.month)}
            series={[
              { id: 'signal', label: 'Announcements', color: 1, values: months.map((m) => m.signal) },
              { id: 'other', label: 'Other posts', color: 0, values: months.map((m) => Math.max(0, m.posts - m.signal)) },
            ]}
          />
        </Stack>
      </Panel>
    </Grid>
  );
}
