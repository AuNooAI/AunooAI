import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Dialog, DialogClose, FileField, SegmentedControl, Stack, Text } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';

/*
 * Loading topic settings or articles from an exported JSON file, as the old import dialogs. Both
 * start in "merge" mode, which adds without deleting. "Replace" deletes what's there first, so it
 * asks before it runs.
 */

interface Props extends SettingsPageProps {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}

const MODES = [{ value: 'merge', label: 'Merge' }, { value: 'replace', label: 'Replace' }];

async function readJson(file: File): Promise<Record<string, unknown>> {
  try {
    return JSON.parse(await file.text());
  } catch {
    throw new Error('That file isn’t valid JSON.');
  }
}

export function TopicImportDialog({ open, onClose, onDone, notify, askConfirm }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState('merge');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setFile(null);
      setMode('merge');
      setError(null);
    }
  }, [open]);

  const doImport = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const data = await readJson(file);
      const r = await api<{ message?: string }>(`/api/import-topics?merge_mode=${mode === 'merge'}`, { method: 'POST', json: data });
      notify(r?.message || 'Topic settings imported');
      onDone();
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const start = () => {
    if (mode !== 'replace') return void doImport();
    askConfirm({
      title: 'Replace all topic settings?',
      message: 'Every current topic configuration is deleted and replaced with the ones in the file.',
      action: 'Replace topic settings',
      onConfirm: () => void doImport(),
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Import topic settings"
      description="Load topic monitoring settings from a JSON file exported here or on another site."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!file || busy} onClick={start}>Import</Button>
        </>
      }
    >
      <Stack gap="md">
        <FileField label="Topic settings file" accept=".json,application/json" onFileChange={setFile} hint="A JSON file of topic configurations." />
        <SegmentedControl label="How to import" options={MODES} value={mode} onValueChange={setMode} />
        <Text variant="caption">
          {mode === 'merge'
            ? 'Adds the file’s topics without removing any. Topics that already exist are skipped.'
            : 'Deletes every current topic configuration and replaces them with the file’s.'}
        </Text>
        {error && <Banner tone="error" title="Not imported" description={error} />}
      </Stack>
    </Dialog>
  );
}

export function ArticleImportDialog({ open, onClose, onDone, notify, askConfirm }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState('merge');
  const [skipDuplicates, setSkip] = useState(true);
  const [updateExisting, setUpdate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setFile(null);
      setMode('merge');
      setSkip(true);
      setUpdate(false);
      setError(null);
    }
  }, [open]);

  const doImport = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const data = await readJson(file);
      if (!Array.isArray((data as { articles?: unknown }).articles)) throw new Error('The file has no "articles" list, so it isn’t an article export.');
      const params = new URLSearchParams({ merge_mode: String(mode === 'merge'), skip_duplicates: String(skipDuplicates), update_existing: String(updateExisting) });
      const r = await api<{ message?: string; statistics?: { failed?: number; errors?: string[] } }>(`/api/import-articles?${params}`, { method: 'POST', json: data });
      const errs = r?.statistics?.errors ?? [];
      notify(errs.length ? `${r?.message ?? 'Imported'}. ${errs.length} errors, e.g. ${errs.slice(0, 2).join('; ')}` : r?.message || 'Articles imported');
      onDone();
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const start = () => {
    if (mode !== 'replace') return void doImport();
    askConfirm({
      title: 'Replace all articles?',
      message: 'Every current article is permanently deleted and replaced with the ones in the file.',
      action: 'Replace all articles',
      onConfirm: () => void doImport(),
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Import articles"
      description="Load articles from a JSON file exported here or on another site."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!file || busy} onClick={start}>Import</Button>
        </>
      }
    >
      <Stack gap="md">
        <FileField label="Article file" accept=".json,application/json" onFileChange={setFile} hint="A JSON file of exported articles." />
        <SegmentedControl label="How to import" options={MODES} value={mode} onValueChange={setMode} />
        <Text variant="caption">
          {mode === 'merge'
            ? 'Adds the file’s articles without removing any.'
            : 'Deletes every current article and replaces them with the file’s.'}
        </Text>
        <Checkbox label="Skip articles already here (same address), and leave them unchanged" checked={skipDuplicates} onCheckedChange={setSkip} />
        <Checkbox label="Update articles already here with the file’s data" checked={updateExisting} onCheckedChange={setUpdate} />
        <Text variant="caption">With both unticked, articles already here are skipped.</Text>
        {error && <Banner tone="error" title="Not imported" description={error} />}
      </Stack>
    </Dialog>
  );
}
