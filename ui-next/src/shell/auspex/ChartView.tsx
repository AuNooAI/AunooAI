import { DonutChart, LineChart, RadarChart, StackedBarChart, Table, Text, type ChartColor } from '@aunoo/ui';
import type { ChartSpec } from './markers';

/*
 * Auspex charts arrive as Plotly figure JSON ({data: traces, layout}), or from deep research as
 * {data: {labels, values}}. The old chat drew them with a Plotly script tag; here the common trace
 * types map onto the library's charts, and anything else shows as a table.
 */

type Trace = { type?: string; name?: string; labels?: unknown; values?: unknown; x?: unknown; y?: unknown; r?: unknown; theta?: unknown; orientation?: string; mode?: string };

/** Plotly ≥6 can pack number arrays as {dtype, bdata}; Plotly 5 sends plain lists. */
function nums(v: unknown): number[] {
  if (Array.isArray(v)) return v.map((x) => Number(x) || 0);
  const p = v as { dtype?: string; bdata?: string } | null;
  if (p?.bdata && p.dtype) {
    const bytes = Uint8Array.from(atob(p.bdata), (c) => c.charCodeAt(0));
    const T = { f8: Float64Array, f4: Float32Array, i4: Int32Array, i2: Int16Array, i1: Int8Array, u4: Uint32Array, u2: Uint16Array, u1: Uint8Array }[p.dtype];
    if (T) return Array.from(new T(bytes.buffer));
  }
  return [];
}
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)) : nums(v).map(String));

const SENTIMENT: Record<string, ChartColor> = { positive: 'positive', negative: 'negative', neutral: 'neutral', critical: 'negative', mixed: 'caution' };
const slot = (i: number) => ((i % 5) + 1) as 1 | 2 | 3 | 4 | 5;
const colorFor = (label: string, i: number): ChartColor => SENTIMENT[label.toLowerCase()] ?? slot(i);

const titleOf = (spec: ChartSpec) => {
  const t = spec.title ?? (spec.layout?.title as { text?: string } | string | undefined);
  const s = typeof t === 'string' ? t : t?.text;
  return s || (spec.type ?? spec.chart_type ?? 'Chart').replace(/_/g, ' ');
};

/** About five ticks on a 1-2-5 step, from zero. */
function ticks(max: number): { domain: [number, number]; ticks: number[] } {
  const raw = (max > 0 ? max : 1) / 5;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((x) => x >= raw) ?? 10 * mag;
  const end = Math.ceil((max > 0 ? max : 1) / step) * step;
  const t: number[] = [];
  for (let v = 0; v <= end + step / 2; v += step) t.push(Number(v.toPrecision(6)));
  return { domain: [0, end], ticks: t };
}

export function ChartView({ spec }: { spec: ChartSpec }) {
  const title = titleOf(spec);
  const fig = spec.data as { data?: Trace[]; labels?: unknown; values?: unknown } | Trace[] | undefined;
  const traces: Trace[] = Array.isArray(fig) ? fig : Array.isArray(fig?.data) ? fig!.data! : fig && 'labels' in fig ? [{ type: 'pie', labels: fig.labels, values: fig.values }] : [];
  if (!traces.length) return <Text variant="hint">{`${title}: no data to draw.`}</Text>;

  const kind = traces[0].type ?? 'scatter';
  if (kind === 'pie') {
    const labels = strs(traces[0].labels);
    const values = nums(traces[0].values);
    return <DonutChart title={title} segments={labels.map((l, i) => ({ id: `${i}`, label: l, value: values[i] ?? 0, color: colorFor(l, i) }))} />;
  }
  if (kind === 'bar') {
    const horizontal = traces[0].orientation === 'h';
    const categories = strs(horizontal ? traces[0].y : traces[0].x);
    return (
      <StackedBarChart
        title={title}
        categories={categories}
        series={traces.map((t, i) => {
          const cats = strs(horizontal ? t.y : t.x);
          const vals = nums(horizontal ? t.x : t.y);
          return { id: `${i}`, label: t.name || title, color: slot(i), values: categories.map((c) => vals[cats.indexOf(c)] ?? 0) };
        })}
      />
    );
  }
  if (kind === 'scatterpolar') {
    const axes = strs(traces[0].theta);
    return <RadarChart title={title} axes={axes} series={traces.map((t, i) => ({ id: `${i}`, label: t.name || title, color: slot(i), values: nums(t.r) }))} />;
  }
  if (kind === 'scatter') {
    const categories = [...new Set(traces.flatMap((t) => strs(t.x)))].sort();
    const series = traces.map((t, i) => {
      const xs = strs(t.x);
      const ys = nums(t.y);
      const name = t.name || title;
      return { id: `${i}`, label: name, color: SENTIMENT[name.toLowerCase()] === 'caution' ? slot(i) : ((SENTIMENT[name.toLowerCase()] as 'positive' | 'negative' | 'neutral' | undefined) ?? slot(i)), values: categories.map((c) => { const j = xs.indexOf(c); return j < 0 ? null : ys[j]; }) };
    });
    const max = Math.max(0, ...series.flatMap((s) => s.values.filter((v): v is number => v != null)));
    const { domain, ticks: yTicks } = ticks(max);
    const short = categories.map((c) => (/^\d{4}-\d{2}-\d{2}/.test(c) ? c.slice(5, 10) : c));
    return <LineChart title={title} categories={categories} categoryLabels={short} series={series} yDomain={domain} yTicks={yTicks} />;
  }
  // Anything else: the numbers as a table
  const rows = traces.flatMap((t, i) => {
    const xs = strs(t.x ?? t.labels);
    const ys = nums(t.y ?? t.values);
    return xs.map((x, j) => ({ id: `${i}-${j}`, series: t.name || `Series ${i + 1}`, x, y: ys[j] ?? '' }));
  });
  return (
    <Table
      caption={title}
      rowKey={(r) => r.id}
      rows={rows}
      columns={[
        { key: 'series', header: 'Series', render: (r) => r.series },
        { key: 'x', header: 'Label', rowHeader: true, render: (r) => r.x },
        { key: 'y', header: 'Value', align: 'end', render: (r) => String(r.y) },
      ]}
    />
  );
}
