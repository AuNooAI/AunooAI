import { useCallback, useEffect, useState } from 'react';
import { SegmentedControl, Stack } from '@aunoo/ui';
import { getFacets, getReviewTasks, type Facets, type ReviewTask } from '@monolith/marketMonitorApi';
import type { MmContext } from '../context';
import { Entrants } from './vendors/Entrants';
import { GeographyMap } from './vendors/GeographyMap';
import { Registry } from './vendors/Registry';
import { ReviewQueue } from './vendors/ReviewQueue';

/*
 * The vendor registry, as the old Vendors view: where the vendors are, then three segments over the
 * same vendor set (all of them, the review queue, and new entrants found in coverage).
 */

type Segment = 'all' | 'review' | 'entrants';

export function Vendors(ctx: MmContext) {
  const { marketId, vendors, reload } = ctx;
  const [segment, setSegment] = useState<Segment>('all');
  const [facets, setFacets] = useState<Facets | null>(null);
  const [tasks, setTasks] = useState<ReviewTask[] | null>(null);

  const loadTasks = useCallback(() => {
    getReviewTasks(marketId, { status: 'open' }).then(setTasks, () => setTasks([]));
  }, [marketId]);
  useEffect(() => {
    let live = true;
    getFacets(marketId).then((f) => live && setFacets(f), () => undefined);
    loadTasks();
    return () => {
      live = false;
    };
  }, [marketId, loadTasks]);

  return (
    <Stack gap="lg">
      <GeographyMap marketId={marketId} />
      <SegmentedControl
        label="Which vendors"
        value={segment}
        onValueChange={(v) => setSegment(v as Segment)}
        options={[
          { value: 'all', label: `All (${vendors?.length ?? 0})` },
          { value: 'review', label: `Needs review${tasks?.length ? ` (${tasks.length})` : ''}` },
          { value: 'entrants', label: 'New entrants' },
        ]}
      />
      {segment === 'all' && <Registry ctx={ctx} facets={facets} />}
      {segment === 'review' && <ReviewQueue ctx={ctx} tasks={tasks} onChanged={() => { loadTasks(); reload(); }} />}
      {segment === 'entrants' && <Entrants ctx={ctx} onChanged={loadTasks} />}
    </Stack>
  );
}
