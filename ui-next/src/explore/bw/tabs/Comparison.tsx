import { useEffect, useMemo, useState } from 'react';
import { Button, DonutChart, EmptyState, LineItems, Panel, Select, Skeleton, Stack, StackedBars, Table, Text } from '@aunoo/ui';
import { getAllAppRatings, type BWAllAppRatings, type BWComparison } from '@monolith/brandWatcherApi';
import type { BwContext } from '../context';
import { AppRatingsComparison } from './analysis/AppRatings';
import { bucketCounts, brandColors, short, topN, topNOptions } from './analysis/shared';

/*
 * Side-by-side brands (GET /comparison, /share-of-voice, /app-ratings), as the old Comparison tab:
 * share of voice, category breakdown, the category table (every cell opens those articles) and
 * sentiment by brand. Shows the primary brand plus the top N by article volume.
 */

export function Comparison({ bw, goTo }: BwContext) {
  const { comparison, shareOfVoice, brands, fetchComparison, fetchShareOfVoice } = bw;
  const days = bw.config.daysBack;
  const [n, setN] = useState(5);
  const [category, setCategory] = useState('all');
  const [apps, setApps] = useState<BWAllAppRatings | null>(null);

  useEffect(() => {
    void fetchComparison();
    void fetchShareOfVoice();
  }, [fetchComparison, fetchShareOfVoice, days]);
  useEffect(() => {
    getAllAppRatings().then(setApps, () => setApps({ brands: [] }));
  }, []);

  const primary = useMemo(() => new Set(brands.filter((b) => b.is_primary).map((b) => b.id)), [brands]);
  const colors = brandColors([...brands].sort((a, b) => Number(b.is_primary) - Number(a.is_primary)).map((b) => b.id));
  const total = Math.max(comparison.length, shareOfVoice.length);

  const comp = n >= comparison.length ? comparison : (() => { const k = topN(comparison, n, (c) => c.total_articles, primary); return comparison.filter((c) => k.has(c.brand_id)); })();
  const sov = (() => {
    if (n >= shareOfVoice.length) return shareOfVoice;
    const k = topN(shareOfVoice, n, (r) => r.mention_count, primary);
    const shown = shareOfVoice.filter((r) => k.has(r.brand_id));
    const rest = shareOfVoice.filter((r) => !k.has(r.brand_id));
    if (rest.length) {
      shown.push({ ...rest[0], brand_id: -1, brand_name: `Others (${rest.length})`, color: null,
        mention_count: rest.reduce((s, r) => s + r.mention_count, 0), percentage: rest.reduce((s, r) => s + r.percentage, 0), owned_count: 0 });
    }
    return shown;
  })();

  const cats = useMemo(() => {
    const set = new Set<string>();
    comp.forEach((c) => Object.entries(c.category_breakdown).forEach(([k, v]) => v > 0 && set.add(k)));
    const sum = (cat: string) => comp.reduce((s, c) => s + (c.category_breakdown[cat] ?? 0), 0);
    return [...set].sort((a, b) => sum(b) - sum(a));
  }, [comp]);
  const shownCats = category === 'all' ? cats.slice(0, 8) : [category];

  if (bw.loadingComparison && !comparison.length) return <Skeleton variant="block" size="chart" />;
  if (!comparison.length && !shareOfVoice.length) {
    return <Panel title="Comparison"><EmptyState icon="ChartBar">No comparison data yet. Add brands and run classification first.</EmptyState></Panel>;
  }

  return (
    <>
      <Stack direction="row" justify="end" gap="sm">
        <Select label="Brands shown" hideLabel options={topNOptions(total)} value={String(Math.min(n, total))} onValueChange={(v) => setN(Number(v))} />
      </Stack>
      <Text variant="caption">Shows the primary brand and the brands with the most articles in this period. Share of voice folds the rest into one “Others” slice.</Text>

      {apps && apps.brands.length > 0 && <AppRatingsComparison brands={apps.brands} />}

      {sov.length > 0 && (
        <Panel title="Share of voice" description="Coverage about each brand, as a share of all tracked brands. A brand’s own posts and pages are listed apart and not counted.">
          <Stack gap="md">
            <DonutChart
              title="Share of voice"
              segments={sov.map((s) => ({ id: String(s.brand_id), label: s.brand_name, value: s.mention_count, color: s.brand_id < 0 ? 0 : colors.get(s.brand_id) ?? 0 }))}
              centerLabel={`${sov.reduce((t, s) => t + s.mention_count, 0)} articles`}
            />
            <Stack as="ul" gap="sm" label="Share of voice by brand">
              {sov.map((s) => (
                <li key={s.brand_id}>
                  <Stack direction="row" justify="between" gap="sm">
                    {s.brand_id < 0 ? <Text as="span">{s.brand_name}</Text> : (
                      <Button variant="ghost" size="sm" onClick={() => goTo('articles', { selectedBrandIds: [s.brand_id], selectedCategories: [] })}>{s.brand_name}</Button>
                    )}
                    <Text variant="label" as="span">
                      {s.percentage.toFixed(1)}% · {s.mention_count} articles{(s.owned_count ?? 0) > 0 ? ` · +${s.owned_count} own posts` : ''}
                    </Text>
                  </Stack>
                </li>
              ))}
            </Stack>
          </Stack>
        </Panel>
      )}

      {comp.length > 0 && (
        <Panel
          title="Category breakdown"
          headerAside={
            <Select
              label="Category"
              hideLabel
              options={[{ value: 'all', label: 'Top 8 categories' }, ...cats.map((c) => ({ value: c, label: `${c} (${comp.reduce((s, x) => s + (x.category_breakdown[c] ?? 0), 0)})` }))]}
              value={category}
              onValueChange={setCategory}
            />
          }
        >
          <StackedBars
            title="Articles per category and brand"
            series={comp.map((c) => ({ id: String(c.brand_id), label: c.brand_name, color: colors.get(c.brand_id) ?? 0 }))}
            rows={shownCats.map((cat) => ({ id: cat, label: cat, values: comp.map((c) => c.category_breakdown[cat] ?? 0) }))}
            emptyText="No categorised articles in this period."
          />
        </Panel>
      )}

      {comp.length > 0 && (
        <Panel title="Category comparison" description="Select a number to open those articles. A brand’s biggest category is marked “top”.">
          <Table<BWComparison>
            caption="Articles per brand and category"
            hideCaption
            rows={comp}
            rowKey={(c) => String(c.brand_id)}
            columns={[
              { key: 'brand', header: 'Brand', rowHeader: true, render: (c) => c.brand_name },
              { key: 'total', header: 'Total', align: 'end', render: (c) => c.total_articles },
              ...cats.map((cat) => ({
                key: cat,
                header: short(cat),
                align: 'end' as const,
                render: (c: BWComparison) => {
                  const count = c.category_breakdown[cat] ?? 0;
                  if (!count) return '–';
                  const lead = Object.entries(c.category_breakdown).sort(([, a], [, b]) => b - a)[0]?.[0] === cat;
                  return (
                    <Button variant="ghost" size="sm" onClick={() => goTo('articles', { selectedBrandIds: [c.brand_id], selectedCategories: [cat] })}>
                      {lead ? `${count} (top)` : String(count)}
                      <span className="visually-hidden"> {c.brand_name} articles in {cat}</span>
                    </Button>
                  );
                },
              })),
            ]}
          />
        </Panel>
      )}

      {comp.some((c) => Object.keys(c.sentiment_breakdown ?? {}).length > 0) && (
        <Panel title="Sentiment by brand" description="Every article’s sentiment, grouped into positive, neutral and negative.">
          <Stack gap="md">
            <StackedBars
              title="Sentiment by brand"
              series={[{ id: 'pos', label: 'Positive', color: 'positive' }, { id: 'neu', label: 'Neutral', color: 'neutral' }, { id: 'neg', label: 'Negative', color: 'negative' }]}
              rows={comp.map((c) => {
                const s = bucketCounts(c.sentiment_breakdown);
                return { id: String(c.brand_id), label: c.brand_name, values: [s.positive, s.neutral, s.negative] };
              })}
            />
            <LineItems
              label="Net sentiment by brand"
              items={comp.map((c) => {
                const s = bucketCounts(c.sentiment_breakdown);
                const t = s.positive + s.neutral + s.negative;
                return { id: String(c.brand_id), label: c.brand_name, amount: t ? `net ${Math.round(((s.positive - s.negative) / t) * 100)} (${s.positive} positive, ${s.negative} negative)` : 'Nothing scored' };
              })}
            />
          </Stack>
        </Panel>
      )}
    </>
  );
}
