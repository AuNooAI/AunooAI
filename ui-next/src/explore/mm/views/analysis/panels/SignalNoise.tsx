import { useState } from 'react';
import { Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Panel, SegmentedControl, Stack, StackedBars, Text } from '@aunoo/ui';
import { SortTable, VendorLink } from '../../../shared/SortTable';
import { CoverageLine, pct, type PanelProps } from './common';

/** What each vendor's own posts contain: announcements, opinion or promotion. */
export function SignalNoise({ ctx, data }: PanelProps) {
  const [order, setOrder] = useState<'count' | 'share'>('count');
  const sn = data.signal_noise;
  if (!sn || sn.error) return null;
  const rows = [...sn.vendors];
  if (order === 'share') rows.sort((a, b) => (b.signal_share ?? -1) - (a.signal_share ?? -1));
  const total = sn.totals.signal + sn.totals.commentary + sn.totals.noise;

  return (
    <Panel
      title="What each vendor’s posts actually contain"
      headerAside={
        <SegmentedControl
          label="Order vendors by"
          options={[{ value: 'count', label: 'By count' }, { value: 'share', label: 'By share' }]}
          value={order}
          onValueChange={(v) => setOrder(v as 'count' | 'share')}
        />
      }
    >
      <Stack gap="md">
        <CoverageLine coverage={sn.coverage} note={`${sn.totals.signal} of ${total} vendor posts announce something.`} />
        {order === 'share' && (
          <Text variant="caption">
            Share is only worked out for vendors with at least {sn.min_posts_for_ratio} posts. A vendor with three posts, all announcements, isn’t the most
            substantive vendor in the market.
          </Text>
        )}
        <StackedBars
          title="Vendor posts by kind"
          series={[
            { id: 'signal', label: 'Announcement', color: 'positive' },
            { id: 'commentary', label: 'Opinion', color: 'neutral' },
            { id: 'noise', label: 'Promotion', color: 0 },
          ]}
          rows={rows.map((v) => ({ id: String(v.brand_id), label: v.vendor, values: [v.signal, v.commentary, v.noise] }))}
          emptyText="No vendor posts have been read yet."
        />
        {sn.signal_kinds.length > 0 && (
          <Stack gap="sm">
            <Text variant="caption">What the announcements were about:</Text>
            <Stack direction="row" gap="sm">
              {sn.signal_kinds.map((k) => <Chip key={k.kind} tone="success" size="sm">{`${k.kind} ${k.n}`}</Chip>)}
            </Stack>
          </Stack>
        )}
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm">The same figures as a table</CollapsibleTrigger>
          <CollapsibleContent>
            <SortTable
              caption="Vendor posts by kind"
              rows={rows}
              rowKey={(v) => v.brand_id}
              initialSort="posts"
              initialDir="desc"
              columns={[
                { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => <VendorLink id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} /> },
                { key: 'signal', label: 'Announcements', align: 'end' },
                { key: 'commentary', label: 'Opinion', align: 'end' },
                { key: 'noise', label: 'Promotion', align: 'end' },
                { key: 'posts', label: 'Posts', align: 'end' },
                { key: 'signal_share', label: 'Share announcing', align: 'end', render: (v) => pct(v.signal_share) },
              ]}
            />
          </CollapsibleContent>
        </Collapsible>
      </Stack>
    </Panel>
  );
}
