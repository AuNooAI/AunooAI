import { useEffect, useState } from 'react';
import { Banner, Button, Panel, Select, Stack, Text, TextField } from '@aunoo/ui';
import { getHorizonControls, getVendors, saveHorizonControls, type HorizonAcquired, type HorizonControls, type MarketHorizon, type Vendor } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import { LinkButton, VendorLink } from '../../shared/SortTable';
import type { MmContext } from '../../context';

/*
 * Acquired, closed, pivoted and large incumbent vendors: listed under the map, never placed on it.
 * An incumbent (CrowdStrike, Microsoft) is still in the market; it's listed because its size can't
 * be compared with the rest. The form writes the same per-vendor status as the vendor page's
 * controls, then recomputes the map, so a sale recorded here shows straight away.
 */

type Status = HorizonControls['status'];
type Marked = Exclude<Status, 'active'>;

const STATUS_OPTIONS: { value: Marked; label: string }[] = [
  { value: 'acquired', label: 'Acquired' },
  { value: 'closed', label: 'Closed (no longer trading)' },
  { value: 'pivoted', label: 'Pivoted (left this market; say where in the note)' },
  { value: 'incumbent', label: 'Large incumbent (in the market, too big to place)' },
];

export function describeStatus(a: HorizonAcquired) {
  const what = a.status === 'incumbent' ? 'large incumbent, not placed'
    : a.status === 'closed' ? 'closed'
      : a.status === 'pivoted' ? 'pivoted'
        : a.acquired_by ? `acquired by ${a.acquired_by}` : 'acquired';
  return `${what}${a.status_date ? `, ${a.status_date}` : ''}${a.note ? ` · ${a.note}` : ''}`;
}

export function StatusPanel({ ctx, horizon, onRecompute }: { ctx: MmContext; horizon: MarketHorizon; onRecompute: () => Promise<void> }) {
  const [vendors, setVendors] = useState<Vendor[] | null>(ctx.vendors);
  const [open, setOpen] = useState(false);
  const [brandId, setBrandId] = useState('');
  const [status, setStatus] = useState<Marked>('acquired');
  const [by, setBy] = useState('');
  const [date, setDate] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState<number | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || vendors) return;
    getVendors(ctx.marketId).then(setVendors, (e) => setError(errorText(e)));
  }, [open, vendors, ctx.marketId]);

  const listed = new Set(horizon.acquired.map((a) => a.brand_id));
  const choices = (vendors ?? []).filter((v) => !listed.has(v.brand_id)).sort((a, b) => a.display_name.localeCompare(b.display_name));

  // Keeps the analyst's multipliers and note when only the status changes
  const setStatusFor = async (bid: number, next: { status: Status; acquired_by?: string | null; status_date?: string | null; note?: string | null }) => {
    const cur = (await getHorizonControls(ctx.marketId, bid)).controls;
    await saveHorizonControls(ctx.marketId, bid, {
      ...cur,
      status: next.status,
      acquired_by: next.status === 'active' ? null : next.acquired_by ?? cur.acquired_by,
      status_date: next.status === 'active' ? null : next.status_date ?? cur.status_date,
      note: next.note === undefined ? cur.note : next.note,
    });
  };

  const add = async () => {
    if (!brandId) return;
    setBusy('new');
    setError(null);
    try {
      await setStatusFor(Number(brandId), { status, acquired_by: status === 'acquired' ? by.trim() || null : null, status_date: date || null, note: note.trim() || null });
      await onRecompute();
      setBrandId(''); setBy(''); setDate(''); setNote(''); setOpen(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const reactivate = (a: HorizonAcquired) =>
    ctx.askConfirm({
      title: `Put ${a.vendor} back on the map?`,
      message: `This marks ${a.vendor} as active again and recomputes the map, so it's rated with the other vendors.`,
      action: 'Mark active and recompute',
      onConfirm: () => void (async () => {
        setBusy(a.brand_id);
        setError(null);
        try {
          await setStatusFor(a.brand_id, { status: 'active' });
          await onRecompute();
        } catch (e) {
          setError(errorText(e));
        } finally {
          setBusy(null);
        }
      })(),
    });

  return (
    <Panel
      title={`Acquired, closed, pivoted and large incumbents (${horizon.acquired.length})`}
      description="Listed here, never placed on the map."
      headingLevel={3}
      headerAside={<Button variant="secondary" size="sm" onClick={() => setOpen((o) => !o)}>{open ? 'Cancel' : 'Mark a vendor'}</Button>}
    >
      <Stack gap="md">
        {horizon.acquired.length === 0 && !open && <Text variant="caption">None recorded.</Text>}
        {horizon.acquired.length > 0 && (
          <ul className="hz-list">
            {horizon.acquired.map((a) => (
              <li key={a.brand_id}>
                <VendorLink id={a.brand_id} name={a.vendor} color={ctx.colours.byId(a.brand_id)} onOpen={ctx.openVendor} />
                <Text as="span" variant="caption">{describeStatus(a)}</Text>
                {busy === a.brand_id ? <Text as="span" variant="caption">Saving…</Text> : (
                  <LinkButton onClick={() => reactivate(a)} label={`Mark ${a.vendor} active again`}>mark active</LinkButton>
                )}
              </li>
            ))}
          </ul>
        )}
        {open && (
          <Stack gap="sm">
            <Select
              label="Vendor"
              placeholder={vendors ? 'Choose a vendor' : 'Loading…'}
              options={choices.map((v) => ({ value: String(v.brand_id), label: `${v.display_name}${v.role !== 'vendor' ? ` (${v.role})` : ''}` }))}
              value={brandId}
              onValueChange={setBrandId}
              fullWidth
            />
            <Select label="Status" options={STATUS_OPTIONS} value={status} onValueChange={(v) => setStatus(v as Marked)} fullWidth />
            {status === 'acquired' && <TextField label="Acquired by" value={by} onChange={setBy} placeholder="The buyer" maxLength={200} />}
            <TextField label="Date" type="date" value={date} onChange={setDate} />
            <TextField label="Note" value={note} onChange={setNote} placeholder="What was bought, or how the closure is known" maxLength={4000} />
            <div>
              <Button disabled={!brandId || busy !== null} busy={busy === 'new'} onClick={() => void add()}>Save and recompute the map</Button>
            </div>
          </Stack>
        )}
        {error && <Banner tone="error" title="Not saved" description={error} />}
      </Stack>
    </Panel>
  );
}
