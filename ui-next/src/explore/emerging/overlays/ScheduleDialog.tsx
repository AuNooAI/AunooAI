import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, LineItems, Select, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../../shell';

/*
 * Scheduled Emerging Topics detection, as the old EmergingTopicsScheduleModal.tsx:
 * GET /api/emerging-topics/schedule/status (read only), POST .../schedule/settings, and
 * POST .../schedule/run-now, which runs a full detection with the AI and waits for it to finish.
 */

interface ScheduleSettings {
  schedule_enabled: boolean;
  check_interval: number;
  interval_unit: string;
  min_articles: number;
}

interface ScheduleStatus {
  last_check_time: string | null;
  next_check_time: string | null;
  topics_detected: number;
  articles_analyzed: number;
  is_running: boolean;
  last_error: string | null;
}

interface RunResult {
  success?: boolean;
  topics_detected?: number;
  articles_analyzed?: number;
  error?: string | null;
}

const DEFAULTS: ScheduleSettings = { schedule_enabled: false, check_interval: 24, interval_unit: 'hours', min_articles: 50 };
const UNITS = [
  { value: 'hours', label: 'hours' },
  { value: 'days', label: 'days' },
];

const when = (iso: string | null) => {
  if (!iso) return 'Never';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-GB');
};

export function EmergingTopicsScheduleModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [settings, setSettings] = useState<ScheduleSettings | null>(null);
  const [status, setStatus] = useState<ScheduleStatus | null>(null);
  const [busy, setBusy] = useState<null | 'save' | 'run'>(null);
  const [confirmRun, setConfirmRun] = useState(false);
  const [note, setNote] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);

  const load = () =>
    api<{ settings?: Partial<ScheduleSettings> | null; status?: ScheduleStatus | null }>('/api/emerging-topics/schedule/status').then(
      (d) => {
        const s = d.settings ?? {};
        setSettings({
          schedule_enabled: s.schedule_enabled || false,
          check_interval: s.check_interval || 24,
          interval_unit: s.interval_unit || 'hours',
          min_articles: s.min_articles || 50,
        });
        setStatus(d.status && Object.keys(d.status).length ? d.status : null);
      },
      (e: unknown) => {
        setSettings(DEFAULTS);
        setNote({ tone: 'error', text: `The saved schedule didn’t load: ${errorText(e)}` });
      },
    );

  useEffect(() => {
    if (!open) return;
    setSettings(null);
    setNote(null);
    setConfirmRun(false);
    void load();
  }, [open]);

  const set = (patch: Partial<ScheduleSettings>) => setSettings((s) => (s ? { ...s, ...patch } : s));

  const save = async () => {
    if (!settings) return;
    setBusy('save');
    setNote(null);
    try {
      await api('/api/emerging-topics/schedule/settings', { method: 'POST', json: settings });
      await load();
      setNote({ tone: 'success', text: settings.schedule_enabled ? `Saved: detection runs every ${settings.check_interval} ${settings.interval_unit}.` : 'Saved: automatic detection is off.' });
    } catch (e) {
      // The old dialog only logged a failed save to the console
      setNote({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const runNow = async () => {
    setConfirmRun(false);
    setBusy('run');
    setNote({ tone: 'info', text: 'Detection is running. This can take a few minutes; keep this open to see the result.' });
    try {
      const r = await api<RunResult>('/api/emerging-topics/schedule/run-now', { method: 'POST' });
      // The route answers 200 with success false when the run failed; the old dialog reported that as "0 topics found"
      setNote(
        r.success === false
          ? { tone: 'error', text: `Detection didn’t finish: ${r.error || 'no reason given'}.` }
          : { tone: 'success', text: `Detection finished: ${r.topics_detected ?? 0} topics found from ${r.articles_analyzed ?? 0} articles.` },
      );
      await load();
    } catch (e) {
      setNote({ tone: 'error', text: `Detection failed: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const running = busy === 'run' || !!status?.is_running;

  const footer = confirmRun ? (
    <>
      <Button variant="secondary" size="lg" onClick={() => setConfirmRun(false)}>Cancel</Button>
      <Button size="lg" onClick={() => void runNow()}>Run detection now</Button>
    </>
  ) : (
    <>
      <Button variant="ghost" size="lg" disabled={busy !== null || running || !settings} onClick={() => setConfirmRun(true)}>
        {busy === 'run' ? 'Running…' : 'Run now'}
      </Button>
      <Button variant="secondary" size="lg" onClick={onClose}>Close</Button>
      <Button size="lg" disabled={busy !== null || !settings} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : 'Save'}</Button>
    </>
  );

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Scheduled detection" description="Run Emerging Topics detection on its own, at a fixed interval." footer={footer}>
      {!settings ? <Skeleton variant="text" lines={5} /> : (
        <Stack gap="lg">
          <Switch label="Automatic detection" description="Run detection on a schedule, across all topics." checked={settings.schedule_enabled} onCheckedChange={(on) => set({ schedule_enabled: on })} />
          <Stack direction="row" gap="sm">
            <TextField
              label="Run every"
              type="number"
              min={1}
              max={168}
              value={String(settings.check_interval)}
              onChange={(v) => set({ check_interval: Math.max(1, Math.min(168, parseInt(v, 10) || 1)) })}
            />
            <Select label="Unit" options={UNITS} value={settings.interval_unit} onValueChange={(v) => set({ interval_unit: v })} />
          </Stack>
          <Text variant="caption">Each run has the AI read a sample of recent articles, so a shorter interval costs more.</Text>

          {status && (
            <LineItems
              label={running ? 'Status: running now' : 'Status'}
              items={[
                { label: 'Last run', amount: running ? 'Running now' : when(status.last_check_time) },
                { label: 'Next run', amount: settings.schedule_enabled ? when(status.next_check_time) : 'Not scheduled' },
                ...(status.topics_detected > 0 ? [{ label: 'Last result', amount: `${status.topics_detected} topics from ${status.articles_analyzed ?? 0} articles` }] : []),
              ]}
            />
          )}
          {status?.last_error && <Banner tone="error" title="The last run failed" description={status.last_error} />}

          {confirmRun && (
            <Banner
              tone="warning"
              title="Run detection now?"
              description="This runs a full detection with the AI across all topics, using the saved schedule settings, and costs the same as a scheduled run. It can take a few minutes."
            />
          )}
          {note && <Banner tone={note.tone} title={note.tone === 'error' ? 'Something went wrong' : note.tone === 'info' ? 'Working' : 'Done'} description={note.text} />}
        </Stack>
      )}
    </Dialog>
  );
}
