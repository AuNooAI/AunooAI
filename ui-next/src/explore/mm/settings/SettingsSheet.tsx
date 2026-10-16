import { useEffect, useState } from 'react';
import { Sheet, Skeleton, Stack, TabPanel, Tabs } from '@aunoo/ui';
import { getRuns, type CollectionRun } from '@monolith/marketMonitorApi';
import type { MmContext, SettingsPanel } from '../context';
import { HealthPanel } from '../views/collection/HealthPanels';
import { ScopePanel } from './ScopePanel';
import { SourcesPanel } from './SourcesPanel';
import { TermsPanel } from './TermsPanel';

/*
 * Market settings, as the old settings drawer: search terms (what gets collected), sources and
 * schedules, health, and scope. "Search terms" rather than "Collection", because the Collection
 * view is a different, read-only thing.
 */

const PANELS: { value: SettingsPanel; label: string }[] = [
  { value: 'collection', label: 'Search terms' },
  { value: 'sources', label: 'Sources and schedules' },
  { value: 'health', label: 'Health' },
  { value: 'scope', label: 'Scope' },
];

export function SettingsSheet({ ctx, panel, onPanel, onMarketsChanged }: { ctx: MmContext; panel: SettingsPanel | null; onPanel: (p: SettingsPanel | null) => void; onMarketsChanged: () => void }) {
  const [runs, setRuns] = useState<CollectionRun[] | null>(null);
  useEffect(() => {
    if (panel !== 'health') return;
    let live = true;
    getRuns(ctx.marketId, 20).then((r) => live && setRuns(r), () => live && setRuns([]));
    return () => {
      live = false;
    };
  }, [panel, ctx.marketId]);

  return (
    <Sheet open={panel !== null} onOpenChange={(o) => !o && onPanel(null)} size="lg" title="Market settings" description={ctx.market.name}>
      <Tabs label="Market settings sections" value={panel ?? 'collection'} onValueChange={(v) => onPanel(v as SettingsPanel)} items={PANELS}>
        {PANELS.map((p) => (
          <TabPanel key={p.value} value={p.value}>
            {p.value === panel && (
              <Stack gap="lg">
                {panel === 'collection' && <TermsPanel ctx={ctx} />}
                {panel === 'sources' && <SourcesPanel ctx={ctx} />}
                {panel === 'health' && (ctx.health ? <HealthPanel health={ctx.health} runs={runs} /> : <Skeleton variant="block" size="card" />)}
                {panel === 'scope' && <ScopePanel ctx={ctx} onSaved={onMarketsChanged} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>
    </Sheet>
  );
}
