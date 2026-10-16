import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Dialog, DialogClose, FileField, Grid, Icon, IconButton, Pagination, Panel, Select, Skeleton, Stack, Stat, Switch, Table, Text,
  TextField, TextLink,
} from '@aunoo/ui';
import { api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import { fmtDate, type MediaBiasSource, type MediaBiasStatus } from './api';

/*
 * Data used to enrich articles, as the old Datasets tab: the media bias list (MBFC and AllSides),
 * whether articles are enriched with it, loading or resetting it, uploading a CSV, and searching,
 * adding, editing and deleting sources. Routes are /api/datasets/media_bias/*.
 */

const PER_PAGE = 20;
const BIAS = ['left', 'left-center', 'center', 'right-center', 'right', 'least biased', 'extreme left', 'extreme right'];
const FACTUAL = ['very high', 'high', 'mostly factual', 'mixed', 'low', 'very low'];
const PRESS = ['free press', 'mostly free', 'partly free', 'not free'];
const POPULARITY = ['very high traffic', 'high traffic', 'medium traffic', 'low traffic'];
const CREDIBILITY = ['high credibility', 'medium credibility', 'low credibility'];
const cap = (s: string) => s.replace(/\b\w/g, (c) => c.toUpperCase());
const opts = (list: string[], none: string) => [{ value: 'any', label: none }, ...list.map((v) => ({ value: v, label: cap(v) }))];

interface Filters { query: string; bias: string; factual: string; country: string }
const NO_FILTERS: Filters = { query: '', bias: 'any', factual: 'any', country: 'any' };

export function DatasetsTab({ notify, askConfirm }: SettingsPageProps) {
  const [status, setStatus] = useState<MediaBiasStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [upload, setUpload] = useState<File | null>(null);
  const [countries, setCountries] = useState<string[]>([]);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [draft, setDraft] = useState('');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<{ sources: MediaBiasSource[]; total: number; total_pages: number } | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [editing, setEditing] = useState<MediaBiasSource | 'new' | null>(null);

  const loadStatus = useCallback(() => {
    setStatusError(null);
    api<{ status: MediaBiasStatus }>('/api/datasets/media_bias').then((r) => setStatus(r.status), (e) => setStatusError(errorText(e)));
    api<{ countries?: string[] }>('/api/datasets/media_bias/filters').then((f) => setCountries((f.countries ?? []).filter(Boolean)), () => setCountries([]));
  }, []);
  useEffect(loadStatus, [loadStatus]);

  const loadList = useCallback(() => {
    setListError(null);
    // One value per filter: the server matches each as a single "contains" pattern (the old page
    // sent several joined by commas, which matched nothing)
    const p = new URLSearchParams({ page: String(page), per_page: String(PER_PAGE) });
    if (filters.query.trim()) p.set('query', filters.query.trim());
    if (filters.bias !== 'any') p.set('bias', filters.bias);
    if (filters.factual !== 'any') p.set('factual', filters.factual);
    if (filters.country !== 'any') p.set('country', filters.country);
    api<{ sources: MediaBiasSource[]; total: number; total_pages: number }>(`/api/datasets/media_bias/search?${p}`).then(setResult, (e) => {
      setResult({ sources: [], total: 0, total_pages: 0 });
      setListError(errorText(e));
    });
  }, [page, filters]);
  useEffect(loadList, [loadList]);

  const refresh = () => {
    loadStatus();
    loadList();
  };
  const run = async (id: string, fn: () => Promise<string>) => {
    setBusy(id);
    try {
      notify(await fn());
      refresh();
    } catch (e) {
      notify(`Didn’t work: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const setEnabled = (on: boolean) =>
    run('enable', async () => {
      await api('/api/datasets/media_bias/enable', { method: 'POST', json: { enabled: on } });
      return on ? 'Media bias enrichment switched on' : 'Media bias enrichment switched off';
    });
  const importDefault = () =>
    askConfirm({
      title: 'Load the media bias list?',
      message: 'The list that ships with the site is loaded, adding new sources and updating ones already here.',
      action: 'Load list',
      onConfirm: () => void run('import', async () => (await api<{ message?: string }>('/api/datasets/media_bias/import', { method: 'POST' })).message || 'List loaded'),
    });
  const reset = () =>
    askConfirm({
      title: 'Delete all media bias data?',
      message: 'Every source in the list is deleted, including ones added or edited by hand. This can’t be undone.',
      action: 'Delete all',
      onConfirm: () => void run('reset', async () => (await api<{ message?: string }>('/api/datasets/media_bias/reset', { method: 'POST' })).message || 'Media bias data deleted'),
    });
  const uploadFile = () =>
    upload &&
    run('upload', async () => {
      const body = new FormData();
      body.append('file', upload);
      const r = await api<{ message?: string }>('/api/datasets/media_bias/upload', { method: 'POST', body });
      setUpload(null);
      return r?.message || 'File loaded';
    });
  const remove = (s: MediaBiasSource) =>
    askConfirm({
      title: `Delete ${s.source}?`,
      message: 'The source is removed from the list. Articles from it stop getting its bias and reliability ratings.',
      action: 'Delete source',
      onConfirm: () => void run(`del-${s.id}`, async () => {
        await api(`/api/datasets/media_bias/${encodeURIComponent(String(s.id))}`, { method: 'DELETE' });
        return `${s.source} deleted`;
      }),
    });
  const applySearch = () => {
    setPage(1);
    setFilters((f) => ({ ...f, query: draft }));
  };
  const setFilter = (k: keyof Filters, v: string) => {
    setPage(1);
    setFilters((f) => ({ ...f, [k]: v }));
  };

  return (
    <Grid columns="rail-main-rail" stackAt="wide" gap="md">
      <Stack gap="lg">
        <Panel
          title="Media bias"
          description={<>Bias and factual-reporting ratings for news sources, from Media Bias/Fact Check (MBFC) and AllSides, based on the <TextLink href="https://github.com/idiap/Factual-Reporting-and-Political-Bias-Web-Interactions" external>Factual Reporting and Political Bias Web Interactions</TextLink> dataset.</>}
        >
          {statusError ? <Banner tone="error" title="Status didn’t load" description={statusError} /> : !status ? <Skeleton variant="text" lines={4} /> : (
            <Stack gap="md">
              <Switch label="Enrich articles with media bias" description="New articles get their source’s bias and reliability ratings." checked={status.enabled} disabled={busy === 'enable'} onCheckedChange={(on) => void setEnabled(on)} />
              <Grid columns={2} gap="sm">
                <Stat size="compact" label="Sources" value={status.total_sources.toLocaleString()} />
                <Stat size="compact" label="Last updated" value={fmtDate(status.last_updated)} wrapValue />
              </Grid>
              <Stack direction="row" gap="sm">
                <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} busy={busy === 'import'} disabled={!!busy} onClick={importDefault}>Load the list</Button>
                <Button variant="danger" iconStart={<Icon name="Trash" size="sm" />} busy={busy === 'reset'} disabled={!!busy} onClick={reset}>Delete all</Button>
              </Stack>
            </Stack>
          )}
        </Panel>
        <Panel title="Upload a dataset" description="Load your own media bias list from a CSV file.">
          <Stack gap="md">
            <FileField label="CSV file" accept=".csv,text/csv" onFileChange={setUpload} hint="Columns as in the list that ships with the site. Sources already here are updated." />
            <div><Button iconStart={<Icon name="UploadSimple" size="sm" />} busy={busy === 'upload'} disabled={!upload || !!busy} onClick={() => void uploadFile()}>Upload and load</Button></div>
          </Stack>
        </Panel>
      </Stack>

      <Panel
        title="Media bias sources"
        description={result ? `${result.total.toLocaleString()} source${result.total === 1 ? '' : 's'} match` : undefined}
        headerAside={<Button size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setEditing('new')}>Add source</Button>}
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <TextField label="Search sources" hideLabel type="search" placeholder="Search sources, e.g. bbc.co.uk" value={draft} onChange={setDraft} onSubmit={applySearch} />
            <Button variant="secondary" onClick={applySearch}>Search</Button>
            <Select label="Bias" hideLabel options={opts(BIAS, 'Any bias')} value={filters.bias} onValueChange={(v) => setFilter('bias', v)} />
            <Select label="Factual reporting" hideLabel options={opts(FACTUAL, 'Any factual reporting')} value={filters.factual} onValueChange={(v) => setFilter('factual', v)} />
            <Select label="Country" hideLabel options={[{ value: 'any', label: 'Any country' }, ...countries.map((c) => ({ value: c, label: cap(c) }))]} value={filters.country} onValueChange={(v) => setFilter('country', v)} />
            {(filters.query || filters.bias !== 'any' || filters.factual !== 'any' || filters.country !== 'any') && (
              <Button variant="ghost" onClick={() => { setDraft(''); setPage(1); setFilters(NO_FILTERS); }}>Clear filters</Button>
            )}
          </Stack>
          {listError && <Banner tone="error" title="The list didn’t load" description={listError} />}
          {!result ? <Skeleton variant="text" lines={8} /> : (
            <Table
              caption="Media bias sources"
              hideCaption
              rows={result.sources}
              rowKey={(s) => String(s.id)}
              emptyText={status?.total_sources ? 'No source matches these filters.' : 'The list is empty. Load it or upload a file.'}
              columns={[
                { key: 'source', header: 'Source', rowHeader: true, wrap: true },
                { key: 'bias', header: 'Bias', render: (s) => (s.bias ? cap(s.bias) : '—') },
                { key: 'factual', header: 'Factual reporting', render: (s) => (s.factual_reporting ? cap(s.factual_reporting) : '—') },
                { key: 'cred', header: 'Credibility', render: (s) => (s.mbfc_credibility_rating ? cap(s.mbfc_credibility_rating) : '—') },
                { key: 'country', header: 'Country', render: (s) => (s.country ? cap(s.country) : '—') },
                {
                  key: 'actions', header: 'Actions', align: 'end',
                  render: (s) => (
                    <Stack direction="row" gap="sm" wrap={false}>
                      <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit ${s.source}`} onClick={() => setEditing(s)} />
                      <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete ${s.source}`} onClick={() => remove(s)} />
                    </Stack>
                  ),
                },
              ]}
            />
          )}
          {result && result.total_pages > 1 && <Pagination page={page} pageCount={result.total_pages} onPageChange={setPage} label="Media bias source pages" />}
        </Stack>
      </Panel>

      <SourceDialog source={editing} onClose={() => setEditing(null)} notify={notify} onSaved={refresh} />
    </Grid>
  );
}

function SourceDialog({ source, onClose, notify, onSaved }: { source: MediaBiasSource | 'new' | null; onClose: () => void; notify: (m: string) => void; onSaved: () => void }) {
  const isNew = source === 'new';
  const [f, setF] = useState<Partial<MediaBiasSource>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setF(source && source !== 'new' ? { ...source } : {});
    setError(null);
  }, [source]);
  const set = (k: keyof MediaBiasSource, v: string) => setF((x) => ({ ...x, [k]: v === 'any' ? '' : v }));
  const pick = (k: keyof MediaBiasSource, list: string[], none: string) => (
    <Select label={none} options={opts(list, 'Not set')} value={(f[k] as string) || 'any'} onValueChange={(v) => set(k, v)} fullWidth />
  );
  const save = async () => {
    if (!f.source?.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body = { ...f, source: f.source.trim() };
      delete (body as { id?: number }).id;
      if (isNew) await api('/api/datasets/media_bias/add', { method: 'POST', json: body });
      else await api(`/api/datasets/media_bias/${encodeURIComponent(String((source as MediaBiasSource).id))}`, { method: 'PUT', json: body });
      notify(isNew ? `${body.source} added` : `${body.source} saved`);
      onSaved();
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={source !== null}
      onOpenChange={(o) => !o && onClose()}
      title={isNew ? 'Add a media source' : 'Edit media source'}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!f.source?.trim() || busy} onClick={() => void save()}>{isNew ? 'Add source' : 'Save changes'}</Button>
        </>
      }
    >
      <Stack gap="md">
        <TextField label="Source address" value={f.source ?? ''} onChange={(v) => set('source', v)} placeholder="e.g. cnn.com" />
        <TextField label="Country" value={f.country ?? ''} onChange={(v) => set('country', v)} placeholder="e.g. usa" />
        <Grid columns={2} stackAt="small" gap="md">
          {pick('bias', BIAS, 'Bias')}
          {pick('factual_reporting', FACTUAL, 'Factual reporting')}
          {pick('press_freedom', PRESS, 'Press freedom')}
          {pick('popularity', POPULARITY, 'Popularity')}
          {pick('mbfc_credibility_rating', CREDIBILITY, 'MBFC credibility rating')}
        </Grid>
        <TextField label="Media type" value={f.media_type ?? ''} onChange={(v) => set('media_type', v)} placeholder="e.g. newspaper/website" />
        {error && <Banner tone="error" title="Not saved" description={error} />}
        <Text variant="caption">Changes apply to articles enriched from now on.</Text>
      </Stack>
    </Dialog>
  );
}
