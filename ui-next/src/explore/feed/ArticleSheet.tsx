import { useEffect, useState } from 'react';
import { Button, Chip, Eyebrow, Icon, LineItems, Menu, IconButton, Sheet, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import type { ClusterRelatedArticle, NewsArticle } from '@monolith/newsFeedApi';
import { SentimentSpread, sentimentTone } from './visuals';
import { api, errorText } from '../../shell';
import { askAuspex, cleanTitle, setArticlePreference } from './api';
import type { PromoteArticle } from './PromoteDialog';
import { AddToBriefingDialog } from '../desk/AddToBriefingDialog';
import { ShareDialog } from '../shared/ShareDialog';
import { SignalsDialog } from '../bw/tabs/SignalsDialog';
import { getSignalsDetail, type BWArticleSignals } from '@monolith/brandWatcherApi';

/*
 * One article's details, opened from any list on the page (the old ArticleDetailPanel). The full
 * record comes from /api/article; when that misses, the fields the list already had are shown.
 */

interface Raw {
  uri: string;
  title?: string;
  original_title?: string;
  summary?: string;
  original_summary?: string;
  news_source?: string;
  publication_date?: string;
  topic?: string;
  category?: string;
  sentiment?: string;
  sentiment_explanation?: string;
  future_signal?: string;
  future_signal_explanation?: string;
  time_to_impact?: string;
  time_to_impact_explanation?: string;
  driver_type?: string;
  bias?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  bias_country?: string;
  tags?: string | string[];
  url?: string;
  user_preference?: string | null;
}

export interface SheetTarget {
  /** What the list already knows; the uri alone is enough */
  article: Partial<NewsArticle> & { uri: string };
  related?: ClusterRelatedArticle[];
}

const fromList = (a: SheetTarget['article']): Raw => ({
  uri: a.uri, title: a.title, summary: a.summary, news_source: a.source?.name, publication_date: a.publication_date, topic: a.topic,
  category: a.category, sentiment: a.sentiment, future_signal: a.future_signal, time_to_impact: a.time_to_impact, bias: a.source?.bias,
  factual_reporting: a.source?.factuality, mbfc_credibility_rating: a.source?.credibility_rating, tags: a.tags, url: a.url,
});
const tagList = (t: Raw['tags']) => (Array.isArray(t) ? t : (t ?? '').split(',').map((x) => x.trim()).filter(Boolean));

interface Props {
  target: SheetTarget | null;
  onClose: () => void;
  onOpenRelated: (uri: string) => void;
  starred: string[];
  onToggleStar: (uri: string) => void;
  onPromote: (a: PromoteArticle) => void;
  notify: (m: string) => void;
}

export function ArticleSheet({ target, onClose, onOpenRelated, starred, onToggleStar, onPromote, notify }: Props) {
  const [a, setA] = useState<Raw | null>(null);
  const [loading, setLoading] = useState(false);
  const [pref, setPref] = useState<'more' | 'less' | null>(null);
  const [toBriefing, setToBriefing] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [signalsOpen, setSignalsOpen] = useState(false);
  const [signals, setSignals] = useState<BWArticleSignals | null>(null);

  useEffect(() => {
    if (!target) return;
    let stale = false;
    setA(fromList(target.article));
    setLoading(true);
    api<Raw>(`/api/article?uri=${encodeURIComponent(target.article.uri)}`).then(
      (r) => {
        if (stale) return;
        if (r?.uri) {
          setA(r);
          setPref(r.user_preference === 'more' || r.user_preference === 'less' ? r.user_preference : null);
        }
      },
      () => undefined,
    ).finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [target]);

  // Five Signals: a Brand Watcher article carries its brand, and its stored screen (if any) is read
  // here. Running a screen calls the AI, so it starts only from the dialog's own button.
  const brandId = (target?.article as { brand_id?: number | null } | undefined)?.brand_id ?? null;
  const screenable = !!brandId && !!target?.article.uri.startsWith('http');
  useEffect(() => {
    setSignals(null);
    if (!screenable || !target || !brandId) return;
    let stale = false;
    getSignalsDetail(target.article.uri, brandId).then((d) => !stale && setSignals(d), () => undefined);
    return () => {
      stale = true;
    };
  }, [screenable, target, brandId, signalsOpen]);

  const url = a ? a.url || a.uri : '';
  const isStarred = !!a && starred.includes(a.uri);
  const related = target?.related ?? [];

  const onMenu = async (id: string) => {
    if (!a) return;
    if (id === 'copy') {
      await navigator.clipboard?.writeText(url).catch(() => undefined);
      notify('Link copied');
    } else if (id === 'briefing') {
      setToBriefing(true);
    } else if (id === 'share') {
      setSharing(true);
    } else if (id === 'promote') {
      onPromote({ uri: a.uri, title: a.title ?? a.uri, summary: a.summary, source: a.news_source, publication_date: a.publication_date, topic: a.topic });
    } else if (id === 'more' || id === 'less') {
      const next = pref === id ? null : id;
      try {
        await setArticlePreference(a.uri, next ?? 'clear');
        setPref(next);
        notify(next ? `You’ll see ${next === 'more' ? 'more' : 'fewer'} articles like this` : 'Preference cleared');
      } catch (e) {
        notify(`Not saved: ${errorText(e)}`);
      }
    }
  };

  const details: { id: string; label: string; amount: string }[] = a
    ? ([
        ['Sentiment', a.sentiment], ['Future signal', a.future_signal], ['Time to impact', a.time_to_impact], ['Driver type', a.driver_type],
        ['Topic', a.topic], ['Bias', a.bias], ['Factual reporting', a.factual_reporting], ['Credibility', a.mbfc_credibility_rating], ['Publisher country', a.bias_country],
      ] as [string, string | undefined][])
        .filter(([, v]) => v)
        .map(([label, v]) => ({ id: label, label, amount: v! }))
    : [];
  const why = a ? ([['Why this sentiment', a.sentiment_explanation], ['Why this signal', a.future_signal_explanation], ['Why this time to impact', a.time_to_impact_explanation]] as [string, string | undefined][]).filter(([, v]) => v) : [];

  return (
    <>
    <Sheet
      open={!!target}
      onOpenChange={(o) => !o && onClose()}
      title={a?.title ? cleanTitle(a.title) : 'Article'}
      description={[a?.news_source, a?.publication_date?.slice(0, 10)].filter(Boolean).join(' · ') || undefined}
      meta={a?.category ? <Chip size="sm" tone="neutral">{a.category}</Chip> : undefined}
      footer={
        a && (
          <Stack direction="row" justify="between" gap="sm">
            <Stack direction="row" gap="sm">
              <Button asChild size="sm" iconStart={<Icon name="ArrowSquareOut" size="sm" />}>
                <a href={url} target="_blank" rel="noreferrer">Read original<span className="visually-hidden"> (opens in new tab)</span></a>
              </Button>
              <Button
                size="sm"
                variant="secondary"
                iconStart={<Icon name="ChatCentered" size="sm" />}
                onClick={() => askAuspex(`Tell me more about this article and what it means for us: "${a.title}" (${a.news_source ?? ''}) ${url}`, a.topic)}
              >
                Ask Auspex
              </Button>
            </Stack>
            <Stack direction="row" gap="sm">
              <IconButton icon={<Icon name="Star" size="sm" />} label={isStarred ? 'Remove star' : 'Star'} onClick={() => onToggleStar(a.uri)} />
              <Menu
                trigger={<IconButton icon={<Icon name="DotsThreeOutlineVertical" size="sm" />} label="More actions" />}
                items={[
                  { id: 'more', label: pref === 'more' ? 'Clear “More like this”' : 'More like this', icon: 'ArrowUp' },
                  { id: 'less', label: pref === 'less' ? 'Clear “Less like this”' : 'Less like this', icon: 'ArrowDown' },
                  { id: 'copy', label: 'Copy link', icon: 'Link' },
                  { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
                  { id: 'briefing', label: 'Add to a briefing', icon: 'Notebook', separatorBefore: true },
                  { id: 'promote', label: 'Promote to incident', icon: 'Warning' },
                ]}
                onSelect={(id) => void onMenu(id)}
                align="end"
                side="top"
              />
            </Stack>
          </Stack>
        )
      }
    >
      {!a ? <Skeleton variant="text" lines={8} /> : (
        <Stack gap="lg">
          {a.original_title && a.original_title !== a.title && <Text variant="caption">Original headline: {a.original_title}</Text>}
          {a.summary ? <Text>{a.summary}</Text> : loading ? <Skeleton variant="text" lines={4} /> : <Text variant="caption">No summary stored for this article.</Text>}
          {a.original_summary && a.original_summary !== a.summary && (
            <Stack gap="sm"><Eyebrow as="h3">Original text</Eyebrow><Text variant="description">{a.original_summary}</Text></Stack>
          )}
          {details.length > 0 && <LineItems label="Article details" items={details} />}
          {why.map(([label, v]) => (
            <Stack key={label} gap="sm"><Eyebrow as="h3">{label}</Eyebrow><Text variant="description">{v}</Text></Stack>
          ))}
          {screenable && (
            <Stack gap="sm">
              <Eyebrow as="h3">Five Signals screen</Eyebrow>
              <Text variant="caption">
                {signals?.status === 'completed'
                  ? `Screened${signals.verdict ? `: ${String(signals.verdict).replace(/_/g, ' ')}` : ''}${signals.composite_score != null ? `, score ${Math.round(Number(signals.composite_score))}` : ''}.`
                  : signals?.status === 'running'
                    ? 'A screen is running for this article.'
                    : 'Not screened yet. The screen checks who first published the story, how it spread, and whether its claims hold up, using the AI.'}
              </Text>
              <div>
                <Button size="sm" variant="secondary" iconStart={<Icon name="ShieldCheck" size="sm" />} onClick={() => setSignalsOpen(true)}>
                  {signals?.status === 'completed' || signals?.status === 'running' ? 'Open the screen' : 'Screen this article'}
                </Button>
              </div>
            </Stack>
          )}
          {tagList(a.tags).length > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h3">Tags</Eyebrow>
              <Stack direction="row" gap="sm">{tagList(a.tags).map((t) => <Chip key={t} size="sm" tone="muted">{t}</Chip>)}</Stack>
            </Stack>
          )}
          {related.length > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h3">Other coverage of this story ({related.length})</Eyebrow>
              {/* As the old panel: how the whole story's coverage leans, this article included */}
              {(() => {
                const all = [a?.sentiment, ...related.map((r) => r.sentiment)].map((x) => sentimentTone(x as string | undefined));
                return <SentimentSpread positive={all.filter((t) => t === 'success').length} neutral={all.filter((t) => t === 'muted' || t === 'warning').length} negative={all.filter((t) => t === 'error').length} />;
              })()}
              <Stack as="ul" gap="sm" label="Other coverage">
                {related.map((r) => (
                  <li key={r.uri}>
                    <Stack gap="sm">
                      <Button variant="ghost" size="sm" onClick={() => onOpenRelated(r.uri)}>{cleanTitle(r.title)}</Button>
                      <Stack direction="row" gap="sm">
                        <Text variant="caption" as="span">{[r.news_source, r.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}</Text>
                        {r.sentiment && <Chip size="sm" tone={sentimentTone(r.sentiment)}>{r.sentiment}</Chip>}
                        {r.factual_reporting && <Chip size="sm" tone="muted">Factual: {r.factual_reporting}</Chip>}
                        {r.bias && <Chip size="sm" tone="muted">Bias: {r.bias}</Chip>}
                      </Stack>
                    </Stack>
                  </li>
                ))}
              </Stack>
            </Stack>
          )}
          <TextLink href={url} external>{url}</TextLink>
        </Stack>
      )}
    </Sheet>
    {a && (
      <ShareDialog
        open={sharing}
        onOpenChange={setSharing}
        kind="article"
        title={a.title ? cleanTitle(a.title) : a.uri}
        payload={{ title: a.title ?? a.uri, url, source: a.news_source, summary: a.summary, category: a.category, topic: a.topic, sentiment: a.sentiment, publication_date: a.publication_date }}
        notify={notify}
      />
    )}
    {screenable && signalsOpen && target && (
      <SignalsDialog target={{ uri: target.article.uri, title: a?.title, brand_id: brandId }} onClose={() => setSignalsOpen(false)} notify={notify} />
    )}
    {a && (
      <AddToBriefingDialog
        open={toBriefing}
        onClose={() => setToBriefing(false)}
        itemType="article"
        article={{
          uri: a.uri, title: a.title ?? a.uri, summary: a.summary, source: a.news_source, publication_date: a.publication_date,
          topic: a.topic, url: a.url || a.uri, sentiment: a.sentiment, bias: a.bias, category: a.category,
        }}
        notify={notify}
      />
    )}
    </>
  );
}
