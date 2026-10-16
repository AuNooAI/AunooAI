import { useEffect, useState } from 'react';
import { SegmentedControl, Skeleton } from '@aunoo/ui';
import { getCollectionState, getReviewTasks, getRuns, getSources, type CollectionRun, type CollectionStateResponse, type SourceSetting } from '@monolith/marketMonitorApi';
import type { CollectionSub, MmContext } from '../context';
import { Coverage } from './collection/Coverage';
import { Data, SourceMap } from './collection/Data';
import { CollectionStatePanel, HealthPanel } from './collection/HealthPanels';
import { CollectionOverview } from './collection/Overview';
import { Wire } from './collection/Wire';

/*
 * The pipeline, as the old Collection view: "what did we collect and is it working", a different
 * question from what the market shows. Six sub-views, each loading only what it needs while open.
 */

const SUBS: { value: CollectionSub; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'health', label: 'Sources and health' },
  { value: 'coverage', label: 'Coverage' },
  { value: 'wire', label: 'Wire' },
  { value: 'data', label: 'Data' },
  { value: 'sourcemap', label: 'Data map' },
];

export function Collection({ ctx, sub, onSub }: { ctx: MmContext; sub: CollectionSub; onSub: (s: CollectionSub) => void }) {
  const { marketId } = ctx;
  const [state, setState] = useState<CollectionStateResponse | null>(null);
  const [runs, setRuns] = useState<CollectionRun[] | null>(null);
  const [sources, setSources] = useState<SourceSetting[] | null>(null);
  const [openTasks, setOpenTasks] = useState<number | null>(null);

  useEffect(() => {
    if (sub !== 'overview' && sub !== 'health') return;
    let live = true;
    getCollectionState(marketId).then((s) => live && setState(s), () => undefined);
    if (sub === 'health') getRuns(marketId, 20).then((r) => live && setRuns(r), () => live && setRuns([]));
    if (sub === 'overview') getReviewTasks(marketId, { status: 'open' }).then((t) => live && setOpenTasks(t.length), () => undefined);
    return () => {
      live = false;
    };
  }, [marketId, sub, ctx.health]);
  useEffect(() => {
    if (sub !== 'sourcemap') return;
    let live = true;
    getSources(marketId).then((s) => live && setSources(s.sources), () => live && setSources([]));
    return () => {
      live = false;
    };
  }, [marketId, sub]);

  return (
    <>
      <SegmentedControl label="Collection views" options={SUBS} value={sub} onValueChange={(v) => onSub(v as CollectionSub)} />
      {sub === 'overview' && <CollectionOverview ctx={ctx} openTasks={openTasks} collectionState={state} />}
      {sub === 'health' && (ctx.health ? (
        <>
          <CollectionStatePanel state={state} />
          <HealthPanel health={ctx.health} runs={runs} />
        </>
      ) : <Skeleton variant="block" size="card" />)}
      {sub === 'coverage' && <Coverage ctx={ctx} />}
      {sub === 'wire' && <Wire ctx={ctx} />}
      {sub === 'data' && <Data ctx={ctx} />}
      {sub === 'sourcemap' && <SourceMap sources={sources} />}
    </>
  );
}
