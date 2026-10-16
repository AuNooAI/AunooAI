import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArticleCard, Button, Checkbox, Chip, Eyebrow, FilterChipRow, Grid, Icon, Pagination, Panel, Popover, ReorderList, SegmentedControl, Select, Skeleton, Stack, Text,
  type MenuItem, type SelectOption,
} from '@aunoo/ui';
import {
  clusterArticleToNewsArticle, getArticleFilterOptions, getArticlesList, getCategoryCounts, getClusteredArticles,
  type ArticleCluster, type ClusterRelatedArticle, type NewsArticle,
} from '@monolith/newsFeedApi';
import { errorText } from '../../shell';
import type { DateRange } from '../lib/useExploreConfig';
import { askAuspex, cleanTitle, download, setArticlePreference, TitleLink } from './api';
import { sentimentTone } from './visuals';
import type { Feed } from './useFeed';

/*
 * Latest News: the old list view (ArticleListView.tsx) on /api/news-feed/articles/list, 25 a page,
 * and the clustered view (TopicCluster.tsx) on /api/news-feed/articles/clustered. As on the old page,
 * the category, source, factuality and bias filters apply to the page that's loaded.
 */

const PER_PAGE = 25;
const FACTUALITY: [string, string][] = [['very high', 'Very high'], ['high', 'High'], ['mostly factual', 'Mostly factual'], ['mixed', 'Mixed'], ['low', 'Low']];
const BIAS: [string, string][] = [['left', 'Left'], ['left-center', 'Left-centre'], ['center', 'Centre'], ['right-center', 'Right-centre'], ['right', 'Right']];
const SORTS: SelectOption[] = [
  { value: 'date_desc', label: 'Newest first' }, { value: 'date_asc', label: 'Oldest first' }, { value: 'source', label: 'By source' }, { value: 'category', label: 'By category' },
];
const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function timeAgo(iso?: string) {
  if (!iso) return '';
  const h = (Date.now() - new Date(iso).getTime()) / 3600000;
  if (Number.isNaN(h)) return '';
  if (h < 1) return 'Just now';
  if (h < 24) return relative.format(-Math.round(h), 'hour');
  return relative.format(-Math.round(h / 24), 'day');
}

function dayLabel(iso?: string) {
  if (!iso) return 'Undated';
  const d = new Date(iso);
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'This week';
  return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
}

const lower = (s?: string) => (s ?? '').toLowerCase();
export type OpenArticle = (a: NewsArticle | string, related?: ClusterRelatedArticle[]) => void;

interface Props {
  feed: Feed;
  dateRange: DateRange;
  notify: (m: string) => void;
  onOpenArticle: OpenArticle;
  /** Bumped by Refresh */
  reloadKey: number;
}

function ArticleRow({ a, feed, read, selected, onSelect, onOpen, notify }: {
  a: NewsArticle; feed: Feed; read: boolean; selected: boolean; onSelect: (on: boolean) => void; onOpen: () => void; notify: (m: string) => void;
}) {
  const [pref, setPref] = useState(a.user_preference ?? null);
  const starred = feed.starred.includes(a.uri);
  const actions: MenuItem[] = [
    { id: 'open', label: 'Details', icon: 'Info' },
    { id: 'star', label: starred ? 'Remove star' : 'Star', icon: 'Star' },
    { id: 'more', label: pref === 'more' ? 'Clear “More like this”' : 'More like this', icon: 'ArrowUp' },
    { id: 'less', label: pref === 'less' ? 'Clear “Less like this”' : 'Less like this', icon: 'ArrowDown' },
    { id: 'copy', label: 'Copy link', icon: 'Link', separatorBefore: true },
  ];
  const onAction = async (id: string) => {
    if (id === 'open') onOpen();
    else if (id === 'star') feed.toggleStar(a.uri);
    else if (id === 'copy') {
      await navigator.clipboard?.writeText(a.url || a.uri).catch(() => undefined);
      notify('Link copied');
    } else if (id === 'more' || id === 'less') {
      const next = pref === id ? null : id;
      try {
        await setArticlePreference(a.uri, next ?? 'clear');
        setPref(next);
        notify(next ? `You’ll see ${next === 'more' ? 'more' : 'fewer'} articles like this` : 'Preference cleared');
      } catch (e) {
        notify(`Not saved: ${errorText(e)}`);
      }
    }
  };
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      read={read}
      leading={<Checkbox label={<span className="visually-hidden">Select “{a.title}”</span>} checked={selected} onCheckedChange={onSelect} />}
      meta={[a.category, a.topic].filter(Boolean).join(' · ')}
      flag={starred ? <Chip size="sm" tone="accent" icon={<Icon name="Star" size="sm" />}>Starred</Chip> : undefined}
      title={<TitleLink href={a.url || a.uri} onOpen={onOpen}>{cleanTitle(a.title)}</TitleLink>}
      summary={a.summary}
      actions={actions}
      actionsLabel={`Actions for “${a.title}”`}
      onAction={(id) => void onAction(id)}
      tags={
        <>
          {a.sentiment && <Chip size="sm" tone={sentimentTone(a.sentiment)}>{a.sentiment}</Chip>}
          {a.time_to_impact && <Chip size="sm" tone="muted">{a.time_to_impact}</Chip>}
        </>
      }
      footer={
        <>
          <span>{a.source?.name}</span>
          {a.source?.bias && <Chip size="sm" tone="muted">Bias: {a.source.bias}</Chip>}
          {a.source?.factuality && <Chip size="sm" tone="muted">Factual: {a.source.factuality}</Chip>}
          {a.publication_date && <time dateTime={a.publication_date}>{timeAgo(a.publication_date)}</time>}
        </>
      }
    />
  );
}

function ListView({ feed, dateRange, notify, onOpenArticle, reloadKey }: Props) {
  const topic = feed.topic;
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ articles: NewsArticle[]; totalCount: number; totalPages: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opts, setOpts] = useState<{ sources: string[]; factuality: string[]; bias: string[] }>({ sources: [], factuality: [], bias: [] });
  const [cats, setCats] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [fact, setFact] = useState<string[]>([]);
  const [bias, setBias] = useState<string[]>([]);
  const [unread, setUnread] = useState(false);
  const [sort, setSort] = useState('date_desc');
  const [read, setRead] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => setPage(1), [topic, dateRange]);
  useEffect(() => {
    let stale = false;
    setData(null);
    setError(null);
    getArticlesList({ dateRange, topic, page, perPage: PER_PAGE }).then(
      (r) => !stale && setData(r),
      (e: unknown) => !stale && setError(errorText(e)),
    );
    return () => {
      stale = true;
    };
  }, [topic, dateRange, page, reloadKey]);
  useEffect(() => {
    getArticleFilterOptions({ dateRange, topic }).then(
      (o) => setOpts({
        sources: o.sources.map((s) => s.name).filter(Boolean) as string[],
        factuality: o.factuality.map((f) => lower(f.level)).filter(Boolean),
        bias: o.bias.map((b) => lower(b.level)).filter(Boolean),
      }),
      () => undefined,
    );
  }, [topic, dateRange, reloadKey]);

  const articles = data?.articles ?? [];
  const categories = useMemo(() => [...new Set(articles.map((a) => a.category).filter(Boolean))].sort() as string[], [articles]);
  const shown = useMemo(() => {
    const m = (f: string[], v: string) => f.length === 0 || f.includes(v);
    const out = articles.filter(
      (a) => m(cats, a.category ?? '') && m(sources, a.source?.name ?? '') && m(fact, lower(a.source?.factuality)) && m(bias, lower(a.source?.bias)) && (!unread || !read.has(a.uri)),
    );
    const t = (a: NewsArticle) => new Date(a.publication_date || 0).getTime();
    const by: Record<string, (a: NewsArticle, b: NewsArticle) => number> = {
      date_desc: (a, b) => t(b) - t(a), date_asc: (a, b) => t(a) - t(b),
      source: (a, b) => (a.source?.name ?? '').localeCompare(b.source?.name ?? ''), category: (a, b) => (a.category ?? '').localeCompare(b.category ?? ''),
    };
    return out.sort(by[sort]);
  }, [articles, cats, sources, fact, bias, unread, read, sort]);
  const groups = useMemo(() => {
    if (sort !== 'date_desc') return [{ label: '', items: shown }];
    const out: { label: string; items: NewsArticle[] }[] = [];
    for (const a of shown) {
      const l = dayLabel(a.publication_date);
      if (out[out.length - 1]?.label === l) out[out.length - 1].items.push(a);
      else out.push({ label: l, items: [a] });
    }
    return out;
  }, [shown, sort]);

  const ids = shown.map((a) => a.uri);
  const allSelected = ids.length > 0 && ids.every((u) => selected.includes(u));
  const picked = articles.filter((a) => selected.includes(a.uri));
  const filtersOn = cats.length + sources.length + fact.length + bias.length > 0 || unread;
  const open = (a: NewsArticle) => {
    setRead((r) => new Set(r).add(a.uri));
    onOpenArticle(a);
  };

  const bulkExport = () => {
    const md = ['# Articles', '', ...picked.flatMap((a) => [`## ${a.title}`, '', `${a.source?.name ?? ''} · ${a.publication_date?.slice(0, 10) ?? ''}`, '', a.summary ?? '', '', a.url || a.uri, ''])];
    download('articles.md', md.join('\n'));
  };
  const bulkAuspex = () =>
    askAuspex(`Analyse these ${picked.length} articles together. What do they say, where do they agree or disagree, and what matters for us?\n\n${picked.map((a) => `- ${a.title} (${a.source?.name ?? ''}) ${a.url || a.uri}`).join('\n')}`, topic);

  return (
    <Stack gap="lg">
      <Stack gap="sm">
        {categories.length > 0 && <FilterChipRow label="Categories" options={categories.map((c) => ({ value: c, label: c }))} selected={cats} onChange={setCats} />}
        {opts.sources.length > 0 && <FilterChipRow label="Sources" total={opts.sources.length} options={opts.sources.map((s) => ({ value: s, label: s }))} selected={sources} onChange={setSources} maxVisible={10} />}
        {opts.factuality.length > 0 && (
          <FilterChipRow label="Factuality" options={FACTUALITY.filter(([k]) => opts.factuality.includes(k)).map(([value, label]) => ({ value, label }))} selected={fact} onChange={setFact} />
        )}
        {opts.bias.length > 0 && <FilterChipRow label="Bias" options={BIAS.filter(([k]) => opts.bias.includes(k)).map(([value, label]) => ({ value, label }))} selected={bias} onChange={setBias} />}
      </Stack>

      <Stack direction="row" justify="between" gap="sm" label="List controls">
        <Stack direction="row" gap="sm">
          <Checkbox label="Select all" checked={allSelected} onCheckedChange={(on) => setSelected((s) => (on ? [...new Set([...s, ...ids])] : s.filter((u) => !ids.includes(u))))} />
          <Checkbox label="Unread only" checked={unread} onCheckedChange={setUnread} />
          {selected.length > 0 && (
            <>
              <Text variant="label" as="span">{selected.length} selected</Text>
              <Button size="sm" variant="secondary" iconStart={<Icon name="Star" size="sm" />} onClick={() => { picked.forEach((a) => !feed.starred.includes(a.uri) && feed.toggleStar(a.uri)); notify(`${picked.length} starred`); }}>Star</Button>
              <Button size="sm" variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={bulkExport}>Download</Button>
              <Button size="sm" variant="secondary" iconStart={<Icon name="ChatCentered" size="sm" />} onClick={bulkAuspex}>Ask Auspex</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected([])}>Clear</Button>
            </>
          )}
          {filtersOn && <Button size="sm" variant="ghost" onClick={() => { setCats([]); setSources([]); setFact([]); setBias([]); setUnread(false); }}>Clear filters</Button>}
        </Stack>
        <Stack direction="row" gap="sm">
          <Select label="Sort" hideLabel options={SORTS} value={sort} onValueChange={setSort} />
          <Text variant="label" as="span"><span role="status">{shown.length} of {(data?.totalCount ?? 0).toLocaleString('en-GB')}</span></Text>
          {(data?.totalPages ?? 0) > 1 && <Pagination label="Latest news pages" page={page} pageCount={data!.totalPages} onPageChange={setPage} />}
        </Stack>
      </Stack>

      {error ? <Text tone="error">Articles didn’t load: {error}</Text> : !data ? <Skeleton variant="text" lines={6} /> : shown.length === 0 ? (
        <Text>{filtersOn ? 'No articles on this page match these filters.' : 'No articles in this date range. Try a longer range or another topic.'}</Text>
      ) : (
        groups.map((g) => (
          <Stack key={g.label || 'all'} gap="sm">
            {g.label && <Eyebrow as="h3">{g.label}</Eyebrow>}
            <Stack as="ul" gap="sm" label={g.label || 'Articles'}>
              {g.items.map((a) => (
                <ArticleRow
                  key={a.uri}
                  a={a}
                  feed={feed}
                  read={read.has(a.uri)}
                  selected={selected.includes(a.uri)}
                  onSelect={(on) => setSelected((s) => (on ? [...s, a.uri] : s.filter((u) => u !== a.uri)))}
                  onOpen={() => open(a)}
                  notify={notify}
                />
              ))}
            </Stack>
          </Stack>
        ))
      )}
    </Stack>
  );
}

// Shared with the old page, so a reader's arrangement carries over
const ORDER_KEY = 'categoryOrder';
const HIDDEN_KEY = 'hiddenCategories';
function readList(key: string): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(key) ?? '[]');
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}
function writeList(key: string, v: string[]) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    // per visit only
  }
}

/**
 * Categories in the reader's own order: those they placed come first, in that order; any others
 * follow by article count. Hidden ones are left out.
 */
function arrange(counts: Record<string, number>, order: string[], hidden: string[]) {
  const all = Object.entries(counts);
  const placed = order.filter((c) => c in counts).map((c) => [c, counts[c]] as [string, number]);
  const rest = all.filter(([c]) => !order.includes(c)).sort((a, b) => b[1] - a[1]);
  return [...placed, ...rest].filter(([c]) => !hidden.includes(c));
}

/** Drag categories into an order and choose which show, as the old section settings did */
function ArrangeCategories({ counts, order, hidden, onOrder, onHidden }: {
  counts: Record<string, number>; order: string[]; hidden: string[]; onOrder: (o: string[]) => void; onHidden: (h: string[]) => void;
}) {
  const ids = arrange(counts, order, []).map(([c]) => c);
  return (
    <Popover
      label="Arrange categories"
      title="Arrange categories"
      width="wide"
      trigger={<Button variant="ghost" size="sm" iconStart={<Icon name="SlidersHorizontal" size="sm" />}>Arrange</Button>}
      footer={<Button variant="ghost" size="sm" disabled={!order.length && !hidden.length} onClick={() => { onOrder([]); onHidden([]); }}>Back to most articles first</Button>}
    >
      <Stack gap="sm">
        <Text variant="caption">Drag a category by its handle, or focus the handle and use the arrow keys. Untick one to hide it. The first nine shown get their own panel.</Text>
        <ReorderList
          label="Categories"
          items={ids.map((c) => ({
            id: c,
            label: c,
            content: (
              <Checkbox
                label={`${c} (${counts[c]})`}
                checked={!hidden.includes(c)}
                onCheckedChange={(on) => onHidden(on ? hidden.filter((h) => h !== c) : [...hidden, c])}
              />
            ),
          }))}
          onReorder={onOrder}
        />
      </Stack>
    </Popover>
  );
}

/** The top nine categories (in the reader's order), each with its biggest stories and how many outlets carried them. */
function CategoryView({ feed, dateRange, onOpenArticle, reloadKey }: Props) {
  const topic = feed.topic;
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [clusters, setClusters] = useState<Record<string, ArticleCluster[]>>({});
  const [more, setMore] = useState<Record<string, boolean>>({});
  const [order, setOrderState] = useState<string[]>(() => readList(ORDER_KEY));
  const [hidden, setHiddenState] = useState<string[]>(() => readList(HIDDEN_KEY));
  const setOrder = (o: string[]) => { setOrderState(o); writeList(ORDER_KEY, o); };
  const setHidden = (h: string[]) => { setHiddenState(h); writeList(HIDDEN_KEY, h); };

  useEffect(() => {
    let live = true;
    setCounts(null);
    setClusters({});
    getCategoryCounts(dateRange, topic).then((c) => live && setCounts(c), () => live && setCounts({}));
    return () => {
      live = false;
    };
  }, [topic, dateRange, reloadKey]);

  const ordered = useMemo(() => (counts ? arrange(counts, order, hidden) : []), [counts, order, hidden]);
  const top = ordered.slice(0, 9).map(([c]) => c);
  const topKey = top.join('|');
  // Stories load for the nine categories on show, and again when the arrangement brings new ones in.
  // `requested` resets with each count load, so a reload fetches the stories again.
  const requested = useRef(new Set<string>());
  useEffect(() => {
    requested.current = new Set();
  }, [counts]);
  useEffect(() => {
    if (!counts) return;
    for (const category of topKey ? topKey.split('|') : []) {
      if (requested.current.has(category)) continue;
      requested.current.add(category);
      getClusteredArticles({ category, topic, dateRange, maxArticles: 100, similarityThreshold: 0.2, maxClusterSize: 5 }).then(
        (r) => setClusters((x) => ({ ...x, [category]: r.clusters })),
        () => setClusters((x) => ({ ...x, [category]: [] })),
      );
    }
  }, [counts, topKey, topic, dateRange]);

  if (!counts) return <Skeleton variant="block" size="card" />;
  if (!Object.keys(counts).length) return <Text>No articles in this date range. Try a longer range or another topic.</Text>;
  return (
    <Stack gap="lg">
      <Stack direction="row" justify="between" gap="sm">
        <Text variant="caption">{order.length || hidden.length ? `In your order${hidden.length ? `, ${hidden.length} hidden` : ''}` : 'Most articles first'}</Text>
        <ArrangeCategories counts={counts} order={order} hidden={hidden} onOrder={setOrder} onHidden={setHidden} />
      </Stack>
      {!ordered.length && <Text>Every category is hidden. Use Arrange to show some again.</Text>}
      <Grid columns={3} stackAt="wide" gap="md">
        {ordered.slice(0, 9).map(([category, count]) => {
          const list = clusters[category];
          const shown = more[category] ? list : list?.slice(0, 4);
          return (
            <Panel key={category} title={category} description={`${count} articles`} headingLevel={3}>
              {!list ? <Skeleton variant="text" lines={4} /> : list.length === 0 ? <Text variant="caption">No stories to group.</Text> : (
                <Stack gap="sm">
                  <Stack as="ul" gap="sm" label={`${category} stories`}>
                    {shown!.map((cl) => (
                      <ArticleCard
                        key={cl.primary.uri}
                        as="li"
                        variant="row"
                        headingLevel={4}
                        title={<TitleLink href={cl.primary.uri} onOpen={() => onOpenArticle(clusterArticleToNewsArticle(cl.primary), cl.related)}>{cleanTitle(cl.primary.title)}</TitleLink>}
                        footer={
                          <>
                            <span>{cl.primary.news_source}</span>
                            {cl.primary.publication_date && <time dateTime={cl.primary.publication_date}>{timeAgo(cl.primary.publication_date)}</time>}
                            {cl.related.length > 0 && <Chip size="sm" tone="info">+{cl.related.length} {cl.related.length === 1 ? 'source' : 'sources'}</Chip>}
                          </>
                        }
                      />
                    ))}
                  </Stack>
                  {list.length > 4 && <div><Button variant="ghost" size="sm" onClick={() => setMore((m) => ({ ...m, [category]: !m[category] }))}>{more[category] ? 'Show fewer' : `Show all ${list.length}`}</Button></div>}
                </Stack>
              )}
            </Panel>
          );
        })}
      </Grid>
      {ordered.length > 9 && (
        <Stack gap="sm">
          <Eyebrow as="h3">More categories</Eyebrow>
          <Stack direction="row" gap="sm">
            {ordered.slice(9).map(([c, n]) => <Chip key={c} tone="neutral">{c} ({n})</Chip>)}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}

export function LatestNews(props: Props) {
  const [view, setView] = useState('list');
  return (
    <Panel
      title="Latest news"
      headerAside={
        <SegmentedControl
          label="Layout"
          value={view}
          onValueChange={setView}
          options={[
            { value: 'list', label: 'List view', icon: 'ListBullets', iconOnly: true },
            { value: 'clusters', label: 'By category', icon: 'SquaresFour', iconOnly: true },
          ]}
        />
      }
    >
      {view === 'list' ? <ListView {...props} /> : <CategoryView {...props} />}
    </Panel>
  );
}
