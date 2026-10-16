import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Chip, Dialog, DialogClose, Icon, IconButton, Select, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../../../shell';
import { createSchedule, deleteSchedule, getSchedules, runSchedule, updateSchedule, type Schedule, type ScheduleInput } from '../api';
import { fmtDateTime } from '../labels';

/*
 * Scheduled updates, as the old ThreatScheduleModal: each schedule has the AI read new articles on its
 * own at an interval or daily time. Running one now calls the AI and waits for it, so it asks first;
 * the old page ran straight away. Failed saves and deletes now say so; the old one only logged them.
 */

type Form = Omit<ScheduleInput, 'schedule_interval' | 'batch_size'> & { schedule_interval: string; batch_size: string };
const EMPTY: Form = { name: '', schedule_type: 'interval', schedule_interval: '1', schedule_unit: 'hours', schedule_time: '06:00', batch_size: '50', schedule_enabled: true };

function describe(s: Schedule) {
  if (s.schedule_type === 'daily') return `Daily at ${s.schedule_time || '00:00'} (server time)`;
  const n = s.schedule_interval || 1;
  const unit = s.schedule_unit || 'hours';
  return n === 1 ? `Every ${unit.replace(/s$/, '')}` : `Every ${n} ${unit}`;
}

export function ScheduleDialog({ open, onOpenChange, notify, askConfirm }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  model: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}) {
  const [list, setList] = useState<Schedule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getSchedules().then(setList, (e) => {
      setList([]);
      setError(errorText(e));
    });
  }, []);
  useEffect(() => {
    if (!open) return;
    setForm(null);
    setEditing(null);
    load();
  }, [open, load]);

  const set = (patch: Partial<Form>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const save = async () => {
    if (!form || !form.name.trim()) return;
    setBusy('save');
    const body: ScheduleInput = {
      ...form,
      name: form.name.trim(),
      schedule_interval: Math.max(1, Number(form.schedule_interval) || 1),
      batch_size: Math.max(1, Math.min(500, Number(form.batch_size) || 50)),
    };
    try {
      if (editing) await updateSchedule(editing, body);
      else await createSchedule(body);
      notify(editing ? 'Schedule saved' : 'Schedule created');
      setForm(null);
      setEditing(null);
      load();
    } catch (e) {
      setError(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };
  const toggle = async (s: Schedule) => {
    setBusy(`t${s.id}`);
    try {
      await updateSchedule(s.id, { schedule_enabled: !s.schedule_enabled });
      load();
    } catch (e) {
      setError(`Not changed: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };
  const run = (s: Schedule) =>
    askConfirm({
      title: `Run “${s.name}” now?`,
      message: `The AI reads up to ${s.batch_size} new articles, one call each, and files the threats it finds. The dialog waits until it finishes.`,
      action: 'Run now',
      onConfirm: async () => {
        setBusy(`r${s.id}`);
        try {
          const r = await runSchedule(s.id);
          notify(r.message || `Read ${r.articles_processed} articles`);
          load();
        } catch (e) {
          setError(`The run failed: ${errorText(e)}`);
        } finally {
          setBusy(null);
        }
      },
    });
  const remove = (s: Schedule) =>
    askConfirm({
      title: `Delete “${s.name}”?`,
      message: 'The schedule stops and is removed. Threats it already filed are kept.',
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

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Scheduled updates"
      description="Have the AI read new articles for threats on its own, at a set interval or once a day. Each article read is one AI call."
      footer={
        form ? (
          <>
            <Button variant="secondary" size="lg" onClick={() => { setForm(null); setEditing(null); }}>Cancel</Button>
            <Button size="lg" disabled={!form.name.trim() || busy === 'save'} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : editing ? 'Save schedule' : 'Create schedule'}</Button>
          </>
        ) : (
          <>
            <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
            <Button size="lg" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setForm(EMPTY)}>New schedule</Button>
          </>
        )
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        {form ? (
          <Stack gap="md">
            <TextField label="Name" value={form.name} onChange={(name) => set({ name })} placeholder="e.g. Hourly threat check" />
            <Select label="When" options={[{ value: 'interval', label: 'At an interval' }, { value: 'daily', label: 'Once a day' }]} value={form.schedule_type} onValueChange={(v) => set({ schedule_type: v as Form['schedule_type'] })} fullWidth />
            {form.schedule_type === 'interval' ? (
              <Stack direction="row" gap="sm">
                <TextField label="Every" type="number" min={1} value={form.schedule_interval} onChange={(schedule_interval) => set({ schedule_interval })} />
                <Select label="Unit" options={[{ value: 'minutes', label: 'Minutes' }, { value: 'hours', label: 'Hours' }, { value: 'days', label: 'Days' }, { value: 'weeks', label: 'Weeks' }]} value={form.schedule_unit} onValueChange={(v) => set({ schedule_unit: v as Form['schedule_unit'] })} />
              </Stack>
            ) : (
              <TextField label="Time" type="time" value={form.schedule_time} onChange={(schedule_time) => set({ schedule_time })} hint="Server time." />
            )}
            <TextField label="Most articles per run" type="number" min={1} max={500} value={form.batch_size} onChange={(batch_size) => set({ batch_size })} hint="Between 1 and 500. Each is one AI call, every run." />
            <Switch label="On" description="A schedule that’s off keeps its settings but doesn’t run." checked={form.schedule_enabled} onCheckedChange={(schedule_enabled) => set({ schedule_enabled })} />
            {!editing && <Text variant="caption">New schedules use the server’s default model.</Text>}
          </Stack>
        ) : !list ? <Skeleton variant="text" lines={4} /> : !list.length ? (
          <Text>No schedules yet. Updates only run when someone presses “Update”.</Text>
        ) : (
          <ul className="threat-plainlist">
            {list.map((s) => (
              <li key={s.id}>
                <Stack direction="row" justify="between" gap="sm">
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm">
                      <Text as="span" variant="label">{s.name}</Text>
                      <Chip tone={s.schedule_enabled ? 'success' : 'muted'} size="sm">{s.schedule_enabled ? 'On' : 'Off'}</Chip>
                      {s.last_run_status === 'error' && <Chip tone="error" size="sm">Last run failed</Chip>}
                    </Stack>
                    <Text variant="caption">
                      {[describe(s), `up to ${s.batch_size} articles`, `last run ${fmtDateTime(s.last_run_at)}`, s.schedule_enabled && s.next_run_at ? `next ${fmtDateTime(s.next_run_at)}` : null, `${s.run_count} run${s.run_count === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}
                    </Text>
                    {s.last_run_status === 'error' && s.last_run_error && <Text variant="caption" tone="error">{s.last_run_error}</Text>}
                  </Stack>
                  <Stack direction="row" gap="sm" wrap={false}>
                    <IconButton icon={<Icon name={s.schedule_enabled ? 'Pause' : 'Play'} size="sm" />} label={s.schedule_enabled ? `Switch off “${s.name}”` : `Switch on “${s.name}”`} disabled={busy !== null} onClick={() => void toggle(s)} />
                    <IconButton icon={<Icon name="Lightning" size="sm" />} label={`Run “${s.name}” now`} disabled={busy !== null} onClick={() => run(s)} />
                    <IconButton
                      icon={<Icon name="PencilSimple" size="sm" />}
                      label={`Edit “${s.name}”`}
                      disabled={busy !== null}
                      onClick={() => {
                        setEditing(s.id);
                        setForm({
                          name: s.name, schedule_type: s.schedule_type ?? 'interval', schedule_interval: String(s.schedule_interval ?? 1), schedule_unit: s.schedule_unit ?? 'hours',
                          schedule_time: s.schedule_time ?? '06:00', batch_size: String(s.batch_size), schedule_enabled: s.schedule_enabled,
                        });
                      }}
                    />
                    <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${s.name}”`} disabled={busy !== null} onClick={() => remove(s)} />
                  </Stack>
                </Stack>
              </li>
            ))}
          </ul>
        )}
        {busy?.startsWith('r') && <Text variant="caption">Running… this can take a few minutes.</Text>}
      </Stack>
    </Dialog>
  );
}
