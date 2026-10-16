import { Eyebrow, Grid, Panel, ScatterChart, SettingRow, Stack, StackedBars, Text } from '@aunoo/ui';
import { LinkButton, VendorLink } from '../../../shared/SortTable';
import { CoverageLine, type PanelProps } from './common';

/*
 * The most funded vendors (disclosed totals, incumbents left out), funding stage, Crunchbase's Growth
 * and Heat scores, and investors backing more than one vendor. None of them follow the period selector.
 */
export function Funding({ ctx, data, investorsThin }: PanelProps & { investorsThin: boolean }) {
  const fu = data.funding;
  if (!fu || fu.error) return null;
  // The server reports the true total beside the top 25 it lists (older servers send only the list)
  const sharedTotal = (fu as { shared_investors_total?: number }).shared_investors_total ?? fu.shared_investors.length;
  const vlink = (id: number, name: string) => <VendorLink id={id} name={name} color={ctx.colours.byId(id)} onOpen={ctx.openVendor} />;

  // Ranked by the two scores averaged; both are already on Crunchbase's 0 to 100 scale
  const ranked = fu.momentum
    .filter((m) => m.growth_score !== null || m.heat_score !== null)
    .map((m) => ({ ...m, combined: ((m.growth_score ?? 0) + (m.heat_score ?? 0)) / 2 }))
    .sort((a, b) => b.combined - a.combined);
  const scored = fu.momentum.filter((m) => m.growth_score !== null && m.heat_score !== null);
  const scoreRow = (m: (typeof ranked)[number]) => (
    <li key={m.brand_id}>
      <SettingRow
        title={vlink(m.brand_id, m.vendor)}
        description={`Growth ${m.growth_score ?? '—'} · attention ${m.heat_score ?? '—'}${m.cb_rank !== null ? ` · Crunchbase rank ${Number(m.cb_rank).toLocaleString()}` : ''}`}
      />
    </li>
  );

  const raised = fu.raised;
  const money = (m: number) => (m >= 1000 ? `$${(m / 1000).toFixed(2)}B` : `$${Number(m.toFixed(1))}M`);

  return (
    <Stack gap="lg">
      {raised && (
        <Panel title="Most funded vendors">
          <Stack gap="md">
            <Text variant="caption">
              Disclosed total funding to date, in $M. {raised.incumbents_left_out} large incumbents are left out, because
              a whole company&rsquo;s funding is not comparable with a startup&rsquo;s.
              {raised.median_musd !== null ? ` The median across vendors with a disclosed total is ${money(raised.median_musd)}.` : ''}
            </Text>
            <StackedBars
              title="Vendors ranked by disclosed total funding, $M"
              series={[{ id: 'raised', label: 'Disclosed total, $M', color: 1 }]}
              rows={raised.top.map((v) => ({ id: String(v.brand_id), label: v.vendor, values: [Number(v.total_musd.toFixed(1))] }))}
              emptyText="No vendor has a disclosed total yet."
            />
            <Text variant="caption">
              {raised.disclosed} of {raised.eligible} vendors have a disclosed total.
              {raised.declared_no_amount > 0 ? ` ${raised.declared_no_amount} say they are undisclosed or bootstrapped.` : ''}
              {raised.not_found > 0 ? ` For ${raised.not_found} we have not found a figure.` : ''}
              {' '}Totals are kept by hand from announcements, so a round from the last few days may not be in yet.
            </Text>
          </Stack>
        </Panel>
      )}

      <Grid columns={2}>
        <Panel title="Funding stage across the market">
          <Stack gap="md">
            <CoverageLine coverage={fu.coverage} note="Latest Crunchbase reading per vendor, not the period picked above." />
            <StackedBars
              title="Vendors per funding stage"
              series={[{ id: 'vendors', label: 'Vendors', color: 1 }]}
              rows={fu.stages.map((s) => ({ id: s.stage, label: s.stage, values: [s.vendors] }))}
              emptyText="No Crunchbase pages have been read yet."
            />
          </Stack>
        </Panel>

        <Panel title="Crunchbase Growth against Heat">
          <Stack gap="md">
            <CoverageLine
              coverage={fu.coverage}
              note="Growth and Heat are Crunchbase’s own scores from 0 to 100. We don’t compute them and can’t reproduce them, and neither is a forecast: Heat is how much attention a company gets now, not a prediction."
            />
            <ScatterChart
              title="Crunchbase Growth against Heat, per vendor"
              xLabel="Growth"
              yLabel="Heat (attention)"
              max={100}
              points={scored.map((m) => ({ id: String(m.brand_id), label: m.vendor, x: m.growth_score!, y: m.heat_score!, color: 1 }))}
              emptyText="No vendor has both scores yet."
            />
            {ranked.length >= 4 && (
              <Grid columns={2}>
                <Stack gap="sm">
                  <Eyebrow as="h4">Growing fast and getting noticed</Eyebrow>
                  <Text variant="caption">Candidates for outreach.</Text>
                  <Stack as="ul" gap="sm" label="Highest Growth and Heat">{ranked.slice(0, 5).map(scoreRow)}</Stack>
                </Stack>
                <Stack gap="sm">
                  <Eyebrow as="h4">Slowing down and going quiet</Eyebrow>
                  <Text variant="caption">Lowest combined scores.</Text>
                  <Stack as="ul" gap="sm" label="Lowest Growth and Heat">{ranked.slice(-5).reverse().map(scoreRow)}</Stack>
                </Stack>
              </Grid>
            )}
          </Stack>
        </Panel>
      </Grid>

      {!investorsThin && (
        <Panel
          title="Investors backing more than one vendor"
          description={sharedTotal > fu.shared_investors.length ? `The ${fu.shared_investors.length} backing the most vendors, of ${sharedTotal}` : undefined}
          headerAside={fu.shared_investors.length > 0 ? (
            <LinkButton onClick={() => ctx.openRecords({ kind: 'investors', title: 'Investors backing more than one vendor', expectedTotal: sharedTotal })}>
              Full list, with the evidence behind each
            </LinkButton>
          ) : undefined}
        >
          <Stack gap="md">
            <CoverageLine coverage={fu.coverage} note="Overlap can only show up among the pages we have read." />
            {fu.shared_investors.length === 0 ? (
              <Text>None among the vendors read so far.</Text>
            ) : (
              <Stack as="ul" gap="sm" label="Shared investors">
                {fu.shared_investors.map((inv) => <li key={inv.investor}><SettingRow title={inv.investor} description={inv.backing.join(', ')} /></li>)}
              </Stack>
            )}
          </Stack>
        </Panel>
      )}
    </Stack>
  );
}
