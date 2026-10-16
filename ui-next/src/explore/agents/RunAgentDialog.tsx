import { useEffect, useState } from 'react';
import { Button, Checkbox, Dialog, DialogClose, Select, Stack, Text } from '@aunoo/ui';

/*
 * The period and options for a run, as the old RunAgentModal. Running reads every article in the
 * period with the AI, so it only starts from the Run button here.
 */

export interface RunChoice {
  daysBack: number;
  tagArticles: boolean;
  generateUnifiedReport?: boolean;
}

const PERIODS = [
  { value: '1', label: 'Last 24 hours', description: 'Most recent articles only' },
  { value: '3', label: 'Last 3 days', description: 'Recent coverage' },
  { value: '7', label: 'Last 7 days', description: 'The past week' },
  { value: '14', label: 'Last 2 weeks', description: 'A longer stretch' },
  { value: '30', label: 'Last 30 days', description: 'A full month' },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The agent's name; undefined = run every active agent */
  agentName?: string;
  activeCount: number;
  onRun: (choice: RunChoice) => void;
}

export function RunAgentDialog({ open, onOpenChange, agentName, activeCount, onRun }: Props) {
  const all = agentName === undefined;
  const [days, setDays] = useState('7');
  const [tag, setTag] = useState(true);
  const [unified, setUnified] = useState(false);
  useEffect(() => {
    if (open) setUnified(false);
  }, [open]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={all ? (activeCount === 1 ? "Run the one active agent" : `Run all ${activeCount} active agents`) : `Run ${agentName}`}
      description={`${all ? 'Each active agent reads' : 'The agent reads'} the articles from the period you pick with the AI and flags the ones that match its instruction. Longer periods take longer and cost more.`}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" onClick={() => onRun({ daysBack: Number(days), tagArticles: tag, generateUnifiedReport: all ? unified : undefined })}>
            {all ? 'Run all agents' : 'Run agent'}
          </Button>
        </>
      }
    >
      <Stack gap="md">
        <Select label="Articles from" options={PERIODS} value={days} onValueChange={setDays} fullWidth />
        <Stack gap="sm">
          <Checkbox label="Tag matching articles" checked={tag} onCheckedChange={setTag} />
          <Text variant="caption">Adds the agent’s signal tag to each matched article, so you can filter for them elsewhere.</Text>
        </Stack>
        {all && (
          <Stack gap="sm">
            <Checkbox label="Write one combined report" checked={unified} onCheckedChange={setUnified} />
            <Text variant="caption">After the run, the AI writes a single report across every agent’s matches. It appears under Saved reports.</Text>
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
