import { useCallback, useMemo, useState } from 'react';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, Grid, Icon, IconButton, LineChart, Meter, Panel,
  SegmentedControl, Select, SettingRow, Stack, Stat, StackedBars, Table, Text,
} from '@aunoo/ui';
import { setFindingState, type BWArticle, type BWSocialPost } from '@monolith/brandWatcherApi';
import { cleanSocialText } from '@monolith/socialText';
import { errorText } from '../../../shell';
import { TitleLink } from '../../feed/api';
import type { BwContext } from '../context';
import { queueAccount } from './social/helpers';
import { AlertSettingsDialog } from './dashboard/AlertSettingsDialog';
import { handleOf } from './dashboard/helpers';
import { Coverage } from './dashboard/Coverage';
import {
  bodyOf, bucketCounts, engagementOf, fmtCount, netOf, platformLabel, sentimentOf, signed, socialBrandOf, weekOf, weeklyNet, type FanCritic,
} from './dashboard/helpers';
import { AddToIncidentDialog, type IncidentSource } from '../overlays/AddToIncidentDialog';
import { NewsRow, SocialRow, type ReviewStatus } from './dashboard/Rows';
import { useDashboardData, type SocialScope } from './dashboard/useDashboardData';

/*
 * The Brand Watcher daily screen, ported from the old tab (BrandWatcherTab.tsx, the "dashboard"
 * sub-tab): problems to look at, the headline figures, news against social sentiment, adverse
 * news first, the loudest negative and positive posts, fans and critics, then coverage analytics.
 * Every figure counts only on-brand items (relevance 0.4 or more). No AI runs here.
 */

const DISMISSED_KEY = 'bw_dismissed_alerts';
const REACH_FLOOR = 10;
const MIN_SCORED = 3;
type LedgerSort = 'reach' | 'newest' | 'relevance';

function loadDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

interface Problem {
  key: string;
  sev: 'high' | 'medium';
  text: string;
  jump: 'social' | 'analysis';
  evidence?: string[];
}

function FanList({ title, rows, kind, profiles, onAuthor, onOpen }: {
  title: string; rows: FanCritic[]; kind: 'fan' | 'critic'; profiles: Record<string, unknown>; onAuthor: () => void; onOpen: (platform: string, handle: string) => void;
}) {
  return (
    <Panel title={title} description={kind === 'fan' ? 'Ranked by the reach of their positive posts.' : 'Ranked by the reach of their negative posts.'} headingLevel={3}>
      <Table
        caption={title}
        hideCaption
        rows={rows.slice(0, 5)}
        rowKey={(a) => `${a.platform}:${a.author}`}
        emptyText="None in this period."
        columns={[
          {
            key: 'author', header: 'Account', rowHeader: true,
            render: (a) => {
              const p = profiles[`${a.platform}:${a.author.toLowerCase()}`] as { verified?: boolean; followers_count?: number | null } | 'missing' | undefined;
              const meta = p && p !== 'missing' ? [p.verified ? 'verified' : '', p.followers_count != null ? `${fmtCount(p.followers_count)} followers` : ''].filter(Boolean).join(' · ') : '';
              return <Stack gap="sm"><TitleLink href={`#account-${a.author}`} onOpen={() => onOpen(a.platform, a.author)}>@{a.author}</TitleLink><Text variant="caption">{[platformLabel(a.platform), meta].filter(Boolean).join(' · ')}</Text></Stack>;
            },
          },
          { key: 'posts', header: kind === 'fan' ? 'Positive posts' : 'Negative posts', align: 'end', render: (a) => (kind === 'fan' ? a.pos : a.neg) },
          { key: 'reach', header: 'Reach', align: 'end', render: (a) => fmtCount(kind === 'fan' ? a.posEng : a.negEng) ?? '0' },
          {
            key: 'trend', header: 'Lately',
            render: (a) => (a.trend === 'up' ? (kind === 'critic' ? 'Posting more' : 'Posting more') : a.trend === 'down' ? 'Posting less' : a.spanDays > 0 ? `Over ${a.spanDays} days` : '–'),
          },
        ]}
      />
      <Button variant="ghost" size="sm" onClick={onAuthor}>See all posts</Button>
    </Panel>
  );
}

export function Dashboard(ctx: BwContext) {
  const { bw, notify, goTo, openArticle, openSignals, selectedBrands, focusBrand } = ctx;
  const { stats, brands } = bw;
  const [scope, setScope] = useState<SocialScope>('selected');
  const d = useDashboardData(ctx, scope);
  // Opens the author in Accounts (their stored profile, or a button to build one)
  const openAccount = (platform: string | null | undefined, handle: string | null | undefined) => {
    if (!handle) return;
    queueAccount(platform || 'twitter', handle);
    goTo('accounts');
  };
  const [sort, setSort] = useState<LedgerSort>('reach');
  const [dismissed, setDismissed] = useState<Set<string>>(loadDismissed);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [attach, setAttach] = useState<IncidentSource | null>(null);
  const [review, setReview] = useState<Record<string, string>>({});
  const [hiddenPosts, setHiddenPosts] = useState<Set<string>>(new Set());

  const dismiss = useCallback((k: string) => {
    setDismissed((prev) => {
      const n = new Set(prev).add(k);
      try {
        localStorage.setItem(DISMISSED_KEY, JSON.stringify([...n].slice(-200)));
      } catch {
        // per visit only
      }
      return n;
    });
  }, []);

  const reviewOf = (a: BWArticle) => review[`${a.uri}|${a.brand_id}`] || a.review_status || 'new';
  const doReview = async (a: BWArticle, status: ReviewStatus) => {
    if (!a.brand_id) return notify('This article has no brand, so it can’t be case-managed.');
    setReview((r) => ({ ...r, [`${a.uri}|${a.brand_id}`]: status }));
    try {
      await setFindingState(a.uri, a.brand_id, status);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    }
  };
  const flagPost = (p: BWSocialPost) => {
    const brandId = brands.find((b) => b.display_name === socialBrandOf(p))?.id;
    if (!brandId) return notify('Couldn’t tell which brand this post belongs to.');
    ctx.askConfirm({
      title: 'Flag this post as not about the brand?',
      message: 'It leaves Brand Watcher and the alert counts, but stays in the database as a labelled example for relevance tuning.',
      action: 'Flag post',
      onConfirm: () => {
        setHiddenPosts((s) => new Set(s).add(p.uri));
        setFindingState(p.uri, brandId, 'false_positive').catch((e: unknown) => notify(`Not flagged: ${errorText(e)}`));
      },
    });
  };
  const postAttach = (p: BWSocialPost): IncidentSource => ({
    refs: [p.uri], label: cleanSocialText(bodyOf(p)).slice(0, 120) || p.uri, brandId: brands.find((b) => b.display_name === socialBrandOf(p))?.id ?? null,
  });

  // ---- News side ----
  const newsSent = bucketCounts(d.totals);
  const newsScored = newsSent.pos + newsSent.neu + newsSent.neg;
  const newsNet = netOf(newsSent.pos, newsSent.neg, newsScored);

  // ---- Social side ----
  const posts = useMemo(() => (d.social ?? []).filter((p) => !hiddenPosts.has(p.uri)), [d.social, hiddenPosts]);
  const onBrand = posts.filter((p) => (p.relevance ?? 0) >= 0.4);
  const soc = { pos: 0, neu: 0, neg: 0 };
  for (const p of posts) {
    const s = sentimentOf(p.sentiment);
    if (s === 'positive') soc.pos++;
    else if (s === 'negative') soc.neg++;
    else if (s === 'neutral') soc.neu++;
  }
  const socScored = soc.pos + soc.neu + soc.neg;
  const socNet = netOf(soc.pos, soc.neg, socScored);

  // ---- Competitor benchmarks: the other brands' average net sentiment ----
  const primaryName = d.primaryId ? brands.find((b) => b.id === d.primaryId)?.display_name ?? '' : focusBrand?.display_name ?? '';
  const newsComp = bw.comparison
    .filter((c) => c.brand_name !== primaryName)
    .map((c) => {
      const b = bucketCounts(c.sentiment_breakdown);
      const scored = b.pos + b.neu + b.neg;
      return scored >= MIN_SCORED ? netOf(b.pos, b.neg, scored) : null;
    })
    .filter((n): n is number => n != null);
  const newsCompAvg = newsComp.length ? Math.round(newsComp.reduce((a, n) => a + n, 0) / newsComp.length) : null;
  const socComp = Object.entries(d.benchByBrand).filter(([b, v]) => b !== primaryName && v.scored >= MIN_SCORED).map(([, v]) => netOf(v.pos, v.neg, v.scored)!);
  const socCompAvg = socComp.length ? Math.round(socComp.reduce((a, n) => a + n, 0) / socComp.length) : null;
  const vsComp = (own: number | null, avg: number | null) => (own == null || avg == null ? '' : ` · ${own - avg >= 0 ? '+' : ''}${own - avg} against the competitor average (${signed(avg)})`);

  // ---- Adverse signals (dismissible; keys roll over with the window) ----
  const iso = (h: number) => new Date(Date.now() - h * 3600e3).toISOString();
  const bucket48 = Math.floor(Date.now() / (48 * 3600e3));
  const weekBucket = Math.floor(Date.now() / (7 * 24 * 3600e3));
  const brandKey = focusBrand?.display_name || 'all';
  const negPosts = onBrand.filter((p) => sentimentOf(p.sentiment) === 'negative');
  const negRecent = negPosts.filter((p) => (p.publication_date || '') >= iso(48));
  const negPrior = negPosts.filter((p) => { const t = p.publication_date || ''; return t >= iso(96) && t < iso(48); });
  const byReach = (a: BWSocialPost, b: BWSocialPost) => engagementOf(b) - engagementOf(a);
  const problems: Problem[] = [];
  if (negPrior.length >= 2 && negRecent.length >= negPrior.length * 2) {
    problems.push({ key: `adv|negspike|${brandKey}|${bucket48}`, sev: 'high', jump: 'social', text: `Negative social posts doubled: ${negRecent.length} in the last 48 hours against ${negPrior.length} in the 48 before.`, evidence: [...negRecent].sort(byReach).slice(0, 5).map((p) => p.uri) });
  }
  const hot = negPosts.filter((p) => engagementOf(p) >= 50);
  if (hot.length) {
    problems.push({ key: `adv|hotneg|${brandKey}|${bucket48}`, sev: 'high', jump: 'social', text: `${hot.length} high-reach negative ${hot.length === 1 ? 'post is' : 'posts are'} circulating (engagement 50 or more).`, evidence: [...hot].sort(byReach).slice(0, 5).map((p) => p.uri) });
  }
  const repeatCritics = d.fc.critics.filter((c) => c.neg >= 3);
  if (repeatCritics.length) {
    problems.push({ key: `adv|critics|${brandKey}|${bucket48}`, sev: 'medium', jump: 'social', text: `${repeatCritics.length} ${repeatCritics.length === 1 ? 'account is' : 'accounts are'} posting repeated criticism (3 or more negative posts): ${repeatCritics.slice(0, 3).map((c) => `@${c.author}`).join(', ')}.` });
  }
  if (newsNet != null && newsNet <= -20) {
    problems.push({ key: `adv|negnews|${brandKey}|${bucket48}`, sev: 'high', jump: 'analysis', text: `News coverage is net negative (${newsNet}).` });
  }
  const shownProblems = problems.filter((p) => !dismissed.has(p.key));
  const spikeKey = (cat: string) => `spike|${cat}|${brandKey}|${weekBucket}`;
  const spikes = d.alerts
    .filter((a) => !dismissed.has(spikeKey(a.category)))
    .sort((a, b) => (a.severity === 'high' ? 0 : 1) - (b.severity === 'high' ? 0 : 1) || b.spike_ratio - a.spike_ratio)
    .slice(0, 3);

  // ---- News: adverse first, one row per story ----
  const pool = d.pool ?? bw.articles;
  const seen = new Set<string>();
  const stories: BWArticle[] = [];
  for (const a of pool) {
    const k = a.story_group_id || (a.title || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 80);
    if (!k || seen.has(k)) continue;
    seen.add(k);
    stories.push(a);
  }
  const isNeg = (a: BWArticle) => sentimentOf(a.sentiment) === 'negative' || (a.risks || []).length > 0 || ((a.story_scored || 0) >= 3 && (a.story_neg || 0) / (a.story_scored || 1) >= 0.7);
  const live = stories.filter((a) => !['dismissed', 'false_positive'].includes(reviewOf(a)));
  const negNews = live.filter(isNeg).sort((a, b) => (b.story_size || 1) - (a.story_size || 1) || (b.publication_date || '').localeCompare(a.publication_date || ''));
  const otherNews = live.filter((a) => !isNeg(a)).sort((a, b) => (b.publication_date || '').localeCompare(a.publication_date || ''));
  const negShown = negNews.slice(0, 8);
  const otherShown = otherNews.slice(0, Math.max(0, 8 - negShown.length));

  // ---- "New today" ----
  const today = new Date().toISOString().slice(0, 10);
  const newsToday = stories.filter((a) => (a.publication_date || '').slice(0, 10) === today).length;
  const negNewsToday = negNews.filter((a) => (a.publication_date || '').slice(0, 10) === today).length;
  const socToday = onBrand.filter((p) => (p.publication_date || '').slice(0, 10) === today).length;

  // ---- What the negative coverage is about ----
  const negByCat: Record<string, number> = {};
  for (const a of pool) if (isNeg(a)) for (const c of a.categories || []) negByCat[c] = (negByCat[c] || 0) + 1;
  const negCats = Object.entries(negByCat).sort((x, y) => y[1] - x[1]).slice(0, 5);

  // ---- Social ledgers: complaints and praise ----
  const cmp = (a: BWSocialPost, b: BWSocialPost) =>
    sort === 'newest' ? (b.publication_date || '').localeCompare(a.publication_date || '')
      : sort === 'relevance' ? (b.relevance ?? -1) - (a.relevance ?? -1) || byReach(a, b)
        : byReach(a, b);
  const ledger = (s: 'positive' | 'negative') => onBrand.filter((p) => sentimentOf(p.sentiment) === s && (sort !== 'reach' || engagementOf(p) >= REACH_FLOOR)).sort(cmp).slice(0, 4);
  const negLedger = ledger('negative');
  const posLedger = ledger('positive');
  const ledgerEmpty = (s: string) => (d.loadingSocial ? 'Loading…' : sort === 'reach' ? `No ${s} posts with reach of ${REACH_FLOOR} or more in this period.` : `No ${s} posts in this period.`);

  // ---- Incidents ----
  const openIncidents = d.incidents.filter((i) => !['resolved', 'closed'].includes(i.status));
  const severeIncidents = openIncidents.filter((i) => i.severity === 'high' || i.severity === 'critical').length;
  const highSpikes = d.alerts.filter((a) => a.severity === 'high').length;

  // ---- Weekly net sentiment, news against social, with competitor averages ----
  const timeline = useMemo(() => {
    const news = weeklyNet(d.weekly, MIN_SCORED);
    const socW: Record<string, { pos: number; neg: number; tot: number }> = {};
    for (const p of posts) {
      const w = weekOf(p.publication_date || '');
      const s = sentimentOf(p.sentiment);
      if (!w || s === 'unrated') continue;
      const c = (socW[w] ||= { pos: 0, neg: 0, tot: 0 });
      if (s === 'positive') c.pos++;
      else if (s === 'negative') c.neg++;
      c.tot++;
    }
    const compNews: Record<string, number[]> = {};
    for (const series of d.compWeekly) for (const [w, n] of Object.entries(weeklyNet(series, MIN_SCORED))) (compNews[w] ||= []).push(n);
    const compSoc: Record<string, number[]> = {};
    const perBrand: Record<string, Record<string, { pos: number; neg: number; tot: number }>> = {};
    for (const p of d.benchPosts ?? []) {
      const b = socialBrandOf(p);
      if (!primaryName || b === primaryName) continue;
      const w = weekOf(p.publication_date || '');
      const s = sentimentOf(p.sentiment);
      if (!w || s === 'unrated') continue;
      const c = ((perBrand[b] ||= {})[w] ||= { pos: 0, neg: 0, tot: 0 });
      if (s === 'positive') c.pos++;
      else if (s === 'negative') c.neg++;
      c.tot++;
    }
    for (const bw2 of Object.values(perBrand)) for (const [w, c] of Object.entries(bw2)) if (c.tot >= MIN_SCORED) (compSoc[w] ||= []).push(((c.pos - c.neg) / c.tot) * 100);
    const avg = (a?: number[]) => (a && a.length ? Math.round(a.reduce((x, y) => x + y, 0) / a.length) : null);
    const weeks = [...new Set([...Object.keys(news), ...Object.keys(socW), ...Object.keys(compNews), ...Object.keys(compSoc)])].sort();
    const rows = weeks.map((w) => ({
      w,
      news: news[w] ?? null,
      social: socW[w] && socW[w].tot >= MIN_SCORED ? Math.round(((socW[w].pos - socW[w].neg) / socW[w].tot) * 100) : null,
      compNews: avg(compNews[w]),
      compSocial: avg(compSoc[w]),
    }));
    return rows.filter((r) => r.news != null || r.social != null).length >= 2 ? rows : null;
  }, [d.weekly, posts, d.compWeekly, d.benchPosts, primaryName]);

  const emp = d.employee;
  const outlook = emp?.overview?.business_outlook_rating != null ? Math.round(emp.overview.business_outlook_rating * 100) : null;
  const scopeLabel = selectedBrands.length > 1 ? `${selectedBrands.length} picked brands` : `${(selectedBrands[0] ?? focusBrand)?.display_name ?? 'Brand'} only`;
  const brandsInPosts = new Set(posts.map(socialBrandOf)).size;

  return (
    <>
      {(shownProblems.length > 0 || spikes.length > 0) && (
        <Stack gap="sm" as="section" label="Problems to look at">
          {shownProblems.map((p) => (
            <Banner
              key={p.key}
              tone={p.sev === 'high' ? 'error' : 'warning'}
              icon="Warning"
              headingLevel={2}
              title={p.text}
              action={
                <Stack direction="row" gap="sm">
                  <Button size="sm" variant="secondary" onClick={() => goTo(p.jump)}>Investigate</Button>
                  {!!p.evidence?.length && (
                    <Button size="sm" variant="secondary" onClick={() => setAttach({ refs: p.evidence!, label: `${p.text} (${p.evidence!.length} ${p.evidence!.length === 1 ? 'post' : 'posts'} captured as evidence)`, brandId: d.primaryId ?? focusBrand?.id ?? null })}>
                      Add to incident
                    </Button>
                  )}
                  <IconButton icon={<Icon name="X" size="sm" />} label="Dismiss (it comes back if it triggers again)" onClick={() => dismiss(p.key)} />
                </Stack>
              }
            />
          ))}
          {spikes.map((a) => (
            <Collapsible key={a.category}>
              <SettingRow
                title={`${a.category}: ${a.current_count} articles this week, ${a.spike_ratio}× the usual ${a.average_count}`}
                description={a.severity === 'high' ? 'High spike' : 'Spike'}
                actions={
                  <Stack direction="row" gap="sm">
                    <CollapsibleTrigger variant="onSurface">Articles</CollapsibleTrigger>
                    <IconButton icon={<Icon name="X" size="sm" />} label={`Dismiss the ${a.category} spike for this week`} onClick={() => dismiss(spikeKey(a.category))} />
                  </Stack>
                }
              >
                <CollapsibleContent>
                  {(a.articles || []).length === 0 ? <Text variant="caption">No articles listed for this spike.</Text> : (
                    <Stack as="ul" gap="sm" label={`${a.category} spike articles`}>
                      {(a.articles || []).map((x) => (
                        <li key={x.uri}>
                          <Stack direction="row" gap="sm">
                            <Button variant="ghost" size="sm" onClick={() => openArticle({ ...x })}>{x.title}</Button>
                            {x.sentiment && <Chip size="sm" tone="muted">{x.sentiment}</Chip>}
                            {x.publication_date && <Text variant="caption" as="span">{x.publication_date.slice(0, 10)}</Text>}
                          </Stack>
                        </li>
                      ))}
                    </Stack>
                  )}
                </CollapsibleContent>
              </SettingRow>
            </Collapsible>
          ))}
        </Stack>
      )}

      <Panel
        title="At a glance"
        description="Every figure counts only on-brand items (relevance 0.4 or more), so other things with the same name stay out."
        headerAside={
          <Stack direction="row" gap="sm">
            <Text variant="label" as="span">{d.loadingSocial ? 'Loading posts…' : `${posts.length} posts · ${brandsInPosts} ${brandsInPosts === 1 ? 'brand' : 'brands'}`}</Text>
            <SegmentedControl
              label="Social posts from"
              options={[{ value: 'selected', label: scopeLabel }, { value: 'all', label: 'With competitors' }]}
              value={scope}
              onValueChange={(v) => setScope(v as SocialScope)}
            />
            <Button size="sm" variant="secondary" iconStart={<Icon name="Bell" size="sm" />} onClick={() => setAlertsOpen(true)}>Alert settings</Button>
          </Stack>
        }
      >
        <Grid as="ul" columns={3} stackAt="small" gap="sm" label="Headline figures">
          <li>
            <Stat
              surface="panel"
              label="News articles"
              value={(stats?.total_articles ?? 0).toLocaleString('en-GB')}
              tone={negNewsToday ? 'error' : 'default'}
              meta={(stats?.owned_articles || 0) > 0 ? `${stats!.owned_articles} of the brand’s own posts left out` : newsToday ? `${newsToday} today${negNewsToday ? `, ${negNewsToday} negative` : ''}` : bw.config.daysBack === 0 ? 'All time' : `Last ${bw.config.daysBack} days`}
            />
          </li>
          <li>
            <Stat
              surface="panel"
              label="News sentiment (net)"
              value={signed(newsNet)}
              tone={newsNet == null ? 'default' : newsNet > 0 ? 'success' : newsNet < 0 ? 'error' : 'default'}
              meta={d.primaryId ? `${newsSent.pos} positive, ${newsSent.neu} neutral, ${newsSent.neg} negative${newsCompAvg != null ? ` · competitors ${signed(newsCompAvg)}` : ''}` : 'Pick one brand to see this'}
            />
          </li>
          <li>
            <Stat surface="panel" label="Social posts" value={posts.length.toLocaleString('en-GB')} meta={socToday ? `${socToday} today · ${socScored} scored` : `${socScored} scored`} />
          </li>
          <li>
            <Stat
              surface="panel"
              label="Social sentiment (net)"
              value={signed(socNet)}
              tone={socNet == null ? 'default' : socNet > 0 ? 'success' : socNet < 0 ? 'error' : 'default'}
              meta={`${soc.pos} positive, ${soc.neu} neutral, ${soc.neg} negative${socCompAvg != null ? ` · competitors ${signed(socCompAvg)}` : ''}`}
            />
          </li>
          <li>
            <Stat surface="panel" label="Coverage spikes" value={d.alerts.length} tone={highSpikes ? 'error' : 'default'} meta={highSpikes ? `${highSpikes} high` : 'None high'} />
          </li>
          <li>
            <Stat
              surface="panel"
              label="Open incidents"
              value={openIncidents.length}
              tone={severeIncidents ? 'error' : 'default'}
              meta={openIncidents.length ? `${severeIncidents} high or critical` : 'None open'}
              action={<IconButton icon={<Icon name="ArrowRight" size="sm" />} label="Open the Incidents tab" onClick={() => goTo('incidents')} />}
            />
          </li>
        </Grid>
      </Panel>

      <Grid columns={emp?.overview ? 3 : 2} stackAt="wide" gap="md">
        <Panel title="Sentiment: news against social" description="Net sentiment is positive minus negative, as a share of scored items. Neutral items pull it towards 0." headingLevel={3}>
          <Stack gap="md">
            <StackedBars
              title="Sentiment of news and social"
              series={[{ id: 'pos', label: 'Positive', color: 'positive' }, { id: 'neu', label: 'Neutral', color: 'neutral' }, { id: 'neg', label: 'Negative', color: 'negative' }]}
              rows={[
                { id: 'news', label: `News: net ${signed(newsNet)}`, values: [newsSent.pos, newsSent.neu, newsSent.neg] },
                { id: 'social', label: `Social: net ${signed(socNet)}`, values: [soc.pos, soc.neu, soc.neg] },
              ]}
              emptyText="Nothing scored in this period."
            />
            {(newsCompAvg != null || socCompAvg != null) && (
              <Text variant="caption">News{vsComp(newsNet, newsCompAvg) || ': no competitor figure'}. Social{vsComp(socNet, socCompAvg) || ': no competitor figure'}.</Text>
            )}
            {newsNet != null && socNet != null && Math.abs(newsNet - socNet) >= 25 && (
              <Banner tone="warning" title="Social and news disagree" description={`Social sentiment is ${Math.abs(newsNet - socNet)} points ${socNet < newsNet ? 'below' : 'above'} the news coverage.`} />
            )}
          </Stack>
        </Panel>

        <Panel title="What the negative coverage is about" description="Negative articles by category, from up to 200 recent articles. Open one to see its articles." headingLevel={3}>
          {negCats.length ? (
            <Stack as="ul" gap="sm" label="Negative coverage by category">
              {negCats.map(([cat, n]) => (
                <li key={cat}>
                  <Stack gap="sm">
                    <Button variant="ghost" size="sm" onClick={() => goTo('articles', { selectedCategories: [cat], page: 1 })}>{cat}</Button>
                    <Meter label={`${cat}: negative articles`} value={n} max={negCats[0][1]} valueText={`${n}`} tone="error" />
                  </Stack>
                </li>
              ))}
            </Stack>
          ) : (
            <Text>{negNews.length ? `${negNews.length} negative ${negNews.length === 1 ? 'article' : 'articles'} in this period, none with a category yet.` : 'No negative articles in this sample.'}</Text>
          )}
        </Panel>

        {emp?.overview && (
          <Panel
            title="Employee signal"
            headingLevel={3}
            headerAside={<Button variant="ghost" size="sm" onClick={() => goTo('workforce')}>Workforce</Button>}
          >
            <Grid as="ul" columns={2} stackAt="never" gap="sm" label="Employee signal">
              <li><Stat size="compact" label="Glassdoor rating" value={emp.overview.rating != null ? `${emp.overview.rating} of 5` : '–'} tone={emp.overview.rating != null && emp.overview.rating < 3 ? 'error' : 'default'} /></li>
              <li><Stat size="compact" label="Positive business outlook" value={outlook != null ? `${outlook}%` : '–'} tone={outlook != null && outlook < 45 ? 'error' : 'default'} /></li>
              <li>
                <Stat
                  size="compact"
                  label="Recent reviews"
                  value={emp.review_sentiment.scored ? signed(emp.review_sentiment.net) : '–'}
                  meta={emp.review_sentiment.scored ? `${emp.review_sentiment.pos} positive, ${emp.review_sentiment.neg} negative` : 'No recent reviews'}
                  tone={emp.review_sentiment.net != null && emp.review_sentiment.net < 0 ? 'error' : 'default'}
                />
              </li>
              <li>
                <Stat
                  size="compact"
                  label="Workforce risks"
                  value={emp.workforce_risks.length}
                  meta={emp.workforce_risks.filter((w) => w.severity === 'high').length ? `${emp.workforce_risks.filter((w) => w.severity === 'high').length} high` : 'None high'}
                  tone={emp.workforce_risks.some((w) => w.severity === 'high') ? 'error' : 'default'}
                />
              </li>
            </Grid>
          </Panel>
        )}
      </Grid>

      {d.apps && d.apps.brand_id === d.primaryId && d.apps.apps.length > 0 && (
        <Panel title="App ratings" description="Collected daily from Google Play and weekly from the App Store." headingLevel={3}>
          <Table
            caption="App ratings"
            hideCaption
            rows={d.apps.apps}
            rowKey={(a) => `${a.store}-${a.app_id}-${a.country}`}
            columns={[
              { key: 'app', header: 'App', rowHeader: true, render: (a) => <Stack gap="sm"><span>{a.app_id}</span><Text variant="caption">{a.store === 'google_play' ? 'Google Play' : 'App Store'} · {a.country.toUpperCase()}</Text></Stack> },
              { key: 'rating', header: 'Store rating', align: 'end', render: (a) => (a.rating != null ? a.rating.toFixed(2) : '–') },
              { key: 'change', header: 'Change, 30 days', align: 'end', render: (a) => (a.rating_change_30d != null ? signed(Number(a.rating_change_30d.toFixed(2))) : '–') },
              { key: 'ours', header: 'Our reviews, 30 days', align: 'end', render: (a) => (a.collected?.avg_30d != null ? `${a.collected.avg_30d.toFixed(1)} from ${a.collected.n_30d}` : '–') },
              { key: 'count', header: 'Store reviews', align: 'end', render: (a) => fmtCount(a.review_count) ?? '–' },
            ]}
          />
        </Panel>
      )}

      {timeline && (
        <Panel title="Sentiment over time: news against social" description={`Weekly net sentiment. Weeks with fewer than ${MIN_SCORED} scored items are skipped. Dashed lines are the competitor average.`} headingLevel={3}>
          <LineChart
            title="Weekly net sentiment, news against social"
            categories={timeline.map((r) => r.w.slice(5))}
            categoryLabels={timeline.map((r) => `Week of ${r.w}`)}
            series={[
              { id: 'news', label: 'News', color: 1, values: timeline.map((r) => r.news) },
              { id: 'social', label: 'Social', color: 2, values: timeline.map((r) => r.social) },
              ...(timeline.some((r) => r.compNews != null) ? [{ id: 'compNews', label: 'Competitors, news', color: 1 as const, dashed: true, values: timeline.map((r) => r.compNews) }] : []),
              ...(timeline.some((r) => r.compSocial != null) ? [{ id: 'compSocial', label: 'Competitors, social', color: 2 as const, dashed: true, values: timeline.map((r) => r.compSocial) }] : []),
            ]}
            yDomain={[-100, 100]}
            yTicks={[-100, -50, 0, 50, 100]}
            baseline={0}
            formatValue={(v) => signed(v)}
          />
        </Panel>
      )}

      <Grid columns={2} stackAt="wide" gap="md">
        <Panel title="News" description="Adverse stories first, one row per story." headingLevel={3} headerAside={<Button variant="ghost" size="sm" onClick={() => goTo('articles')}>All articles</Button>}>
          <Stack gap="md">
            {negShown.length + otherShown.length === 0 && <Text>{bw.loadingArticles ? 'Loading…' : 'No classified articles in this period.'}</Text>}
            {negShown.length > 0 && (
              <Stack as="ul" gap="sm" label="Adverse news">
                {negShown.map((a) => (
                  <NewsRow
                    key={`${a.uri}-${a.brand_id}`}
                    a={a}
                    review={reviewOf(a)}
                    signalsAvailable={bw.signalsAvailable}
                    onOpen={() => openArticle({ ...a })}
                    onSignals={() => openSignals({ uri: a.uri, title: a.title, brand_id: a.brand_id })}
                    onReview={(s) => void doReview(a, s)}
                    onIncident={() => setAttach({ refs: [a.uri], label: a.title || a.uri, brandId: a.brand_id ?? null })}
                  />
                ))}
              </Stack>
            )}
            {otherShown.length > 0 && (
              <>
                {negShown.length > 0 && <Eyebrow as="h4">Other coverage</Eyebrow>}
                <Stack as="ul" gap="sm" label="Other news">
                  {otherShown.map((a) => (
                    <NewsRow
                      key={`${a.uri}-${a.brand_id}`}
                      a={a}
                      review={reviewOf(a)}
                      signalsAvailable={bw.signalsAvailable}
                      onOpen={() => openArticle({ ...a })}
                      onSignals={() => openSignals({ uri: a.uri, title: a.title, brand_id: a.brand_id })}
                      onReview={(s) => void doReview(a, s)}
                      onIncident={() => setAttach({ refs: [a.uri], label: a.title || a.uri, brandId: a.brand_id ?? null })}
                    />
                  ))}
                </Stack>
              </>
            )}
          </Stack>
        </Panel>

        <Panel
          title="Social"
          headingLevel={3}
          description={sort === 'reach' ? `Most amplified first; posts with reach under ${REACH_FLOOR} are left out.` : undefined}
          headerAside={
            <Stack direction="row" gap="sm">
              <Select
                label="Order posts by"
                hideLabel
                options={[{ value: 'reach', label: 'Most amplified' }, { value: 'newest', label: 'Newest' }, { value: 'relevance', label: 'Most relevant' }]}
                value={sort}
                onValueChange={(v) => setSort(v as LedgerSort)}
              />
              <Button variant="ghost" size="sm" onClick={() => goTo('social')}>All social</Button>
            </Stack>
          }
        >
          <Stack gap="md">
            <Eyebrow as="h4">Negative</Eyebrow>
            {negLedger.length ? (
              <Stack as="ul" gap="sm" label="Negative posts">
                {negLedger.map((p) => <SocialRow key={p.uri} p={p} onIncident={() => setAttach(postAttach(p))} onFlag={() => flagPost(p)} onAuthor={() => openAccount(p.platform, handleOf(p))} />)}
              </Stack>
            ) : <Text variant="caption">{ledgerEmpty('negative')}</Text>}
            <Eyebrow as="h4">Positive</Eyebrow>
            {posLedger.length ? (
              <Stack as="ul" gap="sm" label="Positive posts">
                {posLedger.map((p) => <SocialRow key={p.uri} p={p} onIncident={() => setAttach(postAttach(p))} onFlag={() => flagPost(p)} onAuthor={() => openAccount(p.platform, handleOf(p))} />)}
              </Stack>
            ) : <Text variant="caption">{ledgerEmpty('positive')}</Text>}
          </Stack>
        </Panel>
      </Grid>

      {(d.fc.fans.length > 0 || d.fc.critics.length > 0) && (
        <Grid columns={2} stackAt="wide" gap="md">
          <FanList title="Top fans" kind="fan" rows={d.fc.fans} profiles={d.profiles} onAuthor={() => goTo('social')} onOpen={openAccount} />
          <FanList title="Top critics" kind="critic" rows={d.fc.critics} profiles={d.profiles} onAuthor={() => goTo('social')} onOpen={openAccount} />
        </Grid>
      )}

      <Coverage ctx={ctx} d={d} />

      <AlertSettingsDialog open={alertsOpen} onOpenChange={setAlertsOpen} notify={notify} />
      <AddToIncidentDialog source={attach} onClose={() => setAttach(null)} onDone={() => void d.loadIncidents()} notify={notify} />
    </>
  );
}
