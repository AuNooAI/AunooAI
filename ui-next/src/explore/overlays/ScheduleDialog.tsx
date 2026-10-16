import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Dialog, DialogClose, Eyebrow, Grid, LineItems, Select, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';

/*
 * Scheduled dashboard generation, on the old modal's routes (NewsfeedScheduleModal.tsx):
 * GET /api/news-feed/dashboard/schedule/status, POST .../settings, POST .../run-now (runs the AI).
 */

interface Settings {
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily';
  check_interval: number;
  interval_unit: 'hours' | 'days';
  schedule_time: string;
  generate_briefing: boolean;
  generate_highlights: boolean;
  generate_narratives: boolean;
  persona: string;
}
interface Status {
  last_run_time: string | null;
  next_run_time: string | null;
  last_run_status: string | null;
  last_error: string | null;
  is_running: boolean;
  run_count: number;
}

const DEFAULTS: Settings = {
  schedule_enabled: false, schedule_type: 'daily', check_interval: 24, interval_unit: 'hours', schedule_time: '06:00',
  generate_briefing: true, generate_highlights: true, generate_narratives: true, persona: 'CEO',
};
const when = (t: string | null) => (t ? t.slice(0, 16).replace('T', ' ') : 'Never');

export function ScheduleDialog({ open, onOpenChange, notify }: { open: boolean; onOpenChange: (o: boolean) => void; notify: (m: string) => void }) {
  const [draft, setDraft] = useState<Settings | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<{ settings: Partial<Settings> | null; status: Status | null }>('/api/news-feed/dashboard/schedule/status').then(
      (r) => {
        setDraft({ ...DEFAULTS, ...(r.settings ?? {}), schedule_time: (r.settings?.schedule_time ?? DEFAULTS.schedule_time).slice(0, 5) });
        setStatus(r.status);
      },
      (e: unknown) => {
        setDraft(DEFAULTS);
        setError(errorText(e));
      },
    );
  useEffect(() => {
    if (!open) return;
    setDraft(null);
    setError(null);
    void load();
  }, [open]);

  const set = (patch: Partial<Settings>) => setDraft((d) => (d ? { ...d, ...patch } : d));

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      await api('/api/news-feed/dashboard/schedule/settings', { method: 'POST', json: draft });
      notify(!draft.schedule_enabled ? 'Automatic generation turned off' : draft.schedule_type === 'daily' ? `Schedule saved: daily at ${draft.schedule_time}` : 'Schedule saved');
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      await api('/api/news-feed/dashboard/schedule/run-now', { method: 'POST' });
      notify('Generation started. The briefing updates when it finishes.');
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Scheduled dashboard generation"
      footer={
        <>
          <Button variant="ghost" size="lg" disabled={busy || !!status?.is_running} onClick={() => void runNow()}>Run now</Button>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy || !draft} onClick={() => void save()}>Save</Button>
        </>
      }
    >
      {!draft ? <Skeleton variant="text" lines={8} /> : (
        <Stack gap="lg">
          {error && <Banner tone="error" title="Something went wrong" description={error} />}
          <Switch label="Automatic generation" description="Write the dashboard on a schedule, so it’s ready when you open Explore." checked={draft.schedule_enabled} onCheckedChange={(schedule_enabled) => set({ schedule_enabled })} />
          <Select
            label="Schedule"
            fullWidth
            options={[{ value: 'daily', label: 'Daily at a set time' }, { value: 'interval', label: 'At an interval' }]}
            value={draft.schedule_type}
            onValueChange={(v) => set({ schedule_type: v as Settings['schedule_type'] })}
          />
          {draft.schedule_type === 'daily' ? (
            <TextField label="Time" type="time" value={draft.schedule_time} onChange={(schedule_time) => set({ schedule_time })} hint="Server time." />
          ) : (
            <Grid columns={2} stackAt="small" gap="md">
              <TextField label="Every" type="number" min={1} max={168} value={String(draft.check_interval)} onChange={(v) => set({ check_interval: Math.max(1, Number(v) || 1) })} />
              <Select label="Unit" fullWidth options={[{ value: 'hours', label: 'Hours' }, { value: 'days', label: 'Days' }]} value={draft.interval_unit} onValueChange={(v) => set({ interval_unit: v as Settings['interval_unit'] })} />
            </Grid>
          )}
          <Stack gap="md">
            <Eyebrow as="h3">Generate</Eyebrow>
            <Switch label="Executive briefing" description="The top stories with AI analysis" checked={draft.generate_briefing} onCheckedChange={(generate_briefing) => set({ generate_briefing })} />
            <Switch label="Incidents" description="Key events and incidents" checked={draft.generate_highlights} onCheckedChange={(generate_highlights) => set({ generate_highlights })} />
            <Switch label="Narratives" description="Themes running through the coverage" checked={draft.generate_narratives} onCheckedChange={(generate_narratives) => set({ generate_narratives })} />
          </Stack>
          <Select
            label="Briefing persona"
            fullWidth
            options={['CEO', 'CMO', 'CTO', 'CISO'].map((v) => ({ value: v, label: v }))}
            value={draft.persona}
            onValueChange={(persona) => set({ persona })}
          />
          {status && (
            <Stack gap="sm">
              <Eyebrow as="h3">Status</Eyebrow>
              <LineItems
                label="Schedule status"
                items={[
                  { id: 'last', label: 'Last run', amount: when(status.last_run_time) },
                  { id: 'next', label: 'Next run', amount: draft.schedule_enabled ? when(status.next_run_time) : 'Paused' },
                  {
                    id: 'result', label: 'Last result',
                    amount: status.is_running ? <Chip size="sm" tone="info">Running</Chip> : status.last_run_status ? <Chip size="sm" tone={status.last_run_status === 'success' ? 'success' : 'error'}>{status.last_run_status}</Chip> : '–',
                  },
                  { id: 'runs', label: 'Total runs', amount: status.run_count },
                ]}
              />
              {status.last_error && <Text variant="caption" tone="error">{status.last_error}</Text>}
              <Text variant="caption">Times are server time.</Text>
            </Stack>
          )}
        </Stack>
      )}
    </Dialog>
  );
}
