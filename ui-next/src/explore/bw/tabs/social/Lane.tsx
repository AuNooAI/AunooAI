import { useMemo, useState } from 'react';
import { Button, FilterChipRow, Panel, Select, Stack, Text, TextField, type SelectOption } from '@aunoo/ui';
import type { BWSocialPost } from '@monolith/brandWatcherApi';
import { SOCIAL_NEG_THEMES } from '@monolith/socialAnalytics';
import { PostCard, type PostActions } from './PostCard';
import { brandOf, handleOf, platLabel, sentOf } from './helpers';

export interface LaneFilter {
  platforms: string[];
  sentiments: string[];
  /** '' | 'brand::<Name>' | 'kw::<keyword>' */
  entity: string;
  search: string;
  sort: 'recent' | 'oldest' | 'relevance';
}
export const EMPTY_LANE: LaneFilter = { platforms: [], sentiments: [], entity: '', search: '', sort: 'recent' };

/** Filters set from the charts above the lanes; they apply to both lanes. */
export interface PageFilters {
  author: { platform: string; author: string } | null;
  day: string | null;
  theme: string | null;
  brand: string | null;
}

const themeBlob = (p: BWSocialPost) => `${p.title || ''} ${p.summary || ''}`;

export function applyFilters(posts: BWSocialPost[], f: LaneFilter, g: PageFilters) {
  const q = f.search.trim().toLowerCase();
  const entBrand = f.entity.startsWith('brand::') ? f.entity.slice(7) : null;
  const entKw = f.entity.startsWith('kw::') ? f.entity.slice(4).toLowerCase() : null;
  const out = posts.filter((p) => {
    if (g.author && (p.platform !== g.author.platform || (handleOf(p) || '').toLowerCase() !== g.author.author.toLowerCase())) return false;
    if (g.day && (p.publication_date || '').slice(0, 10) !== g.day) return false;
    if (g.brand && brandOf(p) !== g.brand) return false;
    if (g.theme) {
      if (sentOf(p.sentiment) !== 'negative') return false;
      const th = SOCIAL_NEG_THEMES.find((t) => t.key === g.theme);
      if (th ? !th.re.test(themeBlob(p)) : SOCIAL_NEG_THEMES.some((t) => t.re.test(themeBlob(p)))) return false;
    }
    if (f.platforms.length && !f.platforms.includes(p.platform)) return false;
    if (f.sentiments.length && !f.sentiments.includes(sentOf(p.sentiment))) return false;
    if (entBrand && brandOf(p) !== entBrand) return false;
    if (entKw && !(p.matched_keywords ?? []).some((k) => k.toLowerCase() === entKw)) return false;
    if (q && !`${p.title || ''} ${p.summary || ''} ${p.social_meta?.author || ''}`.toLowerCase().includes(q)) return false;
    return true;
  });
  return out.sort((a, b) => {
    if (f.sort === 'relevance') return (b.relevance ?? -1) - (a.relevance ?? -1);
    const da = a.publication_date || '';
    const db = b.publication_date || '';
    return f.sort === 'oldest' ? da.localeCompare(db) : db.localeCompare(da);
  });
}

const SENTS = [
  { value: 'positive', label: 'Positive' }, { value: 'neutral', label: 'Neutral' }, { value: 'negative', label: 'Negative' }, { value: 'unrated', label: 'Not scored' },
];
const SORTS: SelectOption[] = [{ value: 'recent', label: 'Newest' }, { value: 'oldest', label: 'Oldest' }, { value: 'relevance', label: 'Most relevant' }];
const PAGE = 30;

interface Props {
  name: string;
  posts: BWSocialPost[];
  platforms: string[];
  entities: { name: string; count: number; isPrimary: boolean; keywords: [string, number][] }[];
  filter: LaneFilter;
  onChange: (f: LaneFilter) => void;
  page: PageFilters;
  actions: PostActions;
  multiBrand: boolean;
}

/** One column of posts with its own network, sentiment, search, entity and sort, so two networks compare side by side. */
export function Lane({ name, posts, platforms, entities, filter, onChange, page, actions, multiBrand }: Props) {
  const [shown, setShown] = useState(PAGE);
  const items = useMemo(() => applyFilters(posts, filter, page), [posts, filter, page]);
  const sel = filter.platforms;
  const title = sel.length === 0 ? 'All networks' : sel.length === 1 ? platLabel(sel[0]) : `${sel.length} networks`;
  const entityOptions: SelectOption[] = [
    { value: 'all', label: 'All brands and keywords' },
    ...entities.flatMap((g) => [
      { value: `brand::${g.name}`, label: `All ${g.name} posts (${g.count})`, description: g.isPrimary ? 'Primary brand' : undefined },
      ...g.keywords.map(([k, n]) => ({ value: `kw::${k}`, label: `#${k} (${n})`, description: g.name })),
    ]),
  ];
  const set = (patch: Partial<LaneFilter>) => {
    setShown(PAGE);
    onChange({ ...filter, ...patch });
  };
  return (
    <Panel title={title} description={`${items.length}${items.length !== posts.length ? ` of ${posts.length}` : ''} posts`} headingLevel={3}>
      <Stack gap="md">
        <Stack gap="sm">
          <FilterChipRow label={`${name}: network`} options={platforms.map((p) => ({ value: p, label: platLabel(p) }))} selected={sel} onChange={(platforms) => set({ platforms })} />
          <FilterChipRow label={`${name}: sentiment`} options={SENTS} selected={filter.sentiments} onChange={(sentiments) => set({ sentiments })} />
        </Stack>
        <Stack direction="row" gap="sm">
          <TextField label={`Search ${name.toLowerCase()}`} hideLabel placeholder="Search posts" value={filter.search} onChange={(search) => set({ search })} />
          {entities.length > 0 && (
            <Select label={`${name}: brand or keyword`} hideLabel options={entityOptions} value={filter.entity || 'all'} onValueChange={(v) => set({ entity: v === 'all' ? '' : v })} />
          )}
          <Select label={`${name}: sort`} hideLabel options={SORTS} value={filter.sort} onValueChange={(v) => set({ sort: v as LaneFilter['sort'] })} />
        </Stack>
        {posts.length === 0 ? (
          <Text>No social posts yet. Add social monitoring for this brand and wait for a collection run.</Text>
        ) : items.length === 0 ? (
          <Text>No posts match this column’s filters.</Text>
        ) : (
          <>
            <Stack as="ul" gap="sm" label={`${name} posts`}>
              {items.slice(0, shown).map((p) => <PostCard key={p.uri} p={p} actions={actions} showBrand={multiBrand} />)}
            </Stack>
            {items.length > shown && <div><Button variant="ghost" size="sm" onClick={() => setShown((n) => n + PAGE)}>Show {Math.min(PAGE, items.length - shown)} more</Button></div>}
          </>
        )}
      </Stack>
    </Panel>
  );
}
