import { useState } from 'react';
import { ArticleCard, Button, Chip, Stack, Text, TextLink } from '@aunoo/ui';
import type { CorpusArticle } from '@monolith/marketMonitorApi';
import type { VendorColours } from '../../shared/colours';
import { VendorSwatch } from '../../shared/colours';
import { RemoteImage } from '../../shared/RemoteImage';
import '../../shared/mm.css';
import { CLASS_LABEL, CLASS_TONE, engagementOf, VERDICT_LABEL, type CoverageGroup } from './labels';

/** One matched article. Every grouping uses it, so a card looks the same in a vendor, day or kind section */
export function CoverageCard({ article: a, vendorFilter, onVendorFilter, colours }: {
  article: CorpusArticle;
  vendorFilter: number | null;
  onVendorFilter: (id: number | null) => void;
  colours: VendorColours;
}) {
  const sm = a.social_meta ?? {};
  const engagement = engagementOf(a);
  const isSocial = a.article_class === 'social' || a.article_class === 'discussion';
  const account = sm.author && isSocial ? `@${sm.author}` : sm.author_name || sm.author;
  const where = isSocial ? sm.platform ?? a.news_source : a.news_source ?? 'unknown source';
  const meta = [CLASS_LABEL[a.article_class] ?? a.article_class, where, account, a.published ? a.published.slice(0, 10) : 'undated'].filter(Boolean).join(' · ');
  const verdict = a.review_verdict ? (a.review_verdict === 'signal' && a.review_kind ? a.review_kind : VERDICT_LABEL[a.review_verdict] ?? a.review_verdict) : null;
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      title={a.title}
      href={a.uri}
      meta={meta}
      leading={sm.thumbnail ? <RemoteImage src={sm.thumbnail} size={72} /> : undefined}
      flag={a.cluster ? <Chip size="sm" tone="accent">{`${a.cluster.size} sources on this story`}</Chip> : undefined}
      summary={a.summary && a.summary !== a.title ? `${a.summary.slice(0, 200)}${a.summary.length > 200 ? '…' : ''}` : undefined}
      tags={
        <Stack direction="row" gap="sm">
          <Chip size="sm" tone={CLASS_TONE[a.article_class] ?? 'neutral'}>{CLASS_LABEL[a.article_class] ?? a.article_class}</Chip>
          {verdict && <Chip size="sm" tone={a.review_verdict === 'signal' ? 'success' : 'muted'} label={a.review_reason ? `${verdict}: ${a.review_reason}` : verdict}>{verdict}</Chip>}
          {/* A vendor chip narrows the list to that vendor; pressing it again clears the filter */}
          {a.vendors.slice(0, 4).map((v) => (
            <Chip
              key={v.brand_id}
              size="sm"
              tone={vendorFilter === v.brand_id ? 'accent' : 'info'}
              variant={vendorFilter === v.brand_id ? 'fill' : 'outline'}
              label={vendorFilter === v.brand_id ? `Stop filtering on ${v.vendor}` : `Show only ${v.vendor}`}
              icon={<VendorSwatch color={colours.byId(v.brand_id)} />}
              onClick={() => onVendorFilter(vendorFilter === v.brand_id ? null : v.brand_id)}
            >
              {v.vendor}
            </Chip>
          ))}
          {a.matched_terms.slice(0, 3).map((t) => <Chip key={t} size="sm" tone="muted">{t}</Chip>)}
        </Stack>
      }
      footer={engagement > 0 ? `${engagement} reactions (${sm.likes ?? 0} likes, ${sm.comments ?? 0} comments, ${sm.reposts ?? sm.shares ?? 0} reposts)` : undefined}
      details={a.cluster ? (
        <Stack as="ul" gap="sm" label={`The other posts on this story`}>
          {a.cluster.others.map((o) => (
            <li key={o.uri}>
              <TextLink href={o.uri} external>{`${o.author ? `@${o.author}: ` : ''}${o.title ?? o.uri}`}</TextLink>
              <Text as="span" variant="caption">{` · ${o.news_source ?? 'unknown source'} · ${(o.published ?? '').slice(0, 10)}`}</Text>
            </li>
          ))}
        </Stack>
      ) : undefined}
    />
  );
}

/** A section of cards (one vendor's, one day's or one kind's), capped until asked for more so a vendor with 90 posts doesn't bury the rest */
export function GroupSection({ group, colours, vendorFilter, onVendorFilter }: {
  group: CoverageGroup;
  colours: VendorColours;
  vendorFilter: number | null;
  onVendorFilter: (id: number | null) => void;
}) {
  const CAP = 6;
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? group.items : group.items.slice(0, CAP);
  return (
    <Stack gap="sm">
      <Stack direction="row" gap="sm">
        <Text as="span" variant="label">
          <VendorSwatch color={colours.byId(group.brandId)} />
          {group.label}
        </Text>
        <Text as="span" variant="caption">{String(group.items.length)}</Text>
      </Stack>
      <Stack as="ul" gap="sm" label={group.label}>
        {visible.map((a) => <CoverageCard key={a.uri} article={a} vendorFilter={vendorFilter} onVendorFilter={onVendorFilter} colours={colours} />)}
      </Stack>
      {group.items.length > CAP && (
        <div>
          <Button variant="ghost" size="sm" onClick={() => setExpanded((e) => !e)}>{expanded ? 'Show fewer' : `Show ${group.items.length - CAP} more`}</Button>
        </div>
      )}
    </Stack>
  );
}
