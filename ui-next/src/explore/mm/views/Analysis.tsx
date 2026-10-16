import type { MmContext } from '../context';
import { Panels } from './analysis/Panels';
import { Pulse } from './analysis/Pulse';

/** The old Analysis view: the market's one-look state (Pulse), then the cross-sectional panels */
export function Analysis(ctx: MmContext) {
  return (
    <>
      <Pulse {...ctx} />
      <Panels {...ctx} />
    </>
  );
}
