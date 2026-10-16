import { useEffect, useRef, useState } from 'react';
import { Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, FileField, Meter, SegmentedControl, Select, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import {
  getFeedKeywordGroups, getImportStatus, importFromFeed, importFromURL, uploadCSVFile, type FeedKeywordGroup, type ImportStatus,
} from '@monolith/policyTrackerApi';
import { errorText } from '../../../shell';
import { TRACKER_TOPIC } from './api';
import './policy.css';

/*
 * The old PolicyTrackerImportModal. Two ways in:
 *  - sort the articles already collected for a keyword group into the ten categories (the site's own
 *    classifier models, no paid AI);
 *  - import the Trump Action Tracker list, a CSV at a web address, or a CSV file, then sort it.
 * Both run on the server; the dialog follows the import's progress.
 *
 * Changed from the old dialog: its "Full reclassify" button sent the same request as the incremental
 * one, and the server only ever sorts articles that have no category yet, so it reclassified nothing.
 * It's gone. Nothing loads until the dialog opens.
 */

const today = () => new Date().toISOString().slice(0, 10);

export function UpdateDialog({ open, onOpenChange, onDone, notify }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void; notify: (m: string) => void }) {
  const [groups, setGroups] = useState<FeedKeywordGroup[] | null>(null);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'tracker' | 'url' | 'file'>('tracker');
  const [start, setStart] = useState('2025-01-20');
  const [end, setEnd] = useState(today);
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [importId, setImportId] = useState<number | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setGroups(null);
    setError(null);
    setMessage(null);
    setStatus(null);
    setImportId(null);
    getFeedKeywordGroups().then(
      (r) => {
        setGroups(r.groups);
        setGroupId((r.groups.find((g) => g.name === TRACKER_TOPIC) ?? r.groups[0])?.id ?? null);
      },
      (e) => {
        setGroups([]);
        setError(`The keyword groups didn’t load: ${errorText(e)}`);
      },
    );
  }, [open]);

  // Follows a background import every two seconds until it finishes
  useEffect(() => {
    if (importId === null) return;
    const poll = async () => {
      try {
        const s = await getImportStatus(importId);
        setStatus(s);
        if (s.status === 'completed' || s.status === 'failed') {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          setBusy(false);
          setImportId(null);
          if (s.status === 'completed') {
            setMessage(`Done: ${s.articles_created} articles added, ${s.articles_updated} updated, ${s.categories_added} category labels added${s.errors ? `, ${s.errors} rows failed` : ''}.`);
            notify('Crisis Tracker updated');
            onDone();
          } else setError(s.error_message || 'The import failed on the server.');
        }
      } catch {
        // a missed poll is retried on the next tick
      }
    };
    void poll();
    timer.current = window.setInterval(() => void poll(), 2000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [importId, notify, onDone]);

  const group = groups?.find((g) => g.id === groupId);
  const newCount = group ? Math.max(0, group.total_feed_items - group.already_imported) : 0;

  const classify = async () => {
    if (!groupId) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    setMessage('Starting…');
    try {
      const r = await importFromFeed({ group_id: groupId, run_llm_classification: true, regenerate_narrative: false, topic: TRACKER_TOPIC });
      if (r.status === 'processing') {
        setMessage('Sorting articles in the background…');
        setImportId(r.import_id);
      } else {
        setMessage(`Done: ${r.articles_imported} sorted, ${r.articles_skipped} skipped.`);
        setBusy(false);
        onDone();
      }
    } catch (e) {
      setError(errorText(e));
      setMessage(null);
      setBusy(false);
    }
  };

  const runImport = async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    setMessage('Starting the import…');
    try {
      const r = mode === 'file'
        ? await uploadCSVFile(file!, { topic: TRACKER_TOPIC, runLlmClassification: true, regenerateNarrative: false })
        : await importFromURL({
          url: mode === 'url' ? url.trim() : undefined,
          start_date: mode === 'tracker' ? start : undefined,
          end_date: mode === 'tracker' ? end : undefined,
          topic: TRACKER_TOPIC,
          run_llm_classification: true,
          regenerate_narrative: false,
        });
      setMessage(r.message || 'Import started…');
      setImportId(r.import_id);
    } catch (e) {
      setError(errorText(e));
      setMessage(null);
      setBusy(false);
    }
  };

  const canImport = mode === 'file' ? !!file : mode === 'url' ? /^https?:\/\//.test(url.trim()) : !!start && !!end && start <= end;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !busy && onOpenChange(o)}
      size="lg"
      title="Update the Crisis Tracker"
      description="Sort collected articles into the tracker’s ten policy categories, or import new ones. Sorting uses the site’s own classifier models, not a paid AI service."
      footer={<DialogClose><Button variant="secondary" size="lg" disabled={busy}>{busy ? 'Working…' : 'Close'}</Button></DialogClose>}
    >
      <Stack gap="lg">
        <Stack gap="sm">
          <Text variant="label">Sort collected articles</Text>
          {!groups ? <Skeleton variant="text" lines={2} /> : groups.length === 0 ? (
            <Text variant="caption">No keyword groups yet. Create one in Gather and let it collect, then come back here to sort its articles.</Text>
          ) : (
            <>
              <Select
                label="Keyword group"
                value={groupId ? String(groupId) : undefined}
                onValueChange={(v) => setGroupId(Number(v))}
                disabled={busy}
                options={groups.map((g) => ({ value: String(g.id), label: `${g.name} (${Math.max(0, g.total_feed_items - g.already_imported).toLocaleString()} new of ${g.total_feed_items.toLocaleString()})` }))}
              />
              <Text variant="caption">Only articles without a category are sorted; ones already sorted keep their categories.</Text>
              <div>
                <Button disabled={busy || !groupId || newCount === 0} onClick={() => void classify()}>
                  {newCount === 0 ? 'Nothing new to sort' : `Sort the ${newCount.toLocaleString()} new ${newCount === 1 ? 'article' : 'articles'}`}
                </Button>
              </div>
            </>
          )}
        </Stack>

        {(message || status) && (
          <Stack gap="sm">
            {message && <Text>{message}</Text>}
            {status?.status === 'processing' && (
              <Meter label="Rows read so far" value={status.rows_processed} max={Math.max(status.rows_processed, 1)} valueText={`${status.rows_processed.toLocaleString()} rows`} progress />
            )}
          </Stack>
        )}
        {error && <Banner tone="error" title="That didn’t work" description={error} />}

        <Collapsible>
          <CollapsibleTrigger variant="ghost" className="policy-wrap-trigger">Import articles from outside the site</CollapsibleTrigger>
          <CollapsibleContent>
            <Stack gap="md">
              <SegmentedControl className="policy-segmented"
                label="Import from"
                value={mode}
                onValueChange={(v) => setMode(v as typeof mode)}
                options={[{ value: 'tracker', label: 'Trump Action Tracker' }, { value: 'url', label: 'CSV at a web address' }, { value: 'file', label: 'CSV file' }]}
              />
              {mode === 'tracker' && (
                <Stack direction="row" gap="sm">
                  <TextField label="From" type="date" value={start} onChange={setStart} disabled={busy} />
                  <TextField label="To" type="date" value={end} max={today()} onChange={setEnd} disabled={busy} />
                </Stack>
              )}
              {mode === 'url' && <TextField label="Address of the CSV" type="url" placeholder="https://example.com/data.csv" value={url} onChange={setUrl} disabled={busy} />}
              {mode === 'file' && <FileField label="CSV file" accept=".csv,text/csv" onFileChange={setFile} disabled={busy} hint={file ? `${file.name}, ${(file.size / 1024).toFixed(1)} KB` : 'One article per row, with a link column.'} />}
              <Text variant="caption">The tracker and web-address imports fetch the list from that site. New articles are added to the tracker topic and sorted into categories as they arrive; existing ones are updated.</Text>
              <div><Button variant="secondary" disabled={busy || !canImport} onClick={() => void runImport()}>Import and sort</Button></div>
            </Stack>
          </CollapsibleContent>
        </Collapsible>
      </Stack>
    </Dialog>
  );
}
