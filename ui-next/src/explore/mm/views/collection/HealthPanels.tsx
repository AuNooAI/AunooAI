import { Chip, Panel, Stack, Table, Text } from '@aunoo/ui';
import type { CollectionRun, CollectionStateResponse, SourceHealth } from '@monolith/marketMonitorApi';
import { SourceLegend } from '../../shared/metric';
import { fmtDateTime } from './labels';

/**
 * Whether a zero on this page is a measurement. Separate from HealthPanel, which answers "is the
 * collector working": this one's denominator is the source's own eligible vendors, not the whole
 * registry. A source with no vendors set up for it isn't broken, and a source that reached 20 of 39
 * vendors isn't healthy; both used to read as the same "no data".
 */
export function CollectionStatePanel({ state }: { state: CollectionStateResponse | null }) {
  if (!state) return null;
  const unmeasured = new Set(state.unmeasured_states);
  return (
    <>
      <Panel
        title="Can these numbers be believed?"
        description="One row per source. Collected is how many of the vendors this source can run for it actually reached, so a source with no vendors set up reads as not configured rather than empty."
      >
        <Table
          caption="Collection state per source"
          hideCaption
          rows={state.sources}
          rowKey={(s) => s.source}
          columns={[
            { key: 'source', header: 'Source', rowHeader: true, render: (s) => `${s.source}${s.scheduled ? '' : ' (not scheduled)'}` },
            {
              key: 'state', header: 'State',
              render: (s) => <Chip size="sm" tone={s.state === 'healthy' ? 'neutral' : unmeasured.has(s.state) ? 'error' : 'warning'}>{state.state_labels[s.state] ?? s.state}</Chip>,
            },
            { key: 'coverage', header: 'Collected', align: 'end', render: (s) => (s.coverage.eligible ? `${s.coverage.successful}/${s.coverage.eligible}` : '—') },
            { key: 'why', header: 'Why', wrap: true, render: (s) => s.state_detail ?? '' },
          ]}
        />
      </Panel>
      <Panel
        title="Where coverage comes from"
        description="The platform something was published on and the provider we collected it through are different things. Bright Data is a provider and LinkedIn is a platform; Xpoz is a provider whose items carry their own platform."
      >
        <SourceLegend rows={state.legend} />
      </Panel>
    </>
  );
}

/** Per-source outcomes over 30 days and the raw run log. Shown in Collection and in settings, so the two can't drift apart */
export function HealthPanel({ health, runs }: { health: SourceHealth; runs: CollectionRun[] | null }) {
  return (
    <>
      <Panel title="Source health" description="Outcomes per source over the last 30 days. The state is that of the most recent run.">
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <Chip tone={health.providers.brightdata_linkedin_enabled ? 'success' : 'muted'}>{`LinkedIn collection ${health.providers.brightdata_linkedin_enabled ? 'on' : 'off'}`}</Chip>
            <Chip tone={health.providers.webhook_secret_set ? 'success' : 'muted'}>{`Callback secret ${health.providers.webhook_secret_set ? 'set' : 'not set'}`}</Chip>
          </Stack>
          {!health.sources.length ? <Text>No collection runs in the last 30 days.</Text> : (
            <Table
              caption="Source health over 30 days"
              hideCaption
              rows={health.sources}
              rowKey={(s) => `${s.source}:${s.provider}`}
              columns={[
                { key: 'source', header: 'Source', rowHeader: true },
                {
                  key: 'state', header: 'Last run',
                  render: (s) => <Chip size="sm" tone={s.state === 'healthy' ? 'success' : s.state === 'failing' ? 'error' : 'neutral'}>{s.state === 'in_flight' ? 'running' : s.state}</Chip>,
                },
                {
                  key: 'runs', header: 'Over 30 days', wrap: true,
                  // Zero new records is a different outcome from a failure
                  render: (s) => `${s.succeeded} succeeded, ${s.failed} failed${s.stale_hours !== null ? ` · last success ${s.stale_hours}h ago` : ''}${s.found_nothing ? ' · no new records' : ''}`,
                },
                { key: 'last_error', header: 'Last error', wrap: true, render: (s) => (s.last_error ? <Text as="span" variant="caption" tone="error">{s.last_error}</Text> : '') },
              ]}
            />
          )}
        </Stack>
      </Panel>
      {runs && runs.length > 0 && (
        <Panel title="Recent runs" description="The last 20 collection runs, newest first.">
          <Table
            caption="Recent collection runs"
            hideCaption
            scroll
            rows={runs}
            rowKey={(r) => String(r.id)}
            columns={[
              { key: 'id', header: 'Run', render: (r) => `#${r.id}` },
              { key: 'source', header: 'Source', rowHeader: true },
              { key: 'vendor', header: 'Vendor', render: (r) => r.vendor ?? '—' },
              { key: 'status', header: 'Status' },
              { key: 'records_new', header: 'New', align: 'end' },
              { key: 'latency_ms', header: 'Took', align: 'end', render: (r) => (r.latency_ms !== null ? `${r.latency_ms} ms` : '—') },
              { key: 'started_at', header: 'Started', render: (r) => (r.started_at ? fmtDateTime(r.started_at) : '—') },
            ]}
          />
        </Panel>
      )}
    </>
  );
}
