import { useEffect, useState } from 'react';
import { Banner, Chip, Icon, IconButton, Panel, Skeleton, Stack, Table, Text, TextLink } from '@aunoo/ui';
import { datasetCsvDownloadUrl, getDataInventory, getMarketTable, type DatasetInfo, type SourceSetting } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { LinkButton } from '../../shared/SortTable';
import { fmtDateTime, SOURCE_MAP } from './labels';

/** Everything this market has stored. The CSV is the whole table; the preview is the first 200 rows */
export function Data({ ctx }: { ctx: MmContext }) {
  const { marketId, health } = ctx;
  const [inventory, setInventory] = useState<DatasetInfo[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [rows, setRows] = useState<{ total: number; rows: Record<string, unknown>[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getDataInventory(marketId).then((r) => live && setInventory(r.datasets), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId]);
  useEffect(() => {
    if (!open) {
      setRows(null);
      return;
    }
    let live = true;
    setRows(null);
    getMarketTable(marketId, open, 200).then((r) => live && setRows({ total: r.total, rows: r.rows }), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, open]);

  const cols = rows?.rows.length ? Object.keys(rows.rows[0]) : [];
  return (
    <>
      {error && <Banner tone="error" title="Something didn’t load" description={error} />}
      {health && health.sources.length > 0 && (
        <Panel
          title="Fetched by source, last 30 days"
          description="What each provider sent before duplicates were removed, and how much of it was new. A source with a high received count and few new records is mostly fetching again what it already sent."
        >
          <Table
            caption="Records fetched by source over 30 days"
            hideCaption
            rows={health.sources}
            rowKey={(s) => `${s.source}:${s.provider}`}
            columns={[
              { key: 'source', header: 'Source', rowHeader: true },
              { key: 'provider', header: 'Provider' },
              { key: 'records_received', header: 'Received', align: 'end', render: (s) => (s.records_received ?? 0).toLocaleString() },
              { key: 'records_new', header: 'New', align: 'end', render: (s) => (s.records_new ?? 0).toLocaleString() },
              { key: 'runs', header: 'Runs succeeded', align: 'end', render: (s) => `${s.succeeded}/${s.runs}` },
              { key: 'last_success', header: 'Last success', render: (s) => fmtDateTime(s.last_success) },
            ]}
          />
        </Panel>
      )}
      <Panel title="Stored datasets" description="Everything this market has stored. Open a dataset to see its first 200 rows; the CSV holds the whole table.">
        {inventory === null ? <Skeleton variant="text" lines={6} /> : (
          <Table
            caption="Stored datasets"
            hideCaption
            rows={inventory}
            rowKey={(d) => d.dataset}
            columns={[
              { key: 'dataset', header: 'Dataset', rowHeader: true, render: (d) => <LinkButton onClick={() => setOpen(open === d.dataset ? null : d.dataset)}>{d.dataset}</LinkButton> },
              { key: 'description', header: 'Holds', wrap: true },
              { key: 'rows', header: 'Rows', align: 'end', render: (d) => d.rows.toLocaleString() },
              { key: 'last_updated', header: 'Last updated', render: (d) => fmtDateTime(d.last_updated) },
              { key: 'csv', header: 'Download', render: (d) => <TextLink href={datasetCsvDownloadUrl(marketId, d.dataset)}>CSV</TextLink> },
            ]}
          />
        )}
      </Panel>
      {open && (
        <Panel
          title={`Preview: ${open}`}
          description={rows ? `Showing ${rows.rows.length} of ${rows.total.toLocaleString()} rows.` : undefined}
          headerAside={<IconButton icon={<Icon name="X" size="sm" />} label="Close the preview" onClick={() => setOpen(null)} />}
        >
          {rows === null ? <Skeleton variant="text" lines={6} /> : rows.rows.length === 0 ? <Text>Nothing stored yet.</Text> : (
            <Table
              caption={`First rows of ${open}`}
              hideCaption
              scroll
              rows={rows.rows}
              rowKey={(r) => String(rows.rows.indexOf(r))}
              columns={cols.map((c) => ({ key: c, header: c, render: (r: Record<string, unknown>) => { const v = r[c]; const s = v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v); return s.length > 120 ? `${s.slice(0, 120)}…` : s; } }))}
            />
          )}
        </Panel>
      )}
    </>
  );
}

/** What each source collects, where it lands and what a vendor needs on file before it can run */
export function SourceMap({ sources }: { sources: SourceSetting[] | null }) {
  return (
    <>
      <Panel
        title="One-time only: the vendor registry import"
        description="Country, founding year, headcount, funding total and category for the original vendor list came from a one-time CSV import, not an ongoing collector, so nothing refreshes them on a schedule. Ongoing collection only fills in a field the import left blank; it never overwrites a value the import set."
      />
      <Panel
        title="Data map"
        description="What each source collects, where it lands, and what a vendor needs on file before it can run at all. Cost and cadence come from the schedule in Sources and schedules settings. A source missing the identifier it needs quietly does nothing for that vendor rather than failing."
      >
        {sources === null ? <Skeleton variant="text" lines={8} /> : (
          <Table
            caption="What each source collects"
            hideCaption
            rows={SOURCE_MAP}
            rowKey={(r) => r.source}
            columns={[
              { key: 'label', header: 'Source', rowHeader: true },
              { key: 'collects', header: 'What it collects', wrap: true },
              { key: 'landsIn', header: 'Where it lands', wrap: true },
              { key: 'requires', header: 'Needs', wrap: true },
              {
                key: 'cost', header: 'Cost',
                render: (r) => { const s = sources.find((x) => x.source === r.source); return <Chip size="sm" tone={s?.paid ? 'warning' : 'muted'}>{s?.paid ? 'per record' : 'free'}</Chip>; },
              },
              {
                key: 'cadence', header: 'Runs',
                render: (r) => { const s = sources.find((x) => x.source === r.source); return r.manualOnly ? 'by hand only' : s ? (s.enabled ? `every ${s.effective_interval_hours}h` : 'off') : '—'; },
              },
            ]}
          />
        )}
      </Panel>
      <Stack gap="sm"><Text variant="caption">Sources not listed in the schedule show a dash under Runs.</Text></Stack>
    </>
  );
}
