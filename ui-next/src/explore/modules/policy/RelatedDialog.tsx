import { useEffect, useState } from 'react';
import { ArticleCard, Dialog, Skeleton, Stack, Text } from '@aunoo/ui';
import type { RelatedArticle } from '@monolith/policyTrackerApi';
import { errorText } from '../../../shell';
import { TitleLink } from '../../feed/api';
import { fmtDate } from './api';

/** Articles from every topic whose meaning is close to the picked one, as the old related-articles modal */
export function RelatedDialog({ source, load, onClose, onOpen }: {
  source: { uri: string; title: string } | null;
  load: (uri: string) => Promise<RelatedArticle[]>;
  onClose: () => void;
  onOpen: (a: { uri: string; title?: string }) => void;
}) {
  const [rows, setRows] = useState<RelatedArticle[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!source) return;
    let live = true;
    setRows(null);
    setError(null);
    load(source.uri).then((r) => live && setRows(r), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [source, load]);

  return (
    <Dialog open={source !== null} onOpenChange={(o) => !o && onClose()} size="lg" title="Similar articles" description={source ? `Articles from every topic that read most like “${source.title}”.` : undefined}>
      {error ? <Text tone="error">{`They didn’t load: ${error}`}</Text> : !rows ? <Skeleton variant="text" lines={6} /> : rows.length === 0 ? (
        <Text>No similar articles found.</Text>
      ) : (
        <Stack as="ul" gap="sm" label="Similar articles">
          {rows.map((r) => (
            <ArticleCard
              key={r.uri}
              as="li"
              variant="row"
              headingLevel={4}
              title={<TitleLink href={r.uri} onOpen={() => { onClose(); onOpen({ uri: r.uri, title: r.title }); }}>{r.title}</TitleLink>}
              meta={[r.news_source, r.topic, fmtDate(r.publication_date), `${Math.round(r.similarity_score * 100)}% similar`].filter(Boolean).join(' · ')}
            />
          ))}
        </Stack>
      )}
    </Dialog>
  );
}
