import { useEffect, useState } from 'react';
import { Banner, Button, Grid, Panel, Select, Skeleton, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import { getHorizonControls, saveHorizonControls, type HorizonControls } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';

/*
 * The analyst's controls for one vendor on the Market Maturity Map, as the old
 * MarketVendorHorizonControls.tsx, for the vendor page. A multiplier per input (0 to 2, default 1)
 * scales this vendor's weight on that input, to discount noisy posts or stress a real signal; plus a
 * status with buyer and date, and a note. Saved per vendor per market, applied on the next compute,
 * and printed beside the vendor on the map, so an adjustment is never silent.
 */

const STATUS_LABEL: Record<string, string> = {
  active: 'Active',
  acquired: 'Acquired',
  closed: 'Closed',
  pivoted: 'Pivoted (left this market)',
  incumbent: 'Large incumbent (not placed)',
};

export function VendorHorizonControls({ marketId, brandId, notify }: { marketId: number; brandId: number; notify?: (m: string) => void }) {
  const [inputs, setInputs] = useState<Record<string, { label: string; axis: string; weight: number }>>({});
  const [statuses, setStatuses] = useState<string[]>([]);
  const [form, setForm] = useState<HorizonControls | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setForm(null); setMsg(null); setError(null);
    getHorizonControls(marketId, brandId).then(
      (d) => { if (live) { setInputs(d.inputs); setStatuses(d.statuses); setForm(d.controls); } },
      (e) => live && setError(errorText(e)),
    );
    return () => { live = false; };
  }, [marketId, brandId]);

  const save = async () => {
    if (!form) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const saved = await saveHorizonControls(marketId, brandId, {
        ...form,
        acquired_by: form.status === 'active' ? null : form.acquired_by,
        status_date: form.status === 'active' ? null : form.status_date || null,
      });
      setForm(saved);
      const m = 'Saved. It applies the next time the Market Maturity Map is computed.';
      setMsg(m);
      notify?.(m);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const ordered = Object.entries(inputs).sort(([, a], [, b]) => (a.axis === b.axis ? b.weight - a.weight : a.axis === 'scale' ? -1 : 1));
  // The server's list of statuses (the old form offered only three of the five, so a pivoted or
  // incumbent vendor showed as "active" in the picker)
  const statusOptions = (statuses.length ? statuses : ['active', 'acquired', 'closed', 'pivoted', 'incumbent']).map((s) => ({ value: s, label: STATUS_LABEL[s] ?? s }));

  return (
    <Panel
      title="Market Maturity Map controls"
      description="Weights for this vendor's inputs (1 is the market weight, 0 ignores the input, 2 doubles it), its status, and an analyst note. They apply on the next compute and show beside the vendor on the map."
      headingLevel={3}
    >
      {error && <Banner tone="error" title="Something went wrong" description={error} />}
      {!form ? (!error && <Skeleton variant="text" lines={5} />) : (
        <Stack gap="md">
          <Select label="Status" options={statusOptions} value={form.status} onValueChange={(v) => setForm({ ...form, status: v as HorizonControls['status'] })} />
          {form.status !== 'active' && (
            <>
              <TextField
                label={form.status === 'acquired' ? 'Acquired by' : 'Detail'}
                value={form.acquired_by ?? ''}
                maxLength={200}
                placeholder={form.status === 'acquired' ? 'e.g. Cribl (AI technology assets)' : ''}
                onChange={(v) => setForm({ ...form, acquired_by: v })}
              />
              <TextField label="Date" type="date" value={form.status_date ?? ''} onChange={(v) => setForm({ ...form, status_date: v || null })} />
            </>
          )}
          <Stack gap="sm">
            <Text variant="label">Input weights for this vendor</Text>
            <Grid columns={2}>
              {ordered.map(([key, i]) => {
                const m = form.multipliers[key] ?? 1;
                return (
                  <TextField
                    key={key}
                    label={i.label}
                    hint={`${i.axis} axis, market weight ${i.weight.toFixed(2)}${m !== 1 ? ' · adjusted' : ''}`}
                    type="number"
                    min={0}
                    max={2}
                    step={0.25}
                    value={String(m)}
                    onChange={(raw) => {
                      const n = Number(raw);
                      if (raw === '' || Number.isNaN(n)) return;
                      const v = Math.max(0, Math.min(2, n));
                      const next = { ...form.multipliers };
                      if (v === 1) delete next[key];
                      else next[key] = v;
                      setForm({ ...form, multipliers: next });
                    }}
                  />
                );
              })}
            </Grid>
          </Stack>
          <TextArea
            label="Analyst note"
            rows={3}
            value={form.note ?? ''}
            onChange={(v) => setForm({ ...form, note: v })}
            placeholder="Why this vendor is weighted or marked as it is. Shown in the full report, not the shared one."
          />
          <Stack direction="row" gap="sm">
            <Button busy={saving} disabled={saving} onClick={() => void save()}>Save</Button>
            {msg && <Text as="span" variant="caption">{msg}</Text>}
            {form.updated_at && (
              <Text as="span" variant="caption">Last saved {form.updated_at.slice(0, 16).replace('T', ' ')}{form.updated_by ? ` by ${form.updated_by}` : ''}</Text>
            )}
          </Stack>
        </Stack>
      )}
    </Panel>
  );
}
