import { useState } from 'react';
import { DonutChart, Eyebrow, Grid, Panel, SegmentedControl, SettingRow, Stack, StackedBarChart, Text, type ChartColor } from '@aunoo/ui';
import type { ChannelMix } from '@monolith/marketMonitorApi';
import { SortTable, VendorLink } from '../../../shared/SortTable';
import { CoverageLine, pct, type PanelProps } from './common';
import { ClickableBars } from '../../../shared/ClickableBars';
import { DualScatter } from '../../../shared/DualScatter';

/*
 * Share of voice (what other people said), who posts most against who gets the most reaction, and
 * where the coverage comes from. A vendor's own posts are volume, not voice, so they never count
 * toward share of voice.
 */
export function Voice({ ctx, data, mix, sovThin }: PanelProps & { mix: ChannelMix | null; sovThin: boolean }) {
  const sov = data.share_of_voice;
  const [chart, setChart] = useState<'bar' | 'pie'>('bar');
  if (!sov || sov.error || sov.vendors.length === 0) return null;
  const vlink = (id: number, name: string) => <VendorLink id={id} name={name} color={ctx.colours.byId(id)} onOpen={ctx.openVendor} />;

  const earned = sov.vendors.filter((v) => v.earned > 0).sort((a, b) => b.earned - a.earned);
  // A donut is compared slice to slice, so only three named colours stay distinguishable; the rest fold into "Other"
  const top = earned.slice(0, 3);
  const rest = earned.slice(3);
  const segments = [
    ...top.map((v, i) => ({ id: String(v.brand_id), label: `${v.vendor} (${pct(v.earned_share, 1)})`, value: v.earned, color: (i + 1) as ChartColor })),
    ...(rest.length ? [{ id: 'other', label: `Other (${rest.length} vendors)`, value: rest.reduce((s, v) => s + v.earned, 0), color: 0 as ChartColor }] : []),
  ];
  const measured = sov.vendors.filter((v) => v.reactions_per_post !== null);

  return (
    <Stack gap="lg">
      <Grid columns={2}>
        {!sovThin && (
          <Panel
            title="Share of voice"
            headerAside={sov.earned_total > 0 ? (
              <SegmentedControl label="Chart type" options={[{ value: 'bar', label: 'Bars' }, { value: 'pie', label: 'Donut' }]} value={chart} onValueChange={(v) => setChart(v as 'bar' | 'pie')} />
            ) : undefined}
          >
            <Stack gap="md">
              <CoverageLine coverage={sov.coverage} note={`Out of ${sov.earned_total} mentions by somebody other than the vendor.`} />
              <Text variant="caption">
                The share of what other people said. A vendor’s own posts don’t count here at all: they are volume, not voice, and they appear in the next panel.
              </Text>
              {sov.earned_total === 0 ? (
                <Text>Nobody outside the vendors has mentioned any of them yet.</Text>
              ) : chart === 'bar' ? (
                <ClickableBars
                  title="Mentions by others, per vendor"
                  orientation="horizontal"
                  bars={earned.map((v) => ({ id: String(v.brand_id), label: `${v.vendor} (${pct(v.earned_share, 1)})`, value: v.earned, color: ctx.colours.byId(v.brand_id) }))}
                  onSelect={(id) => ctx.openVendor(Number(id))}
                  selectLabel={(b) => `Open the vendor page: ${b.label}, ${b.value} mentions by others`}
                  unit="mentions"
                />
              ) : (
                <DonutChart title="Share of voice" segments={segments} centerLabel={`${sov.earned_total} mentions`} />
              )}
            </Stack>
          </Panel>
        )}

        <Panel title="Who shouts loudest, and who is heard">
          <Stack gap="md">
            <Text variant="caption">
              Posting a lot and getting a reaction aren’t the same thing, and the gap between them is the finding. {sov.reactions_total.toLocaleString()} reactions
              measured. Vendors with fewer than five measured posts are left out, because an average over two posts isn’t an average.
            </Text>
            <DualScatter
              title="Posts published against reactions per post"
              dots={measured.map((v) => ({ id: String(v.brand_id), label: v.vendor, x: v.own_posts, y: v.reactions_per_post ?? 0, color: ctx.colours.byId(v.brand_id) }))}
              xLabel="Posts published"
              yLabel="Reactions per post"
              onSelect={(id) => ctx.openVendor(Number(id))}
            />
            <SortTable
              caption="Posts published against reactions per post"
              rows={measured}
              rowKey={(v) => v.brand_id}
              initialSort="reactions_per_post"
              initialDir="desc"
              scroll
              emptyText="No vendor has enough measured posts yet."
              columns={[
                { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => vlink(v.brand_id, v.vendor) },
                { key: 'own_posts', label: 'Posts published', align: 'end' },
                { key: 'reactions_per_post', label: 'Reactions per post', align: 'end' },
                { key: 'earned', label: 'Mentions by others', align: 'end' },
              ]}
            />
          </Stack>
        </Panel>
      </Grid>

      {sov.loudest.length >= 4 && (
        <Panel title="Loudest and quietest vendors" description={`Own posts in the last ${sov.days ?? ctx.periodDays} days.`}>
          <Grid columns={2}>
            <Stack gap="sm">
              <Eyebrow as="h4">Loudest: most own posts</Eyebrow>
              <Stack as="ul" gap="sm" label="Loudest vendors">
                {sov.loudest.slice(0, 10).map((v) => (
                  <li key={v.brand_id}><SettingRow title={vlink(v.brand_id, v.vendor)} description={`${v.own_posts} post${v.own_posts === 1 ? '' : 's'} about itself`} /></li>
                ))}
              </Stack>
            </Stack>
            <Stack gap="sm">
              <Eyebrow as="h4">Quietest: collected, and said nothing</Eyebrow>
              {/* Both conditions hold: no own posts in the window, and a successful collection for that vendor. The date is the
                  vendor's last post at any time, so a vendor quiet this month isn't called silent forever. */}
              <Stack as="ul" gap="sm" label="Quietest vendors">
                {sov.quietest.slice(0, 10).map((v) => (
                  <li key={v.brand_id}>
                    <SettingRow title={vlink(v.brand_id, v.vendor)} description={v.last_posted_at ? `Last posted ${String(v.last_posted_at).slice(0, 10)}` : 'No post on record'} />
                  </li>
                ))}
              </Stack>
              {sov.quietest_total > 10 && <Text variant="caption">{`${sov.quietest_total - 10} more of ${sov.quietest_total} in all.`}</Text>}
              {sov.unmeasured_total > 0 && (
                <Stack gap="sm">
                  <Eyebrow as="h4">{`Not measured: ${sov.unmeasured_total} never collected`}</Eyebrow>
                  <Text variant="caption">Post collection has never worked for these, so we can’t say whether they are quiet.</Text>
                  <Stack as="ul" gap="sm" label="Vendors never collected">
                    {sov.unmeasured.slice(0, 10).map((v) => <li key={v.brand_id}>{vlink(v.brand_id, v.vendor)}</li>)}
                  </Stack>
                </Stack>
              )}
            </Stack>
          </Grid>
        </Panel>
      )}

      {mix && mix.by_month.length > 0 && (
        <Panel title="Where the coverage comes from">
          <Stack gap="md">
            <Text variant="caption">
              {mix.total} items by month and kind. Vendor posts dominate by volume throughout, which is why they’re shown apart from everything else rather than added
              into it.
            </Text>
            <StackedBarChart
              title="Coverage per month by kind of source"
              categories={mix.by_month.map((m) => String(m.month))}
              series={[
                { id: 'news', label: 'News', color: 1, values: mix.by_month.map((m) => Number(m.news ?? 0)) },
                { id: 'vendor', label: 'Vendor blogs', color: 2, values: mix.by_month.map((m) => Number(m.vendor ?? 0)) },
                { id: 'social', label: 'Vendor posts', color: 3, values: mix.by_month.map((m) => Number(m.social ?? 0)) },
                { id: 'discussion', label: 'Practitioners', color: 4, values: mix.by_month.map((m) => Number(m.discussion ?? 0)) },
                { id: 'research', label: 'Research', color: 5, values: mix.by_month.map((m) => Number(m.research ?? 0)) },
              ]}
            />
          </Stack>
        </Panel>
      )}
    </Stack>
  );
}
