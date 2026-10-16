import {
  ActivityRow, Banner, Button, Chip, Eyebrow, Icon, LineChart, Meter, Panel, Skeleton, Stack, StackedBarChart, StackedBars, Table, Text,
} from '@aunoo/ui';
import { CATEGORY_SHORT_NAMES, type BWCategory, type BWIssue } from '@monolith/brandWatcherApi';
import type { BwContext } from '../../context';
import type { DashboardData } from './useDashboardData';
import { bucketCounts } from './helpers';

const short = (c: string) => (CATEGORY_SHORT_NAMES as Record<string, string>)[c] || c;
const niceMax = (n: number) => {
  if (n <= 5) return 5;
  const step = 10 ** Math.floor(Math.log10(n));
  return Math.ceil(n / step) * step;
};
const SENT_SERIES = [
  { id: 'pos', label: 'Positive', color: 'positive' as const },
  { id: 'neu', label: 'Neutral', color: 'neutral' as const },
  { id: 'neg', label: 'Negative', color: 'negative' as const },
];

function IssueRow({ iss, resolved }: { iss: BWIssue; resolved?: boolean }) {
  const type = `${iss.primary_type.replace(/_/g, ' ')}${iss.secondary_types.length ? ` (also ${iss.secondary_types.map((t) => t.replace(/_/g, ' ')).join(', ')})` : ''}`;
  const meta = resolved
    ? `Coverage ended ${iss.last_seen}; closed ${iss.expired_on} after ${iss.expiry_days} days without new coverage`
    : `${iss.articles} ${iss.articles === 1 ? 'article' : 'articles'} · ${iss.sources} ${iss.sources === 1 ? 'source' : 'sources'} · first seen ${iss.first_seen} · ${iss.momentum}${iss.sector_wide_display && iss.sector_wide?.length ? ` · sector-wide (also ${iss.sector_wide.join(', ')})` : ''}`;
  return (
    <li>
      <Stack gap="sm">
        <Stack direction="row" gap="sm" wrap={false}>
          <Chip size="sm" tone={iss.severity === 'high' ? 'error' : iss.severity === 'medium' ? 'warning' : 'muted'}>{iss.severity}</Chip>
          <Text as="span"><strong>{type}:</strong> {iss.title}</Text>
        </Stack>
        {!resolved && iss.justification && <Text variant="description">{iss.justification}</Text>}
        <Text variant="caption">{meta}</Text>
      </Stack>
    </li>
  );
}

/** The brand risk card: open issues by type and severity, never a blended score. */
function RiskCard({ d }: { d: DashboardData }) {
  const ra = d.risk;
  const level = ra?.risk_level ?? null;
  const badge = !ra ? 'Loading…' : ra.active_issues.length === 0 ? 'No open issues' : `${ra.active_issues.length} open ${ra.active_issues.length === 1 ? 'issue' : 'issues'}, ${level} severity`;
  return (
    <Panel
      title="Brand risk"
      description="Adverse events in the coverage, grouped into issues. The level is the most severe open issue, never an average."
      headingLevel={3}
      headerAside={<Chip tone={level === 'high' ? 'error' : level === 'medium' ? 'warning' : ra ? 'success' : 'muted'}>{badge}</Chip>}
    >
      {!ra ? <Skeleton variant="text" lines={3} /> : (
        <Stack gap="md">
          {ra.escalation_tier && (
            <Banner tone="warning" title={ra.escalation_tier.label} description={`Status set by your rules, triggered by: ${ra.escalation_tier.triggered.join('; ')}`} />
          )}
          {ra.active_issues.length > 0 ? (
            <Stack as="ul" gap="md" label="Open issues">{ra.active_issues.map((i) => <IssueRow key={i.id} iss={i} />)}</Stack>
          ) : <Text>No adverse events are open for this brand.</Text>}
          {(ra.resolved_issues?.length ?? 0) > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h4">Closed in this period</Eyebrow>
              <Stack as="ul" gap="sm" label="Closed issues">{ra.resolved_issues!.map((i) => <IssueRow key={i.id} iss={i} resolved />)}</Stack>
            </Stack>
          )}
          {ra.attention && (
            <Stack gap="sm">
              <Eyebrow as="h4">Attention: coverage volume, not risk</Eyebrow>
              {!ra.attention.available ? <Text variant="caption">Not worked out yet: {ra.attention.reason}.</Text>
                : (ra.attention.category_spikes?.length ?? 0) > 0 ? (
                  <Stack direction="row" gap="sm">
                    {ra.attention.category_spikes!.map((s) => <Chip key={s.category} size="sm" tone="info">{s.category}: {s.multiple}× normal ({s.recent} against {s.weekly_avg} a week)</Chip>)}
                  </Stack>
                ) : <Text variant="caption">Coverage volume is normal for this brand{ra.attention.overall_multiple != null ? ` (${ra.attention.overall_multiple}× its weekly average)` : ''}.</Text>}
            </Stack>
          )}
        </Stack>
      )}
    </Panel>
  );
}

function CategoryTable({ categories, onOpen }: { categories: BWCategory[]; onOpen: (c: string) => void }) {
  const active = categories.filter((c) => c.article_count > 0);
  const total = active.reduce((s, c) => s + c.article_count, 0);
  return (
    <Panel title="Coverage by category" description="Articles can carry several categories. Open one to see its articles." headingLevel={3}>
      <Table
        caption="Coverage by category"
        hideCaption
        rows={active}
        rowKey={(c) => c.category}
        emptyText="No classified articles in this period."
        columns={[
          { key: 'category', header: 'Category', render: (c) => <Button variant="ghost" size="sm" onClick={() => onOpen(c.category)}>{short(c.category)}</Button> },
          { key: 'article_count', header: 'Articles', align: 'end', render: (c) => c.article_count.toLocaleString('en-GB') },
          // The old tiles shaded each category by its share and marked the trend with a coloured arrow
          {
            key: 'share', header: 'Share',
            render: (c) => { const p = total ? (c.article_count / total) * 100 : 0; return <Meter label={`${short(c.category)} share`} value={p} max={100} valueText={`${p.toFixed(1)}%`} />; },
          },
          {
            key: 'trend', header: 'Recent trend',
            render: (c) => (c.recent_trend === 'up'
              ? <Chip size="sm" tone="success" icon={<Icon name="ArrowUp" size="sm" />}>Rising</Chip>
              : c.recent_trend === 'down'
                ? <Chip size="sm" tone="error" icon={<Icon name="ArrowDown" size="sm" />}>Falling</Chip>
                : <Chip size="sm" tone="muted">Steady</Chip>),
          },
        ]}
      />
    </Panel>
  );
}

/** The lower half of the old dashboard: risk, sentiment mix, volume and categories. */
export function Coverage({ ctx, d }: { ctx: BwContext; d: DashboardData }) {
  const { bw, focusBrand } = ctx;
  const { comparison, temporalData, categories, loadingCategories } = bw;
  const sel = d.primaryId ? bw.brands.find((b) => b.id === d.primaryId) ?? focusBrand : null;

  // Weekly sentiment counts for the picked brand
  const weeks = d.weekly.map((w) => ({ week: w.week.slice(0, 10), ...bucketCounts(w.sentiments) })).sort((a, b) => a.week.localeCompare(b.week));
  const tot = bucketCounts(d.totals);
  const totN = tot.pos + tot.neu + tot.neg;
  const negPct = totN ? (tot.neg / totN) * 100 : 0;
  const share = (ws: typeof weeks) => {
    const n = ws.reduce((a, w) => a + w.neg, 0);
    const t = ws.reduce((a, w) => a + w.pos + w.neu + w.neg, 0);
    return t ? (n / t) * 100 : null;
  };
  const recent = share(weeks.slice(-4));
  const prior = weeks.length >= 8 ? share(weeks.slice(-8, -4)) : null;
  const trend = recent != null && prior != null ? recent - prior : 0;
  const weekMax = niceMax(Math.max(0, ...weeks.map((w) => Math.max(w.pos, w.neu, w.neg))));

  const topCats = categories.slice(0, 5).map((c) => c.category);
  const months = temporalData.slice(-12);
  const brandRows = comparison
    .filter((c) => Object.keys(c.sentiment_breakdown || {}).length > 0)
    .map((c) => {
      const b = bucketCounts(c.sentiment_breakdown);
      return { id: String(c.brand_id), label: c.brand_name, values: [b.pos, b.neu, b.neg] };
    });

  return (
    <>
      <Eyebrow as="h2">Coverage analytics</Eyebrow>

      {!d.primaryId && brandRows.length > 0 && (
        <Panel title="Sentiment by brand" description="Positive, neutral and negative articles per brand in this period." headingLevel={3}>
          <StackedBars title="Sentiment by brand" series={SENT_SERIES} rows={brandRows} />
        </Panel>
      )}

      {d.primaryId && d.hasTrends && (
        <>
          <Panel title={`Sentiment of ${sel?.display_name ?? 'the brand'}’s coverage`} headingLevel={3}>
            <Stack gap="md">
              {negPct >= 15 && (
                <Banner tone="error" title={`${negPct.toFixed(0)}% of coverage is negative`} description={`${tot.neg.toLocaleString('en-GB')} of ${totN.toLocaleString('en-GB')} articles are negative or concerning.`} />
              )}
              <StackedBars title="Sentiment of the coverage" series={SENT_SERIES} rows={[{ id: 'all', label: 'All articles', values: [tot.pos, tot.neu, tot.neg] }]} />
            </Stack>
          </Panel>
          <RiskCard d={d} />
          {weeks.length > 1 && (
            <Panel title="Sentiment over time" description="Articles per week by sentiment. A widening negative line is an early warning." headingLevel={3}>
              <Stack gap="md">
                <LineChart
                  title="Articles per week by sentiment"
                  categories={weeks.map((w) => w.week.slice(5))}
                  categoryLabels={weeks.map((w) => `Week of ${w.week}`)}
                  series={[
                    { id: 'pos', label: 'Positive', color: 'positive', values: weeks.map((w) => w.pos) },
                    { id: 'neu', label: 'Neutral', color: 'neutral', values: weeks.map((w) => w.neu) },
                    { id: 'neg', label: 'Negative', color: 'negative', fill: true, values: weeks.map((w) => w.neg) },
                  ]}
                  yDomain={[0, weekMax]}
                  yTicks={[0, weekMax / 2, weekMax]}
                />
                {trend > 2 && <Banner tone="warning" title="Negative share is rising" description={`Up ${trend.toFixed(1)} percentage points in the last 4 weeks against the 4 before.`} />}
                {trend < -2 && <Banner tone="success" title="Negative share is falling" description={`Down ${Math.abs(trend).toFixed(1)} percentage points in the last 4 weeks against the 4 before.`} />}
              </Stack>
            </Panel>
          )}
        </>
      )}
      {d.primaryId && !d.hasTrends && <RiskCard d={d} />}

      {months.length > 0 && (
        <Panel title="Articles per month" description="On-brand articles per month in the top five categories. A spike usually means a story broke." headingLevel={3}>
          <StackedBarChart
            title="Articles per month by category"
            categories={months.map((m) => m.month.slice(5))}
            series={[
              ...topCats.map((c, i) => ({ id: c, label: short(c), color: (i + 1) as 1 | 2 | 3 | 4 | 5, values: months.map((m) => m.by_category?.[c] || 0) })),
              { id: 'other', label: 'Other', color: 0 as const, values: months.map((m) => Math.max(0, m.total - topCats.reduce((s, c) => s + (m.by_category?.[c] || 0), 0))) },
            ]}
          />
        </Panel>
      )}

      {d.primaryId && bw.articles.length > 0 && (
        <Panel title="Latest articles" headingLevel={3} headerAside={<Button variant="ghost" size="sm" onClick={() => ctx.goTo('articles')}>All articles</Button>}>
          <Stack as="ul" gap="sm" label="Latest articles">
            {bw.articles.slice(0, 3).map((a) => (
              <ActivityRow key={`${a.uri}-${a.brand_id}`} as="li" primary={a.title} secondary={[a.sentiment, ...(a.categories || []).slice(0, 2).map(short)].filter(Boolean).join(' · ')} timestamp={a.publication_date?.slice(0, 10)} dateTime={a.publication_date?.slice(0, 10)} />
            ))}
          </Stack>
        </Panel>
      )}

      {loadingCategories ? <Skeleton variant="block" size="card" /> : categories.length > 0 && (
        <CategoryTable categories={categories} onOpen={(c) => ctx.goTo('articles', { selectedCategories: [c], page: 1 })} />
      )}
    </>
  );
}
