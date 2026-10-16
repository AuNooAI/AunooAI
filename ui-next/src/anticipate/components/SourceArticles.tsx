import { useState } from 'react';
import { Button, Panel, Stack, Text, TextLink } from '@aunoo/ui';
import { saveText } from '../lib/download';

export interface SourceArticle {
  title?: string;
  uri?: string;
  url?: string;
  source?: string;
  published_at?: string;
  credibility_score?: number;
}

const SHOWN = 10;

/** The articles a generator read, with a TXT download (what the old References dialogs offered). */
export function SourceArticles({ articles, name }: { articles: SourceArticle[] | undefined; name: string }) {
  const [all, setAll] = useState(false);
  const list = articles ?? [];
  if (!list.length) return null;
  const href = (a: SourceArticle) => a.url || (a.uri && /^https?:/.test(a.uri) ? a.uri : undefined);
  const line = (a: SourceArticle) =>
    [a.source, a.published_at && a.published_at.slice(0, 10), a.credibility_score != null && `credibility ${Math.round(a.credibility_score > 1 ? a.credibility_score : a.credibility_score * 100)}%`].filter(Boolean).join(' · ');
  return (
    <Panel
      title={`Source articles (${list.length})`}
      headerAside={
        <Button variant="ghost" size="sm" onClick={() => saveText(list.map((a, i) => `[${i + 1}] ${a.title ?? a.uri}${line(a) ? ` — ${line(a)}` : ''}${href(a) ? `\n    ${href(a)}` : ''}`).join('\n'), `references-${name}.txt`)}>
          Download TXT
        </Button>
      }
    >
      <Stack gap="sm">
        <Stack as="ul" gap="sm" label="Source articles">
          {(all ? list : list.slice(0, SHOWN)).map((a, i) => (
            <li key={`${i}-${a.uri ?? a.title}`}>
              <Stack gap="sm">
                {href(a) ? <TextLink href={href(a)!} external>{a.title || href(a)}</TextLink> : <Text as="span">{a.title || a.uri}</Text>}
                {line(a) && <Text variant="caption">{line(a)}</Text>}
              </Stack>
            </li>
          ))}
        </Stack>
        {list.length > SHOWN && <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)}>{all ? 'Show fewer' : `Show ${list.length - SHOWN} more`}</Button>}
      </Stack>
    </Panel>
  );
}
