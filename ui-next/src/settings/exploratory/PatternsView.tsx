import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Icon, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import { errorText } from '../../shell';
import { getAnomalies, getPatterns, getProjection, type Anomaly, type ClusterInfo, type Patterns, type ProjectionPoint } from './api';
import './exploratory.css';

/*
 * The old Patterns tab: the most common words and phrases, the clusters the articles fall into, and
 * the outliers (articles least like the rest). It loads when the tab is opened, as before; the
 * clustering runs on the server's CPU and calls no AI. Summarising a cluster calls the AI, from its
 * button only.
 */

interface Cluster { id: number; title: string; summary: string; keywords: string[]; ids: string[] }

export function PatternsView({ scope, onKeepCluster, onSummarise, onOpen }: {
  /** The same query string the result list used */
  scope: URLSearchParams;
  onKeepCluster: (id: number) => void;
  onSummarise: (ids: string[], title: string) => void;
  onOpen: (a: Anomaly) => void;
}) {
  const key = scope.toString();
  const [data, setData] = useState<{ patterns: Patterns; clusters: Cluster[]; outliers: Anomaly[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setErr(null);
    const proj = new URLSearchParams(scope);
    proj.set('dims', '2');
    Promise.all([getPatterns(scope), getProjection(proj), getAnomalies(scope)]).then(
      ([patterns, projection, outliers]) => {
        if (!live) return;
        const byCluster = new Map<number, ProjectionPoint[]>();
        for (const p of projection.points ?? []) byCluster.set(p.cluster, [...(byCluster.get(p.cluster) ?? []), p]);
        const clusters = [...byCluster.entries()].map(([id, pts]) => {
          const info = projection.explain?.[String(id)];
          const ex: ClusterInfo = Array.isArray(info) ? { keywords: info } : info ?? {};
          return {
            id,
            title: ex.title || `Cluster ${id}`,
            summary: ex.summary || `${pts.length} related articles`,
            keywords: ex.keywords ?? [],
            ids: pts.map((p) => p.id),
          };
        }).sort((a, b) => b.ids.length - a.ids.length);
        setData({ patterns, clusters, outliers });
        if (projection.error) setErr(`The clustering failed: ${projection.error}`);
      },
      (e) => live && setErr(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err && !data) return <Banner tone="error" title="Patterns didn’t load" description={err} />;
  if (!data) return <Stack gap="sm"><Text variant="caption">Finding patterns and clusters. On a large search this takes up to a minute.</Text><Skeleton variant="text" lines={8} /></Stack>;

  return (
    <Stack gap="lg">
      {err && <Banner tone="warning" title="Part of this didn’t load" description={err} />}
      <Panel title="Most common words and phrases" headingLevel={3}>
        {data.patterns.ngrams?.length ? (
          <Stack direction="row" gap="sm">
            {data.patterns.ngrams.slice(0, 30).map((n) => <Chip key={n.text} tone="muted">{`${n.text} (${n.count})`}</Chip>)}
          </Stack>
        ) : <Text variant="caption">{data.patterns.error ? `Not available: ${data.patterns.error}` : 'No words stand out.'}</Text>}
      </Panel>
      <Panel title={`Clusters (${data.clusters.length})`} description="Articles grouped by meaning. The titles and summaries are built from each cluster’s most typical words, not written by AI." headingLevel={3}>
        {!data.clusters.length ? <Text variant="caption">No clusters.</Text> : (
          <Stack as="ul" gap="md" label="Clusters">
            {data.clusters.map((c) => (
              <li key={c.id}>
                <Stack gap="sm">
                  <Stack direction="row" justify="between" gap="sm">
                    <Text variant="label" as="span">{`${c.title} · ${c.ids.length} articles · cluster ${c.id}`}</Text>
                    <Stack direction="row" gap="sm">
                      <Button variant="ghost" size="sm" iconStart={<Icon name="Funnel" size="sm" />} onClick={() => onKeepCluster(c.id)}>Keep only this cluster</Button>
                      <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} onClick={() => onSummarise(c.ids, c.title)}>Summarise with AI</Button>
                    </Stack>
                  </Stack>
                  <Text variant="caption">{c.summary}</Text>
                  {c.keywords.length > 0 && <Text variant="caption">{`Words: ${c.keywords.slice(0, 8).join(', ')}`}</Text>}
                </Stack>
              </li>
            ))}
          </Stack>
        )}
      </Panel>
      <Panel title="Outliers" description="The articles least like the others in this search, most unusual first (isolation forest over the embeddings)." headingLevel={3}>
        {!data.outliers.length ? <Text variant="caption">No outliers found.</Text> : (
          <Stack as="ul" gap="sm" label="Outliers">
            {data.outliers.slice(0, 30).map((a) => (
              <li key={a.id}>
                <button type="button" className="text-link xa-link" onClick={() => onOpen(a)}>{a.metadata?.title || a.id}</button>
                <Text as="span" variant="caption">{` · score ${a.score.toFixed(3)}`}</Text>
              </li>
            ))}
          </Stack>
        )}
      </Panel>
    </Stack>
  );
}
