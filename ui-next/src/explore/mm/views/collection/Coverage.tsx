import { useEffect, useMemo, useState } from 'react';
import {
  ActivityRow, Banner, Button, Checkbox, Chip, Grid, Icon, Panel, SegmentedControl, Skeleton, Stack, Stat, Table, Text, TextLink,
} from '@aunoo/ui';
import {
  feedUrl, getCorpusArticles, getCorpusSummary, getLeaderboards, reviewPosts, scanCorpus,
  type ArticleClass, type CorpusArticle, type CorpusSummary, type Leaderboards,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { LinkButton, VendorLink } from '../../shared/SortTable';
import { GroupSection } from './CoverageCard';
import { CoverageTimeline } from './CoverageTimeline';
import { engagementOf, fmtDateTime, groupByDay, groupByKind, groupByVendor } from './labels';

/*
 * Articles already in the database that match this market's phrases, as the old Coverage sub-view.
 * Brand classification matches vendor names, so an article about the category that names no vendor
 * never reaches it; this list does. Grouping reads the whole loaded batch at once, so the list is one
 * window that widens on request rather than pages.
 */

const COVERAGE_START = 300;
const COVERAGE_STEP = 200;
const COVERAGE_MAX = 500; // the API's own ceiling
type GroupMode = 'vendor' | 'day' | 'kind' | 'timeline';

const ORIGINS = [
  { value: 'all', label: 'All' },
  { value: 'corpus', label: 'From other topics' },
  { value: 'collected', label: 'From this market' },
];
const CLASSES: [string, string][] = [['', 'Any kind'], ['news', 'News'], ['vendor', 'Vendor blogs'], ['social', 'Vendor posts'], ['discussion', 'Practitioners'], ['research', 'Research']];

export function Coverage({ ctx }: { ctx: MmContext }) {
  const { marketId, periodDays, vendors, colours } = ctx;
  const [corpus, setCorpus] = useState<CorpusSummary | null>(null);
  const [articles, setArticles] = useState<CorpusArticle[] | null>(null);
  const [more, setMore] = useState(false);
  const [leaderboards, setLeaderboards] = useState<Leaderboards | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [origin, setOrigin] = useState<'' | 'corpus' | 'collected'>('');
  const [cls, setCls] = useState<'' | ArticleClass>('');
  const [allPosts, setAllPosts] = useState(false);
  const [vendorFilter, setVendorFilter] = useState<number | null>(null);
  const [limit, setLimit] = useState(COVERAGE_START);
  const [groupMode, setGroupMode] = useState<GroupMode>('day');
  const [sortMode, setSortMode] = useState<'newest' | 'popular'>('newest');
  const [busy, setBusy] = useState<null | 'scan' | 'review'>(null);
  const [result, setResult] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const [nonce, setNonce] = useState(0);

  // Any filter change starts the window over
  useEffect(() => setLimit(COVERAGE_START), [origin, cls, allPosts, vendorFilter]);

  useEffect(() => {
    let live = true;
    // Story clustering runs whatever the grouping, so the "sources on this story" badge shows everywhere
    Promise.all([
      getCorpusSummary(marketId, periodDays),
      getCorpusArticles(marketId, { limit, offset: 0, origin: origin || undefined, classes: cls || undefined, allPosts, group: true, vendorId: vendorFilter ?? undefined }),
    ]).then(
      ([sum, list]) => {
        if (!live) return;
        setCorpus(sum);
        setArticles(list.articles);
        setMore(list.has_more);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [marketId, periodDays, origin, cls, allPosts, vendorFilter, limit, nonce]);

  // Rankings ignore the type filters above; they follow only the shared period
  useEffect(() => {
    let live = true;
    getLeaderboards(marketId, periodDays).then((r) => live && setLeaderboards(r), () => live && setLeaderboards(null));
    return () => {
      live = false;
    };
  }, [marketId, periodDays]);

  const rescan = () => ctx.askConfirm({
    title: 'Rescan the article database?',
    message: 'This reads up to 50,000 stored articles against the market’s phrases and adds or re-scores matches. No AI and no paid sources are used, but it can take a while.',
    action: 'Rescan',
    onConfirm: async () => {
      setBusy('scan');
      setResult(null);
      try {
        const r = await scanCorpus(marketId, { limit: 50000 });
        setResult({ tone: 'success', text: `${r.matched} articles matched on ${r.terms} phrases: ${r.inserted} new, ${r.updated} re-scored.${r.truncated ? ' The row limit was reached; run it again to continue.' : ''}` });
        setNonce((n) => n + 1);
      } catch (e) {
        setResult({ tone: 'error', text: `The scan failed: ${errorText(e)}` });
      } finally {
        setBusy(null);
      }
    },
  });

  const review = () => ctx.askConfirm({
    title: 'Review vendor posts with the AI?',
    message: 'The AI reads up to 600 vendor posts that haven’t been reviewed yet and judges each one an announcement, an opinion or promotion. This costs AI usage.',
    action: 'Review posts',
    onConfirm: async () => {
      setBusy('review');
      setResult(null);
      try {
        const r = await reviewPosts(marketId, { limit: 600 });
        setResult({
          tone: 'success',
          text: r.candidates === 0
            ? 'Every vendor post has already been read.'
            : `Read ${r.reviewed} posts with ${r.model}: ${r.counts.signal} announcements, ${r.counts.commentary} opinions, ${r.counts.noise} promotion.${r.failed_batches ? ` ${r.failed_batches} batches failed.` : ''}`,
        });
        setNonce((n) => n + 1);
      } catch (e) {
        setResult({ tone: 'error', text: `The review failed: ${errorText(e)}` });
      } finally {
        setBusy(null);
      }
    },
  });

  const groups = useMemo(() => {
    if (!articles) return [];
    // "Most reactions" re-sorts the loaded set; the server already sends newest first
    const ordered = sortMode === 'popular' ? [...articles].sort((a, b) => engagementOf(b) - engagementOf(a)) : articles;
    return groupMode === 'vendor' ? groupByVendor(ordered) : groupMode === 'kind' ? groupByKind(ordered) : groupByDay(ordered);
  }, [articles, groupMode, sortMode]);

  const reviewed = corpus ? (corpus.by_verdict?.signal ?? 0) + (corpus.by_verdict?.commentary ?? 0) + (corpus.by_verdict?.noise ?? 0) : 0;
  const quietNetworks = leaderboards?.networks.filter((n) => !n.most_discussed.length && !n.most_shared.length && !n.top_posts.length) ?? [];
  const topPosts = leaderboards
    ? leaderboards.networks.flatMap((n) => n.top_posts.map((p) => ({ ...p, platform: n.platform }))).sort((a, b) => b.engagement - a.engagement).slice(0, 5)
    : [];
  const filterVendor = vendorFilter !== null ? vendors?.find((v) => v.brand_id === vendorFilter)?.display_name ?? `vendor ${vendorFilter}` : null;

  return (
    <>
      <Panel
        title="Coverage"
        description="Articles already in the database that match this market’s phrases. Brand classification matches vendor names, so an article about the category that names no vendor never reaches it. This list does."
        headerAside={
          <Stack direction="row" gap="sm">
            <TextLink href={feedUrl(marketId)} external>RSS feed</TextLink>
            <Button variant="secondary" size="sm" iconStart={<Icon name="MagnifyingGlass" size="sm" />} busy={busy === 'scan'} disabled={busy !== null} onClick={rescan}>Rescan articles</Button>
            <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} busy={busy === 'review'} disabled={busy !== null} onClick={review}>Review vendor posts</Button>
          </Stack>
        }
      >
        <Stack gap="md">
          {result && <Banner tone={result.tone} title={result.tone === 'error' ? 'Something went wrong' : 'Done'} description={result.text} />}
          {error && <Banner tone="error" title="Coverage didn’t load" description={error} />}
          {corpus && (
            <Grid columns={3}>
              <Stat label="Matched articles (all time)" value={corpus.total.toLocaleString()} meta={`Last scan ${fmtDateTime(corpus.last_scan)}`} />
              <Stat label="From other topics (all time)" value={corpus.corpus.toLocaleString()} meta="Collected for something else, relevant here" />
              <Stat label={`Published in the last ${corpus.recent_days} days`} value={corpus.recent.toLocaleString()} meta="By publication date, not collection date. The only one of these three that follows the period picked above." />
            </Grid>
          )}
        </Stack>
      </Panel>

      {leaderboards && (
        <>
          <Panel
            title={`Most popular, last ${periodDays} days`}
            description="Ranked by reactions on the post itself (likes, comments and reposts), owned or earned. Only posts a platform reports engagement for are ranked; most news and vendor-blog coverage carries none."
          >
            {topPosts.length === 0 ? <Text>No engagement data on any matched post yet.</Text> : (
              <Stack as="ul" gap="sm" label="Most popular posts">
                {topPosts.map((p) => (
                  <ActivityRow
                    key={p.uri}
                    as="li"
                    primary={<TextLink href={p.uri} external>{p.title ?? p.uri}</TextLink>}
                    secondary={`${p.platform} · ${p.is_owned ? 'the vendor’s own post' : 'someone else’s post'} · ${p.engagement} reactions`}
                  />
                ))}
              </Stack>
            )}
          </Panel>
          <Text variant="caption">
            Career moves and Crunchbase score changes for this market are on the <LinkButton onClick={() => ctx.goTo('analysis')}>Analysis view</LinkButton>, not repeated here.
          </Text>
          <Panel
            title="By network"
            description="Most discussed and most shared only count posts tagged to a vendor. A post is tagged when it names the vendor by one of its reviewed keywords, so a practitioner writing “the Dropzone thing” isn’t counted. A network with nothing here had nobody naming a vendor on it in this period."
          >
            <Stack gap="md">
              {quietNetworks.length > 0 && (
                <Text variant="caption">{`Nothing tagged to a vendor yet on ${quietNetworks.map((n) => n.platform[0].toUpperCase() + n.platform.slice(1)).join(', ')}.`}</Text>
              )}
              <Grid columns={3}>
                {leaderboards.networks.filter((n) => !quietNetworks.includes(n)).map((n) => (
                  <Panel key={n.platform} title={n.platform[0].toUpperCase() + n.platform.slice(1)} headingLevel={4}>
                    <Stack gap="sm">
                      <Text variant="label">Most discussed</Text>
                      {n.most_discussed.length === 0 ? <Text variant="caption">Not enough tagged posts yet.</Text> : n.most_discussed.map((v) => (
                        <Stack key={v.brand_id} direction="row" justify="between" gap="sm">
                          <VendorLink id={v.brand_id} name={v.vendor} color={colours.byId(v.brand_id)} onOpen={ctx.openVendor} />
                          <Text as="span" variant="caption">{`${v.mentions} mentions`}</Text>
                        </Stack>
                      ))}
                      <Text variant="label">Most shared</Text>
                      {n.most_shared.length === 0 ? <Text variant="caption">Not enough tagged posts yet.</Text> : n.most_shared.map((v) => (
                        <Stack key={v.brand_id} direction="row" justify="between" gap="sm">
                          <VendorLink id={v.brand_id} name={v.vendor} color={colours.byId(v.brand_id)} onOpen={ctx.openVendor} />
                          <Text as="span" variant="caption">{`${v.shares} shares`}</Text>
                        </Stack>
                      ))}
                      <Text variant="label">Top post</Text>
                      {n.top_posts.length === 0 ? <Text variant="caption">No engagement data.</Text> : <TextLink href={n.top_posts[0].uri} external>{n.top_posts[0].title ?? n.top_posts[0].uri}</TextLink>}
                    </Stack>
                  </Panel>
                ))}
              </Grid>
            </Stack>
          </Panel>
        </>
      )}

      {corpus && (
        <Grid columns={2}>
          <Panel title="Phrases that matched">
            <Stack direction="row" gap="sm">
              {corpus.top_terms.map((t) => <Chip key={t.term} tone="neutral">{`${t.term} · ${t.n}`}</Chip>)}
            </Stack>
          </Panel>
          <Panel title="Sources">
            <Table caption="Top sources" hideCaption rows={corpus.top_sources} rowKey={(s) => s.source} columns={[{ key: 'source', header: 'Source', rowHeader: true }, { key: 'n', header: 'Articles', align: 'end' }]} />
          </Panel>
        </Grid>
      )}

      {corpus?.signal_kinds && corpus.signal_kinds.length > 0 && (
        <Panel
          title="What vendors announced"
          description={`Each post is read once and judged. Only announcements reach the feed, the timeline and the observer agents; the rest are conference notices, employee spotlights and commentary. ${corpus.by_verdict?.signal ?? 0} of ${reviewed} reviewed posts are announcements.`}
        >
          <Stack direction="row" gap="sm">
            {corpus.signal_kinds.map((k) => (
              <Chip key={k.kind} tone="success" label={`Group the list below by kind to see what was announced as ${k.kind}`} onClick={() => setGroupMode('kind')}>{`${k.kind} · ${k.n}`}</Chip>
            ))}
          </Stack>
        </Panel>
      )}

      <Panel title="Matched articles">
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <SegmentedControl label="Where it was collected" options={ORIGINS} value={origin || 'all'} onValueChange={(v) => setOrigin(v === 'all' ? '' : (v as 'corpus' | 'collected'))} />
            <SegmentedControl label="Group by" options={[{ value: 'day', label: 'Day' }, { value: 'vendor', label: 'Vendor' }, { value: 'kind', label: 'Kind' }, { value: 'timeline', label: 'Timeline' }]} value={groupMode} onValueChange={(v) => setGroupMode(v as GroupMode)} />
            <SegmentedControl label="Sort by" options={[{ value: 'newest', label: 'Newest' }, { value: 'popular', label: 'Most reactions' }]} value={sortMode} onValueChange={(v) => setSortMode(v as 'newest' | 'popular')} />
          </Stack>
          <Stack direction="row" gap="sm">
            {CLASSES.map(([id, label]) => (
              <Chip
                key={id || 'any'}
                tone={cls === id ? 'accent' : 'neutral'}
                variant={cls === id ? 'fill' : 'outline'}
                onClick={() => setCls(id as '' | ArticleClass)}
              >
                {id && corpus?.by_class ? `${label} (${corpus.by_class[id as ArticleClass] ?? 0})` : label}
              </Chip>
            ))}
          </Stack>
          <Stack direction="row" gap="sm">
            <Checkbox label="Include posts judged to be promotion" checked={allPosts} onCheckedChange={setAllPosts} />
            {filterVendor && (
              <Chip tone="accent" icon={<Icon name="X" size="sm" />} label={`Stop filtering on ${filterVendor}`} onClick={() => setVendorFilter(null)}>{`Only ${filterVendor}`}</Chip>
            )}
          </Stack>

          {articles === null ? <Skeleton variant="text" lines={8} /> : articles.length === 0 ? (
            <Text>Nothing matched. Run a rescan, or widen the market’s phrases in collection settings.</Text>
          ) : (
            <>
              {groupMode === 'timeline'
                ? <CoverageTimeline articles={articles} colours={colours} />
                : groups.map((g) => <GroupSection key={g.key} group={g} colours={colours} vendorFilter={vendorFilter} onVendorFilter={setVendorFilter} />)}
              <Stack direction="row" gap="sm">
                <Text as="span" variant="caption">{`Showing ${articles.length}${more ? '+' : ''} matched articles`}</Text>
                {more && limit < COVERAGE_MAX && (
                  <Button variant="secondary" size="sm" onClick={() => setLimit((l) => Math.min(COVERAGE_MAX, l + COVERAGE_STEP))}>{`Load ${Math.min(COVERAGE_STEP, COVERAGE_MAX - limit)} more`}</Button>
                )}
                {more && limit >= COVERAGE_MAX && <Text as="span" variant="caption">{`More than ${COVERAGE_MAX} matched. Narrow the list with a filter to see the rest.`}</Text>}
              </Stack>
            </>
          )}
        </Stack>
      </Panel>
    </>
  );
}
