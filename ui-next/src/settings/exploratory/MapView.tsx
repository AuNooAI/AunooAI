import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Icon, Select, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import { errorText } from '../../shell';
import { getProjection, type Projection, type ProjectionPoint } from './api';
import { palette, SENTIMENT_COLOUR } from './colours';
import { ProjectionScatter } from './ProjectionScatter';
import './exploratory.css';

/*
 * The old Visuals tab: every article in the search placed on a map by meaning, coloured by cluster
 * or by a field. The map is drawn when the tab opens and again when you press Redraw; it runs on
 * the server's CPU and calls no AI. The old 3D view and the cluster-method menu are left out: the
 * server never read the cluster method (it always uses k-means), and there is no 3D chart here.
 */

const METHODS = [{ value: 'umap', label: 'UMAP' }, { value: 'tsne', label: 't-SNE' }, { value: 'pca', label: 'PCA' }];
const COLOUR_BY = [
  { value: 'cluster', label: 'Colour by cluster' },
  { value: 'sentiment', label: 'Colour by sentiment' },
  { value: 'category', label: 'Colour by category' },
  { value: 'driver_type', label: 'Colour by driver' },
  { value: 'time_to_impact', label: 'Colour by time to impact' },
] as const;
type ColourBy = (typeof COLOUR_BY)[number]['value'];

export function MapView({ scope, onSelect }: { scope: URLSearchParams; onSelect: (p: ProjectionPoint) => void }) {
  const [method, setMethod] = useState('umap');
  const [clusters, setClusters] = useState('30');
  const [colourBy, setColourBy] = useState<ColourBy>('cluster');
  const [run, setRun] = useState(0);
  const [data, setData] = useState<Projection | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = scope.toString();

  useEffect(() => {
    let live = true;
    setData(null);
    setErr(null);
    const p = new URLSearchParams(scope);
    p.set('method', method);
    p.set('dims', '2');
    const n = Math.min(100, Math.max(2, Number(clusters) || 30));
    p.set('n_clusters', String(n));
    getProjection(p).then((d) => live && setData(d), (e) => live && setErr(errorText(e)));
    return () => {
      live = false;
    };
  }, [key, run]); // eslint-disable-line react-hooks/exhaustive-deps

  const { colourOf, legend } = useMemo(() => {
    const pts = data?.points ?? [];
    const valueOf = (p: ProjectionPoint) => (colourBy === 'cluster' ? String(p.cluster) : String(p[colourBy] ?? 'not set'));
    const counts = new Map<string, number>();
    for (const p of pts) counts.set(valueOf(p), (counts.get(valueOf(p)) ?? 0) + 1);
    const values = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([v]) => v);
    const cols = palette(values.length);
    const map = new Map(values.map((v, i) => [v, colourBy === 'sentiment' ? SENTIMENT_COLOUR[v.toLowerCase()] ?? cols[i] : cols[i]]));
    return {
      colourOf: (p: ProjectionPoint) => map.get(valueOf(p)) ?? 'var(--viz-neutral)',
      legend: values.slice(0, 24).map((v) => ({ v, n: counts.get(v) ?? 0, c: map.get(v)! })),
    };
  }, [data, colourBy]);

  return (
    <Stack gap="md">
      <Stack direction="row" gap="sm">
        <Select label="Layout method" hideLabel options={METHODS} value={method} onValueChange={setMethod} />
        <TextField label="Number of clusters" hideLabel type="number" min={2} max={100} value={clusters} onChange={setClusters} />
        <Select label="Colour" hideLabel options={[...COLOUR_BY]} value={colourBy} onValueChange={(v) => setColourBy(v as ColourBy)} />
        <Button variant="secondary" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => setRun((r) => r + 1)}>Redraw</Button>
      </Stack>
      <Text variant="caption">UMAP keeps nearby articles together and is the default; t-SNE separates tight groups more; PCA is fastest. The number of clusters only changes the colours by cluster. Changing the method or cluster count takes effect on Redraw.</Text>
      {err ? <Banner tone="error" title="The map didn’t draw" description={err} />
        : !data ? <Stack gap="sm"><Text variant="caption">Drawing the map. With a few thousand articles this takes up to a minute.</Text><Skeleton variant="block" size="card" /></Stack>
        : data.error ? <Banner tone="error" title="The map didn’t draw" description={data.error} />
        : !data.points?.length ? <Text>No articles to place.</Text>
        : (
          <>
            <ProjectionScatter points={data.points} colourOf={colourOf} onSelect={onSelect} />
            <Stack direction="row" gap="sm">
              {legend.map((l) => (
                <Text key={l.v} as="span" variant="caption">
                  <span className="xa-swatch" style={{ background: l.c }} />
                  {`${colourBy === 'cluster' ? `Cluster ${l.v}` : l.v} (${l.n})`}
                </Text>
              ))}
            </Stack>
          </>
        )}
    </Stack>
  );
}
