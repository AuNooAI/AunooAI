import { useState } from 'react';
import { ArticleCard, Button, Chip, EmptyState, Icon, Pagination, Panel, Select, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import type { ScienceArticle, ScienceCategory } from '@monolith/scienceFundingApi';
import { TitleLink } from '../../feed/api';
import { categoryColor, fmtDate, HOW_DATA_ARRIVES, periodText, shortName } from './labels';
import type { ScienceData, SortBy } from './useScience';
import './science.css';

/*
 * Articles: the categorised articles, as the old ScienceArticleList. Filter by category, sort,
 * page, or search by meaning across the topic. A title opens the shared details panel; "Find
 * related" lists similar articles from every topic. The old list fell back to the full article
 * list when a search found nothing while saying "Found 0 results"; a search with no hits now
 * shows none.
 */

const SORTS = [
  { value: 'date', label: 'Newest first' },
  { value: 'category_count', label: 'Most categories first' },
];

export function Articles({ sci, onOpen, onRelated }: {
  sci: ScienceData;
  onOpen: (a: ScienceArticle) => void;
  onRelated: (a: ScienceArticle) => void;
}) {
  const { config, updateConfig, articles, articlesLoading, categories, search } = sci;
  const [query, setQuery] = useState(search?.query ?? '');
  const selected = config.selectedCategories;
  const toggle = (c: string) => updateConfig({ selectedCategories: selected.includes(c) ? selected.filter((x) => x !== c) : [...selected, c] });

  const searching = search !== null;
  const shown: ScienceArticle[] | null = searching ? search.results : articles?.list ?? null;

  const card = (a: ScienceArticle) => (
    <ArticleCard
      key={a.uri}
      as="li"
      variant="row"
      headingLevel={3}
      title={<TitleLink href={a.uri} onOpen={() => onOpen(a)}>{a.title}</TitleLink>}
      meta={[a.news_source, fmtDate(a.publication_date)].filter(Boolean).join(' · ')}
      summary={a.summary ?? undefined}
      tags={a.categories.length ? (
        <Stack direction="row" gap="sm">
          {a.categories.map((c) => (
            <Chip key={c} size="sm" tone="muted"><span className="science-dot" style={{ background: categoryColor(c) }} aria-hidden="true" />{shortName(c)}</Chip>
          ))}
        </Stack>
      ) : undefined}
      actions={[
        { id: 'details', label: 'Show details', icon: 'Eye' },
        { id: 'related', label: 'Find related articles', icon: 'Link' },
        { id: 'open', label: 'Open the original', icon: 'ArrowSquareOut' },
      ]}
      onAction={(id) => (id === 'details' ? onOpen(a) : id === 'related' ? onRelated(a) : window.open(a.uri, '_blank', 'noopener'))}
      actionsLabel={`Actions for “${a.title}”`}
    />
  );

  return (
    <Panel
      title="Articles"
      description={searching
        ? (search.results === null ? `Searching for “${search.query}”…` : `The ${search.results.length} closest ${search.results.length === 1 ? 'match' : 'matches'} for “${search.query}”, from any date in the topic (at most 20)`)
        : articles ? `${articles.list.length} of ${articles.total.toLocaleString()} articles from ${periodText(config.daysBack)}${selected.length ? `, in ${selected.length} picked ${selected.length === 1 ? 'category' : 'categories'}` : ''}` : undefined}
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField
            label="Search by meaning"
            hideLabel
            type="search"
            placeholder="Search by meaning, then press Enter"
            value={query}
            onChange={setQuery}
            onSubmit={(q) => (q.trim().length >= 2 ? void sci.runSearch(q) : !q.trim() && sci.clearSearch())}
            hint={query.trim().length === 1 ? 'Type at least two characters.' : undefined}
          />
          {searching && <Button variant="ghost" iconStart={<Icon name="X" size="sm" />} onClick={() => { setQuery(''); sci.clearSearch(); }}>Clear the search</Button>}
          {!searching && <Select label="Sort" hideLabel icon="Funnel" options={SORTS} value={config.sortBy === 'relevance' ? 'date' : config.sortBy} onValueChange={(v) => updateConfig({ sortBy: v as SortBy })} />}
        </Stack>

        {!searching && (categories?.length ?? 0) > 0 && (
          <Stack direction="row" gap="sm">
            {(categories as ScienceCategory[]).map((c) => (
              <Chip
                key={c.category}
                tone={selected.includes(c.category) ? 'accent' : 'neutral'}
                label={`${selected.includes(c.category) ? 'Stop filtering by' : 'Filter by'} ${c.category}`}
                onClick={() => toggle(c.category)}
              >
                <span className="science-dot" style={{ background: categoryColor(c.category) }} aria-hidden="true" />
                {`${shortName(c.category)} (${c.article_count})`}
              </Chip>
            ))}
            {selected.length > 0 && <Button variant="ghost" size="sm" onClick={() => updateConfig({ selectedCategories: [] })}>Clear the filter</Button>}
          </Stack>
        )}

        {shown === null || (!searching && articlesLoading && !articles) ? <Skeleton variant="text" lines={8} /> : shown.length === 0 ? (
          searching ? <Text>Nothing in this topic matches that search.</Text>
            : selected.length ? (
              <EmptyState icon="Funnel" title="No articles in the picked categories" action={<Button variant="secondary" onClick={() => updateConfig({ selectedCategories: [] })}>Clear the filter</Button>}>
                Try fewer categories or a longer period.
              </EmptyState>
            ) : <EmptyState icon="Newspaper" title="No categorised articles yet">{HOW_DATA_ARRIVES}</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="ScienceWatch articles">{shown.map(card)}</Stack>
        )}

        {!searching && articles && articles.pages > 1 && (
          <Pagination page={config.page} pageCount={articles.pages} onPageChange={(page) => updateConfig({ page })} label="Article pages" />
        )}
      </Stack>
    </Panel>
  );
}
