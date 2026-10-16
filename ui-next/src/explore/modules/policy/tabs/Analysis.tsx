import { useEffect, useState } from 'react';
import { Chip, Panel, SegmentedControl, Stack, Table, Text } from '@aunoo/ui';
import { CATEGORY_SHORT_NAMES, getCooccurrence, type Cooccurrence } from '@monolith/policyTrackerApi';
import { errorText } from '../../../../shell';
import { BarList, Heatmap, LoadFailed, Loading } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyAnalysisTab: which categories appear together (as a table of every pair and as the
 * top pairs), and each category's share with its recent direction.
 */

const short = (c: string) => CATEGORY_SHORT_NAMES[c] ?? c;
const TREND: Record<string, { label: string; tone: 'success' | 'error' | 'muted' }> = {
  up: { label: 'rising', tone: 'success' },
  down: { label: 'falling', tone: 'error' },
  stable: { label: 'steady', tone: 'muted' },
};

export function Analysis({ pt }: { pt: PolicyTracker }) {
  const [view, setView] = useState<'heatmap' | 'pairs' | 'breakdown'>('heatmap');
  const { matrix, loadMatrix, categories, config } = pt;
  const [pairs, setPairs] = useState<{ rows: Cooccurrence[]; loading: boolean; error: string | null }>({ rows: [], loading: false, error: null });

  useEffect(() => {
    void loadMatrix();
  }, [loadMatrix]);
  // The old tab fetched the pairs once and kept them when the period changed
  useEffect(() => {
    if (view !== 'pairs') return;
    let live = true;
    setPairs({ rows: [], loading: true, error: null });
    getCooccurrence(config.topic, config.daysBack, 20).then(
      (rows) => live && setPairs({ rows, loading: false, error: null }),
      (e) => live && setPairs({ rows: [], loading: false, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [view, config.topic, config.daysBack]);

  return (
    <Panel
      title="Categories together"
      headingLevel={3}
      headerAside={
        <SegmentedControl className="policy-segmented"
          label="View"
          value={view}
          onValueChange={(v) => setView(v as typeof view)}
          options={[{ value: 'heatmap', label: 'Every pair' }, { value: 'pairs', label: 'Top pairs' }, { value: 'breakdown', label: 'Each category' }]}
        />
      }
    >
      {view === 'heatmap' && (matrix.loading && !matrix.data ? <Loading /> : matrix.failed ? <LoadFailed what="pair table" onRetry={() => void loadMatrix()} /> : matrix.data && matrix.data.categories.length ? (
        <Stack gap="sm">
          <Text variant="caption">Each cell counts the articles that carry both categories. The shaded diagonal is each category’s own total, on its own scale.</Text>
          <Heatmap categories={matrix.data.categories} matrix={matrix.data.matrix} shortName={short} />
        </Stack>
      ) : <Text variant="caption">No categorised articles for this period.</Text>)}

      {view === 'pairs' && (pairs.loading ? <Loading /> : pairs.error ? <Text tone="error">{`The pairs didn’t load: ${pairs.error}`}</Text> : (
        <Table
          caption="Category pairs that most often appear together"
          hideCaption
          rows={pairs.rows}
          rowKey={(p) => `${p.category1}|${p.category2}`}
          emptyText="No two categories share an article in this period."
          columns={[
            { key: 'rank', header: '#', render: (p) => String(pairs.rows.indexOf(p) + 1) },
            { key: 'pair', header: 'Pair', rowHeader: true, wrap: true, render: (p) => `${short(p.category1)} and ${short(p.category2)}` },
            { key: 'count', header: 'Articles', align: 'end', render: (p) => p.count.toLocaleString() },
            { key: 'pct', header: 'Share', align: 'end', render: (p) => `${p.percentage}%` },
          ]}
        />
      ))}

      {view === 'breakdown' && (
        <Stack gap="md">
          <Text variant="caption">Each category’s share of the period’s articles, and whether it has been rising or falling recently.</Text>
          <BarList
            title="Share of articles per category"
            items={categories.map((c) => ({ id: c.category, label: c.category, value: c.article_count, note: `${c.percentage}%, ${TREND[c.recent_trend]?.label ?? c.recent_trend}` }))}
          />
          {categories.length > 0 && (
            <Stack direction="row" gap="sm">
              {(['up', 'stable', 'down'] as const).map((t) => {
                const n = categories.filter((c) => c.recent_trend === t).length;
                return n ? <Chip key={t} tone={TREND[t].tone} size="sm">{`${n} ${TREND[t].label}`}</Chip> : null;
              })}
            </Stack>
          )}
        </Stack>
      )}
    </Panel>
  );
}
