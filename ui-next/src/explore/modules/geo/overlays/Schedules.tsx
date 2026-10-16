import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Chip, EmptyState, Icon, IconButton, Select, SettingRow, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import {
  createSchedule, deleteSchedule, getSchedules, runScheduleNow, updateSchedule,
  type AvailableTopic, type CreateScheduleRequest, type GeopoliticalSchedule,
} from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { fmtDateTime } from '../labels';

/*
 * Scheduled hotspot updates, as the old GeopoliticalScheduleModal: each schedule reads a batch of a
 * topic's articles with the AI on an interval or daily. Opening this only reads the list. "Run now"
 * runs one straight away (AI calls, so it asks first); delete asks first too.
 */

const BATCHES = [10, 25, 50, 100, 200, 500];
type Form = Required<Pick<CreateScheduleRequest, 'name' | 'batch_size' | 'model' | 'process_all' | 'schedule_enabled' | 'notify_on_complete' | 'notify_threshold'>> & {
  topic: string;
  schedule_type: 'interval' | 'daily';
  schedule_interval: number;
  schedule_unit: 'minutes' | 'hours' | 'days';
  schedule_time: string;
};
const blank = (model: string): Form => ({
  name: '', topic: '', batch_size: 50, model, process_all: false, schedule_enabled: true,
  schedule_type: 'interval', schedule_interval: 6, schedule_unit: 'hours', schedule_time: '09:00', notify_on_complete: true, notify_threshold: 1,
});
const fromSchedule = (s: GeopoliticalSchedule): Form => ({
  name: s.name, topic: s.topic || '', batch_size: s.batch_size, model: s.model, process_all: s.process_all, schedule_enabled: s.schedule_enabled,
  schedule_type: s.schedule_type || 'interval', schedule_interval: s.schedule_interval || 6, schedule_unit: s.schedule_unit || 'hours',
  schedule_time: s.schedule_time || '09:00', notify_on_complete: s.notify_on_complete, notify_threshold: s.notify_threshold,
});
const toRequest = (f: Form): CreateScheduleRequest => ({
  name: f.name.trim(), topic: f.topic || undefined, batch_size: f.batch_size, model: f.model, process_all: f.process_all,
  schedule_enabled: f.schedule_enabled, schedule_type: f.schedule_type,
  schedule_interval: f.schedule_type === 'interval' ? f.schedule_interval : undefined,
  schedule_unit: f.schedule_type === 'interval' ? f.schedule_unit : undefined,
  schedule_time: f.schedule_type === 'daily' ? f.schedule_time : undefined,
  notify_on_complete: f.notify_on_complete, notify_threshold: f.notify_threshold,
});
const cadence = (s: GeopoliticalSchedule) =>
  s.schedule_type === 'daily' ? `daily at ${s.schedule_time ?? '?'}` : `every ${s.schedule_interval ?? '?'} ${s.schedule_unit ?? 'hours'}`;

export function Schedules({ open, topics, model, notify, askConfirm, onRan }: {
  open: boolean;
  topics: AvailableTopic[];
  model: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onRan: () => void;
}) {
  const [list, setList] = useState<GeopoliticalSchedule[] | null>(null);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [form, setForm] = useState<Form>(() => blank(model));
  const [busy, setBusy] = useState<number | 'save' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getSchedules().then(setList, (e) => {
      setList([]);
      setError(errorText(e));
    });
  }, []);
  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const save = async () => {
    if (!form.name.trim()) {
      setError('Give the schedule a name.');
      return;
    }
    setBusy('save');
    setError(null);
    try {
      if (editing === 'new') await createSchedule(toRequest(form));
      else if (typeof editing === 'number') await updateSchedule(editing, toRequest(form));
      notify(editing === 'new' ? 'Schedule created' : 'Schedule saved');
      setEditing(null);
      load();
    } catch (e) {
      setError(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };
  const toggle = async (s: GeopoliticalSchedule, on: boolean) => {
    try {
      await updateSchedule(s.id, { schedule_enabled: on });
      load();
    } catch (e) {
      setError(`Not changed: ${errorText(e)}`);
    }
  };
  const runNow = (s: GeopoliticalSchedule) =>
    askConfirm({
      title: `Run “${s.name}” now?`,
      message: `It reads up to ${s.batch_size} articles${s.topic ? ` from ${s.topic}` : ''} with the AI (${s.model}), one call per article.`,
      action: 'Run now',
      onConfirm: async () => {
        setBusy(s.id);
        setError(null);
        try {
          const r = await runScheduleNow(s.id);
          notify(`“${s.name}” ran: ${r.articles_processed ?? 0} articles read, ${r.hotspots_created ?? 0} hotspots created, ${r.hotspots_updated ?? 0} updated`);
          load();
          onRan();
        } catch (e) {
          setError(`The run failed: ${errorText(e)}`);
        } finally {
          setBusy(null);
        }
      },
    });
  const remove = (s: GeopoliticalSchedule) =>
    askConfirm({
      title: `Delete “${s.name}”?`,
      message: 'The schedule stops; hotspots it already made are kept.',
      action: 'Delete schedule',
      onConfirm: async () => {
        try {
          await deleteSchedule(s.id);
          notify('Schedule deleted');
          load();
        } catch (e) {
          setError(`Not deleted: ${errorText(e)}`);
        }
      },
    });

  const formView = (
    <Stack gap="md">
      <TextField label="Name" value={form.name} onChange={(v) => set({ name: v })} placeholder="e.g. Hotspots every 6 hours" maxLength={120} />
      <Select
        label="Topic"
        options={[{ value: 'default', label: 'Geopolitical Hotspots (default)' }, ...topics.filter((t) => t.topic !== 'Geopolitical Hotspots').map((t) => ({ value: t.topic, label: t.topic }))]}
        value={form.topic || 'default'}
        onValueChange={(v) => set({ topic: v === 'default' ? '' : v })}
        fullWidth
      />
      <Select label="Articles per run" options={BATCHES.map((b) => ({ value: String(b), label: `${b} articles` }))} value={String(form.batch_size)} onValueChange={(v) => set({ batch_size: Number(v) })} />
      <Select
        label="When"
        options={[{ value: 'interval', label: 'At an interval' }, { value: 'daily', label: 'Daily at a set time' }]}
        value={form.schedule_type}
        onValueChange={(v) => set({ schedule_type: v as Form['schedule_type'] })}
      />
      {form.schedule_type === 'interval' ? (
        <Stack direction="row" gap="sm">
          <TextField label="Every" type="number" min={1} value={String(form.schedule_interval)} onChange={(v) => set({ schedule_interval: Math.max(1, Number(v) || 1) })} />
          <Select
            label="Unit"
            options={[{ value: 'minutes', label: 'Minutes' }, { value: 'hours', label: 'Hours' }, { value: 'days', label: 'Days' }]}
            value={form.schedule_unit}
            onValueChange={(v) => set({ schedule_unit: v as Form['schedule_unit'] })}
          />
        </Stack>
      ) : (
        <TextField label="Time (server time)" type="time" value={form.schedule_time} onChange={(v) => set({ schedule_time: v })} />
      )}
      <Checkbox label="Send a notification when a run finishes" checked={form.notify_on_complete} onCheckedChange={(c) => set({ notify_on_complete: c })} />
      <Checkbox label="Re-read articles already read" checked={form.process_all} onCheckedChange={(c) => set({ process_all: c })} />
      <Text variant="caption">{`Each run reads up to ${form.batch_size} articles with ${form.model}, one AI call per article, on its own.`}</Text>
      <Stack direction="row" gap="sm">
        <Button disabled={busy === 'save'} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : editing === 'new' ? 'Create schedule' : 'Save schedule'}</Button>
        <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
      </Stack>
    </Stack>
  );

  return (
    <Stack gap="md">
      {error && <Banner tone="error" title="Something went wrong" description={error} />}
      {editing !== null ? formView : !list ? <Skeleton variant="text" lines={4} /> : (
        <>
          {list.length === 0 ? (
            <EmptyState icon="Clock" title="No schedules yet">A schedule reads new articles for hotspots on its own.</EmptyState>
          ) : (
            <Stack as="ul" gap="sm" label="Schedules">
              {list.map((s) => (
                <li key={s.id}>
                  <SettingRow
                    title={s.name}
                    description={[
                      `${s.topic || 'Geopolitical Hotspots'} · ${s.batch_size} articles ${cadence(s)}`,
                      s.next_run_at ? `next ${fmtDateTime(s.next_run_at)}` : 'not scheduled',
                      `${s.run_count} runs`,
                      s.last_run_at ? `last ${fmtDateTime(s.last_run_at)}: ${s.last_run_articles_processed} read, ${s.last_run_hotspots_created} created, ${s.last_run_hotspots_updated} updated` : null,
                    ].filter(Boolean).join(' · ')}
                    actions={
                      <Stack direction="row" gap="sm">
                        {s.last_run_status && <Chip size="sm" tone={s.last_run_status === 'success' ? 'success' : s.last_run_status === 'error' ? 'error' : 'info'}>{s.last_run_status}</Chip>}
                        <Switch label={`Run “${s.name}” on schedule`} checked={s.schedule_enabled} onCheckedChange={(on) => void toggle(s, on)} />
                        <IconButton icon={<Icon name="Play" size="sm" />} label={`Run “${s.name}” now`} disabled={busy === s.id} onClick={() => runNow(s)} />
                        <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit “${s.name}”`} onClick={() => { setForm(fromSchedule(s)); setEditing(s.id); }} />
                        <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${s.name}”`} onClick={() => remove(s)} />
                      </Stack>
                    }
                  />
                  {s.last_run_status === 'error' && s.last_run_error && <Text tone="error">{s.last_run_error}</Text>}
                </li>
              ))}
            </Stack>
          )}
          <div>
            <Button variant="secondary" iconStart={<Icon name="Plus" size="sm" />} onClick={() => { setForm(blank(model)); setEditing('new'); setError(null); }}>New schedule</Button>
          </div>
        </>
      )}
    </Stack>
  );
}
