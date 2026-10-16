import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banner, Button, Checkbox, Chip, DonutChart, FilterChipRow, Grid, Icon, LineChart, Panel, SegmentedControl, Skeleton, Stack, StackedBarChart,
  StackedBars, Stat, Table, Text, type ChartColor,
} from '@aunoo/ui';
import { getSocialPosts, setFindingState, setupSocialMonitoring, type BWSocialPost } from '@monolith/brandWatcherApi';
import { getKeywordGroups } from '@monolith/gatherApi';
import { SOCIAL_NEG_THEMES } from '@monolith/socialAnalytics';
import { downloadSocialReport } from '@monolith/socialReportHtml';
import type { BWAccountProfile } from '@monolith/socialProfileApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';
import { AddToIncidentDialog, type IncidentSource } from '../overlays/AddToIncidentDialog';
import { ExportDialog } from './social/ExportDialog';
import { FansCritics } from './social/FansCritics';
import { EMPTY_LANE, Lane, type LaneFilter, type PageFilters } from './social/Lane';
import { Swimlane, type SwimlaneItem } from '../../shared/Swimlane';
import { SocialSettingsDialog } from '../overlays/SocialSettingsDialog';
import { PLATFORM_ORDER, brandOf, engOf, netOf, platLabel, queueAccount, sentOf, signed } from './social/helpers';
import { SplitBar } from '../charts';

/*
 * Social listening, as the old Social sub-tab (ui/src/components/newsfeed/BrandWatcherTab.tsx):
 * the brand's posts from X, Bluesky, Reddit, Instagram and TikTok, each scored for relevance and
 * sentiment. Everything here reads stored posts; "Add social monitoring" changes collection.
 */

const SLOTS: ChartColor[] = [1, 2, 3, 4, 5, 0];
const INTRO_KEY = 'bw_social_intro_dismissed';
const REL_OPTIONS = [{ value: '0', label: 'All' }, { value: '0.4', label: '0.4 and up' }, { value: '0.6', label: '0.6 and up' }];
const niceMax = (n: number) => (n <= 5 ? 5 : Math.ceil(n / 10 ** Math.floor(Math.log10(n))) * 10 ** Math.floor(Math.log10(n)));
const NO_FILTERS: PageFilters = { author: null, day: null, theme: null, brand: null };

/** Day buckets up to ~60 days, week buckets (Monday) beyond, on one shared axis */
function bucketAxis(daysBack: number) {
  const windowDays = daysBack > 0 ? Math.min(daysBack, 365) : 90;
  const weekly = windowDays > 60;
  const monday = (d: Date) => {
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d;
  };
  const bucketOf = (ds: string | null) => {
    const day = (ds || '').slice(0, 10);
    if (!day) return null;
    if (!weekly) return day;
    const d = new Date(`${day}T00:00:00Z`);
    return Number.isNaN(+d) ? null : monday(d).toISOString().slice(0, 10);
  };
  const buckets: string[] = [];
  const cur = new Date();
  cur.setUTCDate(cur.getUTCDate() - windowDays);
  if (weekly) monday(cur);
  const today = new Date().toISOString().slice(0, 10);
  while (cur.toISOString().slice(0, 10) <= today) {
    buckets.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() + (weekly ? 7 : 1));
  }
  return { buckets, bucketOf, weekly };
}

export function Social(ctx: BwContext) {
  const { bw, notify, askConfirm, focusBrand, selectedBrands, goTo } = ctx;
  const { brands, config, social, loadingSocial, fetchSocial } = bw;
  const [minRel, setMinRel] = useState(0.4);
  const [inclUneval, setInclUneval] = useState(false);
  const [scope, setScope] = useState<'selected' | 'all'>('selected');
  const [bench, setBench] = useState<BWSocialPost[] | null>(null);
  const [groupInfo, setGroupInfo] = useState<{ lastChecked: string | null } | null | undefined>(undefined);
  const [introDismissed, setIntroDismissed] = useState(() => {
    try {
      return localStorage.getItem(INTRO_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [enabling, setEnabling] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [attach, setAttach] = useState<IncidentSource | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [left, setLeft] = useState<LaneFilter>(EMPTY_LANE);
  const [right, setRight] = useState<LaneFilter>(EMPTY_LANE);
  const [page, setPage] = useState<PageFilters>(NO_FILTERS);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // The old tab's "primarySelectedId": the first header-picked brand, else the focus brand
  const brand = selectedBrands[0] ?? focusBrand;

  const reload = useCallback(() => fetchSocial(minRel, undefined, inclUneval, scope), [fetchSocial, minRel, inclUneval, scope]);
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.daysBack, config.selectedBrandIds, config.selectedTopics, scope, brands.length]);

  // Every brand's on-brand posts, for the brand comparison (independent of the scope switch)
  useEffect(() => {
    if (brands.length < 2) {
      setBench(null);
      return;
    }
    let stale = false;
    getSocialPosts(brands.map((b) => `Brand Monitoring ${b.display_name}`), config.daysBack, 0.4, undefined, false, { limit: 2000 }).then(
      (d) => !stale && setBench(d.posts ?? []),
      () => !stale && setBench(null),
    );
    return () => {
      stale = true;
    };
  }, [brands, config.daysBack]);

  // Whether this brand has a social monitoring group, so an empty feed says "not set up" vs "nothing found"
  useEffect(() => {
    if (enabling) return;
    if (!brand) {
      setGroupInfo(null);
      return;
    }
    let stale = false;
    setGroupInfo(undefined);
    getKeywordGroups().then(
      (gs) => {
        if (stale) return;
        const g = gs.find((x) => x.name === `${brand.display_name} - Social`);
        setGroupInfo(g ? { lastChecked: g.last_checked_at ?? null } : null);
      },
      () => !stale && setGroupInfo(null),
    );
    return () => {
      stale = true;
    };
  }, [brand, enabling]);

  // ── What the loaded posts say ──
  const view = useMemo(() => {
    if (!social) return null;
    const posts = (social.posts ?? []).filter((p) => p.review_status !== 'false_positive' && !hidden.has(p.uri));
    const sent = { positive: 0, neutral: 0, negative: 0, unrated: 0 };
    const plat: Record<string, number> = {};
    const byDay: Record<string, { positive: number; neutral: number; negative: number; unrated: number }> = {};
    for (const p of posts) {
      const s = sentOf(p.sentiment);
      sent[s]++;
      plat[p.platform] = (plat[p.platform] || 0) + 1;
      const d = (p.publication_date || '').slice(0, 10);
      if (d) (byDay[d] ||= { positive: 0, neutral: 0, negative: 0, unrated: 0 })[s]++;
    }
    const scored = sent.positive + sent.neutral + sent.negative;
    const perc: Record<string, { pos: number; neg: number; neu: number; total: number }> = {};
    for (const p of posts) {
      if ((p.relevance ?? 0) < 0.4) continue;
      const c = (perc[p.platform] ||= { pos: 0, neg: 0, neu: 0, total: 0 });
      const s = sentOf(p.sentiment);
      if (s === 'positive') c.pos++;
      else if (s === 'negative') c.neg++;
      else if (s === 'neutral') c.neu++;
      c.total++;
    }
    // Networks with fewer than 5 scored posts go last and are marked: one post's +100 is noise
    const perception = Object.entries(perc)
      .map(([platform, c]) => {
        const n = c.pos + c.neg + c.neu;
        return { platform, ...c, net: netOf(c.pos, c.neg, n), low: n < 5 };
      })
      .filter((d) => d.total > 0)
      .sort((a, b) => Number(a.low) - Number(b.low) || (b.net ?? -999) - (a.net ?? -999));
    return {
      all: posts, sent, plat, perception, net: netOf(sent.positive, sent.negative, scored),
      days: Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)),
      platforms: PLATFORM_ORDER.filter((p) => plat[p]),
    };
  }, [social, hidden]);

  // Two columns start on different networks (best- and worst-perceived) instead of two identical "All" lists
  useEffect(() => {
    if (!view || left.platforms.length || right.platforms.length) return;
    const pc = view.perception;
    const [l, r] = pc.length >= 2 ? [pc[0].platform, pc[pc.length - 1].platform] : view.platforms.length >= 2 ? [view.platforms[0], view.platforms[1]] : [null, null];
    if (l && r && l !== r) {
      setLeft((f) => ({ ...f, platforms: [l] }));
      setRight((f) => ({ ...f, platforms: [r] }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const entities = useMemo(() => {
    const g: Record<string, { count: number; kws: Record<string, number> }> = {};
    for (const p of social?.posts ?? []) {
      const b = brandOf(p);
      const e = (g[b] ||= { count: 0, kws: {} });
      e.count++;
      for (const k of p.matched_keywords ?? []) e.kws[k] = (e.kws[k] || 0) + 1;
    }
    const rank = (n: string) => (brands.find((b) => b.display_name === n)?.is_primary ? 0 : 1);
    return Object.entries(g)
      .map(([name, v]) => ({ name, count: v.count, isPrimary: !!brands.find((b) => b.display_name === name)?.is_primary, keywords: Object.entries(v.kws).sort((a, b) => b[1] - a[1]) }))
      .sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
  }, [social, brands]);

  // ── Actions ──
  const onProfile = (platform: string, handle: string) => {
    queueAccount(platform, handle);
    goTo('accounts');
  };
  const brandIdOf = (p: BWSocialPost) => brands.find((b) => b.display_name === brandOf(p))?.id ?? null;
  const actions = {
    onProfile,
    onAttach: (p: BWSocialPost) => setAttach({ kind: 'article' as const, ref: p.uri, label: (p.summary || p.title || p.uri).slice(0, 120), brandId: brandIdOf(p) }),
    onFlag: (p: BWSocialPost) => {
      const id = brandIdOf(p);
      if (!id) {
        notify('This post’s brand couldn’t be found, so it can’t be flagged.');
        return;
      }
      askConfirm({
        title: 'Flag as a false positive?',
        message: 'The post leaves Brand Watcher and the alert counts. It stays in the database as a labelled example for tuning relevance.',
        action: 'Flag post',
        onConfirm: () => {
          setHidden((h) => new Set(h).add(p.uri));
          setFindingState(p.uri, id, 'false_positive').then(
            () => notify('Post flagged as a false positive'),
            (e: unknown) => {
              setHidden((h) => {
                const n = new Set(h);
                n.delete(p.uri);
                return n;
              });
              notify(`Not flagged: ${errorText(e)}`);
            },
          );
        },
      });
    },
  };
  const attachProfile = (p: BWAccountProfile) =>
    setAttach({ kind: 'account_profile', ref: `${p.platform}:${p.handle_canonical || p.handle}`, label: `@${p.handle} on ${platLabel(p.platform)}`, brandId: brand?.id ?? null });

  // Creates or refreshes the brand's social keyword group, which starts paid collection: ask first
  const enable = () => {
    if (!brand) return;
    askConfirm({
      title: `Set up or refresh social monitoring for ${brand.display_name}?`,
      message: 'This creates the brand’s social keyword group, or rewrites its keywords from the brand settings, and collects posts from X, Bluesky, Reddit, Instagram and TikTok every 24 hours. Each collection uses provider credits; pick the networks in Social settings.',
      action: 'Set up',
      onConfirm: () => void enableNow(),
    });
  };
  const enableNow = async () => {
    if (!brand) return;
    setEnabling(true);
    try {
      const r = await setupSocialMonitoring(brand.id, 24);
      notify(`Social monitoring ${r.created ? 'on' : 'updated'}: “${r.group_name}”, ${r.keywords_added} keywords, collected every ${r.interval_hours} hours. Posts arrive after the next run.`);
      void reload();
    } catch (e) {
      notify(`Not set up: ${errorText(e)}`);
    } finally {
      setEnabling(false);
    }
  };

  const report = async () => {
    setReporting(true);
    try {
      const topics = brand ? [`Brand Monitoring ${brand.display_name}`] : config.selectedTopics.length ? config.selectedTopics : undefined;
      const data = await getSocialPosts(topics, config.daysBack, 0, undefined, true, { limit: 5000 }).catch(() => social);
      downloadSocialReport({ brand: brand ?? undefined, daysBack: config.daysBack, social: data, generatedAt: new Date().toISOString() });
    } finally {
      setReporting(false);
    }
  };

  const setRel = (v: string) => {
    const n = Number(v);
    setMinRel(n);
    void fetchSocial(n, undefined, inclUneval, scope);
  };
  const setUneval = (on: boolean) => {
    setInclUneval(on);
    void fetchSocial(minRel, undefined, on, scope);
  };

  const filtersOn = page.author || page.day || page.theme || page.brand;
  const multiBrand = scope === 'all' || selectedBrands.length > 1;

  return (
    <>
      {social && social.total === 0 && groupInfo && (
        <Banner
          tone="info"
          title="No posts in this window"
          description={`Nothing about ${brand?.display_name ?? 'this brand'} in the last ${social.window_days} days matches these filters. Social monitoring is on${groupInfo.lastChecked ? `; the last collection ran ${new Date(groupInfo.lastChecked).toLocaleString('en-GB')}` : ''}.`}
        />
      )}
      {!(social && social.total > 0) && groupInfo === null && !introDismissed && (
        <Banner
          tone="info"
          title="Social mentions"
          description="Posts that mention this brand on X, Bluesky, Reddit, Instagram and TikTok. Each post is scored for whether it’s really about the brand, and for sentiment, so busy chatter stays readable."
          action={
            <Stack direction="row" gap="sm">
              <Button size="sm" iconStart={<Icon name="Plus" size="sm" />} disabled={enabling || !brand} onClick={enable}>{enabling ? 'Setting up…' : 'Add social monitoring'}</Button>
              <Button size="sm" variant="ghost" onClick={() => { setIntroDismissed(true); try { localStorage.setItem(INTRO_KEY, '1'); } catch { /* per visit */ } }}>Dismiss</Button>
            </Stack>
          }
        />
      )}

      <BrandCompare bench={bench} brands={brands.map((b) => b.display_name)} daysBack={config.daysBack} active={page.brand} onPick={(b) => setPage((f) => ({ ...f, brand: b }))} />
      <BrandSwimlane bench={bench} brands={brands} daysBack={config.daysBack} active={page.brand} onPick={(b) => setPage((f) => ({ ...f, brand: b }))} />

      <Panel
        title="Social posts"
        headingLevel={3}
        headerAside={
          <Stack direction="row" gap="sm">
            <Button size="sm" variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={!brands.length} onClick={() => setExportOpen(true)}>Export CSV</Button>
            <Button size="sm" variant="secondary" iconStart={<Icon name="FileText" size="sm" />} disabled={reporting || !brands.length} onClick={() => void report()}>{reporting ? 'Building…' : 'Social report (HTML)'}</Button>
            <Button size="sm" variant="secondary" iconStart={<Icon name="Plus" size="sm" />} disabled={enabling || !brand} onClick={enable}>{enabling ? 'Setting up…' : 'Add or refresh monitoring'}</Button>
            <Button size="sm" variant="secondary" iconStart={<Icon name="GearSix" size="sm" />} disabled={!brand} onClick={() => setSettingsOpen(true)}>Social settings</Button>
          </Stack>
        }
      >
        <Stack gap="md">
          <Stack direction="row" gap="lg">
            <SegmentedControl
              label="Which brands"
              value={scope}
              onValueChange={(v) => setScope(v as 'selected' | 'all')}
              options={[
                { value: 'selected', label: selectedBrands.length > 1 ? `${selectedBrands.length} picked brands` : `${brand?.display_name ?? 'Picked brand'} only` },
                { value: 'all', label: 'With competitors' },
              ]}
            />
            <SegmentedControl label="Minimum relevance" value={String(minRel)} onValueChange={setRel} options={REL_OPTIONS} />
            {minRel === 0 && <Checkbox label="Include posts not yet scored" checked={inclUneval} onCheckedChange={setUneval} />}
          </Stack>
          <Text variant="caption">0.4 and up keeps scored posts that are about the brand. “All” adds scored posts that are off-topic; posts not yet scored are often loose keyword matches.</Text>
        </Stack>
      </Panel>

      {loadingSocial && !social ? <Skeleton variant="block" size="chart" /> : !social || !view ? (
        <Text>No social data loaded.</Text>
      ) : (
        <>
          <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Social at a glance">
            <li><Stat surface="panel" label="Posts" value={social.total.toLocaleString('en-GB')} meta={`last ${social.window_days} days${social.owned_excluded ? ` · ${social.owned_excluded} of the brand’s own left out` : ''}`} /></li>
            <li><Stat surface="panel" label="Scored" value={social.evaluated.toLocaleString('en-GB')} meta="relevance and sentiment" /></li>
            <li><Stat surface="panel" label="Net sentiment" value={signed(view.net)} meta="% positive minus % negative" tone={view.net == null ? 'default' : view.net > 0 ? 'success' : view.net < 0 ? 'error' : 'default'} /></li>
            <li>
              <Stat
                surface="panel"
                label="Best and worst network"
                wrapValue
                value={(() => {
                  const w = view.perception.filter((d) => d.net != null);
                  if (!w.length) return '–';
                  const best = w[0];
                  const worst = w[w.length - 1];
                  return worst.platform !== best.platform ? `${platLabel(best.platform)} ${signed(best.net)}, ${platLabel(worst.platform)} ${signed(worst.net)}` : `${platLabel(best.platform)} ${signed(best.net)}`;
                })()}
                meta="net sentiment of on-brand posts"
              />
            </li>
          </Grid>

          {view.all.length > 0 && <Charts view={view} />}
          {view.all.length > 0 && <Sentiment posts={view.all} />}

          {view.perception.length > 0 && (
            <Panel title="Perception by network" description="Net sentiment (% positive minus % negative) of on-brand posts. Fewer than five scored posts is too few to judge." headingLevel={3}>
              <Table
                caption="Perception by network"
                hideCaption
                rows={view.perception}
                rowKey={(d) => d.platform}
                columns={[
                  { key: 'platform', header: 'Network', rowHeader: true, render: (d) => platLabel(d.platform) },
                  { key: 'net', header: 'Net', align: 'end', render: (d) => (d.net == null ? 'n/a' : signed(d.net)) },
                  // The old panel showed each network's split as a bar
                  {
                    key: 'mix', header: 'Positive / neutral / negative',
                    render: (d) => (
                      <Stack gap="sm">
                        <SplitBar pos={d.pos} neu={d.neu} neg={d.neg} label={platLabel(d.platform)} />
                        <Text as="span" variant="caption">{`${d.pos} / ${d.neu} / ${d.neg}`}</Text>
                      </Stack>
                    ),
                  },
                  { key: 'low', header: 'Sample', render: (d) => (d.low ? <Chip size="sm" tone="warning">Too few to judge</Chip> : <Chip size="sm" tone="muted">{d.total} posts</Chip>) },
                  { key: 'act', header: <span className="visually-hidden">Actions</span>, render: (d) => <Button variant="ghost" size="sm" onClick={() => setLeft((f) => ({ ...f, platforms: [d.platform] }))}>Show in left column</Button> },
                ]}
              />
            </Panel>
          )}

          <FansCritics
            posts={social.posts ?? []}
            brands={brands}
            focusBrand={brand?.display_name ?? null}
            onProfile={onProfile}
            onSeePosts={(platform, author) => setPage((f) => ({ ...f, author: { platform, author } }))}
            onAttachProfile={attachProfile}
            notify={notify}
          />

          <Timeline posts={view.all} page={page} setPage={setPage} />

          {filtersOn && (
            <Stack direction="row" gap="sm" label="Active filters">
              <Text variant="label" as="span">Showing only:</Text>
              {page.brand && <Chip tone="info" onClick={() => setPage((f) => ({ ...f, brand: null }))} label={`Clear brand filter ${page.brand}`}>{page.brand} ✕</Chip>}
              {page.author && <Chip tone="info" onClick={() => setPage((f) => ({ ...f, author: null }))} label={`Clear author filter @${page.author.author}`}>@{page.author.author} on {platLabel(page.author.platform)} ✕</Chip>}
              {page.day && <Chip tone="info" onClick={() => setPage((f) => ({ ...f, day: null }))} label={`Clear day filter ${page.day}`}>{page.day} ✕</Chip>}
              {page.theme && (
                <Chip tone="info" onClick={() => setPage((f) => ({ ...f, theme: null }))} label="Clear theme filter">
                  Negative about {SOCIAL_NEG_THEMES.find((t) => t.key === page.theme)?.label ?? 'other things'} ✕
                </Chip>
              )}
              <Button variant="ghost" size="sm" onClick={() => setPage(NO_FILTERS)}>Clear all</Button>
            </Stack>
          )}

          <Grid columns={2} stackAt="wide" gap="md">
            <Lane name="Left column" posts={view.all} platforms={view.platforms} entities={entities} filter={left} onChange={setLeft} page={page} actions={actions} multiBrand={multiBrand} />
            <Lane name="Right column" posts={view.all} platforms={view.platforms} entities={entities} filter={right} onChange={setRight} page={page} actions={actions} multiBrand={multiBrand} />
          </Grid>
        </>
      )}

      <ExportDialog open={exportOpen} onOpenChange={setExportOpen} brands={brands} preselected={config.selectedBrandIds} notify={notify} />
      <AddToIncidentDialog source={attach} onClose={() => setAttach(null)} notify={notify} />
      <SocialSettingsDialog brand={brand ?? null} open={settingsOpen} onClose={() => setSettingsOpen(false)} notify={notify} askConfirm={askConfirm} onChanged={() => void reload()} />
    </>
  );
}

/** Every brand's on-brand posts side by side: volume over time and the sentiment mix. Pick a brand to filter the posts below. */
/**
 * One lane per brand: a mark per day (per week beyond 60 days), sized by post volume and coloured by
 * the net sentiment of that day's scored posts, as the old tab's brand swimlanes. Picking a mark
 * filters the feed below to that brand, as clicking a lane did.
 */
function BrandSwimlane({ bench, brands, daysBack, active, onPick }: {
  bench: BWSocialPost[] | null;
  brands: { display_name: string; color?: string | null }[];
  daysBack: number;
  active: string | null;
  onPick: (b: string | null) => void;
}) {
  const data = useMemo(() => {
    if (!bench?.length) return null;
    const { buckets, bucketOf, weekly } = bucketAxis(daysBack);
    const cells = new Map<string, { brand: string; bucket: string; pos: number; neu: number; neg: number; total: number }>();
    for (const p of bench) {
      const b = brandOf(p);
      const bk = bucketOf(p.publication_date);
      if (!bk) continue;
      const key = `${b}|${bk}`;
      const c = cells.get(key) ?? { brand: b, bucket: bk, pos: 0, neu: 0, neg: 0, total: 0 };
      c.total++;
      const s = sentOf(p.sentiment);
      if (s === 'positive') c.pos++;
      else if (s === 'negative') c.neg++;
      else if (s === 'neutral') c.neu++;
      cells.set(key, c);
    }
    const present = new Set([...cells.values()].map((c) => c.brand));
    const lanes = brands.filter((b) => present.has(b.display_name)).map((b) => ({ id: b.display_name, label: b.display_name, color: b.color ?? undefined }));
    if (lanes.length < 2) return null;
    const items: SwimlaneItem[] = [...cells.values()].map((c) => {
      const scored = c.pos + c.neu + c.neg;
      const net = scored ? (c.pos - c.neg) / scored : null;
      const tone: SwimlaneItem['tone'] = net == null ? 'neutral' : net > 0.2 ? 'positive' : net < -0.2 ? 'negative' : 'accent';
      return {
        id: `${c.brand}|${c.bucket}`,
        lane: c.brand,
        date: c.bucket,
        weight: c.total,
        tone,
        label: `${c.brand}, ${weekly ? 'week of ' : ''}${c.bucket}: ${c.total} post${c.total === 1 ? '' : 's'} (${c.pos} positive, ${c.neu} neutral, ${c.neg} negative${scored < c.total ? `, ${c.total - scored} not scored` : ''})`,
        onSelect: () => onPick(active === c.brand ? null : c.brand),
      };
    });
    return { lanes, items, from: buckets[0], to: buckets[buckets.length - 1], weekly };
  }, [bench, brands, daysBack, active, onPick]);
  if (!data) return null;
  return (
    <Swimlane
      title={`Brand swimlanes: on-brand posts per ${data.weekly ? 'week' : 'day'}`}
      lanes={data.lanes}
      items={data.items}
      from={data.from}
      to={data.to}
      caption={`Each mark is one brand’s posts that ${data.weekly ? 'week' : 'day'}, larger for more posts. Green leans positive, red leans negative, amber is mixed and grey is not scored. Pick a mark to show only that brand’s posts below${active ? `; showing ${active} now, pick again to clear` : ''}.`}
      emptyText="No posts from two or more brands in this period."
    />
  );
}

function BrandCompare({ bench, brands, daysBack, active, onPick }: { bench: BWSocialPost[] | null; brands: string[]; daysBack: number; active: string | null; onPick: (b: string | null) => void }) {
  const data = useMemo(() => {
    if (!bench?.length) return null;
    const { buckets, bucketOf, weekly } = bucketAxis(daysBack);
    const lanes: Record<string, { cells: Record<string, number>; pos: number; neu: number; neg: number; un: number; total: number }> = {};
    for (const p of bench) {
      const b = brandOf(p);
      const bk = bucketOf(p.publication_date);
      if (!bk) continue;
      const l = (lanes[b] ||= { cells: {}, pos: 0, neu: 0, neg: 0, un: 0, total: 0 });
      l.cells[bk] = (l.cells[bk] || 0) + 1;
      l.total++;
      const s = sentOf(p.sentiment);
      if (s === 'positive') l.pos++;
      else if (s === 'negative') l.neg++;
      else if (s === 'neutral') l.neu++;
      else l.un++;
    }
    const order = brands.filter((n) => lanes[n]);
    return order.length < 2 ? null : { buckets, weekly, lanes, order };
  }, [bench, brands, daysBack]);
  if (!data) return null;
  const { buckets, weekly, lanes, order } = data;
  const top = [...order].sort((a, b) => lanes[b].total - lanes[a].total).slice(0, 5);
  const max = niceMax(Math.max(1, ...top.flatMap((n) => buckets.map((b) => lanes[n].cells[b] || 0))));
  return (
    <Panel title="Brands compared" description={`On-brand posts per ${weekly ? 'week' : 'day'} and the sentiment of each brand’s posts.`} headingLevel={3}>
      <Stack gap="lg">
        <LineChart
          title={`On-brand posts per ${weekly ? 'week' : 'day'}`}
          categories={buckets.map((b) => b.slice(5))}
          categoryLabels={buckets.map((b) => (weekly ? `Week of ${b}` : b))}
          series={top.map((n, i) => ({ id: n, label: n, color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: buckets.map((b) => lanes[n].cells[b] || 0) }))}
          yDomain={[0, max]}
          yTicks={[0, max / 2, max]}
          summary={order.length > 5 ? `The five busiest of ${order.length} brands are drawn.` : undefined}
        />
        <StackedBars
          title="Sentiment of each brand’s posts"
          series={[
            { id: 'pos', label: 'Positive', color: 'positive' }, { id: 'neu', label: 'Neutral', color: 'neutral' },
            { id: 'neg', label: 'Negative', color: 'negative' }, { id: 'un', label: 'Not scored', color: 0 },
          ]}
          rows={order.map((n) => {
            const l = lanes[n];
            return { id: n, label: `${n} (net ${signed(netOf(l.pos, l.neg, l.pos + l.neu + l.neg))})`, values: [l.pos, l.neu, l.neg, l.un] };
          })}
        />
        <FilterChipRow label="Show posts from" allLabel="All brands" options={order.map((n) => ({ value: n, label: n }))} selected={active ? [active] : []} onChange={(v) => onPick(v.length ? v[v.length - 1] : null)} maxVisible={12} />
      </Stack>
    </Panel>
  );
}

/** What Charts reads from the loaded posts */
interface View {
  all: BWSocialPost[];
  sent: Record<'positive' | 'neutral' | 'negative' | 'unrated', number>;
  plat: Record<string, number>;
  days: [string, { positive: number; neutral: number; negative: number; unrated: number }][];
}

function Charts({ view }: { view: View }) {
  return (
    <Grid columns={3} stackAt="wide" gap="md">
      <Panel title="Sentiment mix" headingLevel={3}>
        <DonutChart
          title="Sentiment mix"
          centerLabel={`${view.all.length}`}
          segments={[
            { id: 'positive', label: 'Positive', value: view.sent.positive, color: 'positive' },
            { id: 'neutral', label: 'Neutral', value: view.sent.neutral, color: 'neutral' },
            { id: 'negative', label: 'Negative', value: view.sent.negative, color: 'negative' },
            { id: 'unrated', label: 'Not scored', value: view.sent.unrated, color: 0 },
          ].filter((s) => s.value > 0) as { id: string; label: string; value: number; color: ChartColor }[]}
        />
      </Panel>
      <Panel title="Network mix" headingLevel={3}>
        <DonutChart
          title="Network mix"
          segments={Object.entries(view.plat).map(([p, n], i) => ({ id: p, label: platLabel(p), value: n, color: SLOTS[i % SLOTS.length] }))}
        />
      </Panel>
      <Panel title="Posts by day" headingLevel={3}>
        <StackedBarChart
          title="Posts by day and sentiment"
          categories={view.days.map(([d]) => d)}
          series={[
            { id: 'positive', label: 'Positive', color: 1, values: view.days.map(([, v]) => v.positive) },
            { id: 'neutral', label: 'Neutral', color: 0, values: view.days.map(([, v]) => v.neutral) },
            { id: 'negative', label: 'Negative', color: 2, values: view.days.map(([, v]) => v.negative) },
            { id: 'unrated', label: 'Not scored', color: 3, values: view.days.map(([, v]) => v.unrated) },
          ]}
          maxLabels={6}
        />
      </Panel>
    </Grid>
  );
}

/** Net sentiment over time, posted vs seen (weighted by reach), and sentiment by brand. On-brand scored posts only. */
function Sentiment({ posts }: { posts: BWSocialPost[] }) {
  const onBrand = posts.filter((p) => (p.relevance ?? 0) >= 0.4 && sentOf(p.sentiment) !== 'unrated');
  const byDay: Record<string, { pos: number; neg: number; n: number }> = {};
  const mix = { posts: { pos: 0, neu: 0, neg: 0 }, reach: { pos: 0, neu: 0, neg: 0 } };
  const byBrand: Record<string, { pos: number; neu: number; neg: number }> = {};
  for (const p of onBrand) {
    const s = sentOf(p.sentiment);
    const k = s === 'positive' ? 'pos' : s === 'negative' ? 'neg' : 'neu';
    const d = (p.publication_date || '').slice(0, 10);
    if (d) {
      const e = (byDay[d] ||= { pos: 0, neg: 0, n: 0 });
      if (k === 'pos') e.pos++;
      else if (k === 'neg') e.neg++;
      e.n++;
    }
    mix.posts[k]++;
    // +1: a post with no engagement was still posted
    mix.reach[k] += engOf(p) + 1;
    (byBrand[brandOf(p)] ||= { pos: 0, neu: 0, neg: 0 })[k]++;
  }
  const raw = Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, net: v.n ? Math.round(((v.pos - v.neg) / v.n) * 100) : 0, n: v.n }));
  // 3-day centred, weighted by posts
  const trend = raw.map((d, i) => {
    const w = raw.slice(Math.max(0, i - 1), i + 2);
    const n = w.reduce((a, x) => a + x.n, 0);
    return { ...d, smooth: n ? Math.round(w.reduce((a, x) => a + x.net * x.n, 0) / n) : d.net };
  });
  const net = (m: { pos: number; neu: number; neg: number }) => netOf(m.pos, m.neg, m.pos + m.neu + m.neg);
  const postsNet = net(mix.posts);
  const reachNet = net(mix.reach);
  const amplified = postsNet != null && reachNet != null && reachNet <= postsNet - 15;
  const brandRows = Object.entries(byBrand)
    .map(([b, m]) => ({ b, ...m, total: m.pos + m.neu + m.neg, net: net(m) }))
    .filter((r) => r.total >= 3)
    .sort((a, b) => (b.net ?? -999) - (a.net ?? -999));
  const SENT_SERIES = [{ id: 'pos', label: 'Positive', color: 'positive' as const }, { id: 'neu', label: 'Neutral', color: 'neutral' as const }, { id: 'neg', label: 'Negative', color: 'negative' as const }];
  return (
    <>
      <Grid columns="main-aside" gap="md">
        {trend.length >= 3 ? (
          <Panel title="Net sentiment over time" description="Daily net %, smoothed over three days" headingLevel={3}>
            <LineChart
              title="Net sentiment over time"
              categories={trend.map((d) => d.date.slice(5))}
              categoryLabels={trend.map((d) => `${d.date} (${d.n} posts)`)}
              series={[{ id: 'net', label: 'Net sentiment', color: 2, fill: true, values: trend.map((d) => d.smooth) }]}
              yDomain={[-100, 100]}
              yTicks={[-100, -50, 0, 50, 100]}
              baseline={0}
              formatValue={(v) => signed(v)}
            />
          </Panel>
        ) : <div />}
        <Panel title="Posted vs seen" description="The same posts, weighted by engagement: what the audience actually saw." headingLevel={3}>
          <Stack gap="md">
            <StackedBars
              title="Posted vs seen"
              series={SENT_SERIES}
              rows={[
                { id: 'posts', label: `By posts (net ${signed(postsNet)})`, values: [mix.posts.pos, mix.posts.neu, mix.posts.neg] },
                { id: 'reach', label: `By reach (net ${signed(reachNet)})`, values: [Math.round(mix.reach.pos), Math.round(mix.reach.neu), Math.round(mix.reach.neg)] },
              ]}
            />
            {amplified && <Banner tone="warning" title="Negative posts are being amplified" description={`Sentiment by reach is ${postsNet! - reachNet!} points worse than by number of posts.`} />}
          </Stack>
        </Panel>
      </Grid>
      {brandRows.length >= 2 && (
        <Panel title="Sentiment by brand" description="On-brand scored posts, best to worst" headingLevel={3}>
          <StackedBars title="Sentiment by brand" series={SENT_SERIES} rows={brandRows.map((r) => ({ id: r.b, label: `${r.b} (net ${signed(r.net)}, ${r.total} posts)`, values: [r.pos, r.neu, r.neg] }))} />
        </Panel>
      )}
    </>
  );
}

/** Positive and negative posts per day, and what the negative posts are about. Both filter the posts below. */
function Timeline({ posts, page, setPage }: { posts: BWSocialPost[]; page: PageFilters; setPage: (f: (p: PageFilters) => PageFilters) => void }) {
  const all = posts.filter((p) => (p.relevance ?? 0) >= 0.4);
  const byDay: Record<string, { pos: number; neg: number }> = {};
  for (const p of all) {
    const d = (p.publication_date || '').slice(0, 10);
    const s = sentOf(p.sentiment);
    if (!d || (s !== 'positive' && s !== 'negative')) continue;
    (byDay[d] ||= { pos: 0, neg: 0 })[s === 'positive' ? 'pos' : 'neg']++;
  }
  const days = Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b));
  const neg = all.filter((p) => sentOf(p.sentiment) === 'negative');
  const blob = (p: BWSocialPost) => `${p.title || ''} ${p.summary || ''}`;
  const themes = SOCIAL_NEG_THEMES.map((t) => ({ key: t.key, label: t.label, n: neg.filter((p) => t.re.test(blob(p))).length })).filter((t) => t.n > 0).sort((a, b) => b.n - a.n);
  const other = neg.filter((p) => !SOCIAL_NEG_THEMES.some((t) => t.re.test(blob(p)))).length;
  if (other) themes.push({ key: 'other', label: 'Other', n: other });
  if (days.length < 2 && !themes.length) return null;
  return (
    <Grid columns="main-aside" gap="md">
      {days.length >= 2 ? (
        <Panel title="Positive and negative posts by day" headingLevel={3}>
          <Stack gap="md">
            <StackedBarChart
              title="Positive and negative posts by day"
              categories={days.map(([d]) => d)}
              series={[
                { id: 'pos', label: 'Positive', color: 1, values: days.map(([, v]) => v.pos) },
                { id: 'neg', label: 'Negative', color: 2, values: days.map(([, v]) => v.neg) },
              ]}
              maxLabels={8}
            />
            <FilterChipRow
              label="Show one day"
              allLabel="All days"
              options={[...days].reverse().map(([d, v]) => ({ value: d, label: `${d} (${v.pos} positive, ${v.neg} negative)` }))}
              selected={page.day ? [page.day] : []}
              onChange={(v) => setPage((f) => ({ ...f, day: v.length ? v[v.length - 1] : null }))}
              maxVisible={5}
            />
          </Stack>
        </Panel>
      ) : <div />}
      {themes.length > 0 && (
        <Panel title="What the negative posts are about" description="Matched by keywords; a post can count under several." headingLevel={3}>
          <Stack gap="md">
            <StackedBars title="What the negative posts are about" series={[{ id: 'n', label: 'Negative posts', color: 'negative' }]} rows={themes.map((t) => ({ id: t.key, label: t.label, values: [t.n] }))} />
            <FilterChipRow
              label="Show negative posts about"
              allLabel="Anything"
              options={themes.map((t) => ({ value: t.key, label: t.label }))}
              selected={page.theme ? [page.theme] : []}
              onChange={(v) => setPage((f) => ({ ...f, theme: v.length ? v[v.length - 1] : null }))}
            />
          </Stack>
        </Panel>
      )}
    </Grid>
  );
}
