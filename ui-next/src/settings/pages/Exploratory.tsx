import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Grid, Icon, IconButton, Panel, SegmentedControl, Select, Skeleton, Stack, TabPanel, Tabs, Text, TextField } from '@aunoo/ui';
import { errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import {
  deleteSaved, facetsAndTimeline, keywordSearch, listSaved, scopeParams, summarise, vectorSearch,
  type Anomaly, type ProjectionPoint, type SavedSearch, type SearchHit, type SearchResult,
} from '../exploratory/api';
import { DetailsSheet } from '../exploratory/DetailsSheet';
import { Facets } from '../exploratory/Facets';
import { MapView } from '../exploratory/MapView';
import { PatternsView } from '../exploratory/PatternsView';
import { QueryHelp } from '../exploratory/QueryHelp';
import { PAGE, ResultsList } from '../exploratory/ResultsList';
import { SaveSearchDialog } from '../exploratory/SaveSearchDialog';
import { SummaryDialog, type SummaryState } from '../exploratory/SummaryDialog';
import { TimelineChart } from '../exploratory/TimelineChart';
import {
  keywordOf, metaOf, replaceToken, SORT_OPTIONS, SORT_RE, datesForServer, splitDateFilters, TIME_OPTIONS, TIME_RE, timeToken, toggleToken,
} from '../exploratory/query';

/*
 * Exploratory Analysis (the old templates/vector_analysis_improved.html): search the collected
 * articles by meaning, narrow the search with filters, and look at what the results are made of:
 * the facets, a timeline, the common words, the clusters, the outliers and a map of the articles.
 * Searching, patterns and the map read data and run no AI. The AI summary of a selection or a
 * cluster is a button that asks first. "Remove from search" deletes an article's embedding and
 * asks first.
 */

type Tab = 'results' | 'timeline' | 'patterns' | 'map';

interface Ran {
  query: string;
  result: SearchResult;
  /** The query string the patterns and the map use, so they cover the same articles */
  scope: URLSearchParams;
  dateLabel: string | null;
  keyword: boolean;
}

export function Exploratory({ notify, askConfirm }: SettingsPageProps) {
  const [input, setInput] = useState('');
  const [ran, setRan] = useState<Ran | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('results');
  const [shown, setShown] = useState(PAGE);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compact, setCompact] = useState(false);
  const [sheet, setSheet] = useState<SearchHit | null>(null);
  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<SavedSearch[] | null>(null);
  const [savedId, setSavedId] = useState('none');
  const [timeSel, setTimeSel] = useState('any');
  const [sortSel, setSortSel] = useState('relevance');

  useEffect(() => {
    listSaved().then(setSaved, () => setSaved([]));
  }, []);

  const run = async (override?: string) => {
    const q = (override ?? input).trim();
    if (!q) return;
    if (override !== undefined) setInput(override);
    setBusy(true);
    setError(null);
    try {
      const meta = metaOf(q);
      // As on the old page: no cap by default, limit:n caps it, and a cluster filter fetches more so the cluster is represented
      const topK = meta.limit !== undefined ? (meta.limit === 0 ? 10000 : meta.limit) : meta.cluster !== undefined ? 1000 : 10000;
      const dates = splitDateFilters(q);
      const kw = keywordOf(dates.rest);
      if (!kw && !dates.rest.replace(/\b(sort|limit|cluster)[:=]\S+/gi, '').trim()) {
        setError('Add some words to search for as well as the date filter, for example: AI publication_date>=last_week');
        return;
      }
      let result;
      let scope: URLSearchParams;
      let dateLabel: string | null;
      if (kw) {
        // The keyword route takes no filters, so dates are applied here
        result = await keywordSearch(kw, topK);
        if (dates.test) {
          const results = result.results.filter((h) => dates.test!(h.metadata?.publication_date));
          result = { results, ...facetsAndTimeline(results), comparison: null };
        }
        scope = scopeParams(dates.rest, topK, meta.cluster);
        dateLabel = dates.label && `${dates.label} (applied in the browser, because keyword search takes no filters)`;
      } else {
        // The server filters by date itself, so Patterns and the map follow the same dates
        const server = datesForServer(q);
        scope = scopeParams(server.query, topK, meta.cluster);
        result = await vectorSearch(scope);
        dateLabel = server.label;
      }
      setRan({ query: q, result, scope, dateLabel, keyword: !!kw });
      setShown(PAGE);
      setSelected(new Set());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const addToQuery = (t: string, toggle = false) => {
    const next = toggle ? toggleToken(input, t) : `${input} ${t}`.trim();
    setInput(next);
    if (ran) void run(next);
  };

  const askSummary = (ids: string[], title: string) => {
    const pool = ran?.result.results ?? [];
    const list = ids.slice(0, 100);
    askConfirm({
      title: `Summarise ${list.length} article${list.length === 1 ? '' : 's'} with AI?`,
      message: `One call to the site’s default AI model reads the titles and summaries${ids.length > 100 ? ` of the first 100 of these ${ids.length} articles` : ''} and writes a summary. It costs one model call and isn’t saved.`,
      action: 'Summarise',
      onConfirm: () => {
        const articles = list.map((id) => {
          const h = pool.find((x) => x.id === id);
          return { title: h?.metadata?.title || id, uri: String(h?.metadata?.uri ?? id) };
        });
        setSummary({ title, text: null, articles });
        summarise(list).then(
          (text) => setSummary((s) => (s ? { ...s, text } : s)),
          (e) => setSummary((s) => (s ? { ...s, text: '', error: `The summary failed: ${errorText(e)}` } : s)),
        );
      },
    });
  };

  const removeSaved = () => {
    const s = saved?.find((x) => x.id === savedId);
    if (!s) return;
    askConfirm({
      title: `Delete the saved search “${s.name}”?`,
      message: 'It is removed for everyone on this site. Articles aren’t affected.',
      action: 'Delete',
      onConfirm: () => {
        deleteSaved(s.id).then(
          () => {
            setSaved((l) => (l ?? []).filter((x) => x.id !== s.id));
            setSavedId('none');
            notify('Saved search deleted');
          },
          (e) => notify(`Not deleted: ${errorText(e)}`),
        );
      },
    });
  };

  const openPoint = (p: ProjectionPoint) =>
    setSheet(ran?.result.results.find((h) => h.id === p.id) ?? { id: p.id, score: 0, metadata: { title: p.title ?? undefined, category: p.category ?? undefined, sentiment: p.sentiment ?? undefined, uri: p.id } });
  const openAnomaly = (a: Anomaly) => setSheet({ id: a.id, score: 0, metadata: a.metadata ?? { uri: a.id } });

  const hits = ran?.result.results ?? [];
  const selectedIds = useMemo(() => hits.filter((h) => selected.has(h.id)).map((h) => h.id), [hits, selected]);
  const savedSel = saved?.find((x) => x.id === savedId);

  return (
    <Stack gap="lg">
      <Panel
        title="Exploratory Analysis"
        description="Search the collected articles by meaning, narrow the search with filters, and see what the results are made of."
        headerAside={
          <Stack direction="row" gap="sm">
            <Select
              label="Saved searches"
              hideLabel
              icon="BookmarkSimple"
              options={[{ value: 'none', label: saved?.length ? 'Saved searches' : 'No saved searches' }, ...(saved ?? []).map((s) => ({ value: s.id, label: s.name, description: s.description || undefined }))]}
              value={savedId}
              onValueChange={(id) => {
                setSavedId(id);
                const s = saved?.find((x) => x.id === id);
                if (s) void run(s.query);
              }}
            />
            {savedSel && <IconButton icon={<Icon name="Trash" size="sm" />} tone="danger" label={`Delete the saved search “${savedSel.name}”`} onClick={removeSaved} />}
          </Stack>
        }
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <TextField
              label="Search"
              hideLabel
              type="search"
              placeholder="Search news articles, e.g. AI AND sentiment=Positive"
              value={input}
              onChange={setInput}
              onSubmit={() => void run()}
            />
            <Button iconStart={<Icon name="MagnifyingGlass" size="sm" />} busy={busy} disabled={!input.trim() || busy} onClick={() => void run()}>Search</Button>
            <IconButton icon={<Icon name="BookmarkSimple" size="sm" />} label="Save this search" disabled={!input.trim()} onClick={() => setSaving(true)} />
            <Button
              variant="secondary"
              iconStart={<Icon name="Sparkle" size="sm" />}
              disabled={!hits.length}
              onClick={() => askSummary(selectedIds.length ? selectedIds : hits.map((h) => h.id), selectedIds.length ? `Summary of ${selectedIds.length} selected articles` : `Summary of “${ran?.query ?? ''}”`)}
            >
              {selectedIds.length ? `Summarise ${selectedIds.length} selected` : 'Summarise with AI'}
            </Button>
          </Stack>
          <Stack direction="row" gap="sm">
            <Select
              label="Time"
              hideLabel
              icon="CalendarBlank"
              options={TIME_OPTIONS}
              value={timeSel}
              onValueChange={(v) => {
                setTimeSel(v);
                const next = replaceToken(input, TIME_RE, v === 'any' ? null : timeToken(v));
                setInput(next);
                if (ran) void run(next);
              }}
            />
            <Select
              label="Sort"
              hideLabel
              icon="ListBullets"
              options={SORT_OPTIONS}
              value={sortSel}
              onValueChange={(v) => {
                setSortSel(v);
                const next = replaceToken(input, SORT_RE, v === 'relevance' ? null : `sort:${v}`);
                setInput(next);
                if (ran) void run(next);
              }}
            />
            {input && <Button variant="ghost" size="sm" iconStart={<Icon name="X" size="sm" />} onClick={() => { setInput(''); setTimeSel('any'); setSortSel('relevance'); }}>Clear the query</Button>}
          </Stack>
          <QueryHelp onAdd={(t) => addToQuery(t)} />
          {error && <Banner tone="error" title="The search didn’t run" description={error} />}
        </Stack>
      </Panel>

      {busy && !ran && <Skeleton variant="block" size="card" />}
      {ran && (
        <Grid columns="main-aside" gap="md">
          <Panel
            title={`${hits.length.toLocaleString()} result${hits.length === 1 ? '' : 's'}`}
            description={[
              ran.keyword ? 'Plain text search on title, summary and tags' : 'Search by meaning',
              ran.dateLabel,
            ].filter(Boolean).join(' · ')}
          >
            <Tabs
              label="Result views"
              value={tab}
              onValueChange={(v) => setTab(v as Tab)}
              items={[
                { value: 'results', label: 'Results', count: hits.length },
                { value: 'timeline', label: 'Timeline' },
                { value: 'patterns', label: 'Patterns' },
                { value: 'map', label: 'Map of articles' },
              ]}
            >
              <TabPanel value="results">
                {tab === 'results' && (
                  <Stack gap="md">
                    <Stack direction="row" justify="between" gap="sm">
                      <Stack direction="row" gap="sm">
                        <Button variant="ghost" size="sm" disabled={!hits.length} onClick={() => setSelected(selected.size === hits.length ? new Set() : new Set(hits.map((h) => h.id)))}>
                          {selected.size === hits.length && hits.length ? 'Clear the selection' : 'Select all'}
                        </Button>
                        <Text as="span" variant="caption">{`${selectedIds.length} of ${hits.length} selected`}</Text>
                      </Stack>
                      <SegmentedControl label="Layout" options={[{ value: 'card', label: 'Cards' }, { value: 'row', label: 'Compact' }]} value={compact ? 'row' : 'card'} onValueChange={(v) => setCompact(v === 'row')} />
                    </Stack>
                    <ResultsList
                      hits={hits}
                      shown={shown}
                      onMore={() => setShown((n) => n + PAGE)}
                      selected={selected}
                      onToggle={(id, on) => setSelected((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; })}
                      onOpen={setSheet}
                      onFilter={(field, value) => addToQuery(`${field}="${value}"`, true)}
                      compact={compact}
                    />
                  </Stack>
                )}
              </TabPanel>
              <TabPanel value="timeline">{tab === 'timeline' && <TimelineChart timeline={ran.result.timeline ?? {}} />}</TabPanel>
              <TabPanel value="patterns">
                {tab === 'patterns' && (
                  <Stack gap="sm">
                    {ran.dateLabel && ran.keyword && <Text variant="caption">Patterns cover the search before the date filter.</Text>}
                    <PatternsView scope={ran.scope} onKeepCluster={(id) => addToQuery(`cluster=${id}`)} onSummarise={(ids, title) => askSummary(ids, title)} onOpen={openAnomaly} />
                  </Stack>
                )}
              </TabPanel>
              <TabPanel value="map">
                {tab === 'map' && (
                  <Stack gap="sm">
                    {ran.dateLabel && ran.keyword && <Text variant="caption">The map covers the search before the date filter.</Text>}
                    <MapView scope={ran.scope} onSelect={openPoint} />
                  </Stack>
                )}
              </TabPanel>
            </Tabs>
          </Panel>
          <Panel title="Facets" description="Click a value to filter by it; click it again to remove the filter.">
            <Facets facets={ran.result.facets ?? {}} comparison={ran.result.comparison} query={input} onToggle={(t) => addToQuery(t, true)} />
          </Panel>
        </Grid>
      )}

      <DetailsSheet
        hit={sheet}
        onClose={() => setSheet(null)}
        onOpen={setSheet}
        onFilter={(t) => { setSheet(null); addToQuery(t); }}
        onRemoved={(id) => {
          setSheet(null);
          setRan((r) => (r ? { ...r, result: { ...r.result, results: r.result.results.filter((h) => h.id !== id) } } : r));
        }}
        askConfirm={askConfirm}
        notify={notify}
      />
      <SummaryDialog state={summary} onClose={() => setSummary(null)} />
      <SaveSearchDialog
        open={saving}
        query={input}
        onOpenChange={setSaving}
        onSaved={(s) => {
          setSaved((l) => [...(l ?? []).filter((x) => x.id !== s.id), s]);
          setSavedId(s.id);
          notify(`Saved “${s.name}”`);
        }}
      />
    </Stack>
  );
}
