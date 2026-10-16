import { Chip, IconButton, Icon, Popover, Stack, Table, Text } from '@aunoo/ui';
import type { DataState, MetricMeta, SourceLegendRow } from '@monolith/marketMonitorApi';

/*
 * Whether a number was measured, as the old MarketMetric.tsx. A zero on the page must mean a
 * collector ran across the stated population and found nothing; every other empty-looking outcome
 * (never collected, collecting, failed, partial) is said in words. The server decides
 * (MetricMeta.measured and data_state from app/services/market_metrics.py).
 */

const STATE_TONE: Record<DataState, 'neutral' | 'warning' | 'info' | 'error'> = {
  healthy: 'neutral',
  observed_zero: 'neutral',
  partial: 'warning',
  stale: 'warning',
  collecting: 'info',
  never_collected: 'neutral',
  not_configured: 'neutral',
  failed: 'error',
};

/** The number only when it is a measurement; an em dash otherwise (a zero would read as a fact) */
export function metricValue(meta: MetricMeta | null | undefined, value: number | null | undefined): string {
  if (meta && !meta.measured) return '—';
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}

export function DataStateBadge({ meta }: { meta: MetricMeta | null | undefined }) {
  if (!meta || meta.data_state === 'healthy') return null;
  return <Chip tone={STATE_TONE[meta.data_state]} label={meta.state_detail ?? meta.data_state_label}>{meta.data_state_label}</Chip>;
}

/** The "What this means" control on every metric heading */
export function MetricHelp({ meta }: { meta: MetricMeta | null | undefined }) {
  if (!meta) return null;
  const rows: [string, string][] = [['Counts', meta.numerator]];
  if (meta.denominator) rows.push(['Out of', meta.denominator]);
  if (meta.window?.days != null) rows.push(['Period', `the last ${meta.window.days} days`]);
  if (meta.coverage) rows.push(['Collected', `${meta.coverage.label}${meta.coverage.pct_of_eligible != null ? ` (${meta.coverage.pct_of_eligible}%)` : ''}`]);
  if (meta.freshness?.last_success_at) rows.push(['Last collected', new Date(meta.freshness.last_success_at).toLocaleString('en-GB')]);
  rows.push(['State', `${meta.data_state_label}${meta.state_detail ? `: ${meta.state_detail}` : ''}`]);
  return (
    <Popover label={`What “${meta.label}” means`} title={meta.label} width="wide" trigger={<IconButton icon={<Icon name="Info" size="sm" />} label={`What “${meta.label}” means`} />}>
      <Stack gap="sm">
        <Text variant="caption">{meta.definition}</Text>
        <dl className="mm-dl">
          {rows.map(([k, v]) => (
            <Stack key={k} direction="row" gap="sm" wrap={false}>
              <Text as="span" variant="label">{k}</Text>
              <Text as="span" variant="caption">{v}</Text>
            </Stack>
          ))}
        </dl>
        {meta.sources.length > 0 && (
          <Stack gap="sm">
            <Text variant="label">Where it comes from</Text>
            {meta.sources.map((s, i) => (
              <Text key={i} variant="caption">
                {s.dataset} on {s.platform}, collected via {s.provider} · {s.ownership}
                {s.truncated ? ' · provider limit reached' : ''}
              </Text>
            ))}
          </Stack>
        )}
        {meta.limitations.length > 0 && (
          <Stack gap="sm">
            <Text variant="label">What it does not tell you</Text>
            <ul className="mm-plainlist">
              {meta.limitations.map((l, i) => <li key={i}><Text as="span" variant="caption">{l}</Text></li>)}
            </ul>
          </Stack>
        )}
      </Stack>
    </Popover>
  );
}

/** A metric heading: title, the help control, and the state when it isn't a plain measurement */
export function MetricHeading({ title, meta }: { title: string; meta: MetricMeta | null | undefined }) {
  return (
    <Stack direction="row" gap="sm">
      <Text as="span" variant="label">{title}</Text>
      <MetricHelp meta={meta} />
      <DataStateBadge meta={meta} />
    </Stack>
  );
}

/** For a Panel's headerAside: just the help control and the state */
export function MetricAside({ meta }: { meta: MetricMeta | null | undefined }) {
  if (!meta) return null;
  return (
    <Stack direction="row" gap="sm">
      <DataStateBadge meta={meta} />
      <MetricHelp meta={meta} />
    </Stack>
  );
}

/** In place of a chart when nothing defensible was measured */
export function UnmeasuredNotice({ meta }: { meta: MetricMeta | null | undefined }) {
  if (!meta || meta.measured) return null;
  return (
    <Stack gap="sm">
      <Text variant="label">{meta.data_state_label}</Text>
      {meta.state_detail && <Text variant="caption">{meta.state_detail}</Text>}
      <Text variant="caption">No figure is shown because none was measured.</Text>
    </Stack>
  );
}

/** Platform, provider and ownership per source, from the server */
export function SourceLegend({ rows }: { rows: SourceLegendRow[] }) {
  if (!rows?.length) return null;
  return (
    <Table
      caption="Where each kind of content comes from"
      hideCaption
      rows={rows}
      rowKey={(r) => r.key}
      columns={[
        { key: 'content', header: 'Content', rowHeader: true },
        { key: 'platform', header: 'Platform' },
        { key: 'provider', header: 'Collected by' },
        { key: 'ownership', header: 'Whose voice' },
      ]}
    />
  );
}
