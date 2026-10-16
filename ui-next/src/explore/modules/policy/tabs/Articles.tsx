import { useState } from 'react';
import { ArticleCard, Button, Chip, EmptyState, FilterChipRow, Icon, Pagination, Panel, Select, Stack, Text, TextField } from '@aunoo/ui';
import { CATEGORY_SHORT_NAMES, type PolicyArticle } from '@monolith/policyTrackerApi';
import { TitleLink } from '../../../feed/api';
import { fmtDate, type SortBy } from '../api';
import { Loading } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyArticleList: the tracker's articles, filtered by category and sorted, with a meaning
 * search across them. A title opens the article's details; the menu also finds similar articles from
 * every topic.
 *
 * Fixed from the old list: a search that found nothing went on showing the unfiltered list under
 * "Found 0 results", so it looked as if the search had matched everything.
 */
export function Articles({ pt, onOpen, onRelated }: { pt: PolicyTracker; onOpen: (a: PolicyArticle) => void; onRelated: (a: PolicyArticle) => void }) {
  const { articles, categories, config, updateConfig, totalArticles, totalPages, loadingArticles, search, runSearch, clearSearch } = pt;
  const [query, setQuery] = useState(search?.query ?? '');

  const searching = search !== null;
  const shown = searching ? search.results : articles;
  const card = (a: PolicyArticle) => (
    <ArticleCard
      key={a.uri}
      as="li"
      variant="row"
      headingLevel={4}
      title={<TitleLink href={a.uri} onOpen={() => onOpen(a)}>{a.title}</TitleLink>}
      meta={[a.news_source, fmtDate(a.publication_date)].filter(Boolean).join(' · ')}
      summary={a.summary ?? undefined}
      tags={a.categories.length ? (
        <Stack direction="row" gap="sm">{a.categories.map((c) => <Chip key={c} tone="neutral" size="sm">{CATEGORY_SHORT_NAMES[c] ?? c}</Chip>)}</Stack>
      ) : undefined}
      actions={[
        { id: 'open', label: 'Show details', icon: 'FileText' },
        { id: 'related', label: 'Find similar articles', icon: 'MagnifyingGlass' },
        { id: 'source', label: 'Open the original', icon: 'ArrowSquareOut' },
      ]}
      actionsLabel={`Actions for “${a.title}”`}
      onAction={(id) => {
        if (id === 'open') onOpen(a);
        else if (id === 'related') onRelated(a);
        else window.open(a.uri, '_blank', 'noopener');
      }}
    />
  );

  return (
    <Panel title="Articles" headingLevel={3}>
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField
            label="Search the tracker’s articles"
            hideLabel
            type="search"
            placeholder="Search by meaning, e.g. firing of inspectors general"
            value={query}
            onChange={setQuery}
            onSubmit={(v) => void runSearch(v)}
          />
          <Button variant="secondary" iconStart={<Icon name="MagnifyingGlass" size="sm" />} disabled={!query.trim()} onClick={() => void runSearch(query)}>Search</Button>
          {searching && <Button variant="ghost" onClick={() => { setQuery(''); clearSearch(); }}>Clear search</Button>}
          {!searching && (
            <Select
              label="Sort"
              hideLabel
              value={config.sortBy}
              onValueChange={(v) => updateConfig({ sortBy: v as SortBy })}
              options={[{ value: 'date', label: 'Newest first' }, { value: 'category_count', label: 'Most categories first' }]}
            />
          )}
        </Stack>

        {!searching && categories.length > 0 && (
          <FilterChipRow
            label="Category"
            allLabel="All categories"
            options={categories.map((c) => ({ value: c.category, label: CATEGORY_SHORT_NAMES[c.category] ?? c.category, count: c.article_count }))}
            selected={config.selectedCategories}
            onChange={(selectedCategories) => updateConfig({ selectedCategories })}
          />
        )}

        <Text variant="caption">
          {searching
            ? search.loading ? 'Searching…' : `${search.results.length} ${search.results.length === 1 ? 'article matches' : 'articles match'} “${search.query}”. Search ignores the category filter and the period.`
            : `${articles.length} of ${totalArticles.toLocaleString()} articles${config.selectedCategories.length ? ` in ${config.selectedCategories.length} picked ${config.selectedCategories.length === 1 ? 'category' : 'categories'}` : ''}`}
        </Text>

        {(searching ? search.loading : loadingArticles) ? <Loading /> : shown.length === 0 ? (
          <EmptyState
            icon="Newspaper"
            title={searching ? 'Nothing matched' : 'No articles'}
            action={!searching && config.selectedCategories.length ? <Button variant="secondary" onClick={() => updateConfig({ selectedCategories: [] })}>Clear the category filter</Button> : undefined}
          >
            {searching ? 'Try other words; the search looks for articles with a similar meaning.' : 'No classified articles match this period and filter.'}
          </EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Tracker articles">{shown.map(card)}</Stack>
        )}

        {!searching && totalPages > 1 && <Pagination page={config.page} pageCount={totalPages} onPageChange={(page) => updateConfig({ page })} label="Article pages" />}
      </Stack>
    </Panel>
  );
}
