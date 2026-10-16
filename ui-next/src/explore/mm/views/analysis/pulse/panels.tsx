import { useState } from 'react';
import { Button, Collapsible, CollapsibleContent, CollapsibleTrigger, LineChart, Panel, Select, Stack, Text } from '@aunoo/ui';
import { ClickableBars } from '../../../shared/ClickableBars';
import { DivergingBars } from '../../../shared/DivergingBars';
import type { CorpusSummary, FundingAnalysis, MarketHeadcountTrend, MarketOverview, MarketPulse } from '@monolith/marketMonitorApi';
import type { MmContext } from '../../../context';
import { MetricAside } from '../../../shared/metric';
import { LinkButton, Missing, SortTable, VendorLink } from '../../../shared/SortTable';
import { scale, scoreDelta, signed, signedPct } from './format';

/* The Pulse panels, one component each (old MarketMonitorTab.tsx, the Analysis view's own panels). */

type Active = MarketOverview['most_active'][number];
type Rank = 'index' | 'posts' | 'jobs' | 'earned';
const RANK_OPTIONS = [
  { value: 'index', label: 'Rank by overall activity' },
  { value: 'posts', label: 'Rank by owned posts' },
  { value: 'jobs', label: 'Rank by observed jobs' },
  { value: 'earned', label: 'Rank by earned mentions' },
];

export function MostActive({ ctx, overview }: { ctx: MmContext; overview: MarketOverview }) {
  const [rank, setRank] = useState<Rank>('index');
  const [showAll, setShowAll] = useState(false);
  const all = overview.most_active ?? [];
  const scored = all.filter((v) => v.activity_index !== null);
  const withheld = all.length - scored.length;
  // The index can only order vendors that have one; a raw channel count can order every vendor,
  // because that count was measured even when a sibling channel wasn't
  const pool = rank === 'index' ? scored : all;
  const keyOf = (v: Active) => (rank === 'index' ? v.activity_index : v[rank]) ?? -1;
  const ranked = [...pool].sort((a, b) => keyOf(b) - keyOf(a) || (b.earned ?? 0) - (a.earned ?? 0) || (a.vendor || '').localeCompare(b.vendor || ''));
  const rows = showAll ? ranked : ranked.slice(0, 10);
  return (
    <Panel
      title="Most active vendors"
      description={`The Activity Index scores three channels over the last ${overview.period_days} days: posts the vendor published itself, job listings observed open, and coverage published by somebody else. Each becomes a percentile against the vendors measured on all three, then the three are averaged with equal weight, so dozens of open roles alone can't put a vendor on top. It measures activity, not performance.`}
      headerAside={<Select label="Ranking" hideLabel options={RANK_OPTIONS} value={rank} onValueChange={(v) => setRank(v as Rank)} />}
    >
      <Stack gap="sm">
        <SortTable
          caption="Most active vendors"
          rows={rows}
          rowKey={(v) => v.brand_id}
          columns={[
            { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => <VendorLink id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} /> },
            { key: 'activity_index', label: 'Activity Index', align: 'end', render: (v) => (v.activity_index === null ? <Missing>Partial</Missing> : v.activity_index) },
            { key: 'posts', label: 'Owned posts', align: 'end' },
            { key: 'jobs', label: 'Observed jobs', align: 'end' },
            { key: 'earned', label: 'Earned mentions', align: 'end' },
          ]}
        />
        <Stack direction="row" justify="between" gap="sm">
          <Text variant="caption">
            {withheld > 0
              ? `${withheld} of ${all.length} vendors show as Partial: at least one channel wasn't measured for them this period, so an index would rank them on evidence we don't have.`
              : `All ${all.length} vendors were measured on all three channels this period.`}
          </Text>
          {ranked.length > 10 && <Button variant="ghost" size="sm" onClick={() => setShowAll((s) => !s)}>{showAll ? 'Show top 10' : `Show all ${ranked.length}`}</Button>}
        </Stack>
      </Stack>
    </Panel>
  );
}

export function Sentiment({ corpus }: { corpus: CorpusSummary | null }) {
  const trend = corpus?.sentiment_trend ?? [];
  const latest = [...trend].reverse().find((w) => w.net_all !== null);
  // Vendor-attributed sentiment needs an article matched, attributed to a tracked vendor and scored.
  // Under three real weeks a "line" is a few stranded dots, so it isn't drawn.
  const vendorPoints = trend.filter((w) => w.net_vendor !== null).length;
  const showVendor = vendorPoints >= 3;
  const reading = !latest ? null : latest.net_all! > 10 ? 'leaned positive' : latest.net_all! < -10 ? 'leaned negative' : 'was mixed';
  const series = [
    { id: 'broad', label: 'The market broadly', color: 1 as const, values: trend.map((w) => w.net_broad) },
    ...(showVendor ? [{ id: 'vendor', label: 'Tracked vendors’ own coverage', color: 2 as const, values: trend.map((w) => w.net_vendor) }] : []),
  ];
  const { domain, ticks } = scale(series.flatMap((s) => s.values));
  return (
    <Panel
      title="Sentiment"
      description="Weekly net sentiment: the positive share of classified coverage minus the negative share. A week with too few classified articles to call a direction is left blank rather than plotted at zero, so a gap means low confidence, not neutral."
    >
      {!trend.some((w) => w.net_all !== null) ? <Text>Not enough classified coverage yet to chart sentiment.</Text> : (
        <Stack gap="sm">
          {reading && <Text>{`Coverage in the latest week ${reading}.`}</Text>}
          <LineChart
            title="Weekly net sentiment"
            categories={trend.map((w) => w.week.slice(5))}
            categoryLabels={trend.map((w) => `Week of ${w.week}`)}
            series={series}
            yDomain={domain}
            yTicks={ticks}
            baseline={0}
            formatValue={(v) => `${signed(v)}%`}
          />
          {!showVendor && (
            <Text variant="caption">
              {`Tracked vendors' own sentiment isn't shown: only ${vendorPoints} week${vendorPoints === 1 ? '' : 's'} of their coverage cleared the confidence floor, too few to read as a line.`}
            </Text>
          )}
        </Stack>
      )}
    </Panel>
  );
}

export function HeadcountChange({ ctx, pulse }: { ctx: MmContext; pulse: MarketPulse | null }) {
  const movers = pulse?.headcount_movers ?? [];
  const moverTable = (
    <SortTable
      caption="Headcount movers"
      rows={movers}
      rowKey={(m) => m.brand_id}
      initialSort="delta"
      initialDir="desc"
      columns={[
        { key: 'vendor', label: 'Vendor', rowHeader: true, render: (m) => <VendorLink id={m.brand_id} name={m.vendor} color={ctx.colours.byId(m.brand_id)} onOpen={ctx.openVendor} /> },
        { key: 'delta', label: 'Change (staff)', align: 'end', render: (m) => signed(m.delta) },
        { key: 'pct', label: 'Change', align: 'end', render: (m) => signedPct(m.pct) },
        {
          key: 'readings', label: 'Readings', sortable: false, wrap: true,
          render: (m) => `${m.previous}${m.previous_at ? ` (${m.previous_at.slice(0, 10)})` : ''} → ${m.latest}${m.latest_at ? ` (${m.latest_at.slice(0, 10)})` : ''}`,
        },
      ]}
    />
  );
  return (
    <Panel
      title="Headcount change"
      description="Two LinkedIn readings of the same vendor, each with its own date. Vendors with only one reading are counted as awaiting a second, not shown as unchanged."
      headerAside={<MetricAside meta={pulse?.headcount_metric} />}
    >
      <Stack gap="sm">
        {pulse && (
          <Text>
            {`Observed market headcount ${pulse.observed_market_headcount.toLocaleString()}, across ${pulse.headcount_cohort} vendor${pulse.headcount_cohort === 1 ? '' : 's'} with a current exact reading.`}
          </Text>
        )}
        {pulse && pulse.headcount_n > 0 && (
          <Text>{`Average ${signedPct(pulse.headcount_avg_pct)} · median ${signedPct(pulse.headcount_median_pct)}, across ${pulse.headcount_n} vendor${pulse.headcount_n === 1 ? '' : 's'}.`}</Text>
        )}
        {/* Say why the average is missing, so a withheld figure doesn't look like a fault */}
        {pulse && pulse.headcount_n === 0 && movers.length > 0 && (
          <Text variant="caption">
            {`No market average yet: it needs several vendors with two readings, and ${movers.length === 1 ? 'only one has' : `only ${movers.length} have`} a second so far. An average across one vendor is that vendor's number, not the market's.`}
          </Text>
        )}
        {movers.length === 0 ? (
          <Text>{`No vendor has two LinkedIn readings yet${pulse ? `, so movement can't be measured for any of the ${pulse.headcount_insufficient} awaiting a second one` : ''}.`}</Text>
        ) : (
          <>
            {/* The old tab drew the movers as bars either side of zero; a table alone hid the shape */}
            {movers.length >= 3 && (
              <DivergingBars
                title="Headcount movers: change in staff between two readings"
                rows={[...movers].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 8).map((m) => ({
                  id: m.brand_id, label: m.vendor, value: m.delta, valueText: `${signed(m.delta)} staff (${signedPct(m.pct)})`,
                  color: ctx.colours.byId(m.brand_id), onSelect: () => ctx.openVendor(m.brand_id),
                }))}
              />
            )}
            {movers.length >= 3 ? (
              <Collapsible>
                <CollapsibleTrigger variant="ghost" size="sm">{`Every mover, with both readings (${movers.length})`}</CollapsibleTrigger>
                <CollapsibleContent>{moverTable}</CollapsibleContent>
              </Collapsible>
            ) : moverTable}
          </>
        )}
      </Stack>
    </Panel>
  );
}

export function HeadcountTrend({ trend, withData }: { trend: MarketHeadcountTrend; withData: number }) {
  const values = trend.points.map((p) => p.avg_pct_vs_baseline);
  const { domain, ticks } = scale(values);
  return (
    <Panel
      title="Headcount, market-wide"
      description="Average change against each vendor's own first reading, as of each week. Not a sum of headcounts, which would look like growth purely because more vendors got a first reading."
    >
      <Stack gap="sm">
        <LineChart
          title="Market-wide headcount change by week"
          categories={trend.points.map((p) => p.week.slice(5))}
          categoryLabels={trend.points.map((p) => `Week of ${p.week}: ${p.n_vendors} of ${trend.watching} watched vendors read`)}
          series={[{ id: 'avg', label: 'Average change vs own baseline', color: 'neutral', values }]}
          yDomain={domain}
          yTicks={ticks}
          baseline={0}
          formatValue={(v) => `${signed(v)}%`}
        />
        <Text variant="caption">
          {`${withData} of ${trend.points.length} weeks since this market started tracking have a reading. Weeks where fewer than half the watched vendors had been read are the least trustworthy points.`}
        </Text>
      </Stack>
    </Panel>
  );
}

export function MomentumTrend({ funding, withData }: { funding: FundingAnalysis; withData: number }) {
  return (
    <Panel
      title="Overall market momentum, by month"
      description="How much attention and predicted growth the whole market gets on average, month by month. It moves slowly on purpose: Crunchbase is read about once a week."
    >
      <Stack gap="sm">
        <LineChart
          title="Average Crunchbase Heat and Growth scores by month"
          categories={funding.by_month.map((m) => m.month)}
          series={[
            { id: 'heat', label: 'Crunchbase Heat', color: 1, values: funding.by_month.map((m) => m.avg_heat_score) },
            { id: 'growth', label: 'Crunchbase Growth', color: 2, values: funding.by_month.map((m) => m.avg_growth_score) },
          ]}
          yDomain={[0, 100]}
          yTicks={[0, 25, 50, 75, 100]}
        />
        <Text variant="caption">{`${withData} of ${funding.by_month.length} months since this market started tracking have a Crunchbase reading.`}</Text>
      </Stack>
    </Panel>
  );
}

export function MomentumMoves({ ctx, funding }: { ctx: MmContext; funding: FundingAnalysis | null }) {
  const events = funding?.momentum_events ?? [];
  const idOf = (name: string) => ctx.vendors?.find((v) => v.display_name === name)?.brand_id;
  return (
    <Panel
      title="Who's getting more attention or momentum"
      description="Companies whose Crunchbase Growth or Heat score moved since the last check. Both are Crunchbase's own 0 to 100 scores and we can't reproduce how either is worked out, so a move is a change in what Crunchbase reports, not a measured change in the company. Only real changes are listed."
    >
      {!events.length ? <Text>Nothing has changed since the last check.</Text> : (
        <SortTable
          caption="Crunchbase score moves"
          rows={events.slice(0, 8)}
          rowKey={(e) => `${e.vendor}:${e.observed_at}`}
          columns={[
            {
              key: 'vendor', label: 'Vendor', rowHeader: true,
              render: (e) => { const id = idOf(e.vendor); return id ? <VendorLink id={id} name={e.vendor} color={ctx.colours.byId(id)} onOpen={ctx.openVendor} /> : e.vendor; },
            },
            { key: 'observed_at', label: 'Read on', render: (e) => `${(e.observed_at ?? '').slice(0, 10)}${e.prev_observed_at ? ` (was ${e.prev_observed_at.slice(0, 10)})` : ''}` },
            // The change since the last reading, not the score itself
            { key: 'heat_delta', label: 'Attention (Heat)', align: 'end', render: (e) => (e.heat_delta === null ? <Missing /> : scoreDelta('', e.heat_delta).trim()) },
            { key: 'growth_delta', label: 'Growth outlook', align: 'end', render: (e) => (e.growth_delta === null ? <Missing /> : scoreDelta('', e.growth_delta).trim()) },
          ]}
        />
      )}
    </Panel>
  );
}

export function ContentByWeek({ ctx, overview }: { ctx: MmContext; overview: MarketOverview }) {
  const weeks = (overview.corpus as CorpusSummary).by_week ?? [];
  const anyPartial = weeks.some((w) => w.partial);
  // The newest week is still filling, so its bar is hatched rather than read as a collapse
  const open = (week: string) => {
    const w = weeks.find((x) => x.week === week);
    if (w) ctx.openRecords({ kind: 'coverage', title: `Content observed, week of ${w.week}`, week: w.week, expectedTotal: w.n });
  };
  return (
    <Panel
      title="Content observed by week"
      description="Articles matching the market's phrases, by publication week. A bar is how much we observed that week: a floor for how much was published, not a measure of it."
    >
      {!weeks.length ? <Text>Nothing matched yet. Run a scan from Collection, Coverage.</Text> : (
        <Stack gap="sm">
          <ClickableBars
            title="Articles observed by week"
            bars={weeks.map((w) => ({ id: w.week, label: w.week.slice(5), value: w.n, partial: !!w.partial }))}
            onSelect={open}
            selectLabel={(b) => `Open the ${b.value} articles from the week of ${b.id}${b.partial ? ' (still filling)' : ''}`}
            unit="articles"
          />
          {anyPartial && <Text variant="caption">{weeks.filter((w) => w.partial).map((w) => `Week of ${w.week}: ${w.n} so far, ${w.partial_reason ?? 'still filling'}. Hatched bars are weeks still filling.`).join(' ')}</Text>}
        </Stack>
      )}
    </Panel>
  );
}

export function PostVolume({ ctx, pulse }: { ctx: MmContext; pulse: MarketPulse | null }) {
  const loud = (pulse?.loudest_vendors ?? []).slice(0, 8);
  const days = ctx.periodDays;
  const openVendorPosts = (name: string, n: number) => {
    const v = ctx.vendors?.find((x) => x.display_name === name);
    if (v) ctx.openRecords({ kind: 'posts', title: `${v.display_name}: posts, last ${days} days`, days, vendorId: v.brand_id, ownership: 'owned', expectedTotal: n });
  };
  return (
    <Panel
      title="LinkedIn post volume"
      description="Posts the vendors published in the selected window. Select a bar to read that vendor's posts."
      headerAside={<Button variant="ghost" size="sm" onClick={() => ctx.openRecords({ kind: 'posts', title: `Vendor posts, last ${days} days`, days, ownership: 'owned' })}>All posts</Button>}
    >
      {!loud.length ? <Text>No posts in this window.</Text> : (
        <Stack gap="sm">
          {/* The bar is a post count, so it opens the posts, not the vendor's page */}
          <ClickableBars
            title="Posts per vendor"
            orientation="horizontal"
            bars={loud.map((r) => ({ id: r.vendor, label: r.vendor, value: r.posts, color: ctx.colours.byName(r.vendor) }))}
            onSelect={(name) => openVendorPosts(name, loud.find((r) => r.vendor === name)?.posts ?? 0)}
            selectLabel={(b) => `Open ${b.label}'s ${b.value} posts`}
            unit="posts"
          />
        </Stack>
      )}
    </Panel>
  );
}

export function TopFunded({ ctx, overview }: { ctx: MmContext; overview: MarketOverview }) {
  return (
    <Panel
      title="Largest disclosed total funding"
      description="Cumulative total raised, from the imported registry, not a single round. Vendors that never disclosed a figure are left out rather than shown as zero."
      headerAside={<LinkButton onClick={() => ctx.openRecords({ kind: 'funding', title: 'Funding by vendor' })}>All vendors</LinkButton>}
    >
      <SortTable
        caption="Largest disclosed total funding"
        rows={overview.top_funded}
        rowKey={(v) => v.brand_id}
        scroll
        emptyText="No vendor has disclosed a funding figure."
        columns={[
          { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => <VendorLink id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} /> },
          { key: 'musd', label: 'Disclosed total', align: 'end', render: (v) => (v.musd === null ? <Missing /> : `$${v.musd.toFixed(1)}M`) },
          { key: 'last_round', label: 'Last round', render: (v) => v.last_round ?? <Missing /> },
        ]}
      />
    </Panel>
  );
}

