import { ArticleCard, Chip, Text, type MenuItem } from '@aunoo/ui';
import type { BWSocialPost } from '@monolith/brandWatcherApi';
import { cleanSocialText } from '@monolith/socialText';
import { PROFILE_PLATFORMS, ROLE_LABEL, SENT_LABEL, SENT_TONE, authorOf, bodyOf, brandOf, fmtCount, handleOf, platLabel, sentOf } from './helpers';

export interface PostActions {
  onProfile: (platform: string, handle: string) => void;
  onAttach: (p: BWSocialPost) => void;
  onFlag: (p: BWSocialPost) => void;
}

/** One social post as a list row: who, when, the text, its keywords, relevance, sentiment and reach. */
export function PostCard({ p, actions, showBrand }: { p: BWSocialPost; actions: PostActions; showBrand?: boolean }) {
  const sent = sentOf(p.sentiment);
  const sm = p.social_meta || {};
  const handle = handleOf(p);
  const canProfile = !!handle && PROFILE_PLATFORMS.includes(p.platform);
  const items: MenuItem[] = [
    ...(canProfile ? [{ id: 'profile', label: `Profile @${handle}`, icon: 'User' as const }] : []),
    { id: 'attach', label: 'Add to incident', icon: 'ShieldCheck' },
    { id: 'flag', label: 'Flag as false positive', icon: 'Flag', tone: 'danger', separatorBefore: true },
  ];
  const reach = ([['likes', sm.likes], ['reposts', sm.reposts], ['comments', sm.comments], ['plays', sm.plays]] as [string, number | null | undefined][])
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${fmtCount(v)} ${k}`)
    .join(' · ');
  const text = bodyOf(p);
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      href={p.uri}
      meta={[platLabel(p.platform), p.publication_date?.slice(0, 10), showBrand ? brandOf(p) : null].filter(Boolean).join(' · ')}
      flag={p.author_role && p.author_role !== 'unknown' ? <Chip size="sm" tone="info">{ROLE_LABEL[p.author_role] ?? p.author_role.replace(/_/g, ' ')}</Chip> : undefined}
      title={authorOf(p)}
      summary={text.length > 420 ? `${text.slice(0, 420)}…` : text}
      details={
        p.original_summary ? (
          <Text variant="description">Original, before translation: {cleanSocialText(p.original_summary)}</Text>
        ) : undefined
      }
      actions={items}
      actionsLabel={`Actions for the post by ${authorOf(p)}`}
      onAction={(id) => {
        if (id === 'profile' && handle) actions.onProfile(p.platform, handle);
        else if (id === 'attach') actions.onAttach(p);
        else if (id === 'flag') actions.onFlag(p);
      }}
      tags={
        <>
          <Chip size="sm" tone={SENT_TONE[sent]}>{p.sentiment || SENT_LABEL[sent]}</Chip>
          {p.relevance != null
            ? <Chip size="sm" tone={p.relevance >= 0.6 ? 'success' : p.relevance >= 0.4 ? 'info' : 'muted'}>Relevance {p.relevance.toFixed(2)}</Chip>
            : <Chip size="sm" tone="warning">Not yet evaluated</Chip>}
          {(p.repost_count ?? 1) >= 2 && <Chip size="sm" tone="muted">Posted {p.repost_count} times</Chip>}
          {(p.matched_keywords ?? []).map((k) => <Chip key={k} size="sm" tone="neutral">#{k}</Chip>)}
          {sm.subreddit && <Chip size="sm" tone="muted">r/{sm.subreddit}</Chip>}
        </>
      }
      footer={reach ? <span>{reach}</span> : undefined}
    />
  );
}
