import { useEffect, useState } from 'react';
import { Banner, Button, EmptyState, Grid, Icon, Meter, Panel, Skeleton, Stack, Text, type IconName } from '@aunoo/ui';
import type { Analysis } from '../lib/useAnalysis';

interface ViewStateProps {
  analysis: Analysis;
  generateLabel: string;
  empty: { icon: IconName; title: string; text: string };
  children: React.ReactNode;
}

/** Usual time for a run, for the progress bar; it holds at 95% until the result arrives. */
const TYPICAL_MS = 60000;

function Generating({ startedAt }: { startedAt: number | null }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const elapsed = startedAt ? Math.max(0, now - startedAt) : 0;
  const pct = Math.min(95, Math.round((elapsed / TYPICAL_MS) * 100));
  return (
    <Panel title="Generating analysis" description="This usually takes 30–60 seconds. You can keep using other tabs.">
      <Meter label="Generation progress (estimated)" progress value={pct} valueText={`${Math.round(elapsed / 1000)} s`} />
    </Panel>
  );
}

/** Loading, generating, error, empty, or the view. */
export function ViewState({ analysis, generateLabel, empty, children }: ViewStateProps) {
  const { status } = analysis;
  if (status === 'loading' || status === 'idle') {
    return (
      <div aria-busy="true">
        <span className="visually-hidden" role="status">Loading analysis…</span>
        <Stack gap="lg">
          <Skeleton variant="block" size="card" />
          <Grid columns={3} gap="md">
            <Skeleton variant="block" size="card" />
            <Skeleton variant="block" size="card" />
            <Skeleton variant="block" size="card" />
          </Grid>
        </Stack>
      </div>
    );
  }
  if (status === 'generating') return <Generating startedAt={analysis.startedAt} />;
  if (status === 'error') {
    return (
      <Banner
        tone="error"
        headingLevel={2}
        title="The analysis didn’t complete"
        description={analysis.error ?? 'The analysis service didn’t respond.'}
        action={<Button variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => void analysis.generate()}>Try again</Button>}
      />
    );
  }
  if (status === 'empty') {
    return (
      <Panel title={empty.title}>
        <EmptyState
          icon={empty.icon}
          action={<Button iconStart={<Icon name="Sparkle" size="sm" />} onClick={() => void analysis.generate()}>{generateLabel}</Button>}
        >
          {empty.text}
        </EmptyState>
      </Panel>
    );
  }
  return <>{children}</>;
}

export function Muted({ children }: { children: React.ReactNode }) {
  return <Text variant="hint" as="span">{children}</Text>;
}
