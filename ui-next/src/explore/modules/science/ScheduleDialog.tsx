import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Dialog, DialogClose, EmptyState, Icon, IconButton, Select, SettingRow, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import {
  createSchedule, deleteSchedule, getSchedules, runScheduleNow, updateSchedule,
  type ScienceSchedule, type ScienceScheduleCreate,
} from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { fmtDateTime } from './labels';

/*
 * Scheduled classification, as the old ScienceScheduleModal: runs that sort new articles into the
 * funding categories on their own, every so often or daily at a set time. Each run can call the AI
 * once per article the local classifier can't place. "Run now" and Delete ask first, inside this
 * dialog. The old dialog used the browser's own confirm box for Delete and ran "Run now" at once.
 */

interface Form {
  name: string;
  run_type: 'incremental' | 'full';
  days_back: number;
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily';
  schedule_interval: number;
  schedule_unit: 'minutes' | 'hours' | 'days';
  schedule_time: string;
  notify_on_complete: boolean;
  notify_threshold: number;
}
const BLANK: Form = {
  name: '', run_type: 'incremental', days_back: 30, schedule_enabled: true, schedule_type: 'interval',
  schedule_interval: 6, schedule_unit: 'hours', schedule_time: '09:00', notify_on_complete: true, notify_threshold: 10,
};
const DAYS = [
  { value: '7', label: '7 days' }, { value: '14', label: '14 days' }, { value: '30', label: '30 days' },
  { value: '90', label: '90 days' }, { value: '365', label: '1 year' }, { value: '0', label: 'All time' },
];
const UNITS = [{ value: 'minutes', label: 'minutes' }, { value: 'hours', label: 'hours' }, { value: 'days', label: 'days' }];

const fromSchedule = (s: ScienceSchedule): Form => ({
  name: s.name,
  run_type: s.run_type === 'full' ? 'full' : 'incremental',
  days_back: s.days_back,
  schedule_enabled: s.schedule_enabled,
  schedule_type: s.schedule_type === 'daily' ? 'daily' : 'interval',
  schedule_interval: s.schedule_interval || 6,
  schedule_unit: (s.schedule_unit as Form['schedule_unit']) || 'hours',
  schedule_time: s.schedule_time || '09:00',
  notify_on_complete: s.notify_on_complete,
  notify_threshold: s.notify_threshold,
});
const toBody = (f: Form): ScienceScheduleCreate => ({
  name: f.name.trim(),
  run_type: f.run_type,
  days_back: f.days_back,
  schedule_enabled: f.schedule_enabled,
  schedule_type: f.schedule_type,
  schedule_interval: f.schedule_type === 'interval' ? f.schedule_interval : undefined,
  schedule_unit: f.schedule_type === 'interval' ? f.schedule_unit : undefined,
  schedule_time: f.schedule_type === 'daily' ? f.schedule_time : undefined,
  notify_on_complete: f.notify_on_complete,
  notify_threshold: f.notify_threshold,
});
const when = (s: ScienceSchedule) => (s.schedule_type === 'daily' ? `daily at ${s.schedule_time}` : `every ${s.schedule_interval} ${s.schedule_unit}`);

function FormFields({ form, set }: { form: Form; set: (f: Form) => void }) {
  return (
    <Stack gap="md">
      <TextField label="Name" placeholder="e.g. Daily science classification" value={form.name} maxLength={120} onChange={(name) => set({ ...form, name })} />
      <Stack direction="row" gap="sm">
        <Select label="What it classifies" options={[{ value: 'incremental', label: 'Only new articles' }, { value: 'full', label: 'Everything again' }]} value={form.run_type} onValueChange={(v) => set({ ...form, run_type: v as Form['run_type'] })} />
        <Select label="Looking back" options={DAYS} value={String(form.days_back)} onValueChange={(v) => set({ ...form, days_back: Number(v) })} />
        <Select label="When" options={[{ value: 'interval', label: 'Every so often' }, { value: 'daily', label: 'Daily at a set time' }]} value={form.schedule_type} onValueChange={(v) => set({ ...form, schedule_type: v as Form['schedule_type'] })} />
      </Stack>
      {form.schedule_type === 'interval' ? (
        <Stack direction="row" gap="sm">
          <TextField label="Every" type="number" min={1} value={String(form.schedule_interval)} onChange={(v) => set({ ...form, schedule_interval: Math.max(1, Number(v) || 1) })} />
          <Select label="Unit" options={UNITS} value={form.schedule_unit} onValueChange={(v) => set({ ...form, schedule_unit: v as Form['schedule_unit'] })} />
        </Stack>
      ) : (
        <TextField label="Time" type="time" hint="Server time." value={form.schedule_time} onChange={(schedule_time) => set({ ...form, schedule_time })} />
      )}
      <Switch label="Notify when a run finishes" checked={form.notify_on_complete} onCheckedChange={(notify_on_complete) => set({ ...form, notify_on_complete })} />
      {form.notify_on_complete && (
        <TextField label="Only when at least this many articles were categorised" type="number" min={1} value={String(form.notify_threshold)} onChange={(v) => set({ ...form, notify_threshold: Math.max(1, Number(v) || 1) })} />
      )}
    </Stack>
  );
}

export function ScheduleDialog({ open, onOpenChange, onRan }: { open: boolean; onOpenChange: (o: boolean) => void; onRan: () => void }) {
  const [list, setList] = useState<ScienceSchedule[] | null>(null);
  const [editing, setEditing] = useState<null | 'new' | number>(null);
  const [form, setForm] = useState<Form>(BLANK);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<null | { kind: 'delete' | 'run'; s: ScienceSchedule }>(null);
  const [note, setNote] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const load = () => getSchedules().then(setList, (e) => { setList([]); setNote({ tone: 'error', text: `Schedules didn’t load: ${errorText(e)}` }); });
  useEffect(() => {
    if (!open) {
      setEditing(null);
      setPending(null);
      setNote(null);
      return;
    }
    setList(null);
    void load();
  }, [open]);

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      setNote({ tone: 'success', text: done });
      await load();
      return true;
    } catch (e) {
      setNote({ tone: 'error', text: errorText(e) });
      return false;
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!form.name.trim()) {
      setNote({ tone: 'error', text: 'Give the schedule a name.' });
      return;
    }
    const id = editing;
    const ok = await act(() => (id === 'new' ? createSchedule(toBody(form)) : updateSchedule(id as number, toBody(form))), id === 'new' ? 'Schedule created.' : 'Schedule saved.');
    if (ok) setEditing(null);
  };
  const confirmPending = async () => {
    const p = pending!;
    setPending(null);
    if (p.kind === 'delete') await act(() => deleteSchedule(p.s.id), `Deleted “${p.s.name}”.`);
    else {
      setBusy(true);
      setNote(null);
      try {
        const r = await runScheduleNow(p.s.id);
        setNote({ tone: 'success', text: `“${p.s.name}” ran: ${r.articles_processed} articles read, ${r.articles_categorized} categorised.` });
        onRan();
        await load();
      } catch (e) {
        setNote({ tone: 'error', text: `The run failed: ${errorText(e)}` });
      } finally {
        setBusy(false);
      }
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Scheduled classification"
      description="Sort new ScienceWatch articles into the funding categories on their own. Each run can make one AI call per article the local classifier can't place."
      footer={<DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>}
    >
      <Stack gap="lg">
        {note && <Banner tone={note.tone} title={note.tone === 'error' ? 'Something went wrong' : 'Done'} description={note.text} />}
        {pending && (
          <Banner
            tone="warning"
            title={pending.kind === 'delete' ? `Delete “${pending.s.name}”?` : `Run “${pending.s.name}” now?`}
            description={pending.kind === 'delete'
              ? 'It stops running. Articles it already categorised keep their categories.'
              : `Classifies ${pending.s.run_type === 'full' ? 'every article again' : 'new articles'} from ${pending.s.days_back === 0 ? 'all time' : `the last ${pending.s.days_back} days`} now, and waits for it to finish. Articles the local classifier can't place go to the AI, one call each.`}
            action={
              <Stack direction="row" gap="sm">
                <Button variant="secondary" size="sm" onClick={() => setPending(null)}>Cancel</Button>
                <Button size="sm" onClick={() => void confirmPending()}>{pending.kind === 'delete' ? 'Delete' : 'Run it'}</Button>
              </Stack>
            }
          />
        )}
        {busy && pending === null && <Banner tone="info" title="Working" description="A run can take a few minutes." />}

        {list === null ? <Skeleton variant="text" lines={5} /> : list.length === 0 && editing !== 'new' ? (
          <EmptyState icon="Clock" title="No schedules yet">Create one to classify new articles automatically.</EmptyState>
        ) : (
          <Stack as="ul" gap="md" label="Schedules">
            {list.map((s) => (
              <li key={s.id}>
                {editing === s.id ? (
                  <Stack gap="md">
                    <FormFields form={form} set={setForm} />
                    <Stack direction="row" gap="sm">
                      <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                      <Button disabled={busy} onClick={() => void save()}>Save</Button>
                    </Stack>
                  </Stack>
                ) : (
                  <SettingRow
                    title={<span>{s.name} <Chip size="sm" tone={s.schedule_enabled ? 'success' : 'muted'}>{s.schedule_enabled ? 'On' : 'Off'}</Chip></span>}
                    description={[
                      `${s.run_type === 'full' ? 'Everything again' : 'New articles only'}, ${s.days_back === 0 ? 'all time' : `last ${s.days_back} days`}, ${when(s)}.`,
                      `Next run: ${s.next_run_at ? fmtDateTime(s.next_run_at) : 'not scheduled'}. Runs so far: ${s.run_count}.`,
                      s.last_run_at
                        ? `Last run ${fmtDateTime(s.last_run_at)}: ${s.last_run_status ?? 'unknown'}, ${s.last_run_articles_processed} read, ${s.last_run_articles_categorized} categorised.`
                        : 'Never run.',
                      s.notify_on_complete ? `Notifies when ${s.notify_threshold} or more are categorised.` : 'No notification.',
                    ].join(' ')}
                    actions={
                      <Stack direction="row" gap="sm" wrap={false}>
                        <Switch label="On schedule" checked={s.schedule_enabled} disabled={busy} onCheckedChange={(on) => void act(() => updateSchedule(s.id, { schedule_enabled: on }), on ? `“${s.name}” is on.` : `“${s.name}” is off.`)} />
                        <IconButton icon={<Icon name="Play" size="sm" />} label={`Run “${s.name}” now`} disabled={busy} onClick={() => setPending({ kind: 'run', s })} />
                        <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit “${s.name}”`} disabled={busy} onClick={() => { setForm(fromSchedule(s)); setEditing(s.id); }} />
                        <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${s.name}”`} disabled={busy} onClick={() => setPending({ kind: 'delete', s })} />
                      </Stack>
                    }
                  />
                )}
              </li>
            ))}
          </Stack>
        )}

        {editing === 'new' ? (
          <Stack gap="md">
            <Text variant="label">New schedule</Text>
            <FormFields form={form} set={setForm} />
            <Stack direction="row" gap="sm">
              <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
              <Button disabled={busy} onClick={() => void save()}>Create the schedule</Button>
            </Stack>
          </Stack>
        ) : list !== null && (
          <div><Button variant="secondary" iconStart={<Icon name="Plus" size="sm" />} onClick={() => { setForm(BLANK); setEditing('new'); }}>New schedule</Button></div>
        )}
      </Stack>
    </Dialog>
  );
}
