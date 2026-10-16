import { Chip, Grid, Panel, Skeleton, Stack, Stat, Table, Text } from '@aunoo/ui';
import type { CollectionStateResponse } from '@monolith/marketMonitorApi';
import type { MmContext } from '../../context';
import { LinkButton } from '../../shared/SortTable';
import { AnalystFeeds } from '../briefings/AnalystFeeds';
import { SEVERITY_TONE } from './labels';

/** Collection overview: analyst feeds, the headline counts, count reconciliation and the last run per source */
export function CollectionOverview({ ctx, openTasks, collectionState }: { ctx: MmContext; openTasks: number | null; collectionState: CollectionStateResponse | null }) {
  const { overview, pulse, market, health } = ctx;
  if (!overview) return <Skeleton variant="block" size="card" />;
  const c = overview.coverage;
  // The registry's own count and the header's are allowed to differ (this one includes excluded
  // vendors), but the gap should be visible rather than silent
  const reconcile = [
    { surface: 'Header and Vendors tab count', n: c.vendors, basis: 'watching plus paused, without excluded vendors' },
    { surface: 'Registry (all rows)', n: c.registry, basis: 'every row ever added, excluded ones included' },
    { surface: 'Excluded', n: c.excluded, basis: 'marked out of scope, kept so they can be brought back' },
    { surface: 'Collecting', n: c.watching, basis: 'collection switched on' },
    { surface: 'Observed at least once', n: c.observed, basis: 'any reading, all time' },
  ];
  return (
    <>
      <AnalystFeeds marketId={ctx.marketId} askConfirm={ctx.askConfirm} />
      <Grid columns={4}>
        <Stat label="Vendors" value={market.vendors} />
        <Stat label="Collecting" value={market.collecting} action={<LinkButton onClick={() => ctx.openDrill('watched')}>Show these vendors</LinkButton>} />
        <Stat label="Open reviews" value={openTasks ?? '—'} meta="Review tasks waiting on the Vendors tab" />
        <Stat label="No LinkedIn page" value={health?.coverage?.without_linkedin ?? '—'} action={<LinkButton onClick={() => ctx.openDrill('no_linkedin')}>Show these vendors</LinkButton>} />
      </Grid>
      <Panel title="Count reconciliation" description="The same market, counted by each place that reports it.">
        <Table
          caption="Count reconciliation"
          hideCaption
          rows={reconcile}
          rowKey={(r) => r.surface}
          columns={[
            { key: 'surface', header: 'Where', rowHeader: true },
            { key: 'n', header: 'Reports', align: 'end' },
            { key: 'basis', header: 'Counts', wrap: true },
          ]}
        />
      </Panel>
      <Grid columns={2}>
        {pulse && pulse.open_questions.length > 0 && (
          <Panel title="Open review tasks" description="By kind and severity. Work through them on the Vendors tab.">
            <Stack direction="row" gap="sm">
              {pulse.open_questions.map((q, i) => (
                <Chip key={i} tone={SEVERITY_TONE[q.severity] ?? 'neutral'}>{`${q.n} ${q.kind.replace(/_/g, ' ')} (${q.severity})`}</Chip>
              ))}
            </Stack>
          </Panel>
        )}
        <Panel title="Last run per source" description="The state of the most recent run, not a 30-day history.">
          {!overview.last_runs.length ? <Text>No runs yet.</Text> : (
            <Table
              caption="Last run per source"
              hideCaption
              scroll
              rows={overview.last_runs}
              rowKey={(r) => r.source}
              columns={[
                { key: 'source', header: 'Source', rowHeader: true },
                { key: 'records_received', header: 'Records', align: 'end' },
                {
                  key: 'status', header: 'Status',
                  render: (r) => {
                    // A source nobody schedules isn't broken because its last hand-run failed months ago
                    const manualOnly = collectionState?.sources.some((s) => s.source === r.source && !s.scheduled) ?? false;
                    if (manualOnly && r.status !== 'succeeded') return <Chip size="sm" tone="muted" label={r.error ?? undefined}>{`manual only · last run ${r.status}`}</Chip>;
                    return <Chip size="sm" tone={r.status === 'succeeded' ? 'success' : r.status === 'partial' ? 'warning' : 'error'} label={r.error ?? undefined}>{r.status}</Chip>;
                  },
                },
              ]}
            />
          )}
        </Panel>
      </Grid>
    </>
  );
}
