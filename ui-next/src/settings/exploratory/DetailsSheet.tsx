import { useEffect, useState } from 'react';
import { Banner, Button, Icon, Sheet, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell';
import { removeFromSearch, similarTo, type Meta, type SearchHit } from './api';
import { token } from './query';
import './exploratory.css';

/*
 * One article's stored fields (the old page's right-hand Metadata panel), the five most similar
 * articles, and "Remove from search". Field values that make sense as a filter add that filter to
 * the query, as on the old page.
 */

const FILTERABLE = new Set(['topic', 'category', 'news_source', 'sentiment', 'driver_type']);
// Long text fields read better on their own line under the table
const LONG = new Set(['summary', 'sentiment_explanation', 'time_to_impact_explanation', 'driver_type_explanation', 'future_signal_explanation', 'category_explanation']);

function fmtDate(v: unknown) {
  const d = new Date(String(v));
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

export function DetailsSheet({ hit, onClose, onOpen, onFilter, onRemoved, askConfirm, notify }: {
  hit: SearchHit | null;
  onClose: () => void;
  /** Opens another article in this sheet (a related one) */
  onOpen: (h: SearchHit) => void;
  /** Adds a token to the query and searches again */
  onFilter: (t: string) => void;
  onRemoved: (id: string) => void;
  askConfirm: (c: Confirm) => void;
  notify: (m: string) => void;
}) {
  const [related, setRelated] = useState<SearchHit[] | null>(null);
  const [relErr, setRelErr] = useState<string | null>(null);
  const m: Meta = hit?.metadata ?? {};
  const uri = String(m.uri ?? hit?.id ?? '');

  useEffect(() => {
    if (!hit) return;
    let live = true;
    setRelated(null);
    setRelErr(null);
    similarTo(uri).then((r) => live && setRelated(r.filter((x) => x.id !== hit.id)), (e) => live && setRelErr(errorText(e)));
    return () => {
      live = false;
    };
  }, [hit, uri]);

  if (!hit) return null;
  const entries = Object.entries(m).filter(([, v]) => v !== null && v !== undefined && v !== '' && typeof v !== 'object');
  const short = entries.filter(([k]) => !LONG.has(k) && k !== 'title');
  const long = entries.filter(([k]) => LONG.has(k));

  const remove = () =>
    askConfirm({
      title: 'Remove this article from search?',
      message: 'Its embedding is deleted, so it stops appearing in Exploratory Analysis, similarity search and the article map. The article itself stays in the database and everywhere else on the site. This can’t be undone here; the article is only searchable again if it is embedded again.',
      action: 'Remove from search',
      onConfirm: () => void (async () => {
        try {
          await removeFromSearch(hit.id);
          notify('Removed from search');
          onRemoved(hit.id);
        } catch (e) {
          notify(`Not removed: ${errorText(e)}`);
        }
      })(),
    });

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      size="lg"
      title={m.title || 'Untitled'}
      description={[m.news_source, m.publication_date ? fmtDate(m.publication_date) : null, hit.score ? `match ${hit.score.toFixed(3)}` : null].filter(Boolean).join(' · ')}
      footer={
        <Stack direction="row" justify="between" gap="sm">
          <Button variant="danger" iconStart={<Icon name="Trash" size="sm" />} onClick={remove}>Remove from search</Button>
          {uri.startsWith('http') && <TextLink href={uri} external>Open the original</TextLink>}
        </Stack>
      }
    >
      <Stack gap="lg">
        <table className="xa-meta">
          <caption className="visually-hidden">Stored fields</caption>
          <tbody>
            {short.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k.replace(/_/g, ' ')}</th>
                <td>
                  {k === 'uri' || k === 'url' ? <TextLink href={String(v)} external>{String(v)}</TextLink>
                    : FILTERABLE.has(k) ? <button type="button" className="text-link xa-link" title="Add as a filter" onClick={() => onFilter(token(k, String(v)))}>{String(v)}</button>
                    : k === 'publication_date' ? fmtDate(v)
                    : String(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {long.map(([k, v]) => (
          <Stack key={k} gap="sm">
            <Text variant="label">{k.replace(/_/g, ' ')}</Text>
            <Text>{String(v)}</Text>
          </Stack>
        ))}
        <Stack gap="sm">
          <Text variant="label">Most similar articles</Text>
          {relErr ? <Banner tone="error" title="Similar articles didn’t load" description={relErr} />
            : !related ? <Skeleton variant="text" lines={4} />
            : !related.length ? <Text variant="caption">None found.</Text>
            : (
              <Stack as="ul" gap="sm" label="Most similar articles">
                {related.map((r) => (
                  <li key={r.id}>
                    <button type="button" className="text-link xa-link" onClick={() => onOpen(r)}>{r.metadata?.title || r.id}</button>
                    {r.metadata?.news_source && <Text as="span" variant="caption">{` · ${r.metadata.news_source}`}</Text>}
                  </li>
                ))}
              </Stack>
            )}
        </Stack>
      </Stack>
    </Sheet>
  );
}
