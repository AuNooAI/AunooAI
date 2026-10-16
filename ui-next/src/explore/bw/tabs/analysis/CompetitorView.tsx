import { useEffect, useState } from 'react';
import { ArticleCard, Chip, Grid, Panel, Skeleton, Stack, StackedBars, Stat, Text } from '@aunoo/ui';
import { getArticles, type BWArticle, type Brand, type BWComparison } from '@monolith/brandWatcherApi';
import { cleanTitle, TitleLink } from '../../../feed/api';
import type { BwContext } from '../../context';
import { bucketCounts, short } from './shared';
import { GroupedBars } from '../../charts';

/*
 * One competitor beside the brand, as the old Brand analysis competitor view. Sentiment now comes
 * from each brand's whole period (the comparison data); the old view counted only the articles on
 * the Articles tab's current page.
 */

export function CompetitorView({ brand, competitor, comparison, ctx }: { brand: Brand; competitor: Brand; comparison: BWComparison[]; ctx: BwContext }) {
  const days = ctx.bw.config.daysBack;
  const mine = comparison.find((c) => c.brand_id === brand.id);
  const theirs = comparison.find((c) => c.brand_id === competitor.id);
  const [recent, setRecent] = useState<BWArticle[] | null>(null);

  useEffect(() => {
    let stale = false;
    setRecent(null);
    getArticles({ brand_ids: [competitor.id], days_back: days, page: 1, per_page: 5 }).then((r) => !stale && setRecent(r.articles), () => !stale && setRecent([]));
    return () => {
      stale = true;
    };
  }, [competitor.id, days]);

  const cats = new Set<string>();
  for (const c of [mine, theirs]) Object.entries(c?.category_breakdown ?? {}).forEach(([k, v]) => v > 0 && cats.add(k));
  const sorted = [...cats].sort(
    (a, b) => (mine?.category_breakdown[b] ?? 0) + (theirs?.category_breakdown[b] ?? 0) - (mine?.category_breakdown[a] ?? 0) - (theirs?.category_breakdown[a] ?? 0),
  );
  const sent = (c?: BWComparison) => bucketCounts(c?.sentiment_breakdown);

  return (
    <>
      <Grid as="ul" columns={2} stackAt="small" gap="sm" label="Articles in this period">
        <li><Stat surface="panel" label={brand.display_name} value={mine?.total_articles ?? 0} meta="articles" /></li>
        <li><Stat surface="panel" label={competitor.display_name} value={theirs?.total_articles ?? 0} meta="articles" /></li>
      </Grid>
      <Panel title="Sentiment compared" headingLevel={3}>
        <StackedBars
          title="Sentiment compared"
          series={[{ id: 'pos', label: 'Positive', color: 'positive' }, { id: 'neu', label: 'Neutral', color: 'neutral' }, { id: 'neg', label: 'Negative', color: 'negative' }]}
          rows={[brand, competitor].map((b, i) => {
            const s = sent(i === 0 ? mine : theirs);
            return { id: String(b.id), label: b.display_name, values: [s.positive, s.neutral, s.negative] };
          })}
        />
      </Panel>
      {sorted.length > 0 && (
        <Panel title="Categories compared" headingLevel={3}>
          {/* Side by side, as the old chart: stacking two brands' counts made each bar their combined total */}
          <GroupedBars
            title="Articles per category"
            groups={sorted.slice(0, 8).map((cat) => ({ id: cat, label: short(cat) }))}
            series={[
              { id: 'me', label: brand.display_name, color: brand.color || 'var(--viz-series-1)' },
              { id: 'them', label: competitor.display_name, color: competitor.color || 'var(--viz-series-2)' },
            ]}
            values={[mine, theirs].map((c) => sorted.slice(0, 8).map((cat) => c?.category_breakdown[cat] ?? 0))}
            max={Math.max(1, ...sorted.slice(0, 8).flatMap((cat) => [mine?.category_breakdown[cat] ?? 0, theirs?.category_breakdown[cat] ?? 0]))}
            format={(v) => String(Math.round(v))}
          />
        </Panel>
      )}
      <Panel title={`Latest ${competitor.display_name} articles`} headingLevel={3}>
        {!recent ? <Skeleton variant="text" lines={4} /> : recent.length === 0 ? <Text>No articles in this period.</Text> : (
          <Stack as="ul" gap="sm" label={`Latest ${competitor.display_name} articles`}>
            {recent.map((a) => (
              <ArticleCard
                key={a.uri}
                as="li"
                variant="row"
                headingLevel={4}
                meta={[a.news_source, a.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}
                title={<TitleLink href={a.uri} onOpen={() => ctx.openArticle({ uri: a.uri, title: a.title })}>{cleanTitle(a.title)}</TitleLink>}
                tags={a.categories.slice(0, 2).map((c) => <Chip key={c} size="sm" tone="neutral">{short(c)}</Chip>)}
              />
            ))}
          </Stack>
        )}
      </Panel>
    </>
  );
}
