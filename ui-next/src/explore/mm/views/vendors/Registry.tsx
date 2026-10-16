import { useMemo, useState } from 'react';
import { Button, Chip, Grid, Icon, IconButton, Panel, Select, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import { addVendor, ALL_IN_SCOPE, setVendorCollection, type Facets, type Vendor, type VendorFilter, type VendorSwitch } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { Missing, SortTable, VendorLink } from '../../shared/SortTable';
import { takeFoundedFilter } from './handoff';

/*
 * The vendor registry, as the old Vendors view's "All" segment: find and filter vendors, add one by
 * name, and switch collection and brand monitoring per vendor or in bulk. The two switches are
 * independent and cost different things: collection pays to fetch the vendor's site and LinkedIn,
 * brand monitoring also tracks it in Brand Watcher with its own sentiment and alerts.
 */

/** A null amount under a funding state means it was never disclosed: show the state, not a zero */
export function fundingLabel(v: Vendor) {
  const f = v.baseline?.funding_baseline;
  if (!f?.status) return '—';
  if (f.total_musd === null || f.total_musd === undefined) return f.status;
  return `$${f.total_musd}M`;
}

const SWITCH_WORDS: Record<VendorSwitch, { name: string; on: string; off: string }> = {
  collection: { name: 'collection', on: 'Collecting', off: 'Not collecting' },
  brand_monitoring: { name: 'brand monitoring', on: 'Monitored as a brand', off: 'Not monitored as a brand' },
};

export function Registry({ ctx, facets }: { ctx: MmContext; facets: Facets | null }) {
  const { marketId, vendors, colours, notify, askConfirm, reload, openVendor } = ctx;
  const [search, setSearch] = useState('');
  const [funding, setFunding] = useState('');
  const [founded, setFounded] = useState(takeFoundedFilter);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSite, setNewSite] = useState('');

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (vendors ?? []).filter((v) => (!q || v.display_name.toLowerCase().includes(q)) && (!funding || v.baseline?.funding_baseline?.status === funding) && (!founded || String(v.baseline?.founded_year ?? '') === founded));
  }, [vendors, search, funding, founded]);
  // On a single-segment market the sub-category column would repeat one value on every row
  const showSub = useMemo(() => new Set(shown.map((v) => v.baseline?.taxonomy?.sub_category ?? '—')).size > 1, [shown]);

  const apply = async (filter: VendorFilter, enabled: boolean, field: VendorSwitch) => {
    setBusy(true);
    try {
      const r = await setVendorCollection(marketId, enabled, filter, false, field);
      notify(
        `${r.changed ?? 0} vendor${r.changed === 1 ? '' : 's'} updated (${SWITCH_WORDS[field].name}).` +
          (r.keywords_rewritten ? ` ${r.keywords_rewritten} keyword list${r.keywords_rewritten === 1 ? '' : 's'} rewritten so they don’t match ordinary words.` : ''),
      );
      reload();
    } catch (e) {
      notify(`Not changed: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  /** Bulk changes check first what would change, then ask before doing it */
  const bulk = async (filter: VendorFilter, enabled: boolean, field: VendorSwitch, what: string) => {
    setBusy(true);
    try {
      const dry = await setVendorCollection(marketId, enabled, filter, true, field);
      if (!dry.would_change) {
        notify(`${dry.matched} vendors match and none would change.`);
        return;
      }
      const words = SWITCH_WORDS[field].name;
      askConfirm({
        title: `${enabled ? 'Switch on' : 'Switch off'} ${words} for ${dry.would_change} vendor${dry.would_change === 1 ? '' : 's'}?`,
        message: `${what}: ${dry.matched} vendors match, and ${dry.would_change} would change.${field === 'collection' && enabled ? ' Collection fetches each vendor’s website and LinkedIn, which costs money on every run.' : ''}`,
        action: enabled ? `Switch on for ${dry.would_change}` : `Switch off for ${dry.would_change}`,
        onConfirm: () => void apply(filter, enabled, field),
      });
    } catch (e) {
      notify(`Couldn’t check: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const r = await addVendor(marketId, newName.trim(), newSite.trim() || undefined);
      notify(`${r.display_name} added and watched.`);
      setNewName('');
      setNewSite('');
      setAdding(false);
      reload();
    } catch (e) {
      notify(`Couldn’t add that vendor: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const switchCell = (v: Vendor, field: VendorSwitch) => {
    const on = field === 'collection' ? v.collection_enabled : v.brand_monitoring_enabled;
    const w = SWITCH_WORDS[field];
    return (
      <IconButton
        icon={<Icon name={on ? 'CheckCircle' : 'Minus'} size="sm" />}
        label={`${on ? w.on : w.off}: ${on ? 'switch off' : 'switch on'} ${w.name} for ${v.display_name}`}
        disabled={busy}
        onClick={() => void apply({ brand_ids: [v.brand_id] }, !on, field)}
      />
    );
  };

  const bulkPanel = (field: VendorSwitch, title: string, what: string) => {
    const on = (vendors ?? []).filter((v) => (field === 'collection' ? v.collection_enabled : v.brand_monitoring_enabled)).length;
    return (
      <Panel title={title} description={`${what}${vendors ? ` ${on} on.` : ''}`} headingLevel={3}>
        <Stack direction="row" gap="sm">
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void bulk(ALL_IN_SCOPE, true, field, 'All vendors in scope')}>Switch on for all</Button>
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void bulk(ALL_IN_SCOPE, false, field, 'All vendors in scope')}>Switch off for all</Button>
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void bulk({ funding_status: ['Disclosed'] }, true, field, 'Vendors with disclosed funding')}>Switch on for funded</Button>
        </Stack>
      </Panel>
    );
  };

  if (!vendors) return <Skeleton variant="block" size="card" />;

  return (
    <Stack gap="lg">
      <Grid columns={2}>
        {bulkPanel('collection', 'Collection', 'Watch the vendor’s website and LinkedIn.')}
        {bulkPanel('brand_monitoring', 'Brand monitoring', 'Also track the vendor as a brand, with its own sentiment and alerts.')}
      </Grid>

      <Panel
        title="Vendors"
        description={`${shown.length} of ${vendors.length} shown. Open a vendor for its detail page.`}
        headerAside={!adding && <Button variant="secondary" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setAdding(true)}>Add vendor</Button>}
      >
        <Stack gap="md">
          {/* A company that shows up in the market's coverage without being tracked needs one row, not a re-import */}
          {adding && (
            <Stack direction="row" gap="sm">
              <TextField label="Vendor name" value={newName} onChange={setNewName} onSubmit={() => void add()} />
              <TextField label="Website (optional)" type="url" value={newSite} onChange={setNewSite} onSubmit={() => void add()} />
              <Button disabled={busy || !newName.trim()} busy={busy} onClick={() => void add()}>Add</Button>
              <Button variant="ghost" onClick={() => { setAdding(false); setNewName(''); setNewSite(''); }}>Cancel</Button>
            </Stack>
          )}
          <Stack direction="row" gap="sm">
            <TextField label="Find a vendor" hideLabel type="search" placeholder="Find a vendor" value={search} onChange={setSearch} />
            <Select
              label="Funding state"
              hideLabel
              icon="Funnel"
              value={funding || 'all'}
              onValueChange={(v) => setFunding(v === 'all' ? '' : v)}
              options={[{ value: 'all', label: 'All funding states' }, ...(facets?.funding_status ?? []).map((f) => ({ value: f.value, label: `${f.value} (${f.n})` }))]}
            />
            {funding && <Chip tone="accent" icon={<Icon name="X" size="sm" />} label={`Remove the ${funding} filter`} onClick={() => setFunding('')}>{funding}</Chip>}
            {founded && <Chip tone="accent" icon={<Icon name="X" size="sm" />} label={`Remove the founded in ${founded} filter`} onClick={() => setFounded('')}>{`Founded ${founded}`}</Chip>}
          </Stack>
          <SortTable<Vendor>
            caption="Vendors in this market"
            rows={shown}
            rowKey={(v) => v.brand_id}
            initialSort="vendor"
            scroll
            emptyText="No vendors match."
            columns={[
              {
                key: 'vendor', label: 'Vendor', rowHeader: true, value: (v) => v.display_name,
                render: (v) => (
                  <Stack gap="sm">
                    <VendorLink id={v.brand_id} name={v.display_name} color={v.color ?? colours.byId(v.brand_id)} onOpen={openVendor} />
                    {v.role === 'excluded' && <Text as="span" variant="hint">out of scope</Text>}
                  </Stack>
                ),
              },
              ...(showSub ? [{ key: 'sub', label: 'Sub-category', groupable: true, value: (v: Vendor) => v.baseline?.taxonomy?.sub_category ?? null, render: (v: Vendor) => v.baseline?.taxonomy?.sub_category ?? <Missing /> }] : []),
              { key: 'country', label: 'Country', groupable: true, value: (v) => v.baseline?.hq_country ?? null, render: (v) => v.baseline?.hq_country ?? <Missing /> },
              { key: 'founded', label: 'Founded', groupable: true, value: (v) => v.baseline?.founded_year ?? null, render: (v) => v.baseline?.founded_year ?? <Missing /> },
              { key: 'staff', label: 'LinkedIn headcount', align: 'end', value: (v) => v.baseline?.metrics?.employee_count ?? null, render: (v) => v.baseline?.metrics?.employee_count ?? <Missing /> },
              { key: 'funding', label: 'Funding', groupable: true, value: (v) => v.baseline?.funding_baseline?.total_musd ?? v.baseline?.funding_baseline?.status ?? null, render: fundingLabel },
              {
                key: 'links', label: 'Links on file', sortable: false,
                render: (v) => [v.identifiers?.some((i) => i.kind === 'website_url') && 'website', v.identifiers?.some((i) => i.kind === 'linkedin_company_url') && 'LinkedIn'].filter(Boolean).join(', ') || <Missing>none</Missing>,
              },
              { key: 'collecting', label: 'Collecting', value: (v) => (v.collection_enabled ? 1 : 0), render: (v) => switchCell(v, 'collection') },
              { key: 'brand', label: 'Brand', value: (v) => (v.brand_monitoring_enabled ? 1 : 0), render: (v) => switchCell(v, 'brand_monitoring') },
            ]}
          />
        </Stack>
      </Panel>
    </Stack>
  );
}
