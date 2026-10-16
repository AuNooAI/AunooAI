import { useEffect, useMemo, useState } from 'react';
import { ArticleCard, Button, Grid, Panel, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import {
  getAnalyses, getHeadcountTrend, getWireArticles,
  type CorpusSummary, type FundingAnalysis, type MarketHeadcountTrend, type WireArticle,
} from '@monolith/marketMonitorApi';
import type { MmContext } from '../../context';
import { ConfidenceGate, type ThinPanel } from '../../shared/ConfidenceGate';
import { VendorChip } from '../findings/VendorChip';
import { EventCard } from './pulse/EventCard';
import { money, signed } from './pulse/format';
import { ContentByWeek, HeadcountChange, HeadcountTrend, MomentumMoves, MomentumTrend, MostActive, PostVolume, Sentiment, TopFunded } from './pulse/panels';

/*
 * The market's one-look state: the first half of the Analysis view (old MarketMonitorTab.tsx, the
 * panels above MarketAnalysisView). Overview and pulse come from the frame for the shared period.
 * The headcount trend and the funding analysis are heavier reads, so they load here, only while this
 * view is open. A panel that hasn't cleared its own sample-size floor folds into the "Not enough data
 * yet" list instead of drawing a two-point line.
 */

export function Pulse(ctx: MmContext) {
  const { marketId, overview, pulse } = ctx;
  const [trend, setTrend] = useState<MarketHeadcountTrend | null>(null);
  const [funding, setFunding] = useState<FundingAnalysis | null>(null);
  const [topArticles, setTopArticles] = useState<WireArticle[] | null>(null);

  useEffect(() => {
    let live = true;
    setTrend(null);
    setFunding(null);
    getHeadcountTrend(marketId, 26).then((r) => live && setTrend(r), () => undefined);
    // The panels still render without momentum if the analysis call fails
    getAnalyses(marketId).then((r) => live && setFunding(r.funding ?? null), () => undefined);
    return () => {
      live = false;
    };
  }, [marketId]);

  const uris = pulse?.top_article_uris;
  useEffect(() => {
    if (!uris) {
      setTopArticles(null);
      return;
    }
    let live = true;
    if (!uris.length) setTopArticles([]);
    else getWireArticles(uris).then((a) => live && setTopArticles(a), () => live && setTopArticles([]));
    return () => {
      live = false;
    };
  }, [uris]);

  // Two points make a line, not a trend. A week counts when at least half the watched vendors had
  // been read as of that week, and three such weeks are needed before the line is drawn.
  const headcount = useMemo(() => {
    const withData = trend?.points.filter((p) => p.avg_pct_vs_baseline !== null) ?? [];
    const watching = trend?.watching ?? 0;
    const solid = withData.filter((p) => watching > 0 && p.n_vendors * 2 >= watching);
    return { ok: solid.length >= 3, withData: withData.length, solid: solid.length };
  }, [trend]);
  const momentum = useMemo(() => {
    const withData = funding?.by_month.filter((m) => m.avg_heat_score !== null).length ?? 0;
    return { ok: withData > 1, withData };
  }, [funding]);
  const thin: ThinPanel[] = [];
  if (!headcount.ok) {
    const total = trend?.points.length ?? 0;
    thin.push({
      id: 'headcount-trend', title: 'Headcount, market-wide', why: 'Average change against each vendor’s own first reading, by week.',
      need: total ? `${headcount.solid} of ${total} weeks read by at least half the vendors; three needed` : 'loading, or no readings yet',
    });
  }
  if (!momentum.ok) {
    const total = funding?.by_month.length ?? 0;
    thin.push({
      id: 'momentum-trend', title: 'Overall market momentum, by month', why: 'Attention and predicted growth across the whole market, month by month.',
      need: total ? `${momentum.withData} of ${total} months` : 'loading, or no readings yet',
    });
  }

  const vendorIds = useMemo(() => new Map((ctx.vendors ?? []).map((v) => [v.display_name.toLowerCase(), v.brand_id])), [ctx.vendors]);

  if (!overview) return <Skeleton variant="block" size="card" />;
  const corpus = 'total' in overview.corpus ? (overview.corpus as CorpusSummary) : null;
  const latest = [...(corpus?.sentiment_trend ?? [])].reverse().find((w) => w.net_all !== null);
  const show = (label: string, onClick: () => void) => <Button variant="ghost" size="sm" onClick={onClick}>{label}</Button>;

  return (
    <>
      <Grid columns={3} label="The market at a glance">
        <Stat
          label="Vendors watched"
          value={`${overview.coverage.watching} of ${overview.coverage.vendors}`}
          meta={`${overview.coverage.paused} paused · ${overview.coverage.observed} observed at least once`}
          action={show('Show these vendors', () => ctx.openDrill('watched'))}
        />
        <Stat
          label="Cumulative disclosed funding"
          value={money(overview.funding.total_musd)}
          meta={`Across ${overview.funding.disclosed} of ${overview.funding.disclosed + overview.funding.undisclosed} vendors`}
          action={show('Show these vendors', () => ctx.openDrill('disclosed'))}
        />
        <Stat
          label="Coverage matched this period"
          value={String(corpus?.total ?? 0)}
          meta={`${corpus?.corpus ?? 0} of those were first collected for other topics`}
          action={show('Open coverage', () => ctx.goTo('collection', 'coverage'))}
        />
        <Stat
          label="No observed activity"
          value={String(overview.quiet_vendors)}
          meta="No vendor posts, open roles or matched coverage seen from monitored sources this period"
          action={show('Show these vendors', () => ctx.openDrill('quiet'))}
        />
        <Stat
          label="Sentiment, latest week"
          value={latest ? `${signed(latest.net_all!)}%` : '—'}
          tone={!latest || latest.net_all === 0 ? 'default' : latest.net_all! > 0 ? 'success' : 'error'}
          meta="Positive minus negative share of classified coverage. Not shown for a week with too little classified coverage to call a direction."
          action={show('Open coverage', () => ctx.goTo('collection', 'coverage'))}
        />
      </Grid>

      <MostActive ctx={ctx} overview={overview} />
      <Sentiment corpus={corpus} />

      {/* A panel whose neighbour folded into "Not enough data yet" takes the whole row */}
      {headcount.ok && trend ? (
        <Grid columns={2}>
          <HeadcountChange ctx={ctx} pulse={pulse} />
          <HeadcountTrend trend={trend} withData={headcount.withData} />
        </Grid>
      ) : <HeadcountChange ctx={ctx} pulse={pulse} />}

      {momentum.ok && funding ? (
        <Grid columns={2}>
          <MomentumTrend funding={funding} withData={momentum.withData} />
          <MomentumMoves ctx={ctx} funding={funding} />
        </Grid>
      ) : <MomentumMoves ctx={ctx} funding={funding} />}

      <ConfidenceGate panels={thin} />

      <Grid columns={2}>
        <ContentByWeek ctx={ctx} overview={overview} />
        <PostVolume ctx={ctx} pulse={pulse} />
      </Grid>

      <TopFunded ctx={ctx} overview={overview} />

      <Panel title="Events" description={`What the market's timeline recorded in the last ${pulse?.period_days ?? ctx.periodDays} days.`}>
        {!pulse || pulse.events.length === 0 ? <Text>No events in this window.</Text> : (
          <Stack as="ul" gap="sm" label="Events">
            {pulse.events.map((e) => <EventCard key={e.id} event={e} vendorIds={vendorIds} colours={ctx.colours} onVendor={ctx.openVendor} />)}
          </Stack>
        )}
      </Panel>

      <Panel title="Top posts, articles and news" description="Everything matched to this market in the window, most engaged first.">
        {!pulse || topArticles === null ? <Skeleton variant="text" lines={4} /> : topArticles.length === 0 ? <Text>Nothing matched this market in this window.</Text> : (
          <Stack as="ul" gap="sm" label="Top posts, articles and news">
            {topArticles.map((a) => (
              <ArticleCard
                key={a.uri}
                as="li"
                variant="row"
                headingLevel={3}
                title={a.title}
                href={a.uri}
                meta={`${a.news_source ?? 'unknown source'}${a.publication_date ? ` · ${a.publication_date.slice(0, 10)}` : ''}`}
                tags={a.vendors.length ? (
                  <Stack direction="row" gap="sm">
                    {a.vendors.map((v) => <VendorChip key={v.brand_id} id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} />)}
                  </Stack>
                ) : undefined}
              />
            ))}
          </Stack>
        )}
      </Panel>
    </>
  );
}
