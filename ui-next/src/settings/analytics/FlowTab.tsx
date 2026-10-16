import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Checkbox, Grid, Icon, MultiSelect, Panel, Select, Skeleton, Stack, TextField } from '@aunoo/ui';
import { errorText } from '../../shell';
import { fetchFlow, type FlowRecord } from './api';
import { ChartPanel } from './ChartPanel';
import { Sankey, type SankeyLink, type SankeyNode } from './Sankey';

/*
 * "Follow the flow": how articles move from the outlets that published them, through their category,
 * to their sentiment. Reads /api/flow_data (up to 2,000 articles) and builds the flow in the browser,
 * as the old page did.
 */

const FLOW_TIMEFRAMES = [
  { value: 'all', label: 'All time' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
];
const COLOUR_BY = [
  { value: 'stage', label: 'Stage' },
  { value: 'source', label: 'Source' },
  { value: 'category', label: 'Category' },
];
// Stage colours from the design system's chart slots (source, category, sentiment)
const STAGE = ['var(--chart-1, #6366f1)', 'var(--chart-2, #8b5cf6)', 'var(--chart-3, #ec4899)'];
const hue = (i: number, n: number) => `hsl(${Math.round((i * 360) / Math.max(1, n))}, 55%, 58%)`;

interface State {
  topic: string;
  timeframe: string;
  topSources: number;
  colourBy: string;
  sources: string[];
  categories: string[];
  sentiments: string[];
  includeOther: boolean;
  showCategory: boolean;
}
const DEFAULTS: State = { topic: '', timeframe: 'all', topSources: 12, colourBy: 'stage', sources: [], categories: [], sentiments: [], includeOther: true, showCategory: true };

function build(records: FlowRecord[], s: State): { nodes: SankeyNode[]; links: SankeyLink[] } {
  const kept = records.filter((r) =>
    (!s.sources.length || s.sources.includes(r.source || '')) &&
    (!s.categories.length || s.categories.includes(r.category || '')) &&
    (!s.sentiments.length || s.sentiments.includes(r.sentiment || '')));
  const srcCount = new Map<string, number>();
  kept.forEach((r) => srcCount.set(r.source || 'Unknown source', (srcCount.get(r.source || 'Unknown source') ?? 0) + 1));
  const topSrc = new Set([...srcCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, s.topSources).map(([n]) => n));

  const nodes = new Map<string, SankeyNode>();
  const pairs = new Map<string, { source: string; target: string; value: number; origin: string; cat: string }>();
  const node = (column: number, label: string) => {
    const id = `${column}:${label}`;
    if (!nodes.has(id)) nodes.set(id, { id, label, column, color: STAGE[column] });
    return id;
  };
  kept.forEach((r) => {
    let src = r.source || 'Unknown source';
    if (!topSrc.has(src)) {
      if (!s.includeOther) return;
      src = 'Other sources';
    }
    const cat = r.category || 'Unknown';
    if (cat.toLowerCase().includes('unknown')) return; // as the old page: articles without a category are left out
    const sent = r.sentiment || 'Unknown sentiment';
    const steps: [number, string][] = s.showCategory ? [[0, src], [1, cat], [2, sent]] : [[0, src], [1, sent]];
    for (let i = 0; i < steps.length - 1; i++) {
      const a = node(steps[i][0], steps[i][1]);
      const b = node(steps[i + 1][0], steps[i + 1][1]);
      const key = `${a}>${b}|${src}|${cat}`;
      const p = pairs.get(key) ?? { source: a, target: b, value: 0, origin: src, cat };
      p.value++;
      pairs.set(key, p);
    }
  });

  // "Colour by" now works: the old page read the choice and always coloured by stage
  const srcs = [...new Set([...pairs.values()].map((p) => p.origin))];
  const cats = [...new Set([...pairs.values()].map((p) => p.cat))];
  const linkColour = (p: { origin: string; cat: string; source: string }) =>
    s.colourBy === 'source' ? hue(srcs.indexOf(p.origin), srcs.length)
      : s.colourBy === 'category' ? hue(cats.indexOf(p.cat), cats.length)
        : STAGE[Number(p.source.split(':')[0])];
  // Merge pairs again per node pair, keeping one colour per band
  const merged = new Map<string, SankeyLink>();
  pairs.forEach((p) => {
    const key = s.colourBy === 'stage' ? `${p.source}>${p.target}` : `${p.source}>${p.target}>${s.colourBy === 'source' ? p.origin : p.cat}`;
    const m = merged.get(key) ?? { source: p.source, target: p.target, value: 0, color: linkColour(p) };
    m.value += p.value;
    merged.set(key, m);
  });
  if (s.colourBy !== 'stage') {
    nodes.forEach((n) => {
      if (s.colourBy === 'source' && n.column === 0) n.color = hue(srcs.indexOf(n.label), srcs.length);
      if (s.colourBy === 'category' && n.column === 1 && s.showCategory) n.color = hue(cats.indexOf(n.label), cats.length);
    });
  }
  return { nodes: [...nodes.values()], links: [...merged.values()] };
}

export function FlowTab({ topics, notify }: { topics: string[]; notify: (m: string) => void }) {
  const [s, setS] = useState<State>(DEFAULTS);
  const [records, setRecords] = useState<FlowRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const set = (patch: Partial<State>) => setS((c) => ({ ...c, ...patch }));

  useEffect(() => {
    let live = true;
    setRecords(null);
    setError(null);
    fetchFlow(s.timeframe, s.topic).then((r) => live && setRecords(Array.isArray(r) ? r : []), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [s.timeframe, s.topic, reload]);

  const uniq = (k: keyof FlowRecord) => [...new Set((records ?? []).map((r) => r[k]).filter(Boolean) as string[])].sort().map((v) => ({ value: v, label: v }));
  const flow = useMemo(() => (records ? build(records, s) : null), [records, s]);

  return (
    <Stack gap="lg">
      <Panel
        title="Follow the flow"
        description="How articles move from the outlets that published them, through their category, to their sentiment. Articles without a category are left out."
        headerAside={
          <Stack direction="row" gap="sm">
            <Button variant="secondary" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => setReload((n) => n + 1)}>Refresh</Button>
            <Button variant="ghost" size="sm" onClick={() => setS(DEFAULTS)}>Reset</Button>
          </Stack>
        }
      >
        <Stack gap="md">
          <Grid columns={4} gap="md">
            <Select label="Topic" options={[{ value: 'all', label: 'All topics' }, ...topics.map((t) => ({ value: t, label: t }))]} value={s.topic || 'all'} onValueChange={(v) => set({ topic: v === 'all' ? '' : v, sources: [], categories: [], sentiments: [] })} fullWidth />
            <Select label="Timeframe" options={FLOW_TIMEFRAMES} value={s.timeframe} onValueChange={(timeframe) => set({ timeframe })} fullWidth />
            <TextField label="Top sources" type="number" min={3} max={50} value={String(s.topSources)} onChange={(v) => set({ topSources: Math.max(3, Math.min(50, Number(v) || 12)) })} hint="The rest are grouped as “Other sources”." />
            <Select label="Colour by" options={COLOUR_BY} value={s.colourBy} onValueChange={(colourBy) => set({ colourBy })} fullWidth />
          </Grid>
          <Grid columns={3} gap="md">
            <MultiSelect label="Sources" options={uniq('source')} value={s.sources} onValueChange={(sources) => set({ sources })} placeholder="All sources" />
            <MultiSelect label="Categories" options={uniq('category').filter((o) => o.value !== 'Unknown category')} value={s.categories} onValueChange={(categories) => set({ categories })} placeholder="All categories" />
            <MultiSelect label="Sentiments" options={uniq('sentiment')} value={s.sentiments} onValueChange={(sentiments) => set({ sentiments })} placeholder="All sentiments" />
          </Grid>
          <Stack direction="row" gap="lg">
            <Checkbox label="Include “Other sources”" checked={s.includeOther} onCheckedChange={(includeOther) => set({ includeOther })} />
            <Checkbox label="Show the category step" checked={s.showCategory} onCheckedChange={(showCategory) => set({ showCategory })} />
          </Stack>
        </Stack>
      </Panel>
      {error && <Banner tone="error" title="The flow didn’t load" description={error} />}
      {!flow ? (!error && <Skeleton variant="block" size="card" />) : (
        <ChartPanel
          title={s.showCategory ? 'Article flow: source → category → sentiment' : 'Article flow: source → sentiment'}
          description={`${records!.length.toLocaleString()} articles read (at most 2,000, the newest first).`}
          file="article-flow"
          notify={notify}
        >
          <Sankey title="Article flow" nodes={flow.nodes} links={flow.links} />
        </ChartPanel>
      )}
    </Stack>
  );
}
