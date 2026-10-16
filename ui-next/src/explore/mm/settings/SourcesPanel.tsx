import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Panel, Skeleton, Stack, Switch, Table, TextField } from '@aunoo/ui';
import { getSources, saveSources, type SourceSetting } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { fmtDateTime } from '../views/collection/labels';

/**
 * Collection sources and how often each runs. Sources marked "per record" are billed by the
 * provider. Switching one on or off saves at once (turning a paid one on asks first); interval
 * changes are saved together with the button.
 */
export function SourcesPanel({ ctx }: { ctx: MmContext }) {
  const { marketId } = ctx;
  const [sources, setSources] = useState<SourceSetting[] | null>(null);
  const [minInterval, setMinInterval] = useState(6);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const load = () => getSources(marketId).then((s) => { setSources(s.sources); setMinInterval(s.min_interval_hours); setDrafts({}); }, (e) => setMsg({ tone: 'error', text: errorText(e) }));
  useEffect(() => void load(), [marketId]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (next: Record<string, { enabled: boolean; interval_hours: number | null }>, done: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await saveSources(marketId, next);
      setMsg({ tone: 'success', text: done });
      await load();
      ctx.reload();
    } catch (e) {
      setMsg({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(false);
    }
  };
  const current = (list: SourceSetting[]) => Object.fromEntries(list.map((x) => [x.source, { enabled: x.enabled, interval_hours: x.interval_hours }]));

  const toggle = (s: SourceSetting) => {
    if (!sources) return;
    const next = current(sources);
    next[s.source] = { ...next[s.source], enabled: !s.enabled };
    const name = s.source.replace(/_/g, ' ');
    const go = () => void save(next, `${name} switched ${s.enabled ? 'off' : 'on'}.`);
    if (!s.enabled && s.paid) {
      ctx.askConfirm({ title: `Switch on ${name}?`, message: `This source is billed per record by the provider. It runs every ${s.effective_interval_hours} hours from the next scheduled run.`, action: 'Switch on', onConfirm: go });
    } else go();
  };

  const changed = Object.entries(drafts).filter(([k, v]) => {
    const s = sources?.find((x) => x.source === k);
    return s && Number(v) && Number(v) !== s.effective_interval_hours;
  });
  const tooShort = changed.some(([, v]) => Number(v) < minInterval);
  const saveIntervals = () => {
    if (!sources) return;
    const next = current(sources);
    for (const [k, v] of changed) next[k] = { ...next[k], interval_hours: Number(v) };
    void save(next, `${changed.length} interval${changed.length === 1 ? '' : 's'} saved.`);
  };

  return (
    <Panel title="Sources and schedules" description={`Collection sources and how often each runs. Sources marked “per record” are billed by the provider. The shortest interval allowed is ${minInterval} hours.`}>
      <Stack gap="md">
        {msg && <Banner tone={msg.tone} title={msg.tone === 'error' ? 'Something went wrong' : 'Saved'} description={msg.text} />}
        {!sources ? <Skeleton variant="text" lines={8} /> : (
          <Table
            caption="Collection sources and schedules"
            hideCaption
            rows={sources}
            rowKey={(s) => s.source}
            columns={[
              { key: 'source', header: 'Source', rowHeader: true, render: (s) => s.source.replace(/_/g, ' ') },
              { key: 'paid', header: 'Cost', render: (s) => <Chip size="sm" tone={s.paid ? 'warning' : 'muted'}>{s.paid ? 'per record' : 'bandwidth only'}</Chip> },
              { key: 'enabled', header: 'On', render: (s) => <Switch label={`Run ${s.source.replace(/_/g, ' ')}`} checked={s.enabled} disabled={busy} onCheckedChange={() => toggle(s)} /> },
              {
                key: 'interval', header: 'Every (hours)',
                render: (s) => (
                  <TextField
                    label={`Hours between ${s.source.replace(/_/g, ' ')} runs`}
                    hideLabel
                    type="number"
                    min={minInterval}
                    value={drafts[s.source] ?? String(s.effective_interval_hours)}
                    onChange={(v) => setDrafts((d) => ({ ...d, [s.source]: v }))}
                    hint={s.interval_hours ? `default ${s.default_interval_hours}h` : undefined}
                  />
                ),
              },
              { key: 'last_success', header: 'Last success', render: (s) => fmtDateTime(s.last_success) },
            ]}
          />
        )}
        {tooShort && <Banner tone="warning" title="An interval is too short" description={`Intervals must be at least ${minInterval} hours.`} />}
        <div><Button disabled={busy || !changed.length || tooShort} onClick={saveIntervals}>{changed.length ? `Save ${changed.length} interval${changed.length === 1 ? '' : 's'}` : 'Save intervals'}</Button></div>
      </Stack>
    </Panel>
  );
}
