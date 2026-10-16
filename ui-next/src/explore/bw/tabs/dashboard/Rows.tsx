import { ArticleCard, Chip, type MenuItem } from '@aunoo/ui';
import type { BWArticle, BWSocialPost } from '@monolith/brandWatcherApi';
import { cleanSocialText, stripSocialMarkdown } from '@monolith/socialText';
import { TitleLink } from '../../../feed/api';
import {
  RISK_CAT, bodyOf, engagementOf, fmtCount, handleOf, isNegConsensus, isPolarized, platformLabel, relDate, ROLE_LABEL, sentimentOf,
} from './helpers';

type Tone = 'success' | 'warning' | 'error' | 'info' | 'muted' | 'neutral' | 'accent';
const SENT_TONE: Record<string, Tone> = { positive: 'success', negative: 'error', neutral: 'muted', unrated: 'muted' };
const factTone = (f: string): Tone => {
  const t = f.toLowerCase();
  if (t.includes('very high') || t === 'high') return 'success';
  if (t.includes('mixed') || t.includes('mostly')) return 'warning';
  if (t.includes('low')) return 'error';
  return 'muted';
};
const REVIEW_LABEL: Record<string, string> = { reviewed: 'Reviewed', escalated: 'Escalated', dismissed: 'Dismissed', false_positive: 'False positive' };

export type ReviewStatus = 'reviewed' | 'escalated' | 'dismissed' | 'false_positive';

/** Five Signals state as a chip; the chip opens the screening dialog. */
export function SignalsChip({ a, available, onOpen }: { a: BWArticle; available: boolean; onOpen: () => void }) {
  const s = a.signals_summary;
  if (s?.status === 'running') return <Chip size="sm" tone="info">Screening…</Chip>;
  if (s?.status === 'completed') {
    return (
      <Chip size="sm" tone="info" onClick={onOpen} label={`Five Signals result for “${a.title}”`}>
        Signals: {s.verdict || 'done'}{s.composite != null ? ` · ${s.composite}/100` : ''}
      </Chip>
    );
  }
  if (s?.status === 'failed') return <Chip size="sm" tone="error" onClick={onOpen} label={`Retry Five Signals for “${a.title}”`}>Signals failed</Chip>;
  if (available && String(a.uri).startsWith('http')) return <Chip size="sm" tone="muted" onClick={onOpen} label={`Screen “${a.title}” with Five Signals`}>Screen</Chip>;
  return null;
}

interface NewsRowProps {
  a: BWArticle;
  review: string;
  signalsAvailable: boolean;
  onOpen: () => void;
  onSignals: () => void;
  onReview: (s: ReviewStatus) => void;
  onIncident: () => void;
}

/** One news story: adverse cues first (consensus, risks, factuality), then the case actions. */
export function NewsRow({ a, review, signalsAvailable, onOpen, onSignals, onReview, onIncident }: NewsRowProps) {
  const sent = sentimentOf(a.sentiment);
  const cats = [...(a.categories || []).filter((c) => RISK_CAT.test(c)), ...(a.categories || []).filter((c) => !RISK_CAT.test(c))].slice(0, 2);
  const actions: MenuItem[] = [
    { id: 'reviewed', label: 'Mark reviewed', icon: 'Check' },
    { id: 'escalated', label: 'Escalate', icon: 'ArrowUp' },
    { id: 'dismissed', label: 'Dismiss', icon: 'EyeSlash' },
    { id: 'false_positive', label: 'Not about this brand (false positive)', icon: 'X' },
    { id: 'incident', label: 'Add to incident…', icon: 'Warning', separatorBefore: true },
    { id: 'signals', label: 'Five Signals screening', icon: 'ShieldCheck' },
  ];
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      meta={[(a.news_source || '').replace(/^www\./, ''), relDate(a.publication_date)].filter(Boolean).join(' · ')}
      flag={
        isNegConsensus(a) ? <Chip size="sm" tone="error">Negative across {a.story_neg} of {a.story_scored} sources</Chip>
          : isPolarized(a) ? <Chip size="sm" tone="warning">Coverage split: {a.story_pos} positive, {a.story_neg} negative</Chip>
            : undefined
      }
      title={<TitleLink href={a.uri} onOpen={onOpen}>{a.title}</TitleLink>}
      summary={sent === 'negative' && a.summary ? stripSocialMarkdown(a.summary) : undefined}
      actions={actions}
      actionsLabel={`Actions for “${a.title}”`}
      onAction={(id) => (id === 'incident' ? onIncident() : id === 'signals' ? onSignals() : onReview(id as ReviewStatus))}
      tags={
        <>
          {sent !== 'unrated' && <Chip size="sm" tone={SENT_TONE[sent]}>{sent}</Chip>}
          {a.is_owned && <Chip size="sm" tone="muted">Owned (not counted)</Chip>}
          {(a.story_size || 1) >= 2 && <Chip size="sm" tone={(a.story_size || 0) >= 3 ? 'warning' : 'muted'}>Carried by {a.story_size} sources</Chip>}
          {(a.risks || []).map((r) => (
            <Chip key={r.risk_type} size="sm" tone={r.severity === 'high' ? 'error' : r.severity === 'medium' ? 'warning' : 'muted'}>
              Risk: {r.risk_type.replace(/_/g, ' ')} ({r.severity})
            </Chip>
          ))}
          {a.factual_reporting && <Chip size="sm" tone={factTone(a.factual_reporting)}>Factual: {a.factual_reporting}</Chip>}
          {cats.map((c) => <Chip key={c} size="sm" tone={RISK_CAT.test(c) ? 'warning' : 'neutral'}>{c}</Chip>)}
          {a.entity_match?.verified && <Chip size="sm" tone="info">Verified on Wikidata</Chip>}
          <SignalsChip a={a} available={signalsAvailable} onOpen={onSignals} />
          {review !== 'new' && <Chip size="sm" tone={review === 'escalated' ? 'error' : 'muted'}>{REVIEW_LABEL[review] ?? review}</Chip>}
        </>
      }
    />
  );
}

interface SocialRowProps {
  p: BWSocialPost;
  onIncident: () => void;
  onFlag: () => void;
  onAuthor?: () => void;
}

/** One social post: network, author, role, text, reach. */
export function SocialRow({ p, onIncident, onFlag, onAuthor }: SocialRowProps) {
  const sent = sentimentOf(p.sentiment);
  const h = handleOf(p);
  const m = (p.social_meta || {}) as Record<string, number | undefined>;
  const reach = [
    m.likes ? `${fmtCount(m.likes)} likes` : '', m.reposts ? `${fmtCount(m.reposts)} reposts` : '',
    m.comments ? `${fmtCount(m.comments)} comments` : '', m.plays ? `${fmtCount(m.plays)} plays` : '',
  ].filter(Boolean).join(' · ');
  const actions: MenuItem[] = [
    { id: 'incident', label: 'Add to incident…', icon: 'Warning' },
    ...(onAuthor && h ? [{ id: 'author', label: `Open @${h}’s account`, icon: 'User' as const }] : []),
    { id: 'flag', label: 'Not about this brand (false positive)', icon: 'Flag', separatorBefore: true },
  ];
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      href={p.uri}
      meta={[platformLabel(p.platform), p.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}
      title={h ? `@${h}` : p.news_source || 'Post'}
      summary={cleanSocialText(stripSocialMarkdown(bodyOf(p))).slice(0, 400)}
      actions={actions}
      actionsLabel={`Actions for the post by ${h ? `@${h}` : 'this account'}`}
      onAction={(id) => (id === 'incident' ? onIncident() : id === 'flag' ? onFlag() : onAuthor?.())}
      tags={
        <>
          {sent !== 'unrated' && <Chip size="sm" tone={SENT_TONE[sent]}>{sent}</Chip>}
          {p.author_role && p.author_role !== 'unknown' && <Chip size="sm" tone="neutral">{ROLE_LABEL[p.author_role] || p.author_role}</Chip>}
          {(p.repost_count || 1) >= 2 && <Chip size="sm" tone="muted">Posted {p.repost_count} times</Chip>}
          {engagementOf(p) >= 50 && <Chip size="sm" tone="warning">High reach</Chip>}
        </>
      }
      footer={reach || undefined}
    />
  );
}
