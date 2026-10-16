import { useEffect, useMemo, useState } from 'react';
import {
  Banner, BubbleMatrix, Checkbox, DonutChart, EmptyState, Grid, LineChart, MultiSelect, Panel, RadarChart, SegmentedControl, Select, Skeleton,
  Stack, StackedBarChart, Stat, Text,
} from '@aunoo/ui';
import { errorText } from '../../shell';
import {
  fetchAnalytics, fetchCategories, fetchTopicOptions, TIMEFRAMES,
  type AnalyticsData, type Bubble, type ByCategory, type Distribution, type Filters, type TopicOptions,
} from './api';
import { ChartPanel } from './ChartPanel';
import { lineColor, ordered, sentimentColor, slot, stackSlot, timeColor } from './colors';

/*
 * The Charts tab of the old Analytics page: one topic's articles broken down by sentiment, future
 * signal, time to impact and category, with the same filters. Every chart reads /api/analytics.
 */

const KEY = 'aunoo.settings.analytics';
const EMPTY: Filters = { topic: '', categories: [], timeframe: 'all', curated: true, sentiments: [], timeToImpacts: [], driverTypes: [] };

function loadFilters(): Filters {
  try {
    return { ...EMPTY, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return EMPTY;
  }
}

const PERIODS = [
  { value: '1m', label: '1 month' },
  { value: '6m', label: '6 months' },
  { value: 'ytd', label: 'This year' },
  { value: '1y', label: '1 year' },
  { value: 'all', label: 'All' },
];

function cutoff(period: string): string | null {
  const d = new Date();
  if (period === '1m') d.setMonth(d.getMonth() - 1);
  else if (period === '6m') d.setMonth(d.getMonth() - 6);
  else if (period === 'ytd') return `${d.getFullYear()}-01-01`;
  else if (period === '1y') d.setFullYear(d.getFullYear() - 1);
  else return null;
  return d.toISOString().slice(0, 10);
}

/** A y axis from 0 to a round number above the largest value */
function axis(max: number): { domain: [number, number]; ticks: number[] } {
  const top = Math.max(1, max);
  const step = Math.pow(10, Math.floor(Math.log10(top)));
  const nice = [1, 2, 5, 10].map((m) => m * step).find((s) => top / s <= 5) ?? step * 10;
  const end = Math.ceil(top / nice) * nice;
  const ticks: number[] = [];
  for (let v = 0; v <= end; v += nice) ticks.push(v);
  return { domain: [0, end], ticks };
}

const top = (d: Distribution | undefined) => {
  if (!d?.values?.length) return null;
  const i = d.values.indexOf(Math.max(...d.values));
  return d.values[i] > 0 ? { label: d.labels[i], n: d.values[i] } : null;
};

function DistributionPair({ title, file, dist, known, color, notify }: {
  title: string; file: string; dist: Distribution; known: string[]; color: (l: string, i: number) => import('@aunoo/ui').ChartColor; notify: (m: string) => void;
}) {
  const labels = ordered(dist.labels, known);
  const value = (l: string) => dist.values[dist.labels.indexOf(l)] ?? 0;
  return (
    <Grid columns={2} gap="md">
      <ChartPanel title={`${title}: share`} file={`${file}-share`} notify={notify}>
        <DonutChart title={title} segments={labels.map((l, i) => ({ id: l, label: l, value: value(l), color: color(l, i) }))} emptyText="No articles match these filters." />
      </ChartPanel>
      <ChartPanel title={`${title}: counts`} file={`${file}-counts`} notify={notify}>
        <StackedBarChart title={title} categories={labels} series={[{ id: 'n', label: 'Articles', color: 1, values: labels.map(value) }]} emptyText="No articles match these filters." />
      </ChartPanel>
    </Grid>
  );
}

function ByCategoryChart({ title, file, data, keys, known, notify, description }: {
  title: string; file: string; data: ByCategory; keys: string[]; known: string[]; notify: (m: string) => void; description: string;
}) {
  const series = ordered(keys, known);
  return (
    <ChartPanel title={title} description={description} file={file} notify={notify}>
      {/* The design system's stacked bars carry six colours; a seventh value reuses the first */}
      <StackedBarChart
        title={title}
        categories={data.categories}
        series={series.map((s, i) => ({ id: s, label: s, color: stackSlot(i), values: data.categories.map((c) => data.data?.[c]?.[s] ?? 0) }))}
        emptyText="No articles match these filters."
      />
    </ChartPanel>
  );
}

function Bubbles({ title, file, rows, rowField, rowKnown, signals, color, notify, description }: {
  title: string; file: string; rows: Bubble[]; rowField: 'sentiment' | 'time_to_impact'; rowKnown: string[]; signals: string[];
  color: (l: string, i: number) => import('@aunoo/ui').ChartColor; notify: (m: string) => void; description: string;
}) {
  const rowLabels = ordered([...new Set(rows.map((r) => r[rowField] ?? ''))].filter(Boolean), rowKnown);
  const cols = ordered([...new Set(rows.map((r) => r.future_signal))].filter(Boolean), signals);
  const count = (row: string, col: string) => rows.filter((r) => r[rowField] === row && r.future_signal === col).reduce((a, r) => a + r.count, 0);
  return (
    <ChartPanel title={title} description={description} file={file} notify={notify}>
      {!rows.length ? <Text>No articles match these filters.</Text> : (
        <div className="an-scroll">
          <BubbleMatrix title={title} hideTitle columns={cols} rows={rowLabels.map((r, i) => ({ id: r, label: r, color: color(r, i), values: cols.map((c) => count(r, c)) }))} />
        </div>
      )}
    </ChartPanel>
  );
}

function SentimentOverTime({ data, known, notify }: { data: AnalyticsData['sentimentTimeSeries']; known: string[]; notify: (m: string) => void }) {
  const [period, setPeriod] = useState('all');
  const [average, setAverage] = useState(true);
  const view = useMemo(() => {
    const from = cutoff(period);
    const dates = [...new Set(data.map((d) => d.date))].sort().filter((d) => !from || d >= from);
    const sentiments = ordered([...new Set(data.map((d) => d.sentiment))], known);
    const counts = (s: string) => dates.map((d) => data.filter((x) => x.date === d && x.sentiment === s).reduce((a, x) => a + x.count, 0));
    // Average of this point and the two before it. The old chart never reset its divisor, so its
    // "moving average" sank towards zero along the line, and it was labelled 3-month.
    const avg = (v: number[]) => v.map((_, i) => {
      const w = v.slice(Math.max(0, i - 2), i + 1);
      return Math.round((w.reduce((a, x) => a + x, 0) / w.length) * 10) / 10;
    });
    const series = sentiments.flatMap((s, i) => {
      const v = counts(s);
      const base = { id: s, label: s, color: lineColor(s, i), markers: dates.length <= 40, values: v };
      return average ? [base, { id: `${s}-avg`, label: `${s} (average of 3 points)`, color: lineColor(s, i), dashed: true, values: avg(v) }] : [base];
    });
    const max = Math.max(0, ...series.flatMap((s) => s.values.map((x) => x ?? 0)));
    return { dates, series, ...axis(max) };
  }, [data, known, period, average]);
  return (
    <ChartPanel
      title="Sentiment over time"
      description="Articles per sentiment, by publication date."
      file="sentiment-over-time"
      notify={notify}
      aside={<SegmentedControl label="Period" options={PERIODS} value={period} onValueChange={setPeriod} />}
    >
      <Stack gap="sm">
        <Checkbox label="Show the average of each point and the two before it" checked={average} onCheckedChange={setAverage} />
        {view.dates.length < 2 ? <Text>Not enough dates in this period to draw a line.</Text> : (
          <LineChart title="Sentiment over time" categories={view.dates} series={view.series} yDomain={view.domain} yTicks={view.ticks} formatValue={(v) => `${v} articles`} />
        )}
      </Stack>
    </ChartPanel>
  );
}

function CategoriesOverTime({ data, notify }: { data: AnalyticsData['categoryTimeSeries']; notify: (m: string) => void }) {
  const [period, setPeriod] = useState('all');
  const view = useMemo(() => {
    const from = cutoff(period);
    const dates = [...new Set(data.map((d) => d.date))].sort().filter((d) => !from || d >= from);
    const cats = [...new Set(data.map((d) => d.category))];
    // Biggest categories first, so the six colours go to the ones that matter most
    const total = (c: string) => data.filter((d) => d.category === c && dates.includes(d.date)).reduce((a, d) => a + d.count, 0);
    cats.sort((a, b) => total(b) - total(a));
    return { dates, series: cats.map((c, i) => ({ id: c, label: c, color: stackSlot(i), values: dates.map((d) => data.filter((x) => x.date === d && x.category === c).reduce((a, x) => a + x.count, 0)) })) };
  }, [data, period]);
  return (
    <ChartPanel
      title="Category counts over time"
      description="Articles per category, by publication date."
      file="category-counts-over-time"
      notify={notify}
      aside={<SegmentedControl label="Period" options={PERIODS} value={period} onValueChange={setPeriod} />}
    >
      <div className="an-scroll">
        <StackedBarChart title="Category counts over time" categories={view.dates} series={view.series} maxLabels={12} emptyText="No articles in this period." />
      </div>
    </ChartPanel>
  );
}

export function ChartsTab({ topics, notify }: { topics: string[]; notify: (m: string) => void }) {
  const [f, setF] = useState<Filters>(loadFilters);
  const [options, setOptions] = useState<TopicOptions | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<Filters>) => setF((cur) => ({ ...cur, ...patch }));

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(f));
    } catch {
      // per visit only
    }
  }, [f]);

  // A remembered topic that no longer exists is dropped
  useEffect(() => {
    if (topics.length && f.topic && !topics.includes(f.topic)) set({ ...EMPTY });
  }, [topics]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!f.topic) {
      setOptions(null);
      setCategories([]);
      return;
    }
    let live = true;
    Promise.all([fetchTopicOptions(f.topic), fetchCategories(f.topic).catch(() => [] as string[])]).then(
      ([o, c]) => {
        if (!live) return;
        setOptions(o);
        setCategories(c);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [f.topic]);

  const key = JSON.stringify(f);
  useEffect(() => {
    if (!f.topic) {
      setData(null);
      return;
    }
    let live = true;
    setLoading(true);
    setError(null);
    fetchAnalytics(f)
      .then((d) => live && setData(d), (e) => live && setError(errorText(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const o = options ?? { sentiments: [], futureSignals: [], timeToImpacts: [], driverTypes: [] };
  const opt = (v: string[]) => v.map((x) => ({ value: x, label: x }));
  const stats = data && [
    { label: 'Articles', value: data.totalArticles.toLocaleString(), meta: f.curated ? 'curated only' : 'all collected' },
    ...[['Top sentiment', top(data.sentimentDistribution)], ['Top future signal', top(data.futureSignalDistribution)], ['Top time to impact', top(data.timeToImpactDistribution)]].map(([label, t]) => {
      const v = t as { label: string; n: number } | null;
      return { label: label as string, value: v?.label ?? '—', meta: v ? `${v.n.toLocaleString()} articles` : 'no articles' };
    }),
  ];

  return (
    <Stack gap="lg">
      <Panel title="Filters" description="Pick a topic; the other filters narrow its articles. Empty filters mean all.">
        <Stack gap="md">
          <Grid columns={4} gap="md">
            <Select label="Topic" placeholder="Pick a topic" options={topics.map((t) => ({ value: t, label: t }))} value={f.topic || undefined} onValueChange={(topic) => set({ ...EMPTY, topic, timeframe: f.timeframe, curated: f.curated })} fullWidth />
            <MultiSelect label="Categories" options={opt(categories)} value={f.categories} onValueChange={(categories) => set({ categories })} placeholder="All categories" disabled={!f.topic} />
            <Select label="Timeframe" options={TIMEFRAMES} value={f.timeframe} onValueChange={(timeframe) => set({ timeframe })} fullWidth />
            <Checkbox label="Only curated articles" checked={f.curated} onCheckedChange={(curated) => set({ curated })} />
          </Grid>
          <Grid columns={3} gap="md">
            <MultiSelect label="Sentiment" options={opt(o.sentiments)} value={f.sentiments} onValueChange={(sentiments) => set({ sentiments })} placeholder="All sentiments" disabled={!f.topic} />
            <MultiSelect label="Time to impact" options={opt(o.timeToImpacts)} value={f.timeToImpacts} onValueChange={(timeToImpacts) => set({ timeToImpacts })} placeholder="All" disabled={!f.topic} />
            <MultiSelect label="Driver type" options={opt(o.driverTypes)} value={f.driverTypes} onValueChange={(driverTypes) => set({ driverTypes })} placeholder="All driver types" disabled={!f.topic} />
          </Grid>
        </Stack>
      </Panel>

      {error && <Banner tone="error" title="The analytics didn’t load" description={error} />}
      {!f.topic ? (
        <Panel title="Charts"><EmptyState icon="ChartBar" title="Pick a topic">The charts show the articles of one topic. Pick it in the filters above.</EmptyState></Panel>
      ) : !data ? (loading ? <Skeleton variant="block" size="card" /> : null) : (
        <>
          <Grid columns={4} gap="md">
            {stats!.map((s) => <Stat key={s.label} label={s.label} value={s.value} meta={s.meta} size="compact" wrapValue />)}
          </Grid>
          <DistributionPair title="Sentiment" file="sentiment-distribution" dist={data.sentimentDistribution} known={o.sentiments} color={sentimentColor} notify={notify} />
          <DistributionPair title="Time to impact" file="time-to-impact-distribution" dist={data.timeToImpactDistribution} known={o.timeToImpacts} color={timeColor} notify={notify} />
          <DistributionPair title="Future signal" file="future-signal-distribution" dist={data.futureSignalDistribution} known={o.futureSignals} color={(_l, i) => slot(i)} notify={notify} />
          <ByCategoryChart
            title="Sentiment across categories" file="sentiment-by-category" notify={notify}
            description="How each category's articles split by sentiment. This breakdown covers the whole topic; the category filter doesn't apply to it."
            data={data.sentimentByCategory} keys={data.sentimentByCategory.sentiments ?? []} known={o.sentiments}
          />
          <ByCategoryChart
            title="Future signal across categories" file="future-signal-by-category" notify={notify}
            description="How each category's articles split by future signal. This breakdown covers the whole topic; the category filter doesn't apply to it."
            data={data.futureSignalByCategory} keys={data.futureSignalByCategory.future_signals ?? []} known={o.futureSignals}
          />
          <Bubbles
            title="Articles by future signal and sentiment" file="future-signal-by-sentiment" notify={notify}
            description="Each circle is the number of articles with that future signal and sentiment."
            rows={data.articlesBubbleChart} rowField="sentiment" rowKnown={o.sentiments} signals={o.futureSignals} color={sentimentColor}
          />
          <Bubbles
            title="Articles by future signal and time to impact" file="future-signal-by-time-to-impact" notify={notify}
            description="Each circle is the number of articles with that future signal and time to impact."
            rows={data.articlesFutureTimeBubbleChart} rowField="time_to_impact" rowKnown={o.timeToImpacts} signals={o.futureSignals} color={timeColor}
          />
          <RadarPanel data={data.radarChartData} o={o} notify={notify} />
          <SentimentOverTime data={data.sentimentTimeSeries ?? []} known={o.sentiments} notify={notify} />
          <CategoriesOverTime data={data.categoryTimeSeries ?? []} notify={notify} />
        </>
      )}
    </Stack>
  );
}

/** Future signals around the circle, one line per sentiment: how many articles carry each pair */
function RadarPanel({ data, o, notify }: { data: Bubble[]; o: TopicOptions; notify: (m: string) => void }) {
  const axes = ordered([...new Set(data.map((d) => d.future_signal))].filter(Boolean), o.futureSignals);
  const sentiments = ordered([...new Set(data.map((d) => d.sentiment ?? ''))].filter(Boolean), o.sentiments);
  const count = (s: string, a: string) => data.filter((d) => d.sentiment === s && d.future_signal === a).reduce((x, d) => x + d.count, 0);
  return (
    <ChartPanel title="Future signal by sentiment" description="Future signals around the circle; each line is one sentiment, further out means more articles." file="future-signal-radar" notify={notify}>
      {axes.length < 3 ? <Text>A radar needs at least three future signals; these filters leave {axes.length}.</Text> : (
        <RadarChart title="Future signal by sentiment" axes={axes} series={sentiments.map((s, i) => ({ id: s, label: s, color: sentimentColor(s, i), values: axes.map((a) => count(s, a)) }))} formatValue={(v) => `${v} articles`} />
      )}
    </ChartPanel>
  );
}
