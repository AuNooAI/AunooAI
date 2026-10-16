import { useState } from 'react';
import { Button, Chip, EmptyState, Panel, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import { autoCloseReviewTasks, closeReviewTask, fixReviewTask, type ReviewTask } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { LinkButton } from '../../shared/SortTable';

/*
 * Questions the registry import raised where it wouldn't guess, as the old "Needs review" segment.
 * A question can be corrected (with a source, which is required: a corrected figure with no source
 * is the same problem one step later), accepted as having no answer, or dismissed as a wrong flag.
 */

const SEVERITY_TONE: Record<string, 'error' | 'warning' | 'muted'> = { high: 'error', medium: 'warning', low: 'muted' };

export function ReviewQueue({ ctx, tasks, onChanged }: { ctx: MmContext; tasks: ReviewTask[] | null; onChanged: () => void }) {
  const { marketId, notify, openVendor } = ctx;
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState<{ id: number; value: string; source: string } | null>(null);

  const run = async (work: () => Promise<string | void>) => {
    setBusy(true);
    try {
      const msg = await work();
      if (msg) notify(msg);
      onChanged();
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const closeAnswered = () =>
    run(async () => {
      const r = await autoCloseReviewTasks(marketId);
      return r.closed ? `${r.closed} of ${r.checked} closed: collection has since answered them.` : `Checked ${r.checked}; collection hasn’t answered any of them yet.`;
    });

  return (
    <Panel
      title="Needs review"
      description="Correct the value, or accept the question as unanswerable. A company founded in 2026 can’t have a year-on-year figure, and no correction will make one exist."
      headerAside={<Button variant="secondary" size="sm" disabled={busy || !tasks?.length} onClick={() => void closeAnswered()}>Close answered questions</Button>}
    >
      {!tasks ? <Skeleton variant="text" lines={5} /> : !tasks.length ? (
        <EmptyState icon="CheckCircle" title="Nothing to review">No open review tasks.</EmptyState>
      ) : (
        <Stack as="ul" gap="md" label="Open review tasks">
          {tasks.map((t) => (
            <li key={t.id}>
              <Stack gap="sm">
                <Stack direction="row" justify="between" gap="sm">
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm">
                      <Chip tone={SEVERITY_TONE[t.severity] ?? 'muted'} size="sm">{t.severity}</Chip>
                      <Text as="span">{t.message}</Text>
                    </Stack>
                    <Text variant="caption">
                      {t.brand_id ? <LinkButton onClick={() => openVendor(t.brand_id!)}>{t.vendor ?? 'vendor'}</LinkButton> : 'market'}
                      {` · ${t.kind}`}
                      {t.target_field ? ` · ${t.target_field}` : ''}
                      {t.current_value !== null && t.current_value !== undefined ? ` · currently ${t.current_value}` : ''}
                    </Text>
                  </Stack>
                  <Stack direction="row" gap="sm">
                    {t.target_field && (
                      <Button variant="secondary" size="sm" onClick={() => setFixing(fixing?.id === t.id ? null : { id: t.id, value: t.current_value ?? '', source: '' })}>Correct it</Button>
                    )}
                    <Button variant="ghost" size="sm" disabled={busy} onClick={() => void run(async () => void (await closeReviewTask(marketId, t.id, 'accepted')))}>Accept: no answer</Button>
                    <Button variant="ghost" size="sm" disabled={busy} onClick={() => void run(async () => void (await closeReviewTask(marketId, t.id, 'dismissed')))}>Dismiss: wrong flag</Button>
                  </Stack>
                </Stack>
                {fixing?.id === t.id && (
                  <Stack direction="row" gap="sm">
                    <TextField label={`New ${t.target_field}`} value={fixing.value} onChange={(value) => setFixing({ ...fixing, value })} />
                    <TextField label="Source (required)" placeholder="Where this came from" value={fixing.source} onChange={(source) => setFixing({ ...fixing, source })} />
                    <Button
                      disabled={busy || !fixing.source.trim()}
                      onClick={() =>
                        void run(async () => {
                          await fixReviewTask(marketId, t.id, { value: fixing.value, source: fixing.source });
                          setFixing(null);
                          return `${t.vendor ?? 'Market'}: ${t.target_field} set to ${fixing.value}.`;
                        })
                      }
                    >
                      Save
                    </Button>
                  </Stack>
                )}
              </Stack>
            </li>
          ))}
        </Stack>
      )}
    </Panel>
  );
}
