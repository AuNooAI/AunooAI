import { useCallback, useEffect, useRef, useState } from 'react';
import { Banner, Button, DialogClose, Dialog, Grid, Meter, Select, Stack, Stat, Switch, Text, TextField } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { getAvailableTopics, getProcessingStatus, processArticles, type AvailableTopic, type ProcessingStatus } from '../api';

/*
 * "Update": the AI reads collected articles and files the threats, actors and indicators they
 * describe, as the old ThreatImportModal. It runs on the server in the background; this dialog starts
 * it and follows its progress. Each article read is one AI call, so the dialog says how many before
 * starting.
 *
 * The old dialog only followed progress for a run it had started itself: opened during a run started
 * elsewhere, it showed the run but never updated. This one follows any run in progress.
 */

export function UpdateDialog({ open, onOpenChange, model, notify, onFinished }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  model: string;
  notify: (m: string) => void;
  onFinished: () => void;
}) {
  const [topics, setTopics] = useState<AvailableTopic[] | null>(null);
  const [topic, setTopic] = useState('all');
  const [limit, setLimit] = useState('100');
  const [all, setAll] = useState(false);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const wasRunning = useRef(false);

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  const poll = useCallback(async () => {
    try {
      const s = await getProcessingStatus();
      setStatus(s);
      if (s.status === 'processing') {
        wasRunning.current = true;
        if (!timer.current) timer.current = setInterval(() => void poll(), 2000);
      } else {
        stop();
        if (wasRunning.current) {
          wasRunning.current = false;
          if (s.status === 'completed') {
            notify(`Update finished: ${s.threats_extracted} threats from ${s.processed} articles`);
            onFinished();
          }
        }
      }
    } catch (e) {
      setError(errorText(e));
      stop();
    }
  }, [notify, onFinished]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setConfirming(false);
    getAvailableTopics().then(setTopics, () => setTopics([]));
    void poll();
    return stop;
  }, [open, poll]);

  const n = Math.max(1, Math.min(500, Number(limit) || 0));
  const picked = topics?.find((t) => t.topic === topic);
  const waiting = all ? (picked?.total_articles ?? null) : picked ? picked.unprocessed_count : topics ? topics.reduce((s, t) => s + t.unprocessed_count, 0) : null;
  const willRead = waiting === null ? n : Math.min(n, waiting);
  const running = status?.status === 'processing';

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      await processArticles({ batch_size: n, model, topic: topic === 'all' ? undefined : topic, process_all: all });
      setConfirming(false);
      wasRunning.current = true;
      void poll();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setStarting(false);
    }
  };

  const pct = status && status.total_articles ? Math.round((status.processed / status.total_articles) * 100) : 0;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Update threat intelligence"
      description="The AI reads collected articles and files the threats, actors and indicators they describe."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">{running ? 'Close (it keeps running)' : 'Close'}</Button></DialogClose>
          {!running && (confirming ? (
            <Button size="lg" disabled={starting} onClick={() => void start()}>{starting ? 'Starting…' : `Read ${willRead} article${willRead === 1 ? '' : 's'}`}</Button>
          ) : (
            <Button size="lg" disabled={topics === null} onClick={() => setConfirming(true)}>Start</Button>
          ))}
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        {running && status ? (
          <Stack gap="md">
            <Meter label="Articles read" value={pct} progress tone="neutral" />
            <Text variant="caption">{`${status.processed} of ${status.total_articles} articles read`}</Text>
            <Grid columns={3}>
              <Stat label="Threats filed" value={String(status.threats_extracted)} size="compact" />
              <Stat label="Actors named" value={String(status.actors_identified)} size="compact" />
              <Stat label="Indicators" value={String(status.iocs_extracted)} size="compact" />
            </Grid>
            {status.current_article && <Text variant="caption">{`Reading: ${status.current_article}`}</Text>}
          </Stack>
        ) : (
          <Stack gap="md">
            {status?.status === 'completed' && <Banner tone="success" title="Last update finished" description={`${status.threats_extracted} threats filed from ${status.processed} articles.`} />}
            {status?.status === 'failed' && <Banner tone="error" title="Last update failed" description={status.error ?? 'No reason was given.'} />}
            <Select
              label="Topic"
              options={[{ value: 'all', label: 'All topics' }, ...(topics ?? []).map((t) => ({ value: t.topic, label: `${t.topic} (${t.unprocessed_count} not yet read of ${t.total_articles})` }))]}
              value={topic}
              onValueChange={setTopic}
              fullWidth
            />
            <TextField label="Most articles to read" type="number" min={1} max={500} value={limit} onChange={setLimit} hint="Between 1 and 500. Each article read is one AI call." />
            <Switch label="Read articles again" description={all ? 'Articles already read are read again, and their threats refreshed.' : 'Only articles not read yet.'} checked={all} onCheckedChange={setAll} />
            {confirming && (
              <Banner
                tone="warning"
                title="This calls the AI"
                description={`The AI (${model}) reads up to ${willRead} article${willRead === 1 ? '' : 's'}${topic === 'all' ? ' across all topics' : ` from ${topic}`}, one call each. It runs in the background; you can close this and keep working.`}
              />
            )}
            {!confirming && waiting === 0 && !all && <Text variant="caption">There is nothing new to read here. Switch on “Read articles again” to refresh threats from articles already read.</Text>}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
