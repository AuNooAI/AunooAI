import { useEffect, useState } from 'react';
import { ArticleCard, Banner, Button, Chip, EmptyState, Icon, Pagination, Panel, Select, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import { getAllArticles, type Hotspot, type LinkedArticle, type RiskLevel, type ThreatCategory } from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { TitleLink } from '../../../feed/api';
import { CATEGORIES, RISK_LABEL, RISK_ORDER, RISK_TONE, cap, fmtDate } from '../labels';

/*
 * Articles linked to hotspots, as the old Articles tab, filtered by hotspot, risk level, category or
 * search. A click elsewhere on the page arrives as `initial`.
 *
 * The old tab never sent the page or the sort order to the server, so "Next page" and every sort
 * option showed the same first 20 articles; both are sent now. Clicking an article there only logged
 * it to the browser console; it now opens the article's details.
 */

export interface ArticleFilter {
  hotspot?: Hotspot;
  risk?: RiskLevel;
  category?: ThreatCategory;
}

type Sort = 'date-desc' | 'date-asc' | 'intensity-desc' | 'relevance-desc' | 'title-asc';
const SORTS: { value: Sort; label: string }[] = [
  { value: 'date-desc', label: 'Newest first' },
  { value: 'date-asc', label: 'Oldest first' },
  { value: 'intensity-desc', label: 'Highest intensity' },
  { value: 'relevance-desc', label: 'Most relevant' },
  { value: 'title-asc', label: 'Title, A to Z' },
];
const PAGE_SIZE = 20;
const ALL = 'all';

export function Articles({ initial, onOpen }: {
  initial: ArticleFilter;
  onOpen: (a: { uri: string; title?: string | null; summary?: string | null; publication_date?: string | null }) => void;
}) {
  const [hotspot, setHotspot] = useState<Hotspot | undefined>(initial.hotspot);
  const [risk, setRisk] = useState<RiskLevel | undefined>(initial.risk);
  const [category, setCategory] = useState<ThreatCategory | undefined>(initial.category);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<Sort>('date-desc');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ rows: LinkedArticle[]; total: number; pages: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Search waits for a pause in typing
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    const [sortBy, sortOrder] = sort.split('-') as ['date' | 'title' | 'relevance' | 'intensity', 'asc' | 'desc'];
    getAllArticles({ page, pageSize: PAGE_SIZE, riskLevel: risk, category, hotspotId: hotspot?.id, search: search || undefined, sortBy, sortOrder }).then(
      (r) => live && setData({ rows: r.data ?? [], total: r.total ?? 0, pages: r.total_pages ?? 0 }),
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [page, risk, category, hotspot, search, sort]);

  const filtered = Boolean(hotspot || risk || category || search);
  const clearAll = () => {
    setHotspot(undefined);
    setRisk(undefined);
    setCategory(undefined);
    setSearchInput('');
    setSearch('');
    setPage(1);
  };

  return (
    <Panel
      title="Articles linked to hotspots"
      description={data ? `${data.total.toLocaleString()} article${data.total === 1 ? '' : 's'}${filtered ? ' match these filters' : ''}` : undefined}
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField label="Search articles" hideLabel type="search" placeholder="Search titles and summaries" value={searchInput} onChange={setSearchInput} />
          <Select
            label="Risk level"
            hideLabel
            icon="Warning"
            options={[{ value: ALL, label: 'Any risk level' }, ...RISK_ORDER.map((r) => ({ value: r, label: `${RISK_LABEL[r]} risk` }))]}
            value={risk ?? ALL}
            onValueChange={(v) => { setRisk(v === ALL ? undefined : (v as RiskLevel)); setPage(1); }}
          />
          <Select
            label="Category"
            hideLabel
            icon="Tag"
            options={[{ value: ALL, label: 'Any category' }, ...CATEGORIES.map((c) => ({ value: c, label: cap(c) }))]}
            value={category ?? ALL}
            onValueChange={(v) => { setCategory(v === ALL ? undefined : (v as ThreatCategory)); setPage(1); }}
          />
          <Select label="Sort" hideLabel icon="ListBullets" options={SORTS} value={sort} onValueChange={(v) => { setSort(v as Sort); setPage(1); }} />
        </Stack>
        {(hotspot || filtered) && (
          <Stack direction="row" gap="sm">
            {hotspot && (
              <Chip tone="accent" icon={<Icon name="X" size="sm" />} label={`Stop filtering by ${hotspot.location_name}`} onClick={() => { setHotspot(undefined); setPage(1); }}>
                {`Hotspot: ${hotspot.location_name}${hotspot.country_name && hotspot.country_name !== hotspot.location_name ? `, ${hotspot.country_name}` : ''} (${RISK_LABEL[hotspot.risk_level]} risk)`}
              </Chip>
            )}
            {filtered && <Button variant="ghost" size="sm" onClick={clearAll}>Clear all filters</Button>}
          </Stack>
        )}

        {error && <Banner tone="error" title="Articles didn’t load" description={error} />}
        {!data && !error && <Skeleton variant="text" lines={8} />}
        {data && data.rows.length === 0 && (
          <EmptyState icon="Newspaper" title="No articles found" action={filtered ? <Button variant="secondary" onClick={clearAll}>Clear all filters</Button> : undefined}>
            {filtered ? 'Try fewer filters.' : 'Articles appear here once “Update hotspots” has read them for places and linked them to hotspots.'}
          </EmptyState>
        )}
        {data && data.rows.length > 0 && (
          <Stack as="ul" gap="sm" label="Articles">
            {data.rows.map((a) => {
              const places = a.hotspots?.length ? a.hotspots : [{ id: a.hotspot_id, name: a.hotspot_name, risk_level: a.risk_level, category: a.hotspot_category, intensity: a.intensity_score }];
              return (
                <ArticleCard
                  key={a.uri}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  meta={[a.source, fmtDate(a.publication_date), a.category ? cap(a.category) : null, a.mention_type ? `${a.mention_type} mention` : null].filter(Boolean).join(' · ')}
                  title={<TitleLink href={a.uri} onOpen={() => onOpen(a)}>{a.title || 'Untitled article'}</TitleLink>}
                  summary={a.summary ?? undefined}
                  tags={
                    <Stack direction="row" gap="sm">
                      {places.slice(0, 4).map((p, i) => (
                        <Chip key={`${p.id}-${i}`} size="sm" tone={RISK_TONE[p.risk_level || 'info']}>{`${p.name} · ${RISK_LABEL[p.risk_level || 'info']}`}</Chip>
                      ))}
                      {places.length > 4 && <Text as="span" variant="caption">{`and ${places.length - 4} more places`}</Text>}
                    </Stack>
                  }
                  actions={[
                    { id: 'details', label: 'Show details', icon: 'Info' },
                    { id: 'open', label: 'Open the original', icon: 'ArrowSquareOut' },
                  ]}
                  actionsLabel={`Actions for “${a.title || a.uri}”`}
                  onAction={(id) => (id === 'details' ? onOpen(a) : window.open(a.uri, '_blank', 'noopener'))}
                />
              );
            })}
          </Stack>
        )}
        {data && data.pages > 1 && (
          <Stack gap="sm">
            <Pagination page={page} pageCount={data.pages} onPageChange={setPage} label="Article pages" />
            <Text variant="caption">{`Showing ${(page - 1) * PAGE_SIZE + 1} to ${Math.min(page * PAGE_SIZE, data.total)} of ${data.total.toLocaleString()}`}</Text>
          </Stack>
        )}
      </Stack>
    </Panel>
  );
}
