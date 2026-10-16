import { Collapsible, CollapsibleContent, CollapsibleTrigger, SettingRow, Stack } from '@aunoo/ui';

/*
 * "Not enough data yet": one folded list for every panel that didn't clear its own sample-size
 * floor, as the old ConfidenceGate.tsx, in place of a two-point chart or five near-identical
 * placeholder paragraphs.
 */

export interface ThinPanel {
  id: string;
  /** The panel's title */
  title: string;
  /** What it measures, one sentence */
  why: string;
  /** How far short it is, in a reader's units ("2 of 6 weeks read") */
  need: string;
}

export function ConfidenceGate({ panels }: { panels: ThinPanel[] }) {
  if (!panels.length) return null;
  return (
    <Collapsible>
      <CollapsibleTrigger variant="secondary">{`Not enough data yet (${panels.length} panel${panels.length === 1 ? '' : 's'})`}</CollapsibleTrigger>
      <CollapsibleContent>
        <Stack as="ul" gap="sm" label="Panels waiting for data">
          {panels.map((p) => (
            <li key={p.id}><SettingRow title={p.title} description={`${p.why} Waiting for: ${p.need}.`} /></li>
          ))}
        </Stack>
      </CollapsibleContent>
    </Collapsible>
  );
}
