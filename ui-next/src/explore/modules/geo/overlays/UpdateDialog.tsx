import { useCallback, useEffect, useRef, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Meter, Select, Skeleton, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { getAvailableTopics, getProcessingStats, type AvailableTopic, type ProcessingStats } from '@monolith/geopoliticalHotspotsApi';
import { api, errorText } from '../../../../shell';
import { Schedules } from './Schedules';

/*
 * "Update hotspots", as the old GeopoliticalImportModal: the AI reads curated articles of a topic for
 * the places they report on, creating or updating hotspots. Opening it only reads the topic list and
 * the processed/unprocessed counts. Every run calls the AI once per article; the larger runs say so
 * and need a second click. Schedules for unattended runs are on the second tab.
 *
 * The old dialog never sent the model picked in Explore, so runs always used the server's default
 * model; it is sent now. Its "all new articles" button asked for more than the 500 the server
 * accepts once a topic had a large backlog, and the run failed; batches are capped at 500.
 */

interface RunStatus {
  running?: boolean;
  completed?: boolean;
  progress?: number;
  total?: number;
  processed?: number;
  created?: number;
  updated?: number;
  skipped?: number;
  errors?: number;
  message?: string;
  last_error?: string | null;
}

const MAX_BATCH = 500;
type Pending = { kind: 'run'; batch: number; all: boolean } | { kind: 'clear' } | null;

export function UpdateDialog({ open, onClose, model, notify, askConfirm, onChanged }: {
  open: boolean;
  onClose: () => void;
  model: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<'run' | 'schedules'>('run');
  const [topics, setTopics] = useState<AvailableTopic[] | null>(null);
  const [topic, setTopic] = useState('');
  const [stats, setStats] = useState<ProcessingStats | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(() => stopPolling, []);

  useEffect(() => {
    if (!open) {
      stopPolling();
      setPending(null);
      setError(null);
      return;
    }
    setTopics(null);
    getAvailableTopics().then(
      (t) => {
        setTopics(t);
        setTopic((cur) => cur || (t.find((x) => x.topic === 'Geopolitical Hotspots') ?? t[0])?.topic || '');
      },
      (e) => {
        setTopics([]);
        setError(errorText(e));
      },
    );
  }, [open]);

  const loadStats = useCallback(() => {
    if (!open) return;
    getProcessingStats(topic || undefined).then(setStats, () => setStats(null));
  }, [open, topic]);
  useEffect(() => loadStats(), [loadStats]);

  const finish = (s: RunStatus) => {
    stopPolling();
    setRunning(false);
    notify(`Hotspots updated: ${s.processed ?? 0} articles read, ${s.created ?? 0} hotspots created, ${s.updated ?? 0} updated`);
    loadStats();
    onChanged();
  };

  const poll = async () => {
    try {
      const s = await api<RunStatus>('/api/geopolitical-hotspots/process-articles/status');
      setStatus(s);
      if (s.completed || (!s.running && s.total && s.progress === s.total)) finish(s);
    } catch {
      // keep polling; a missed tick isn't a failure
    }
  };

  const run = async (batch: number, all: boolean) => {
    setPending(null);
    setError(null);
    setRunning(true);
    setStatus(null);
    try {
      const r = await api<RunStatus & { status?: string; articles_processed?: number; hotspots_created?: number; hotspots_updated?: number }>(
        '/api/geopolitical-hotspots/process-articles',
        { method: 'POST', json: { batch_size: Math.min(batch, MAX_BATCH), topic: topic || undefined, process_all: all, model } },
      );
      if (r.status === 'started' || r.status === 'running') {
        stopPolling();
        timer.current = setInterval(() => void poll(), 2000);
      } else {
        finish({ processed: r.articles_processed, created: r.hotspots_created, updated: r.hotspots_updated });
      }
    } catch (e) {
      setRunning(false);
      setError(`The update didn’t start: ${errorText(e)}`);
    }
  };

  const clearAll = async () => {
    setPending(null);
    setError(null);
    try {
      await api('/api/geopolitical-hotspots/clear-hotspots', { method: 'DELETE' });
      notify('All hotspot data deleted');
      loadStats();
      onChanged();
    } catch (e) {
      setError(`Not deleted: ${errorText(e)}`);
    }
  };

  const unprocessed = stats?.unprocessed_articles ?? 0;
  const total = stats?.total_curated_articles ?? 0;
  const ask = (batch: number, all: boolean) => {
    // Small batches start straight away; big ones say what they cost first
    if (!all && batch <= 50) void run(batch, all);
    else setPending({ kind: 'run', batch: Math.min(batch, MAX_BATCH), all });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && !running && onClose()}
      size="lg"
      title="Update hotspots"
      description="The AI reads curated articles for the places they report on, and creates or updates hotspots."
      footer={<DialogClose><Button variant="secondary" size="lg" disabled={running}>Close</Button></DialogClose>}
    >
      <Tabs label="Update hotspots" value={tab} onValueChange={(v) => setTab(v as 'run' | 'schedules')} items={[{ value: 'run', label: 'Run now' }, { value: 'schedules', label: 'Schedules' }]}>
        <TabPanel value="run">
          <Stack gap="md">
            {error && <Banner tone="error" title="Something went wrong" description={error} />}
            {!topics ? <Skeleton variant="text" lines={3} /> : topics.length === 0 ? <Text>No topic has curated articles to read.</Text> : (
              <Select
                label="Topic"
                options={topics.map((t) => ({ value: t.topic, label: `${t.topic} (${t.unprocessed_count} not read of ${t.total_articles})` }))}
                value={topic}
                onValueChange={setTopic}
                disabled={running}
                fullWidth
              />
            )}
            {stats && (
              <Text variant="caption">
                {`${unprocessed.toLocaleString()} of ${total.toLocaleString()} curated articles haven’t been read for places yet. ${stats.total_hotspots.toLocaleString()} hotspots on file. Each article read is one AI call (${model}).`}
              </Text>
            )}
            <Stack direction="row" gap="sm">
              <Button disabled={running || unprocessed === 0} onClick={() => ask(unprocessed, false)}>
                {`Read the ${Math.min(unprocessed, MAX_BATCH).toLocaleString()} newest unread${unprocessed > MAX_BATCH ? ' (most per run)' : ''}`}
              </Button>
              <Button variant="secondary" disabled={running || unprocessed === 0} onClick={() => ask(50, false)}>Read 50</Button>
              <Button variant="secondary" disabled={running || unprocessed === 0} onClick={() => ask(200, false)}>Read 200</Button>
              <Button variant="ghost" disabled={running || total === 0} onClick={() => ask(MAX_BATCH, true)}>Re-read 500, including read ones</Button>
            </Stack>

            {pending?.kind === 'run' && (
              <Banner
                tone="warning"
                title={pending.all ? `Re-read ${pending.batch} articles?` : `Read ${pending.batch} articles?`}
                description={`That is ${pending.batch} AI calls with ${model}.${pending.all ? ' Articles already read are read again and their hotspot links refreshed.' : ''} It runs in the background; you can close this dialog.`}
                action={
                  <Stack direction="row" gap="sm">
                    <Button size="sm" onClick={() => void run(pending.batch, pending.all)}>Start</Button>
                    <Button size="sm" variant="secondary" onClick={() => setPending(null)}>Cancel</Button>
                  </Stack>
                }
              />
            )}

            {(running || status) && (
              <Stack gap="sm">
                {status?.total ? (
                  <Meter label="Articles read" value={status.progress ?? 0} min={0} max={status.total} valueText={`${status.progress ?? 0} of ${status.total}`} progress />
                ) : running ? <Text variant="caption">Starting…</Text> : null}
                {status && (
                  <Text variant="caption">
                    {`${status.created ?? 0} hotspots created, ${status.updated ?? 0} updated, ${status.skipped ?? 0} articles skipped${status.errors ? `, ${status.errors} errors` : ''}.`}
                  </Text>
                )}
                {status?.last_error && <Text tone="error">{`Last error: ${status.last_error}`}</Text>}
              </Stack>
            )}

            {pending?.kind === 'clear' ? (
              <Banner
                tone="error"
                title={`Delete all ${stats?.total_hotspots ?? 0} hotspots?`}
                description="Every hotspot and its article links are deleted. This can’t be undone; the articles themselves are kept and can be read again."
                action={
                  <Stack direction="row" gap="sm">
                    <Button size="sm" variant="secondary" onClick={() => setPending(null)}>Cancel</Button>
                    <Button size="sm" onClick={() => void clearAll()}>Delete all hotspots</Button>
                  </Stack>
                }
              />
            ) : (
              <div>
                <Button variant="ghost" size="sm" disabled={running || !stats || stats.total_hotspots === 0} onClick={() => setPending({ kind: 'clear' })}>
                  {`Delete all hotspot data (${stats?.total_hotspots ?? 0} hotspots)`}
                </Button>
              </div>
            )}
          </Stack>
        </TabPanel>
        <TabPanel value="schedules">
          {tab === 'schedules' && <Schedules open={open} topics={topics ?? []} model={model} notify={notify} askConfirm={askConfirm} onRan={onChanged} />}
        </TabPanel>
      </Tabs>
    </Dialog>
  );
}
