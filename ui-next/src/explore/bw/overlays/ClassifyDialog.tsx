import { useEffect, useRef, useState } from 'react';
import {
  ActivityRow, Banner, Button, Checkbox, Dialog, DialogClose, Eyebrow, Grid, Icon, IconButton, PanelDivider, Select, Stack, Switch, Text, TextField,
} from '@aunoo/ui';
import {
  classifyArticles, createSchedule, deleteSchedule, getClassifyStatus, getSchedules, runScheduleNow, updateSchedule, type BWSchedule,
} from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';

/*
 * Classify articles into brand categories with the AI, now or on a schedule, as the old Classify
 * modal did (/api/brand-watcher/classify, /schedules). Every run here calls a model.
 */

const RUNS: { type: string; days: number; label: string }[] = [
  { type: 'incremental_since_last', days: 0, label: 'New since the last run' },
  { type: 'incremental', days: 30, label: 'Unclassified, last 30 days' },
  { type: 'incremental', days: 90, label: 'Unclassified, last 90 days' },
  { type: 'full', days: 365, label: 'Everything, last year (reclassify)' },
];
const EMPTY_FORM = { name: '', run_type: 'incremental', days_back: '30', schedule_type: 'interval', schedule_interval: '24', schedule_time: '02:00' };

function TopicPicker({ topics, picked, onChange, label }: { topics: { topic: string; article_count: number }[]; picked: string[]; onChange: (t: string[]) => void; label: string }) {
  return (
    <Stack gap="sm">
      <Stack direction="row" justify="between" gap="sm">
        <Text variant="label" as="span">{label} ({picked.length ? `${picked.length} picked` : 'all'})</Text>
        {picked.length > 0 && <Button variant="ghost" size="sm" onClick={() => onChange([])}>Clear</Button>}
      </Stack>
      {topics.length === 0 ? <Text variant="caption">No topics yet.</Text> : (
        <div>
          {topics.map((t) => (
            <Checkbox
              key={t.topic}
              label={`${t.topic} (${t.article_count})`}
              checked={picked.includes(t.topic)}
              onCheckedChange={(on) => onChange(on ? [...picked, t.topic] : picked.filter((x) => x !== t.topic))}
            />
          ))}
        </div>
      )}
    </Stack>
  );
}

export function ClassifyDialog({ open, onOpenChange, ctx }: { open: boolean; onOpenChange: (o: boolean) => void; ctx: BwContext }) {
  const { bw, notify, askConfirm } = ctx;
  const brand = ctx.selectedBrands.length === 1 ? ctx.selectedBrands[0] : null;
  const [status, setStatus] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [schedules, setSchedules] = useState<BWSchedule[] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formTopics, setFormTopics] = useState<string[]>([]);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadSchedules = () => getSchedules().then((r) => setSchedules(r.schedules), () => setSchedules([]));
  useEffect(() => {
    if (open) void loadSchedules();
  }, [open]);
  useEffect(() => () => { if (poll.current) clearInterval(poll.current); }, []);

  const watch = (runId: number) => {
    setRunning(true);
    setStatus('Running…');
    if (poll.current) clearInterval(poll.current);
    poll.current = setInterval(async () => {
      try {
        const s = await getClassifyStatus(runId);
        setStatus(`${s.status === 'running' ? 'Running' : s.status === 'completed' ? 'Finished' : s.status}: ${s.articles_processed} articles read, ${s.articles_categorized} classified`);
        if (s.status !== 'running') {
          clearInterval(poll.current!);
          setRunning(false);
          void bw.refresh();
        }
      } catch {
        clearInterval(poll.current!);
        setRunning(false);
      }
    }, 3000);
  };

  const run = async (type: string, days: number) => {
    try {
      const r = await classifyArticles({ brand_id: brand?.id, topics: bw.config.selectedTopics.length ? bw.config.selectedTopics : undefined, run_type: type, days_back: days });
      watch(r.run_id);
    } catch (e) {
      setStatus(`Didn’t start: ${errorText(e)}`);
    }
  };

  const create = async () => {
    try {
      await createSchedule({
        name: form.name || `${brand?.display_name ?? 'All brands'}, ${form.schedule_type === 'daily' ? 'daily' : `every ${form.schedule_interval}h`}`,
        brand_id: brand?.id, topics: formTopics.length ? formTopics : undefined, run_type: form.run_type, days_back: Number(form.days_back),
        schedule_type: form.schedule_type, schedule_interval: Number(form.schedule_interval) || 24, schedule_unit: 'hours',
        schedule_time: form.schedule_type === 'daily' ? form.schedule_time : undefined,
      });
      setFormOpen(false);
      setForm(EMPTY_FORM);
      setFormTopics([]);
      notify('Schedule created');
      void loadSchedules();
    } catch (e) {
      notify(`Not created: ${errorText(e)}`);
    }
  };

  const runNow = async (s: BWSchedule) => {
    try {
      const r = await runScheduleNow(s.id);
      watch(r.run_id);
      void loadSchedules();
    } catch (e) {
      notify(`Didn’t start: ${errorText(e)}`);
    }
  };

  const del = (s: BWSchedule) =>
    askConfirm({
      title: `Delete “${s.name}”?`,
      message: 'The schedule stops. Classifications already made stay.',
      action: 'Delete schedule',
      onConfirm: () => void deleteSchedule(s.id).then(() => setSchedules((x) => x?.filter((y) => y.id !== s.id) ?? null), (e: unknown) => notify(`Not deleted: ${errorText(e)}`)),
    });

  const toggle = (s: BWSchedule, on: boolean) =>
    void updateSchedule(s.id, { schedule_enabled: on }).then(() => loadSchedules(), (e: unknown) => notify(`Not changed: ${errorText(e)}`));

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Classify articles"
      description={`The AI sorts articles that match brand keywords into brand categories. For: ${brand?.display_name ?? 'all brands'}.`}
      footer={<DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>}
    >
      <Stack gap="lg">
        <TopicPicker topics={bw.topics} picked={bw.config.selectedTopics} onChange={(selectedTopics) => bw.updateConfig({ selectedTopics })} label="Topics" />
        <Text variant="caption">The topics you pick here also filter the Brand Watcher views.</Text>

        <Stack gap="sm">
          <Eyebrow as="h3">Run now</Eyebrow>
          <Grid columns={2} stackAt="small" gap="sm">
            {RUNS.map((r) => (
              <Button key={r.label} variant="secondary" disabled={running} onClick={() => void run(r.type, r.days)}>{r.label}</Button>
            ))}
          </Grid>
          {status && <Banner tone={status.startsWith('Didn') ? 'error' : 'info'} title="Classification" description={<span role="status">{status}</span>} />}
        </Stack>

        <PanelDivider />

        <Stack gap="md">
          <Stack direction="row" justify="between" gap="sm">
            <Eyebrow as="h3">Schedules</Eyebrow>
            <Button variant="secondary" size="sm" iconStart={<Icon name={formOpen ? 'X' : 'Plus'} size="sm" />} onClick={() => setFormOpen((o) => !o)}>{formOpen ? 'Cancel' : 'New schedule'}</Button>
          </Stack>
          {formOpen && (
            <Stack gap="md">
              <TextField label="Name" value={form.name} onChange={(name) => setForm({ ...form, name })} placeholder={`${brand?.display_name ?? 'All brands'} daily`} />
              <Grid columns={2} stackAt="small" gap="md">
                <Select label="What to classify" fullWidth value={form.run_type} onValueChange={(run_type) => setForm({ ...form, run_type })}
                  options={[{ value: 'incremental', label: 'Unclassified articles' }, { value: 'incremental_since_last', label: 'New since the last run' }, { value: 'full', label: 'Everything (reclassify)' }]} />
                <Select label="How far back" fullWidth value={form.days_back} onValueChange={(days_back) => setForm({ ...form, days_back })}
                  options={[{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }, { value: '365', label: '1 year' }]} />
                <Select label="How often" fullWidth value={form.schedule_type} onValueChange={(schedule_type) => setForm({ ...form, schedule_type })}
                  options={[{ value: 'interval', label: 'Every few hours' }, { value: 'daily', label: 'Daily at a set time' }]} />
                {form.schedule_type === 'interval' ? (
                  <TextField label="Every (hours)" type="number" min={1} max={168} value={form.schedule_interval} onChange={(schedule_interval) => setForm({ ...form, schedule_interval })} />
                ) : (
                  <TextField label="Time" type="time" value={form.schedule_time} onChange={(schedule_time) => setForm({ ...form, schedule_time })} hint="Server time." />
                )}
              </Grid>
              <TopicPicker topics={bw.topics} picked={formTopics} onChange={setFormTopics} label="Topics" />
              <div><Button onClick={() => void create()}>Create schedule</Button></div>
            </Stack>
          )}
          {schedules === null ? <Text variant="caption">Loading…</Text> : schedules.length === 0 && !formOpen ? (
            <Text>No schedules yet.</Text>
          ) : (
            <Stack as="ul" gap="sm" label="Schedules">
              {schedules.map((s) => (
                <li key={s.id}>
                  <Stack direction="row" justify="between" gap="sm">
                    <ActivityRow
                      primary={s.name}
                      secondary={[
                        s.schedule_type === 'daily' ? `Daily at ${s.schedule_time || '02:00'}` : `Every ${s.schedule_interval}h`,
                        s.brand_name ?? 'All brands',
                        s.last_run_at ? `last run ${new Date(s.last_run_at).toLocaleDateString('en-GB')}` : 'never run',
                      ].join(' · ')}
                      dotTone={s.schedule_enabled ? 'live' : 'pending'}
                      dotLabel={s.schedule_enabled ? 'On' : 'Off'}
                    />
                    <Stack direction="row" gap="sm" wrap={false}>
                      <Switch label={<span className="visually-hidden">{s.name} on</span>} checked={s.schedule_enabled} onCheckedChange={(on) => toggle(s, on)} />
                      <IconButton icon={<Icon name="Play" size="sm" />} label={`Run ${s.name} now`} disabled={running} onClick={() => void runNow(s)} />
                      <IconButton icon={<Icon name="Trash" size="sm" />} label={`Delete ${s.name}`} onClick={() => del(s)} />
                    </Stack>
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Stack>
      </Stack>
    </Dialog>
  );
}
