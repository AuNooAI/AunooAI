import { useEffect, useState } from 'react';
import { Button, Chip, Grid, Panel, SegmentedControl, Skeleton, Stack, StackedBars, Table, Text, TextLink } from '@aunoo/ui';
import { getJobPostings, type JobPosting } from '@monolith/marketMonitorApi';
import { LinkButton, SortTable, VendorLink } from '../../../shared/SortTable';
import { CoverageLine, type PanelProps } from './common';

type Cut = 'role' | 'function' | 'region' | 'seniority';

/** Observed hiring across the market, and openings per vendor. */
export function Hiring({ ctx, data }: PanelProps) {
  const [cut, setCut] = useState<Cut>('role');
  const [showJobs, setShowJobs] = useState(false);
  const [jobs, setJobs] = useState<JobPosting[] | null>(null);
  const [split, setSplit] = useState<number | null>(null);
  const hi = data.hiring;

  useEffect(() => {
    if (!showJobs || jobs) return;
    let live = true;
    getJobPostings(ctx.marketId).then((r) => live && setJobs(r.postings), () => live && setJobs([]));
    return () => {
      live = false;
    };
  }, [showJobs, jobs, ctx.marketId]);

  if (!hi || hi.error) return null;
  const bars: { label: string; openings: number }[] =
    cut === 'role' ? hi.by_role.slice(0, 12).map((r) => ({ label: r.role, openings: r.openings }))
      : cut === 'function' ? hi.by_function.map((r) => ({ label: r.function, openings: r.openings }))
        : cut === 'region' ? hi.by_region.map((r) => ({ label: r.region, openings: r.openings }))
          : hi.by_seniority.map((r) => ({ label: r.seniority, openings: r.openings }));
  const [first, second] = hi.by_vendor;
  const opened = split !== null ? hi.by_vendor.find((v) => v.brand_id === split) : undefined;
  const chips = (rec: Record<string, number>) => (
    <Stack direction="row" gap="sm">
      {Object.entries(rec).sort((a, b) => b[1] - a[1]).map(([k, n]) => <Chip key={k} tone="neutral" size="sm">{`${k} ${n}`}</Chip>)}
    </Stack>
  );

  return (
    <Grid columns={2}>
      <Panel
        title="Observed hiring"
        headerAside={
          <SegmentedControl
            label="Split openings by"
            options={[{ value: 'role', label: 'Role' }, { value: 'function', label: 'Function' }, { value: 'region', label: 'Region' }, { value: 'seniority', label: 'Seniority' }]}
            value={cut}
            onValueChange={(v) => setCut(v as Cut)}
          />
        }
      >
        <Stack gap="md">
          <Text>
            {hi.openings} open roles were observed across {hi.by_vendor.length} vendors.
            {first && ` Hiring is concentrated: ${first.vendor} accounts for ${first.openings} of them${second ? `, and ${second.vendor} for another ${second.openings}.` : '.'}`}
          </Text>
          <Text variant="caption">The mix of roles can show where companies are investing, but it doesn’t measure product maturity or commercial traction.</Text>
          <CoverageLine coverage={hi.coverage} />
          <StackedBars title={`Openings by ${cut}`} series={[{ id: 'openings', label: 'Openings', color: 1 }]} rows={bars.map((b) => ({ id: b.label, label: b.label, values: [b.openings] }))} emptyText="No open roles observed." />
          {cut === 'region' && hi.function_by_region.length > 0 && (
            <Stack gap="sm">
              <Text variant="caption">Function within each region. Engineering in one place and sales in another is a company expanding, not simply hiring.</Text>
              <Table
                caption="Openings by function within each region"
                hideCaption
                rows={hi.function_by_region}
                rowKey={(r) => String(r.region)}
                columns={[
                  { key: 'region', header: 'Region', rowHeader: true },
                  { key: 'engineering', header: 'Engineering', align: 'end' },
                  { key: 'sales', header: 'Sales', align: 'end' },
                  { key: 'marketing', header: 'Marketing', align: 'end' },
                  { key: 'operations', header: 'Operations', align: 'end' },
                ]}
              />
            </Stack>
          )}
        </Stack>
      </Panel>

      <Panel
        title="Openings per vendor"
        headerAside={<Button variant="secondary" size="sm" onClick={() => setShowJobs((s) => !s)}>{showJobs ? 'Show the counts' : 'Show the postings'}</Button>}
      >
        <Stack gap="md">
          <CoverageLine coverage={hi.coverage} />
          {showJobs ? (
            jobs === null ? <Skeleton variant="text" lines={6} /> : (
              <SortTable
                caption="Job postings"
                rows={jobs}
                rowKey={(j) => j.url ?? `${j.vendor}-${j.title}`}
                initialSort="vendor"
                scroll
                emptyText="No postings on file."
                columns={[
                  { key: 'vendor', label: 'Vendor', rowHeader: true, groupable: true, render: (j) => <VendorLink id={j.brand_id} name={j.vendor} color={ctx.colours.byId(j.brand_id)} onOpen={ctx.openVendor} /> },
                  { key: 'title', label: 'Role', wrap: true, render: (j) => (j.url ? <TextLink href={j.url} external>{j.title ?? 'Untitled role'}</TextLink> : j.title ?? '—') },
                  { key: 'function_group', label: 'Function', groupable: true },
                  { key: 'seniority', label: 'Level', groupable: true },
                  { key: 'location', label: 'Location', groupable: true, wrap: true },
                  { key: 'posted_date', label: 'Posted' },
                ]}
              />
            )
          ) : (
            <>
              <SortTable
                caption="Openings per vendor"
                rows={hi.by_vendor}
                rowKey={(v) => v.brand_id}
                initialSort="openings"
                initialDir="desc"
                scroll
                columns={[
                  { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => <VendorLink id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} /> },
                  {
                    key: 'openings', label: 'Open', align: 'end',
                    render: (v) => <LinkButton label={`List ${v.vendor}'s job listings`} onClick={() => ctx.openRecords({ kind: 'jobs', title: `${v.vendor}: job listings`, vendorId: v.brand_id, expectedTotal: v.openings })}>{v.openings}</LinkButton>,
                  },
                  { key: 'engineering', label: 'Engineering', align: 'end' },
                  { key: 'sales', label: 'Sales', align: 'end' },
                  {
                    key: 'split', label: 'Split', sortable: false,
                    render: (v) => <LinkButton onClick={() => setSplit(split === v.brand_id ? null : v.brand_id)}>{split === v.brand_id ? 'Hide' : 'Show'}</LinkButton>,
                  },
                ]}
              />
              {/* A count of twenty says a company is hiring; the split says whether it is building or selling */}
              {opened && (
                <Panel title={`${opened.vendor}: ${opened.openings} open`} headingLevel={4}>
                  <Stack gap="md">
                    <Stack gap="sm"><Text variant="label">By function</Text>{chips(opened.by_function)}</Stack>
                    <Stack gap="sm"><Text variant="label">By role</Text>{chips(opened.by_role)}</Stack>
                  </Stack>
                </Panel>
              )}
            </>
          )}
        </Stack>
      </Panel>
    </Grid>
  );
}
