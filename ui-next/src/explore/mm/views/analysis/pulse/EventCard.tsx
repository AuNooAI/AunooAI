import { useState } from 'react';
import { ArticleCard, Button, Chip, Icon, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import { getWireArticles, type TimelineEvent, type WireArticle } from '@monolith/marketMonitorApi';
import type { VendorColours } from '../../../shared/colours';
import { VendorChip } from '../../findings/VendorChip';

/*
 * One event from the market's timeline (old WireEventCard in MarketMonitorTab.tsx). The extractor
 * names every company in the story; the tracked vendors are chips that open their page, the rest
 * are plain text, so a customer or a rival outside the registry can't pass for a tracked vendor.
 * Its articles load only when asked for.
 */

const SIGNIFICANCE_TONE: Record<string, 'error' | 'warning' | 'muted'> = { critical: 'error', high: 'error', medium: 'warning', low: 'muted' };

export function EventCard({ event: e, vendorIds, colours, onVendor }: {
  event: TimelineEvent;
  /** lower-cased display name → brand id, for the market's vendors */
  vendorIds: Map<string, number>;
  colours: VendorColours;
  onVendor: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [articles, setArticles] = useState<WireArticle[] | null>(null);
  const hasArticles = (e.article_uris?.length ?? 0) > 0;

  const toggle = () => {
    setOpen((o) => !o);
    if (!open && articles === null && e.article_uris?.length) getWireArticles(e.article_uris).then(setArticles, () => setArticles([]));
  };

  const named = Array.isArray(e.entities) ? (e.entities as unknown[]).filter((n): n is string => typeof n === 'string') : [];
  const tracked = named.filter((n) => vendorIds.has(n.toLowerCase()));
  const others = named.filter((n) => !vendorIds.has(n.toLowerCase()));
  const meta = [e.event_date, e.event_type, e.event_subtype, `${e.article_count} article${e.article_count === 1 ? '' : 's'}`, e.occurrence_count > 1 ? `seen ${e.occurrence_count} times` : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={3}
      title={e.title}
      meta={meta}
      flag={<Chip size="sm" tone={SIGNIFICANCE_TONE[e.significance] ?? 'muted'}>{e.significance}</Chip>}
      summary={e.description ?? undefined}
      tags={named.length ? (
        <Stack direction="row" gap="sm">
          {tracked.map((n) => <VendorChip key={n} id={vendorIds.get(n.toLowerCase())!} name={n} color={colours.byName(n)} onOpen={onVendor} />)}
          {others.length > 0 && <Text as="span" variant="caption">{`${tracked.length ? 'with ' : ''}${others.join(', ')}${tracked.length ? '' : ' (not tracked vendors)'}`}</Text>}
        </Stack>
      ) : undefined}
      footer={hasArticles ? (
        <Stack gap="sm">
          <div>
            <Button variant="ghost" size="sm" iconStart={<Icon name={open ? 'CaretDown' : 'CaretRight'} size="sm" />} onClick={toggle}>{open ? 'Hide articles' : 'Show articles'}</Button>
          </div>
          {open && (articles === null ? <Skeleton variant="text" lines={2} /> : articles.length === 0 ? <Text variant="caption">These articles didn’t load.</Text> : (
            <Stack as="ul" gap="sm" label={`Articles behind “${e.title}”`}>
              {articles.map((a) => (
                <li key={a.uri}>
                  <Stack gap="sm">
                    <TextLink href={a.uri} external>{a.title}</TextLink>
                    <Stack direction="row" gap="sm">
                      <Text as="span" variant="caption">{`${a.news_source ?? 'unknown source'}${a.publication_date ? ` · ${a.publication_date.slice(0, 10)}` : ''}`}</Text>
                      {a.vendors.map((v) => <VendorChip key={v.brand_id} id={v.brand_id} name={v.vendor} color={colours.byId(v.brand_id)} onOpen={onVendor} />)}
                    </Stack>
                  </Stack>
                </li>
              ))}
            </Stack>
          ))}
        </Stack>
      ) : undefined}
    />
  );
}
