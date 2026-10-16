import { useEffect, useState } from 'react';
import { ArticleCard, Banner, Dialog, Skeleton, Stack, Text } from '@aunoo/ui';
import { getRelatedArticles, type RelatedArticle } from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { TitleLink } from '../../feed/api';
import { fmtDate } from './labels';

/*
 * Articles like the one picked, from every topic (not only ScienceWatch's), found by meaning, as
 * the old related-articles modal. A title opens the shared details panel.
 */
export function RelatedDialog({ article, onClose, onOpen }: {
  article: { uri: string; title: string } | null;
  onClose: () => void;
  onOpen: (a: { uri: string; title: string }) => void;
}) {
  const [list, setList] = useState<RelatedArticle[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!article) return;
    let live = true;
    setList(null);
    setError(null);
    getRelatedArticles(article.uri).then((r) => live && setList(r), (e) => { if (live) { setError(errorText(e)); setList([]); } });
    return () => {
      live = false;
    };
  }, [article]);

  return (
    <Dialog open={article !== null} onOpenChange={(o) => !o && onClose()} size="lg" title="Related articles" description={article ? `Similar to “${article.title}”, from all topics` : undefined}>
      <Stack gap="md">
        {error && <Banner tone="error" title="Related articles didn’t load" description={error} />}
        {list === null ? <Skeleton variant="text" lines={6} /> : list.length === 0 ? !error && <Text>No similar articles found.</Text> : (
          <Stack as="ul" gap="sm" label="Related articles">
            {list.map((r) => (
              <ArticleCard
                key={r.uri}
                as="li"
                variant="row"
                headingLevel={3}
                title={<TitleLink href={r.uri} onOpen={() => { onClose(); onOpen({ uri: r.uri, title: r.title }); }}>{r.title}</TitleLink>}
                meta={[r.news_source, r.topic, fmtDate(r.publication_date), `${Math.round(r.similarity_score * 100)}% similar`].filter(Boolean).join(' · ')}
              />
            ))}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
