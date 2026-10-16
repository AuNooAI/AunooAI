import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banner, Button, Checkbox, Chip, EmptyState, Grid, Icon, IconButton, Menu, MultiSelect, Pagination, Panel, SegmentedControl, Select, Skeleton, Stack, Table, Text, TextField,
} from '@aunoo/ui';
import { errorText } from '../../shell';
import { ArticleEditor } from '../database/ArticleEditor';
import {
  LOAD_CAP, bulkDelete, deleteArticle, deleteFromIndex, formatDay, isAnalyzed, isoDay, listTopics, topicArticles, topicStats, type EditorArticle,
} from '../database/api';
import type { SettingsPageProps } from '../types';
import '../database/database.css';

/*
 * Database Editor, rebuilt from templates/database_editor.html. Pick a topic and a date range, filter
 * the loaded articles, then edit an article's stored analysis or delete articles. Deleting can also
 * remove the article from the search index, as the old "Database + Vector Store" option did. The
 * topic sits in the address (?topic=) so a link opens it directly, as before.
 */

const PAGE_SIZE = 25;
const RANGES = [
  { value: '1', label: '1 day' },
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '365 days' },
  { value: 'all', label: 'All' },
];
const NO_TOPIC = '__none__';

function rangeDates(range: string) {
  const end = new Date();
  const start = range === 'all' ? new Date('2000-01-01') : new Date(Date.now() - Number(range) * 86400000);
  return { start: isoDay(start), end: isoDay(end) };
}

const topicFromUrl = () => new URLSearchParams(window.location.search).get('topic') ?? '';
function writeTopicToUrl(topic: string) {
  const url = new URL(window.location.href);
  if (topic) url.searchParams.set('topic', topic);
  else url.searchParams.delete('topic');
  window.history.replaceState({}, '', url.toString());
}

type FilterKey = 'category' | 'sentiment' | 'future_signal' | 'time_to_impact' | 'driver_type';
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'category', label: 'Categories' },
  { key: 'sentiment', label: 'Sentiment' },
  { key: 'future_signal', label: 'Future signal' },
  { key: 'time_to_impact', label: 'Time to impact' },
  { key: 'driver_type', label: 'Driver type' },
];

export function DatabaseEditor({ notify, askConfirm }: SettingsPageProps) {
  const [topics, setTopics] = useState<string[] | null>(null);
  const [topic, setTopic] = useState(topicFromUrl);
  const [stats, setStats] = useState<{ articleCount: number; latestArticle: string | null } | null>(null);
  const [range, setRange] = useState('7');
  const [dates, setDates] = useState(() => rangeDates('7'));
  const [articles, setArticles] = useState<EditorArticle[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<Record<FilterKey, string[]>>({ category: [], sentiment: [], future_signal: [], time_to_impact: [], driver_type: [] });
  const [analyzed, setAnalyzed] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listTopics().then(setTopics, (e) => {
      setTopics([]);
      setLoadError(errorText(e));
    });
  }, []);

  const load = useCallback(() => {
    if (!topic) return;
    setArticles(null);
    setLoadError(null);
    topicArticles(topic, dates.start, dates.end).then(setArticles, (e) => {
      setArticles([]);
      setLoadError(errorText(e));
    });
    topicStats(topic).then(setStats, () => setStats(null));
  }, [topic, dates]);
  useEffect(() => load(), [load]);
  useEffect(() => {
    writeTopicToUrl(topic);
    setSelected(new Set());
    setPage(1);
  }, [topic]);
  useEffect(() => setPage(1), [search, filters, analyzed, dates]);

  // Filter choices come from the loaded articles, so each lists only values that occur
  const choices = useMemo(() => {
    const out = {} as Record<FilterKey, string[]>;
    for (const f of FILTERS) out[f.key] = [...new Set((articles ?? []).map((a) => a[f.key]).filter((v): v is string => !!v))].sort();
    return out;
  }, [articles]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (articles ?? []).filter((a) => {
      if (q && !`${a.title ?? ''} ${a.summary ?? ''}`.toLowerCase().includes(q)) return false;
      for (const f of FILTERS) if (filters[f.key].length && !filters[f.key].includes(a[f.key] ?? '')) return false;
      if (analyzed.length && !analyzed.includes(isAnalyzed(a) ? 'yes' : 'no')) return false;
      return true;
    });
  }, [articles, search, filters, analyzed]);

  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const pageRows = shown.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const allOnPage = pageRows.length > 0 && pageRows.every((a) => selected.has(a.uri));
  const toggle = (uri: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(uri);
      else n.delete(uri);
      return n;
    });

  const pickRange = (r: string) => {
    setRange(r);
    setDates(rangeDates(r));
  };

  /** Deletes from the database, then optionally from the search index; says what each step did */
  const runDelete = async (uris: string[], index: boolean) => {
    setBusy(true);
    try {
      let dbCount = 0;
      if (uris.length === 1) {
        await deleteArticle(uris[0]);
        dbCount = 1;
      } else {
        dbCount = (await bulkDelete(uris)).deleted_count ?? 0;
      }
      let msg = `${dbCount} article${dbCount === 1 ? '' : 's'} deleted from the database`;
      if (index) {
        const results = await Promise.allSettled(uris.map((u) => deleteFromIndex(u)));
        const failed = results.filter((r) => r.status === 'rejected').length;
        msg += failed ? `; ${uris.length - failed} removed from the search index, ${failed} failed` : ' and the search index';
      }
      notify(msg);
      setSelected((s) => {
        const n = new Set(s);
        uris.forEach((u) => n.delete(u));
        return n;
      });
      load();
    } catch (e) {
      notify(`Not deleted: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = (uris: string[], index: boolean, what: string) =>
    askConfirm({
      title: `Delete ${what}?`,
      message: index
        ? 'The articles are removed from the database and from the search index. Their analysis and notes go with them. This can’t be undone.'
        : 'The articles are removed from the database, with their analysis and notes. Their copy in the search index stays until it is removed there. This can’t be undone.',
      action: index ? 'Delete from both' : 'Delete from the database',
      onConfirm: () => void runDelete(uris, index),
    });

  const deleteItems = (count: number) => [
    { id: 'db', label: 'From the database only', icon: 'Database' as const, tone: 'danger' as const },
    { id: 'both', label: 'From the database and the search index', icon: 'Trash' as const, tone: 'danger' as const, disabled: count === 0 },
  ];

  return (
    <Stack gap="lg">
      <Panel
        title="Database Editor"
        description="Browse a topic’s stored articles, correct their analysis by hand, or delete them."
        headerAside={topic ? <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload articles" onClick={load} /> : undefined}
      >
        <Stack gap="md">
          {!topics ? <Skeleton variant="text" lines={1} /> : (
            <Select
              label="Topic"
              value={topic || NO_TOPIC}
              onValueChange={(v) => setTopic(v === NO_TOPIC ? '' : v)}
              options={[{ value: NO_TOPIC, label: 'Pick a topic' }, ...topics.map((t) => ({ value: t, label: t }))]}
            />
          )}
          {topic && stats && (
            <Text variant="caption">
              {`${stats.articleCount.toLocaleString()} articles in this topic${stats.latestArticle ? `, the newest from ${formatDay(stats.latestArticle)}` : ''}.`}
            </Text>
          )}
        </Stack>
      </Panel>

      {loadError && <Banner tone="error" title="Something didn’t load" description={loadError} />}

      {!topic ? (
        <Panel title="Articles">
          <EmptyState icon="Database" title="Pick a topic">Choose a topic above to see its articles.</EmptyState>
        </Panel>
      ) : (
        <>
          <Panel title="Filters">
            <Stack gap="md">
              <SegmentedControl label="Period" options={RANGES} value={range} onValueChange={pickRange} />
              <Grid columns={3} stackAt="small" gap="md">
                <TextField label="From" type="date" value={dates.start} max={dates.end} onChange={(start) => { setRange(''); setDates((d) => ({ ...d, start })); }} />
                <TextField label="To" type="date" value={dates.end} min={dates.start} onChange={(end) => { setRange(''); setDates((d) => ({ ...d, end })); }} />
                <TextField label="Search titles and summaries" type="search" value={search} onChange={setSearch} />
              </Grid>
              <Grid columns={3} stackAt="small" gap="md">
                {FILTERS.map((f) => (
                  <MultiSelect
                    key={f.key}
                    label={f.label}
                    placeholder="Any"
                    options={choices[f.key].map((v) => ({ value: v, label: v }))}
                    value={filters[f.key]}
                    onValueChange={(v) => setFilters((x) => ({ ...x, [f.key]: v }))}
                  />
                ))}
                <MultiSelect
                  label="Analysis"
                  placeholder="Any"
                  options={[{ value: 'yes', label: 'Analysed' }, { value: 'no', label: 'Not analysed' }]}
                  value={analyzed}
                  onValueChange={setAnalyzed}
                />
              </Grid>
            </Stack>
          </Panel>

          <Panel
            title="Articles"
            description={articles ? `${shown.length.toLocaleString()} of ${articles.length.toLocaleString()} loaded articles match` : undefined}
            headerAside={
              <Menu
                label="Delete the selected articles"
                align="end"
                trigger={<Button variant="danger" size="sm" disabled={!selected.size || busy} iconStart={<Icon name="Trash" size="sm" />}>{`Delete selected (${selected.size})`}</Button>}
                items={deleteItems(selected.size)}
                onSelect={(id) => confirmDelete([...selected], id === 'both', `${selected.size} selected article${selected.size === 1 ? '' : 's'}`)}
              />
            }
          >
            <Stack gap="md">
              {articles && articles.length >= LOAD_CAP && (
                <Banner tone="warning" title="Only the first 1,000 articles loaded" description="The server loads at most 1,000 articles at a time. Pick a shorter period to see the rest." />
              )}
              {!articles ? <Skeleton variant="text" lines={8} /> : (
                <>
                  <Table
                    caption="Articles in this topic"
                    hideCaption
                    rows={pageRows}
                    rowKey={(a) => a.uri}
                    emptyText="No articles match these filters."
                    columns={[
                      {
                        key: 'select',
                        header: <Checkbox label="Select every article on this page" hideLabel checked={allOnPage} onCheckedChange={(on) => pageRows.forEach((a) => toggle(a.uri, on))} />,
                        render: (a) => <Checkbox label={`Select ${a.title ?? a.uri}`} hideLabel checked={selected.has(a.uri)} onCheckedChange={(on) => toggle(a.uri, on)} />,
                      },
                      { key: 'title', header: 'Title', rowHeader: true, wrap: true, render: (a) => <span className="db-title">{a.title || a.uri}</span> },
                      { key: 'publication_date', header: 'Published', render: (a) => formatDay(a.publication_date) },
                      { key: 'category', header: 'Category', wrap: true },
                      { key: 'sentiment', header: 'Sentiment' },
                      { key: 'future_signal', header: 'Future signal', wrap: true },
                      { key: 'time_to_impact', header: 'Time to impact', wrap: true },
                      { key: 'driver_type', header: 'Driver type', wrap: true },
                      { key: 'analyzed', header: 'Analysed', render: (a) => <Chip size="sm" tone={isAnalyzed(a) ? 'success' : 'muted'}>{isAnalyzed(a) ? 'Yes' : 'No'}</Chip> },
                      {
                        key: 'actions', header: 'Actions',
                        render: (a) => (
                          <Stack direction="row" gap="sm" wrap={false}>
                            <Button size="sm" variant="secondary" onClick={() => setEditing(a.uri)}>Edit</Button>
                            <Menu
                              label={`Delete ${a.title ?? 'this article'}`}
                              align="end"
                              trigger={<IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete ${a.title ?? 'this article'}`} disabled={busy} />}
                              items={deleteItems(1)}
                              onSelect={(id) => confirmDelete([a.uri], id === 'both', `“${a.title ?? a.uri}”`)}
                            />
                          </Stack>
                        ),
                      },
                    ]}
                  />
                  {pageCount > 1 && <Pagination page={page} pageCount={pageCount} onPageChange={setPage} label="Article pages" />}
                </>
              )}
            </Stack>
          </Panel>
        </>
      )}

      <ArticleEditor uri={editing} pageTopic={topic} onClose={() => setEditing(null)} onSaved={load} notify={notify} askConfirm={askConfirm} />
    </Stack>
  );
}
