import { useEffect, useState } from 'react';
import { ImagePanel } from '../../common/ImagePanel';
import { Banner, BubbleMatrix, EmptyState, Grid, Panel, SegmentedControl, Skeleton, Stat } from '@aunoo/ui';
import { getCategoriesData, getCategoryCooccurrence, type CategoryCooccurrence, type CategoryData } from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../../shell';
import { BarList } from '../BarList';
import { cap } from '../labels';

/*
 * Which threat categories appear together, as the old Analysis tab: a co-occurrence table, the most
 * frequent pairs, and a per-category breakdown. Covers every hotspot on file (the server takes no
 * period here).
 *
 * The old breakdown drew an up, down or flat "trend" arrow per category that was really its average
 * intensity (60 or more meant "up"). There is no trend in that data, so the breakdown now shows the
 * intensity as what it is.
 */

type View = 'heatmap' | 'pairs' | 'breakdown';

export function Analysis({ onCategory }: { onCategory: (c: string) => void }) {
  const [view, setView] = useState<View>('heatmap');
  const [co, setCo] = useState<CategoryCooccurrence | null>(null);
  const [cats, setCats] = useState<CategoryData[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getCategoryCooccurrence(), getCategoriesData()]).then(
      ([c, k]) => {
        if (!live) return;
        setCo(c);
        setCats(k);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, []);

  if (error) return <Banner tone="error" title="The analysis didn’t load" description={error} />;
  if (!co || !cats) return <Skeleton variant="block" size="card" />;
  const active = cats.filter((c) => c.count > 0);
  if (!active.length && !co.pairs.length) {
    return <Panel title="Analysis"><EmptyState icon="ChartBar" title="No analysis yet">Read some articles for hotspots first; the category patterns appear here.</EmptyState></Panel>;
  }

  const hotspots = active.reduce((s, c) => s + c.count, 0);
  const articles = active.reduce((s, c) => s + c.total_articles, 0);
  const weighted = hotspots ? active.reduce((s, c) => s + c.avg_intensity * c.count, 0) / hotspots : 0;
  const top10 = co.categories.slice(0, 10);
  const maxPair = Math.max(1, ...co.pairs.map((p) => p.count));

  return (
    <>
      <Grid columns={4} gap="sm">
        <Stat label="Categories in use" value={active.length} />
        <Stat label="Category pairs" value={co.pairs.length} meta="seen together at least once" />
        <Stat label="Average intensity" value={weighted.toFixed(1)} meta="out of 100, weighted by hotspots" />
        <Stat label="Hotspots" value={hotspots.toLocaleString()} meta={`${articles.toLocaleString()} articles`} />
      </Grid>
      <SegmentedControl
        label="Analysis view"
        options={[{ value: 'heatmap', label: 'Together' }, { value: 'pairs', label: 'Top pairs' }, { value: 'breakdown', label: 'Breakdown' }]}
        value={view}
        onValueChange={(v) => setView(v as View)}
      />

      {view === 'heatmap' && (
        <Grid columns={2} gap="md">
          <ImagePanel filename="geohotspots-categories-seen-together" title="Categories seen together" description="How often two categories appear in the same related articles. Bigger circle = more often. The ten biggest categories.">
            {top10.length ? (
              <BubbleMatrix
                title="Category co-occurrence"
                hideTitle
                columns={top10.map(cap)}
                rows={top10.map((r) => ({ id: r, label: cap(r), color: 1, values: top10.map((c) => co.matrix[r]?.[c] || 0) }))}
              />
            ) : <EmptyState icon="ChartBar" title="No pairs yet">No two categories have appeared together yet.</EmptyState>}
          </ImagePanel>
          <Panel title="Average intensity by category" description="Out of 100, the ten highest.">
            <BarList
              max={100}
              rows={[...active].sort((a, b) => b.avg_intensity - a.avg_intensity).slice(0, 10).map((c) => ({
                id: c.category, label: cap(c.category), value: c.avg_intensity, valueText: `${c.avg_intensity.toFixed(1)} · ${c.count} hotspots · ${c.total_articles} articles`,
                tone: c.avg_intensity >= 70 ? 'error' : c.avg_intensity >= 50 ? 'warning' : 'neutral',
              }))}
            />
          </Panel>
        </Grid>
      )}

      {view === 'pairs' && (
        <Grid columns={2} gap="md">
          <Panel title="Pairs seen together most">
            <BarList
              rows={co.pairs.slice(0, 10).map((p, i) => ({ id: `${p.category1}-${p.category2}`, label: `${i + 1}. ${cap(p.category1)} + ${cap(p.category2)}`, value: p.count, valueText: `${p.count} times` }))}
              max={maxPair}
              empty="No category pairs yet."
            />
          </Panel>
          <Panel title="Articles by category" description="The ten categories with most linked articles. Click one to see them.">
            <BarList
              rows={[...active].sort((a, b) => b.total_articles - a.total_articles).slice(0, 10).map((c) => ({ id: c.category, label: cap(c.category), value: c.total_articles, valueText: `${c.total_articles} articles · ${c.count} hotspots` }))}
              onPick={onCategory}
              pickLabel={(l) => `Show ${l} articles`}
            />
          </Panel>
        </Grid>
      )}

      {view === 'breakdown' && (
        <Panel title="Category breakdown" description="Share of hotspots per category, with articles and average intensity. Click one to see its articles.">
          <BarList
            rows={[...active].sort((a, b) => b.count - a.count).map((c) => ({
              id: c.category, label: cap(c.category), value: c.count,
              valueText: `${c.count} hotspots (${((c.count / Math.max(1, hotspots)) * 100).toFixed(1)}%) · ${c.total_articles} articles (${((c.total_articles / Math.max(1, articles)) * 100).toFixed(1)}%) · intensity ${c.avg_intensity.toFixed(0)}`,
            }))}
            onPick={onCategory}
            pickLabel={(l) => `Show ${l} articles`}
          />
        </Panel>
      )}
    </>
  );
}
