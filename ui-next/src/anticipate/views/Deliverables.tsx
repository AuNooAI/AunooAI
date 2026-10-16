import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Checkbox, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Grid, Icon, Meter, Panel, Select, SettingRow,
  Skeleton, Stack, Stat, Table, Text, TextField,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import type { DeliverablePreview, TopicDeliveryConfig } from '@monolith-types/forecastAssessment';
import { api, errorText } from '../../shell';
import { BriefEditor } from '../brief/BriefEditor';
import { currentPeriodLabel } from '../brief/model';
import { downloadFile } from '../lib/download';
import { fmtDate, useJob } from '../lib/jobs';

const CUSTOMER_LABEL: Record<string, string> = { 'Above baseline': 'Strengthening', 'At baseline': 'Stable', 'Below baseline': 'Cooling' };
const LABEL_TONE: Record<string, 'success' | 'neutral' | 'warning'> = { 'Above baseline': 'success', 'At baseline': 'neutral', 'Below baseline': 'warning' };

interface Finding { stage: string; artefact_key: string; severity: 'info' | 'warning' | 'error'; finding: string; suggested_fix?: string }
interface Review { period_label?: string; status?: string; reviewer_findings?: Finding[] }

const bundleQuery = (cadence: string, updatesOnly: boolean) => `cadence=${cadence}&updates_only=${updatesOnly}`;

/** Every tracked topic's latest assessment, with links to the bundle (Forecast Tracker → All topics). */
// Status icons beside each label, as the old all-topics cards drew them
const LABEL_ICON: Record<string, 'TrendUp' | 'Minus' | 'ArrowDown'> = { 'Above baseline': 'TrendUp', 'At baseline': 'Minus', 'Below baseline': 'ArrowDown' };

export function AllTopicsForecast({ notify, onOpen }: { notify: (m: string) => void; onOpen: (topic: string) => void }) {
  const [p, setP] = useState<DeliverablePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    api<DeliverablePreview>('/api/forecast/deliverables/preview?cadence=all').then(setP, (e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  const ready = p?.ready_count ?? 0;
  return (
    <Panel
      title="Forecast Tracker — all topics"
      description={p ? `${ready} of ${p.topics.length} topics have a stored assessment.` : undefined}
      headerAside={
        <Stack direction="row" gap="sm">
          <Button variant="secondary" size="sm" disabled={!ready} iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => { notify('Building the bundle — this can take a few minutes'); downloadFile(`/api/forecast/deliverables/bundle.pptx?${bundleQuery('all', false)}`, 'forecast-bundle-all.pptx').catch((e) => notify(errorText(e))); }}>Bundle .pptx</Button>
          <Button variant="ghost" size="sm" disabled={!ready} onClick={() => downloadFile(`/api/forecast/deliverables/bundle.pptx?${bundleQuery('all', true)}`, 'forecast-bundle-all-updates.pptx').catch((e) => notify(errorText(e)))}>Updates only</Button>
          <Button variant="ghost" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={load}>Refresh</Button>
        </Stack>
      }
    >
      {error ? (
        <Banner tone="error" icon="WarningCircle" title="Couldn’t load topics" description={error} />
      ) : !p ? (
        <Skeleton lines={4} />
      ) : !p.topics.length ? (
        <EmptyState>No assessments stored yet. Run one from a topic’s Forecast Tracker.</EmptyState>
      ) : (
        <Grid as="ul" columns={2} gap="sm" label="Topics">
          {p.topics.map((t) => (
            <li key={t.topic}>
              <SettingRow
                title={t.topic}
                description={t.ready ? `Assessed ${fmtDate(t.assessed_at)} · ${t.scenarios_count ?? 0} scenarios · ${t.evidence_count ?? 0} articles · ${t.surprises_count ?? 0} emerging themes` : t.reason || 'Not assessed yet'}
                actionsPlacement="title"
                actions={t.ready && <Button variant="ghost" size="sm" iconEnd={<Icon name="CaretRight" size="sm" />} onClick={() => onOpen(t.topic)}>Open</Button>}
              >
                <Stack direction="row" gap="sm">
                  {Object.entries(t.label_distribution ?? {}).sort((a, b) => b[1] - a[1]).map(([label, n]) => (
                    <Chip key={label} size="sm" tone={LABEL_TONE[label] ?? 'muted'} icon={LABEL_ICON[label] && <Icon name={LABEL_ICON[label]} size="sm" />}>{`${CUSTOMER_LABEL[label] ?? label} ${n}`}</Chip>
                  ))}
                  <Chip size="sm" tone="neutral">{`Cadence: ${t.cadence ?? 'none'}${t.recipient_email ? ` → ${t.recipient_email}` : ''}`}</Chip>
                </Stack>
              </SettingRow>
            </li>
          ))}
        </Grid>
      )}
    </Panel>
  );
}

function BundleCard({ cadence, preview, review, updatesOnly, notify, onChanged, onEdit }: { cadence: 'monthly' | 'quarterly'; preview: DeliverablePreview | null; review: Review | null; updatesOnly: boolean; notify: (m: string) => void; onChanged: () => void; onEdit: () => void }) {
  const job = useJob(1500);
  const [sending, setSending] = useState(false);
  const title = cadence === 'monthly' ? 'Monthly bundle' : 'Quarterly bundle';
  const ready = preview?.ready_count ?? 0;
  const blocked = review?.status === 'revision_requested' || review?.status === 'under_review';
  const q = bundleQuery(cadence, updatesOnly);

  const pptx = async () => {
    try {
      const r = await api<{ task_id: string; bundle_url: string; status_url: string }>(`/api/forecast/deliverables/bundle/start?${q}`, { method: 'POST' });
      job.watch(r.status_url ?? `/api/forecast/assessment/job/${r.task_id}`, () =>
        downloadFile(r.bundle_url, `forecast-bundle-${cadence}.pptx`).then(onChanged, (e) => notify(errorText(e))),
      );
    } catch (e) {
      notify(`Bundle didn’t start: ${errorText(e)}`);
    }
  };
  const send = async () => {
    setSending(true);
    try {
      const r = await api<{ ok?: boolean; status?: string; period_label?: string; recipients?: string[]; findings?: Finding[] }>(`/api/forecast/deliverables/send?${q}`, { method: 'POST' });
      if (r.status === 'revision_requested') {
        notify(`The reviewer flagged ${(r.findings ?? []).filter((f) => f.severity === 'error').length} errors; the bundle is held for review below.`);
      } else {
        notify(r.ok ? `Sent “${r.period_label}” to ${(r.recipients ?? []).join(', ')}` : 'Email send failed — check the email provider settings');
      }
      onChanged();
    } catch (e) {
      notify(`Not sent: ${errorText(e)}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <SettingRow
      title={title}
      description={preview ? `${preview.configured_count} topics configured · ${ready} ready` : 'Loading…'}
      actionsPlacement="title"
      actions={review?.status && review.status !== 'awaiting_synth' && <Chip size="sm" tone={review.status.startsWith('approved') || review.status === 'shipped' ? 'success' : 'warning'}>{review.status.replace(/_/g, ' ')}</Chip>}
    >
      <Stack gap="sm">
        {(preview?.topics ?? []).slice(0, 6).map((t) => (
          <Text key={t.topic} variant="caption">{`${t.ready ? '✓' : '○'} ${t.topic}${t.recipient_email ? ` → ${t.recipient_email}` : ''}`}</Text>
        ))}
        {job.state.kind === 'running' && <Meter label={`${title} progress`} progress value={job.state.pct} valueText={`${job.state.pct}% · ${job.state.message}`} />}
        {job.state.kind === 'failed' && <Text tone="error">{job.state.message}</Text>}
        <Stack direction="row" gap="sm">
          <Button size="sm" variant="secondary" disabled={!ready || job.state.kind === 'running'} onClick={pptx}>.pptx</Button>
          {(['docx', 'md', 'html'] as const).map((ext) => (
            <Button key={ext} size="sm" variant="ghost" disabled={!ready} onClick={() => downloadFile(`/api/forecast/deliverables/bundle.${ext}?${q}`, `forecast-bundle-${cadence}.${ext}`).catch((e) => notify(errorText(e)))}>{`.${ext}`}</Button>
          ))}
          <Button size="sm" iconStart={<Icon name="Megaphone" size="sm" />} disabled={!ready || blocked} busy={sending} onClick={send}>Send now</Button>
          <Button size="sm" variant="secondary" iconStart={<Icon name="PencilSimple" size="sm" />} onClick={onEdit}>Edit and curate</Button>
        </Stack>
      </Stack>
    </SettingRow>
  );
}

/** Scheduled deliverables: per-topic cadence, the review gate, and the monthly/quarterly bundles. */
export function Deliverables({ notify, askConfirm }: { notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<{ cadence: string; period: string } | null>(null);
  const [configs, setConfigs] = useState<TopicDeliveryConfig[] | null>(null);
  const [edits, setEdits] = useState<Record<string, { cadence: string; recipient: string }>>({});
  const [previews, setPreviews] = useState<Record<string, DeliverablePreview | null>>({});
  const [reviews, setReviews] = useState<Record<string, Review | null>>({});
  const [updatesOnly, setUpdatesOnly] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    Promise.all([
      api<{ configs: TopicDeliveryConfig[] }>('/api/forecast/topics/delivery'),
      ...(['monthly', 'quarterly'] as const).map((c) => api<DeliverablePreview>(`/api/forecast/deliverables/preview?cadence=${c}`).catch(() => null)),
      ...(['monthly', 'quarterly'] as const).map((c) => api<{ review: Review | null }>(`/api/forecast/deliverables/review-status?cadence=${c}`).catch(() => ({ review: null }))),
    ]).then(
      ([d, pm, pq, rm, rq]) => {
        setConfigs((d as { configs: TopicDeliveryConfig[] }).configs ?? []);
        setEdits({});
        setPreviews({ monthly: pm as DeliverablePreview | null, quarterly: pq as DeliverablePreview | null });
        setReviews({ monthly: (rm as { review: Review | null }).review, quarterly: (rq as { review: Review | null }).review });
      },
      (e) => setError(errorText(e)),
    );
  }, []);
  useEffect(() => {
    if (open && !configs) load();
  }, [open, configs, load]);

  const saveRow = async (topic: string) => {
    const e = edits[topic];
    try {
      await api(`/api/forecast/topics/${encodeURIComponent(topic)}/delivery`, { method: 'PATCH', json: { cadence: e.cadence, recipient_email: e.recipient.trim() || null } });
      notify(`Cadence saved for “${topic}”`);
      load();
    } catch (err) {
      notify(`Not saved: ${errorText(err)}`);
    }
  };
  const reviewAction = async (cadence: string, action: 'approve' | 'request-revision') => {
    const r = reviews[cadence];
    const stages = Array.from(new Set((r?.reviewer_findings ?? []).filter((f) => f.severity === 'error').map((f) => f.stage)));
    try {
      await api(`/api/forecast/deliverables/review/${action}`, {
        method: 'POST',
        json: action === 'approve' ? { cadence, period_label: r?.period_label, approved_by: 'ui' } : { cadence, period_label: r?.period_label, target_stages: stages },
      });
      notify(action === 'approve' ? 'Overrides approved — the bundle can ship' : 'Revision requested — regenerate the bundle to re-run the flagged stages');
      load();
    } catch (e) {
      // The old panel ignored failures here (approve needs an admin account)
      notify(`That didn’t work: ${errorText(e)}`);
    }
  };
  const flagged = (['monthly', 'quarterly'] as const).filter((c) => reviews[c]?.status === 'revision_requested');

  return (
    <>
    <Collapsible open={open} onOpenChange={setOpen}>
      <Panel
        title="Scheduled deliverables"
        description="Monthly per-topic updates, the quarterly bundle, and scheduled email."
        headerAside={<CollapsibleTrigger variant="secondary">{open ? 'Hide' : 'Show'}</CollapsibleTrigger>}
      >
        <CollapsibleContent>
          {error ? (
            <Banner tone="error" icon="WarningCircle" title="Couldn’t load deliverables" description={error} />
          ) : !configs ? (
            <Skeleton lines={4} />
          ) : (
            <Stack gap="lg">
              {flagged.map((c) => {
                const r = reviews[c]!;
                const f = r.reviewer_findings ?? [];
                return (
                  <Banner
                    key={c}
                    tone="error"
                    icon="Warning"
                    title={`Reviewer flagged errors — ${c} bundle “${r.period_label}” held`}
                    description={
                      <Stack gap="sm">
                        <Text>{`${f.filter((x) => x.severity === 'error').length} errors · ${f.filter((x) => x.severity === 'warning').length} warnings`}</Text>
                        {f.slice(0, 8).map((x, i) => (
                          <Text key={i} variant="caption">{`${x.severity.toUpperCase()} · ${x.artefact_key}: ${x.finding}${x.suggested_fix ? ` — Fix: ${x.suggested_fix}` : ''}`}</Text>
                        ))}
                        <Stack direction="row" gap="sm">
                          <Button size="sm" variant="secondary" onClick={() => void reviewAction(c, 'approve')}>Approve overrides and ship</Button>
                          <Button size="sm" onClick={() => void reviewAction(c, 'request-revision')}>Request fix and regenerate</Button>
                        </Stack>
                      </Stack>
                    }
                  />
                );
              })}
              <Grid as="ul" columns={2} gap="sm" label="Bundles">
                {(['monthly', 'quarterly'] as const).map((c) => (
                  <li key={c}>
                    <BundleCard cadence={c} preview={previews[c] ?? null} review={reviews[c] ?? null} updatesOnly={updatesOnly} notify={notify} onChanged={load} onEdit={() => setEditing({ cadence: c, period: reviews[c]?.period_label || currentPeriodLabel(c) })} />
                  </li>
                ))}
              </Grid>
              <Checkbox label="Bundle in “updates only” mode (each topic’s changes since its last snapshot)" checked={updatesOnly} onCheckedChange={setUpdatesOnly} />
              {configs.length ? (
                <Table
                  caption="Per-topic cadence"
                  rowKey={(c) => c.topic}
                  rows={configs}
                  columns={[
                    { key: 'topic', header: 'Topic', rowHeader: true, wrap: true },
                    {
                      key: 'cadence',
                      header: 'Cadence',
                      render: (c) => (
                        <Select
                          label={`Cadence for ${c.topic}`}
                          hideLabel
                          options={[{ value: 'none', label: 'None' }, { value: 'monthly', label: 'Monthly' }, { value: 'quarterly', label: 'Quarterly' }]}
                          value={edits[c.topic]?.cadence ?? c.cadence}
                          onValueChange={(v) => setEdits((e) => ({ ...e, [c.topic]: { cadence: v, recipient: e[c.topic]?.recipient ?? c.recipient_email ?? '' } }))}
                        />
                      ),
                    },
                    {
                      key: 'recipient',
                      header: 'Recipients',
                      render: (c) => (
                        <TextField
                          label={`Recipients for ${c.topic}`}
                          hideLabel
                          value={edits[c.topic]?.recipient ?? c.recipient_email ?? ''}
                          onChange={(v) => setEdits((e) => ({ ...e, [c.topic]: { cadence: e[c.topic]?.cadence ?? c.cadence, recipient: v } }))}
                        />
                      ),
                    },
                    { key: 'delivered', header: 'Last delivered', render: (c) => fmtDate(c.last_delivered_at) },
                    { key: 'save', header: <span className="visually-hidden">Save</span>, render: (c) => edits[c.topic] && <Button size="sm" onClick={() => void saveRow(c.topic)}>Save</Button> },
                  ]}
                />
              ) : (
                <EmptyState>No topic has a delivery cadence yet. Set one in a topic’s Forecast Tracker.</EmptyState>
              )}
              <Grid columns={2} stackAt="never" gap="sm">
                <Stat size="compact" label="Monthly topics ready" value={`${previews.monthly?.ready_count ?? 0} / ${previews.monthly?.configured_count ?? 0}`} />
                <Stat size="compact" label="Quarterly topics ready" value={`${previews.quarterly?.ready_count ?? 0} / ${previews.quarterly?.configured_count ?? 0}`} />
              </Grid>
            </Stack>
          )}
        </CollapsibleContent>
      </Panel>
    </Collapsible>
    {editing && (
      <BriefEditor open onOpenChange={(o) => !o && setEditing(null)} cadence={editing.cadence} periodLabel={editing.period} notify={notify} askConfirm={askConfirm} onChanged={load} />
    )}
    </>
  );
}
