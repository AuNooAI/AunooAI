import { useEffect, useState } from 'react';
import { ActivityRow, Banner, Button, Chip, Dialog, DialogClose, Eyebrow, Icon, Select, Stack, Text, TextField } from '@aunoo/ui';
import { testProcessArticle, type TestProcessResult, type TestProcessStep } from '@monolith/gatherApi';
import { errorText } from '../../shell';
import type { KeywordGroup } from '../model';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: KeywordGroup[];
  /** Preloaded article and group (from a recent article, or the header's first group with articles). */
  initial?: { uri: string; groupId: string } | null;
  /** After a successful run, so the group counts refresh. */
  onSuccess: () => void;
}

// Failed steps get the accent dot so they stand out from waiting ones
const DOT = { success: 'live', error: 'accent', warning: 'pending', info: 'live' } as const;
const STATUS_LABEL = { success: 'Done', error: 'Failed', warning: 'Warning', info: 'Info' } as const;

const detailText = (details: TestProcessStep['details']) =>
  Object.entries(details ?? {})
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}`)
    .join(' · ');

/** Test LLM Enrichment: POST test-process-article, then each workflow step as the backend reports it. */
export function TestEnrichmentDialog({ open, onOpenChange, groups, initial, onSuccess }: Props) {
  const [uri, setUri] = useState('');
  const [group, setGroup] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TestProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setUri(initial?.uri ?? '');
      setGroup(initial?.groupId ?? groups[0]?.id ?? '');
      setResult(null);
      setError(null);
      setRunning(false);
    }
  }, [open, initial?.uri, initial?.groupId]);

  const run = async () => {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      setResult(await testProcessArticle(uri.trim(), Number(group)));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRunning(false);
    }
  };

  const close = (o: boolean) => {
    if (!o && result?.success) onSuccess();
    onOpenChange(o);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Test LLM Enrichment"
      description="Process a single article through the enrichment workflow. View each step to troubleshoot issues."
      size="lg"
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">{result ? 'Close' : 'Cancel'}</Button>
          </DialogClose>
          <Button size="lg" iconStart={<Icon name="Flask" size="sm" />} disabled={!uri.trim() || !group} busy={running} onClick={run}>
            {running ? 'Processing…' : 'Process Article'}
          </Button>
        </>
      }
    >
      <Stack gap="lg">
        <TextField
          label="Article URI"
          placeholder="https://example.com/article or http://arxiv.org/abs/..."
          value={uri}
          onChange={setUri}
          hint="An article in the database, or a URL to scrape first"
        />
        <Select
          label="Keyword Group"
          fullWidth
          placeholder="Select group..."
          options={groups.map((g) => ({ value: g.id, label: `${g.name} (${g.topic})` }))}
          value={group}
          onValueChange={setGroup}
        />
        <Text variant="hint">The topic from this group determines the ontology used for analysis.</Text>
        {error && <Banner tone="error" icon="WarningCircle" title="Processing failed" description={error} />}
        {result && (
          <Stack gap="md">
            <Eyebrow as="h3">Workflow steps</Eyebrow>
            <Stack as="ul" gap="sm" label="Workflow steps">
              {result.steps.map((s, i) => (
                <ActivityRow
                  key={`${s.name}-${i}`}
                  as="li"
                  primary={`${s.name}: ${s.message}`}
                  secondary={detailText(s.details) || undefined}
                  dotTone={DOT[s.status] ?? 'pending'}
                  dotLabel={STATUS_LABEL[s.status] ?? s.status}
                />
              ))}
            </Stack>
            <Banner
              tone={result.success ? 'success' : 'error'}
              icon={result.success ? 'CheckCircle' : 'WarningCircle'}
              title={result.success ? 'Success' : 'Failed'}
              description={result.message}
            />
            {result.success && Object.keys(result.enrichment_fields ?? {}).length > 0 && (
              <Stack direction="row" gap="sm">
                {Object.entries(result.enrichment_fields).map(([k, v]) => (
                  <Chip key={k} size="sm" tone="neutral">{`${k.replace(/_/g, ' ')}: ${v}`}</Chip>
                ))}
              </Stack>
            )}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
