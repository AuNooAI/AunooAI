import { useEffect, useState } from 'react';
import { ArticleCard, Chip, EmptyState, Panel, Skeleton, Stack, Text, type MenuItem } from '@aunoo/ui';
import { api } from '../../shell';
import { TitleLink } from '../feed/api';
import { ShareDialog } from '../shared/ShareDialog';

/*
 * Starred articles, as the old SavedArticlesSection: the starred list is the URIs in localStorage
 * (newsFeed_starred), and each article is read from /api/article. Newest first.
 */

interface Row {
  uri: string;
  title?: string;
  summary?: string;
  news_source?: string;
  publication_date?: string;
  category?: string;
  topic?: string;
}

const fmtDate = (d?: string) => {
  if (!d) return '';
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

const ACTIONS: MenuItem[] = [
  { id: 'details', label: 'Show details', icon: 'Info' },
  { id: 'open', label: 'Open the original', icon: 'ArrowSquareOut' },
  { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
  { id: 'unstar', label: 'Remove the star', icon: 'Star', separatorBefore: true },
];

export function Articles({ starred, onUnstar, openArticle, notify }: {
  starred: string[];
  notify?: (m: string) => void;
  onUnstar: (uri: string) => void;
  openArticle: (a: { uri: string; title?: string }) => void;
}) {
  // undefined = still loading; null = the article didn't load (kept, so it can still be unstarred)
  const [rows, setRows] = useState<Record<string, Row | null>>({});
  const [sharing, setSharing] = useState<Row | null>(null);

  useEffect(() => {
    let live = true;
    const missing = starred.filter((u) => !(u in rows));
    for (const uri of missing) {
      api<Row>(`/api/article?uri=${encodeURIComponent(uri)}`).then(
        (r) => live && setRows((m) => ({ ...m, [uri]: { ...r, uri } })),
        () => live && setRows((m) => ({ ...m, [uri]: null })),
      );
    }
    return () => {
      live = false;
    };
  }, [starred]); // eslint-disable-line react-hooks/exhaustive-deps

  const loaded = starred.map((u) => rows[u]).filter((r): r is Row => !!r);
  loaded.sort((a, b) => (b.publication_date ? new Date(b.publication_date).getTime() : 0) - (a.publication_date ? new Date(a.publication_date).getTime() : 0));
  const failed = starred.filter((u) => rows[u] === null);
  const pending = starred.filter((u) => rows[u] === undefined).length;

  return (
    <Panel title="Starred articles" description={`${starred.length} saved in this browser. Star an article from its details to keep it here.`}>
      {starred.length === 0 ? (
        <EmptyState icon="Star" title="No starred articles">Star an article from its details panel on any Explore tab and it appears here.</EmptyState>
      ) : (
        <Stack gap="md">
          {loaded.length > 0 && (
            <Stack as="ul" gap="sm" label="Starred articles">
              {loaded.map((a) => (
                <ArticleCard
                  key={a.uri}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  meta={[a.news_source, fmtDate(a.publication_date), a.topic].filter(Boolean).join(' · ')}
                  flag={a.category ? <Chip size="sm" tone="muted">{a.category}</Chip> : undefined}
                  title={<TitleLink href={a.uri} onOpen={() => openArticle(a)}>{a.title || a.uri}</TitleLink>}
                  summary={a.summary}
                  actions={ACTIONS}
                  actionsLabel={`Actions for “${a.title || a.uri}”`}
                  onAction={(id) => {
                    if (id === 'details') openArticle(a);
                    else if (id === 'open') window.open(a.uri, '_blank', 'noopener');
                    else if (id === 'share') setSharing(a);
                    else if (id === 'unstar') onUnstar(a.uri);
                  }}
                />
              ))}
            </Stack>
          )}
          {pending > 0 && <Skeleton variant="text" lines={Math.min(pending, 4) * 2} />}
          {/* The old list dropped these without a word, so the count and the list disagreed */}
          {failed.length > 0 && (
            <Stack gap="sm">
              <Text variant="caption">{`${failed.length} starred article${failed.length === 1 ? '' : 's'} couldn’t be loaded. It may have been removed from the collection.`}</Text>
              <Stack as="ul" gap="sm" label="Starred articles that didn’t load">
                {failed.map((u) => (
                  <ArticleCard
                    key={u}
                    as="li"
                    variant="row"
                    headingLevel={3}
                    title={<TitleLink href={u} onOpen={() => window.open(u, '_blank', 'noopener')}>{u}</TitleLink>}
                    actions={[{ id: 'unstar', label: 'Remove the star', icon: 'Star' }]}
                    actionsLabel={`Actions for ${u}`}
                    onAction={() => onUnstar(u)}
                  />
                ))}
              </Stack>
            </Stack>
          )}
        </Stack>
      )}
      {sharing && (
        <ShareDialog
          open
          onOpenChange={(o) => !o && setSharing(null)}
          kind="article"
          title={sharing.title || sharing.uri}
          payload={{ title: sharing.title || sharing.uri, url: sharing.uri, source: sharing.news_source, summary: sharing.summary, category: sharing.category, topic: sharing.topic, publication_date: sharing.publication_date }}
          notify={notify}
        />
      )}
    </Panel>
  );
}
