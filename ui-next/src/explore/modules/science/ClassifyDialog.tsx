import { useEffect, useRef, useState } from 'react';
import {
  Banner, Button, Checkbox, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, FileField, SegmentedControl,
  Skeleton, Stack, Switch, Text, TextField,
} from '@aunoo/ui';
import { getClassifyStatus, getImportStatus, importFromURL, runClassification, uploadCSVFile } from '@monolith/scienceFundingApi';
import { api, errorText } from '../../../shell';
import { SCIENCE_TOPIC } from './labels';
import './science.css';

/*
 * Classify articles, as the old ScienceFundingImportModal: sort a topic's articles into the ten
 * funding categories, and optionally import articles from a URL or a CSV file first. Classifying
 * tries a local classifier first and falls back to the AI for each article it can't place, so a
 * run can make one AI call per article; every run asks first, inside this dialog. Closing the
 * dialog stops watching a run, but the run carries on on the server.
 */

interface TopicItem { topic: string; article_count: number }
type RunChoice = { runType: 'incremental' | 'full'; days: number; label: string };
const RUNS: RunChoice[] = [
  { runType: 'incremental', days: 30, label: 'New articles from the last 30 days' },
  { runType: 'incremental', days: 90, label: 'New articles from the last 90 days' },
  { runType: 'incremental', days: 365, label: 'New articles from the last year' },
  { runType: 'full', days: 365, label: 'Everything from the last year, again' },
];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const today = () => new Date().toISOString().slice(0, 10);

export function ClassifyDialog({ open, onOpenChange, onDone, onOpenSchedules }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  /** After a run or import finishes, so the page reloads its figures */
  onDone: () => void;
  onOpenSchedules: () => void;
}) {
  const [topics, setTopics] = useState<TopicItem[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [pending, setPending] = useState<null | { kind: 'run'; choice: RunChoice } | { kind: 'import' }>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'url' | 'file'>('url');
  const [fromSource, setFromSource] = useState(false);
  const [url, setUrl] = useState('');
  const [start, setStart] = useState('2025-01-20');
  const [end, setEnd] = useState(today);
  const [file, setFile] = useState<File | null>(null);
  const watching = useRef(0);

  useEffect(() => {
    if (!open) {
      // Stop any status polling; the server keeps going
      watching.current += 1;
      setPending(null);
      setBusy(false);
      setStatus(null);
      setError(null);
      setFile(null);
      setPicked([]);
      return;
    }
    setTopics(null);
    api<TopicItem[]>('/api/brand-watcher/topics').then((t) => setTopics(Array.isArray(t) ? t : []), () => setTopics([]));
  }, [open]);

  const targets = picked.length ? picked : [SCIENCE_TOPIC];

  const classify = async (choice: RunChoice) => {
    const token = ++watching.current;
    setBusy(true);
    setError(null);
    let processed = 0;
    let categorised = 0;
    const failed: string[] = [];
    try {
      for (let i = 0; i < targets.length; i++) {
        const t = targets[i];
        setStatus(`Topic ${i + 1} of ${targets.length}, “${t}”: starting…`);
        const { run_id } = await runClassification({ topic: t, run_type: choice.runType, days_back: choice.days });
        for (;;) {
          await sleep(2000);
          if (watching.current !== token) return;
          const s = await getClassifyStatus(run_id);
          setStatus(`Topic ${i + 1} of ${targets.length}, “${t}”: ${s.status}, ${s.articles_processed} read, ${s.articles_categorized} categorised`);
          if (s.status === 'completed' || s.status === 'failed') {
            processed += s.articles_processed;
            categorised += s.articles_categorized;
            // The old dialog counted a failed run as done
            if (s.status === 'failed') failed.push(`${t}${s.error_message ? ` (${s.error_message})` : ''}`);
            break;
          }
        }
      }
      setStatus(`Finished: ${processed} articles read, ${categorised} categorised, across ${targets.length} ${targets.length === 1 ? 'topic' : 'topics'}.`);
      if (failed.length) setError(`These runs failed: ${failed.join('; ')}.`);
      onDone();
    } catch (e) {
      if (watching.current === token) setError(errorText(e));
    } finally {
      if (watching.current === token) setBusy(false);
    }
  };

  const runImport = async () => {
    const token = ++watching.current;
    setBusy(true);
    setError(null);
    setStatus('Starting the import…');
    try {
      const r = mode === 'file'
        ? await uploadCSVFile(file!, { topic: SCIENCE_TOPIC, runLlmClassification: true, regenerateNarrative: false })
        : await importFromURL({
          url: fromSource ? undefined : url.trim() || undefined,
          start_date: fromSource ? start : undefined,
          end_date: fromSource ? end : undefined,
          topic: SCIENCE_TOPIC,
          run_llm_classification: true,
          regenerate_narrative: false,
        });
      for (;;) {
        await sleep(2000);
        if (watching.current !== token) return;
        const s = await getImportStatus(r.import_id);
        if (s.status === 'completed') {
          setStatus(`Imported: ${s.articles_created} new articles, ${s.articles_updated} updated, ${s.categories_added} category tags added${s.errors ? `, ${s.errors} rows with errors` : ''}.`);
          onDone();
          break;
        }
        if (s.status === 'failed') {
          setStatus(null);
          setError(`The import failed${s.error_message ? `: ${s.error_message}` : '.'}`);
          break;
        }
        setStatus(`Importing: ${s.rows_processed} rows read so far…`);
      }
    } catch (e) {
      if (watching.current === token) {
        setStatus(null);
        setError(errorText(e));
      }
    } finally {
      if (watching.current === token) setBusy(false);
    }
  };

  const importReady = mode === 'file' ? !!file : fromSource || !!url.trim();
  const confirmText = pending?.kind === 'run'
    ? `${pending.choice.label}, for ${targets.length === 1 ? `“${targets[0]}”` : `${targets.length} topics`}. Each article goes to a local classifier first; any it can’t place go to the AI, one call per article.${pending.choice.runType === 'full' ? ' Articles already categorised are categorised again.' : ''}`
    : `Imports the ${mode === 'file' ? 'CSV file' : fromSource ? 'records from the science data source for the dates picked' : 'file at that address'} into “${SCIENCE_TOPIC}” and classifies each new article, with the AI where needed.`;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Classify articles"
      description="Sort articles into the ten science funding categories. Classified articles fill in every ScienceWatch view."
      footer={
        <>
          <Button variant="ghost" size="lg" onClick={() => { onOpenChange(false); onOpenSchedules(); }}>Schedules</Button>
          <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
        </>
      }
    >
      <Stack gap="lg">
        <Stack gap="sm">
          <Text variant="label">{`Topics to classify${picked.length ? ` (${picked.length} picked)` : ''}`}</Text>
          <Text variant="caption">{`With none picked, the ScienceWatch topic “${SCIENCE_TOPIC}” is classified.`}</Text>
          {topics === null ? <Skeleton variant="text" lines={3} /> : topics.length === 0 ? <Text variant="caption">No topics found.</Text> : (
            <Collapsible>
              <CollapsibleTrigger variant="ghost" size="sm" className="science-wrap-trigger">{picked.length ? `Change the topics (${picked.length} picked)` : 'Pick other topics'}</CollapsibleTrigger>
              <CollapsibleContent>
                <div>
                  {topics.map((t) => (
                    <Checkbox
                      key={t.topic}
                      label={`${t.topic} (${t.article_count} articles)`}
                      checked={picked.includes(t.topic)}
                      disabled={busy}
                      onCheckedChange={(on) => setPicked((p) => (on ? [...p, t.topic] : p.filter((x) => x !== t.topic)))}
                    />
                  ))}
                </div>
                {picked.length > 0 && <Button variant="ghost" size="sm" disabled={busy} onClick={() => setPicked([])}>Clear the topics</Button>}
              </CollapsibleContent>
            </Collapsible>
          )}
        </Stack>

        <Stack gap="sm">
          <Text variant="label">Run now</Text>
          <Stack direction="row" gap="sm">
            {RUNS.map((r) => (
              <Button key={r.label} variant={r.runType === 'full' ? 'ghost' : 'secondary'} disabled={busy} onClick={() => setPending({ kind: 'run', choice: r })}>{r.label}</Button>
            ))}
          </Stack>
        </Stack>

        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm" className="science-wrap-trigger">Import articles from a URL or a CSV file</CollapsibleTrigger>
          <CollapsibleContent>
            <Stack gap="md">
              <SegmentedControl label="Import from" options={[{ value: 'url', label: 'A web address' }, { value: 'file', label: 'A CSV file' }]} value={mode} onValueChange={(v) => setMode(v as 'url' | 'file')} />
              {mode === 'url' ? (
                <Stack gap="sm">
                  <Switch label="Fetch from the science data source" description="Reads the source's records between two dates instead of a file at an address." checked={fromSource} onCheckedChange={setFromSource} />
                  {fromSource ? (
                    <Stack direction="row" gap="sm">
                      <TextField label="From" type="date" value={start} onChange={setStart} className="science-input" />
                      <TextField label="To" type="date" value={end} onChange={setEnd} className="science-input" />
                    </Stack>
                  ) : (
                    <TextField label="Address of the CSV file" type="url" placeholder="https://example.com/science-data.csv" value={url} onChange={setUrl} />
                  )}
                </Stack>
              ) : (
                <FileField label="CSV file" accept=".csv,text/csv" onFileChange={setFile} hint="One article per row." className="science-input" />
              )}
              <div><Button variant="secondary" disabled={busy || !importReady} onClick={() => setPending({ kind: 'import' })}>Import and classify</Button></div>
            </Stack>
          </CollapsibleContent>
        </Collapsible>

        {pending && (
          <Banner
            tone="warning"
            title={pending.kind === 'run' ? 'Run this classification?' : 'Import and classify?'}
            description={confirmText}
            action={
              <Stack direction="row" gap="sm">
                <Button variant="secondary" size="sm" onClick={() => setPending(null)}>Cancel</Button>
                <Button size="sm" onClick={() => { const p = pending; setPending(null); void (p.kind === 'run' ? classify(p.choice) : runImport()); }}>
                  {pending.kind === 'run' ? 'Run it' : 'Import'}
                </Button>
              </Stack>
            }
          />
        )}
        {status && <Banner tone={busy ? 'info' : 'success'} title={busy ? 'Working' : 'Done'} description={status} />}
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
      </Stack>
    </Dialog>
  );
}
