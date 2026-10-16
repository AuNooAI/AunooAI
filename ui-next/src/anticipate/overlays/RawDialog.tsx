import { useEffect, useState } from 'react';
import { Banner, CodeBlock, Dialog, LineItems, Skeleton, Stack } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import type { Payload } from '../lib/model';

/** Raw-output endpoint per backend tab (market signals has its own router). */
const RAW: Record<string, (id: string) => string> = {
  consensus: (id) => `/api/trend-convergence/consensus/${id}/raw`,
  signals: (id) => `/api/market-signals/${id}/raw`,
  timeline: (id) => `/api/trend-convergence/timeline/${id}/raw`,
  strategic: (id) => `/api/trend-convergence/strategic/${id}/raw`,
  horizons: (id) => `/api/trend-convergence/horizons/${id}/raw`,
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  backendTab: string;
  analysisId: string | undefined;
  /** Shown when the stored record has no model (consensus raw doesn't carry one). */
  fallbackModel?: string;
  onCopy: () => void;
}

/** "Raw analysis output": the stored record's metadata and the model's JSON. */
export function RawDialog({ open, onOpenChange, backendTab, analysisId, fallbackModel, onCopy }: Props) {
  const [raw, setRaw] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open || !analysisId) return;
    setRaw(null);
    setError(null);
    api<Payload>(RAW[backendTab](encodeURIComponent(analysisId))).then(setRaw, (e) => setError(errorText(e)));
  }, [open, analysisId, backendTab]);

  const output = raw ? (typeof raw.raw_output === 'string' ? raw.raw_output : JSON.stringify(raw.raw_output, null, 2)) : '';
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title="Raw analysis output">
      {error ? (
        <Banner tone="error" icon="WarningCircle" title="Couldn’t load the stored analysis" description={error} />
      ) : !raw ? (
        <Skeleton variant="block" />
      ) : (
        <Stack gap="lg">
          <LineItems
            label="Analysis metadata"
            items={[
              { id: 'id', label: 'Analysis ID', amount: String(raw.analysis_id ?? analysisId) },
              { id: 'topic', label: 'Topic', amount: String(raw.topic ?? '') },
              { id: 'model', label: 'Model', amount: String(raw.model_used ?? fallbackModel ?? '—') },
              { id: 'created', label: 'Created', amount: raw.created_at ? new Date(raw.created_at).toLocaleString('en-GB') : '—' },
              { id: 'articles', label: 'Articles analyzed', amount: String(raw.total_articles_analyzed ?? '—') },
            ]}
          />
          <CodeBlock label="JSON" code={output} onCopy={onCopy} />
        </Stack>
      )}
    </Dialog>
  );
}
