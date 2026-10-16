import '../components/topicsHealth.css';
import { useCallback, useEffect, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, EmptyState, Grid, Icon, Meter, Panel, SegmentedControl, Select, Skeleton, Stack, Table, Text,
  TextField, TextLink,
} from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { daysAgo, fmtDate, useJob } from '../lib/jobs';
import { AddTopicWizard } from '../overlays/AddTopicWizard';
import { DocPanel } from './Docs';
import type { ViewProps } from './types';

export interface TopicRow {
  topic: string;
  display_name?: string | null;
  description?: string | null;
  owner?: string | null;
  status?: string;
  tags?: string[] | null;
  overlay_status?: string;
  cadence?: string | null;
  recipient_email?: string | null;
  last_delivered_at?: string | null;
  assessment_id?: string | null;
  assessed_at?: string | null;
  scenarios_count?: number | null;
}

/** GET /api/forecast/topics — every tracked topic with its lifecycle. */
export function useTrackedTopics() {
  const [rows, setRows] = useState<TopicRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    api<{ topics: TopicRow[] }>('/api/forecast/topics').then((r) => setRows(r.topics ?? []), (e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  return { rows, error, reload: load };
}

/** The old dashboard's health rules, first match wins (TopicsDashboard.computeHealth): red, amber or green */
type Health = 'red' | 'amber' | 'green';
function health(t: TopicRow): { level: Health; reason: string } {
  const age = daysAgo(t.assessed_at);
  if (t.status === 'archived') return { level: 'amber', reason: 'Archived, excluded from bundles' };
  if (!t.assessment_id) return { level: 'red', reason: 'No assessment yet' };
  if (t.overlay_status === 'missing') return { level: 'red', reason: 'No deck overlay' };
  if (age == null) return { level: 'amber', reason: 'Assessment date unknown' };
  if (age > 90) return { level: 'red', reason: `Assessed ${age} days ago, stale` };
  if (age > 30) return { level: 'amber', reason: `Assessed ${age} days ago` };
  if (t.overlay_status === 'auto_generated') return { level: 'amber', reason: 'Overlay not reviewed' };
  if (!t.cadence || t.cadence === 'none') return { level: 'amber', reason: 'No delivery cadence' };
  return { level: 'green', reason: 'Healthy' };
}

/** The health as a red, amber or green dot with its reason written beside it */
function HealthCell({ t }: { t: TopicRow }) {
  const h = health(t);
  return (
    <span className="topics-health">
      <span className={`topics-health__dot topics-health__dot--${h.level}`} aria-hidden="true" />
      <Text as="span" variant="caption">{h.reason}</Text>
    </span>
  );
}

const STATUS_TONE: Record<string, 'warning' | 'success' | 'muted'> = { draft: 'warning', active: 'success', archived: 'muted' };
const OVERLAY_TONE: Record<string, 'error' | 'warning' | 'success'> = { missing: 'error', auto_generated: 'warning', human_reviewed: 'success' };

const STATUSES = ['active', 'draft', 'archived', 'all'].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }));

function Tracked({ openTopic, onAdd }: { openTopic: (t: string) => void; onAdd: () => void }) {
  const { rows, error, reload } = useTrackedTopics();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('active');
  const q = query.trim().toLowerCase();
  const shown = (rows ?? []).filter(
    (t) =>
      (status === 'all' || (t.status ?? 'active') === status) &&
      (!q || [t.display_name || t.topic, t.owner ?? '', ...(t.tags ?? [])].some((x) => x.toLowerCase().includes(q))),
  );
  return (
    <Panel
      title="Topics"
      description={rows ? `${shown.length} shown of ${rows.length} · open a topic to see its Forecast Tracker` : undefined}
      headerAside={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={onAdd}>Add topic</Button>}
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField label="Search topics" hideLabel type="search" placeholder="Search topic, owner, tag…" value={query} onChange={setQuery} />
          <Select label="Status" hideLabel options={STATUSES} value={status} onValueChange={setStatus} />
          <Button variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={reload}>Refresh</Button>
        </Stack>
        {error ? (
          <Banner tone="error" icon="WarningCircle" title="Couldn’t load topics" description={error} />
        ) : !rows ? (
          <Skeleton lines={5} />
        ) : shown.length ? (
          <Table
            caption="Tracked topics"
            hideCaption
            rowKey={(t) => t.topic}
            rows={shown}
            columns={[
              { key: 'health', header: 'Health', wrap: true, render: (t) => <HealthCell t={t} /> },
              {
                key: 'topic',
                header: 'Topic',
                rowHeader: true,
                wrap: true,
                render: (t) => (
                  <div>
                    <Button variant="ghost" size="sm" onClick={() => openTopic(t.topic)}>{t.display_name || t.topic}</Button>
                    {t.description && <Text variant="caption" as="div">{t.description}</Text>}
                  </div>
                ),
              },
              { key: 'owner', header: 'Owner', render: (t) => t.owner || '—' },
              { key: 'tags', header: 'Tags', render: (t) => <Stack direction="row" gap="sm">{(t.tags ?? []).slice(0, 3).map((g) => <Chip key={g} size="sm" tone="neutral">{g}</Chip>)}</Stack> },
              {
                key: 'assessed',
                header: 'Last assessed',
                render: (t) => {
                  const d = daysAgo(t.assessed_at);
                  // Amber after 30 days and red after 90, as the old dashboard coloured it
                  return <div>{fmtDate(t.assessed_at)}{d != null && <div><Chip size="sm" tone={d > 90 ? 'error' : d > 30 ? 'warning' : 'muted'}>{`${d}d ago`}</Chip></div>}</div>;
                },
              },
              { key: 'cadence', header: 'Cadence', wrap: true, render: (t) => <div>{t.cadence && t.cadence !== 'none' ? t.cadence : 'None'}{t.recipient_email && <Text variant="caption" as="div">{t.recipient_email}</Text>}</div> },
              { key: 'delivered', header: 'Last delivered', render: (t) => fmtDate(t.last_delivered_at) },
              { key: 'overlay', header: 'Overlay', render: (t) => <Chip size="sm" tone={OVERLAY_TONE[t.overlay_status ?? 'missing'] ?? 'muted'}>{(t.overlay_status ?? 'missing').replace(/_/g, ' ')}</Chip> },
              { key: 'status', header: 'Status', render: (t) => <Chip size="sm" tone={STATUS_TONE[t.status ?? 'active'] ?? 'muted'}>{t.status ?? 'active'}</Chip> },
            ]}
          />
        ) : (
          <EmptyState>No topics match. Try the “All” status, or add one.</EmptyState>
        )}
      </Stack>
    </Panel>
  );
}

interface Candidate {
  id: number;
  topic_label?: string;
  proposed_topic_name?: string;
  proposed_description?: string;
  topic_description?: string;
  relevance_rationale?: string;
  relevance_verdict?: 'in_scope' | 'adjacent' | 'off_scope';
  relevance_score?: number;
  detection_date?: string;
  article_count?: number;
  growth_rate?: number;
  /** A word on current rows ("accelerating"), a number on older ones */
  velocity?: number | string;
  avg_novelty_score?: number | null;
  key_themes?: string[] | string;
  proposed_tags?: string[] | string;
  sample_article_uris?: string[] | string;
  representative_keywords?: string[] | string;
  triage_status?: string;
  snooze_until?: string;
  rejected_reason?: string;
  /** Set for both promoted and merged candidates */
  promoted_to_topic?: string;
}

const list = (v: unknown): string[] => {
  if (Array.isArray(v)) return v.map(String);
  if (typeof v === 'string') {
    try {
      const p = JSON.parse(v);
      if (Array.isArray(p)) return p.map(String);
    } catch {
      return v ? [v] : [];
    }
  }
  return [];
};
const CAND_STATUSES = ['pending', 'snoozed', 'rejected', 'promoted', 'merged', 'all'].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }));
const VERDICT_TONE = { in_scope: 'success', adjacent: 'info', off_scope: 'muted' } as const;
const pctOf = (v?: number | null) => (typeof v !== 'number' ? '—' : `${Math.round(v * 100)}%`);
const num = (v: unknown) => (typeof v === 'number' ? v.toFixed(2) : typeof v === 'string' && v ? v : '—');

function Candidates({ knownTopics, notify, onPromoted }: { knownTopics: string[]; notify: (m: string) => void; onPromoted: (topic: string) => void }) {
  const [status, setStatus] = useState('pending');
  const [items, setItems] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [mergeInto, setMergeInto] = useState<Record<number, string>>({});
  const [reason, setReason] = useState<Record<number, string>>({});
  const scan = useJob(3000);
  const promote = useJob(3000);

  const load = useCallback(() => {
    setError(null);
    api<{ candidates: Candidate[] }>(`/api/forecast/candidates?triage_status=${status}`).then((r) => setItems(r.candidates ?? []), (e) => setError(errorText(e)));
  }, [status]);
  useEffect(load, [load]);

  const act = async (c: Candidate, action: 'promote' | 'snooze' | 'reject' | 'merge', body: Record<string, unknown>, done: string) => {
    setBusy(c.id);
    try {
      const r = await api<{ task_id?: string }>(`/api/forecast/candidates/${c.id}/${action}`, { method: 'POST', json: body });
      if (action === 'promote' && r.task_id) {
        notify('Promoting — building the topic’s forecast (several minutes)');
        promote.watch(`/api/forecast/candidates/job/${r.task_id}`, (job) => {
          load();
          if (job.result?.topic) onPromoted(job.result.topic);
        });
      } else {
        notify(done);
      }
      load();
    } catch (e) {
      notify(`${action} failed: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const pending = (items ?? []).filter((c) => (c.triage_status ?? 'pending') === 'pending');
  return (
    <Panel
      title="Candidates"
      description={items ? `${items.length} ${status} · ${pending.filter((c) => c.relevance_verdict === 'in_scope').length} in-scope · ${pending.filter((c) => c.relevance_verdict === 'adjacent').length} adjacent` : 'Emerging clusters the weekly scan judged in scope. Triage them here.'}
      headerAside={
        <Button
          iconStart={<Icon name="Sparkle" size="sm" />}
          busy={scan.state.kind === 'running'}
          onClick={async () => {
            try {
              const r = await api<{ task_id: string }>('/api/forecast/candidates/scan', { method: 'POST' });
              scan.watch(`/api/forecast/candidates/job/${r.task_id}`, () => { notify('Scan finished'); load(); });
            } catch (e) {
              notify(`Scan didn’t start: ${errorText(e)}`);
            }
          }}
        >
          {scan.state.kind === 'running' ? 'Scanning…' : 'Scan now'}
        </Button>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <Select label="Candidate status" hideLabel options={CAND_STATUSES} value={status} onValueChange={setStatus} />
          <Button variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={load}>Refresh</Button>
        </Stack>
        {scan.state.kind === 'running' && <Meter label="Scan progress" progress value={scan.state.pct} valueText={`${scan.state.pct}% · ${scan.state.message} — usually 2–6 minutes`} />}
        {scan.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Scan failed" description={scan.state.message} />}
        {promote.state.kind === 'running' && <Meter label="Promotion progress" progress value={promote.state.pct} valueText={`Promoting · ${promote.state.pct}% · ${promote.state.message}`} />}
        {promote.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Promotion failed" description={promote.state.message} />}
        {error ? (
          <Banner tone="error" icon="WarningCircle" title="Couldn’t load candidates" description={error} />
        ) : !items ? (
          <Skeleton lines={4} />
        ) : items.length === 0 ? (
          <EmptyState>{`No ${status} candidates. The weekly scan runs automatically; Scan now runs it immediately.`}</EmptyState>
        ) : (
          <Grid as="ul" columns={2} gap="sm" label="Candidates">
            {items.map((c) => {
              const name = c.proposed_topic_name || c.topic_label || `Candidate ${c.id}`;
              const isPending = (c.triage_status ?? 'pending') === 'pending';
              const samples = list(c.sample_article_uris).slice(0, 5);
              return (
                <ArticleCard
                  key={c.id}
                  as="li"
                  variant="row"
                  expandFullWidth
                  flag={c.relevance_verdict && <Chip size="sm" tone={VERDICT_TONE[c.relevance_verdict]}>{c.relevance_verdict.replace('_', '-')}</Chip>}
                  meta={`score ${pctOf(c.relevance_score)}${c.detection_date ? ` · detected ${fmtDate(c.detection_date)}` : ''}`}
                  title={name}
                  summary={c.proposed_description || c.topic_description || c.relevance_rationale}
                  details={
                    <Stack gap="sm">
                      {c.relevance_rationale && (c.proposed_description || c.topic_description) && <Text variant="caption"><em>judge: {c.relevance_rationale}</em></Text>}
                      <Text variant="label">{`${c.article_count ?? 0} articles · growth ${pctOf(c.growth_rate)} · novelty ${num(c.avg_novelty_score)} · velocity ${num(c.velocity)}`}</Text>
                      <Stack direction="row" gap="sm">
                        {list(c.key_themes).slice(0, 4).map((k) => <Chip key={k} size="sm" tone="neutral">{k}</Chip>)}
                        {list(c.proposed_tags).map((t) => <Chip key={t} size="sm" tone="muted">#{t}</Chip>)}
                      </Stack>
                      {list(c.representative_keywords).length > 0 && <Text variant="caption">{`keywords: ${list(c.representative_keywords).slice(0, 6).join(', ')}`}</Text>}
                      {samples.length > 0 && (
                        <Stack as="ul" gap="sm" label="Sample articles">
                          {samples.map((u) => <li key={u}><TextLink href={u} external>{u}</TextLink></li>)}
                        </Stack>
                      )}
                    </Stack>
                  }
                  footer={
                    isPending ? (
                      <Stack gap="sm">
                        <Stack direction="row" gap="sm">
                          <Button size="sm" iconStart={<Icon name="Play" size="sm" />} busy={busy === c.id} onClick={() => void act(c, 'promote', {}, '')}>Promote</Button>
                          <Button variant="ghost" size="sm" aria-label={`Snooze “${name}” for 7 days`} onClick={() => void act(c, 'snooze', { days: 7 }, 'Snoozed for 7 days')}>Snooze 7d</Button>
                          <Button variant="ghost" size="sm" aria-label={`Snooze “${name}” for 14 days`} onClick={() => void act(c, 'snooze', { days: 14 }, 'Snoozed for 14 days')}>14d</Button>
                        </Stack>
                        <Stack direction="row" gap="sm">
                          <Select label={`Merge “${name}” into`} hideLabel placeholder="Merge into…" options={knownTopics.map((t) => ({ value: t, label: t }))} value={mergeInto[c.id] ?? ''} onValueChange={(v) => setMergeInto((m) => ({ ...m, [c.id]: v }))} />
                          <Button variant="secondary" size="sm" disabled={!mergeInto[c.id]} onClick={() => void act(c, 'merge', { into_topic: mergeInto[c.id] }, `Merged into “${mergeInto[c.id]}”`)}>Merge</Button>
                        </Stack>
                        <TextField
                          label={`Reason for rejecting “${name}”`}
                          hideLabel
                          placeholder="Reason (e.g. not relevant)"
                          value={reason[c.id] ?? ''}
                          onChange={(v) => setReason((r) => ({ ...r, [c.id]: v }))}
                          action={<Button variant="secondary" size="lg" iconStart={<Icon name="X" size="sm" />} disabled={!reason[c.id]?.trim()} onClick={() => void act(c, 'reject', { reason: reason[c.id].trim() }, `Rejected “${name}”`)}>Reject</Button>}
                        />
                      </Stack>
                    ) : (
                      <Text variant="caption">
                        {c.triage_status === 'snoozed' && `Snoozed until ${fmtDate(c.snooze_until)}`}
                        {c.triage_status === 'rejected' && `Rejected${c.rejected_reason ? `: ${c.rejected_reason}` : ''}`}
                        {c.triage_status === 'promoted' && `Promoted to “${c.promoted_to_topic ?? name}”`}
                        {c.triage_status === 'merged' && `Merged into “${c.promoted_to_topic ?? ''}”`}
                      </Text>
                    )
                  }
                />
              );
            })}
          </Grid>
        )}
      </Stack>
    </Panel>
  );
}

export function Topics({ navigate, notify, setTopic }: ViewProps) {
  const [view, setView] = useState('tracked');
  const [wizard, setWizard] = useState<{ topic?: string; step?: number } | null>(null);
  const known = useTrackedTopics();
  const openTopic = (t: string) => {
    setTopic(t);
    navigate('forecast-tracker');
  };
  return (
    <>
      <SegmentedControl
        label="Topics view"
        value={view}
        onValueChange={setView}
        options={[{ value: 'tracked', label: 'Tracked' }, { value: 'candidates', label: 'Candidates' }, { value: 'how', label: 'How it works' }]}
      />
      {view === 'tracked' && <Tracked openTopic={openTopic} onAdd={() => setWizard({})} />}
      {view === 'candidates' && (
        <Candidates
          knownTopics={(known.rows ?? []).map((r) => r.topic)}
          notify={notify}
          // A promoted candidate opens at the overlay step (the old page reopened step 1)
          onPromoted={(topic) => setWizard({ topic, step: 2 })}
        />
      )}
      {view === 'how' && <DocPanel name="how-it-works-topics" title="How it works" />}
      <AddTopicWizard
        open={wizard !== null}
        onOpenChange={(o) => !o && setWizard(null)}
        initialTopic={wizard?.topic}
        initialStep={wizard?.step}
        notify={notify}
        onCompleted={openTopic}
      />
    </>
  );
}
