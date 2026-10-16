import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, EmptyState, Grid, Icon, LineItems, Meter,
  Panel, SegmentedControl, Select, SettingRow, Skeleton, Stack, Stat, Table, Text, TextArea, TextField, TextLink,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import type {
  AddendumScenario, AssessmentSnapshot, BaselineCorrection, ForecastAssessment, ForecastAssessmentResponse, ScenarioDraft, ScenarioStatusesResponse,
  ScenarioVerdict, SurpriseCluster,
} from '@monolith-types/forecastAssessment';
import { api, errorText } from '../../shell';
import { downloadFile } from '../lib/download';
import { fmtDate, useJob } from '../lib/jobs';
import { DocPanel } from './Docs';
import { SnapshotGrid } from '../components/ForecastCharts';
import { Deliverables, AllTopicsForecast } from './Deliverables';
import type { ViewProps } from './types';

const HORIZON_LABEL: Record<string, string> = { h1: 'H1 · Declining', h2: 'H2 · Transition', h3: 'H3 · Future' };
/** Paired-mode labels as customers see them (matches the PPTX builder's CUSTOMER_LABEL). */
const CUSTOMER_LABEL: Record<string, string> = { 'Above baseline': 'Strengthening', 'At baseline': 'Stable', 'Below baseline': 'Cooling' };
const LABEL_TONE: Record<string, 'success' | 'neutral' | 'warning'> = { 'Above baseline': 'success', 'At baseline': 'neutral', 'Below baseline': 'warning' };
const VERDICTS = ['Accelerating', 'On-track', 'Stalled', 'Off-track', 'Inconclusive'] as const;
const VERDICT_TONE: Record<string, 'success' | 'info' | 'warning' | 'error' | 'muted'> = {
  Accelerating: 'success', 'On-track': 'info', Stalled: 'warning', 'Off-track': 'error', Inconclusive: 'muted',
};
// Icons for each status, as the old page drew them beside the label
const VERDICT_ICON: Record<string, 'TrendUp' | 'CheckCircle' | 'Minus' | 'ArrowDown' | 'WarningCircle'> = {
  Accelerating: 'TrendUp', 'On-track': 'CheckCircle', Stalled: 'Minus', 'Off-track': 'ArrowDown', Inconclusive: 'WarningCircle',
};
const VERDICT_STAT_TONE: Record<string, 'success' | 'info' | 'warning' | 'error' | 'default'> = {
  Accelerating: 'success', 'On-track': 'info', Stalled: 'warning', 'Off-track': 'error', Inconclusive: 'default',
};
const LABEL_ICON: Record<string, 'TrendUp' | 'Minus' | 'ArrowDown'> = { 'Above baseline': 'TrendUp', 'At baseline': 'Minus', 'Below baseline': 'ArrowDown' };
const MODES = [
  { value: 'paired', label: 'Paired (recommended — adjusts for the pre-existing trend)' },
  { value: 'live', label: 'Post-forecast only' },
  { value: 'placebo', label: 'Pre-forecast comparison' },
];
const enc = encodeURIComponent;

/** Promoted scenarios matched to their verdict by user_scenario_id (positions shift when one is added or skipped). */
function addendumsByIdx(verdicts: ScenarioVerdict[], addendums: AddendumScenario[]) {
  const byId = new Map(addendums.map((a) => [a.id, a]));
  const out: Record<number, AddendumScenario> = {};
  verdicts.forEach((v) => {
    const a = v.user_scenario_id ? byId.get(v.user_scenario_id) : undefined;
    if (a) out[v.scenario_idx] = a;
  });
  return out;
}

/** The stored forecast run for a topic, its assessment, and its promoted/resolved scenarios. */
function useForecast(topic: string) {
  const [run, setRun] = useState<{ run_id: string; generated_at?: string } | null | undefined>(undefined);
  const [resp, setResp] = useState<ForecastAssessmentResponse | null>(null);
  const [addendums, setAddendums] = useState<AddendumScenario[]>([]);
  const [statuses, setStatuses] = useState<ScenarioStatusesResponse>({ originals: {}, addendums: {} });
  const [error, setError] = useState<string | null>(null);

  const loadRun = useCallback(async (runId: string) => {
    const [a, s] = await Promise.all([
      api<ForecastAssessmentResponse>(`/api/forecast/${enc(runId)}/assessment`),
      api<{ addendum_scenarios: AddendumScenario[]; scenario_statuses: ScenarioStatusesResponse }>(`/api/forecast/${enc(runId)}/scenarios`).catch(() => null),
    ]);
    setResp(a);
    setAddendums(s?.addendum_scenarios ?? []);
    setStatuses(s?.scenario_statuses ?? { originals: {}, addendums: {} });
  }, []);

  const load = useCallback(async () => {
    setError(null);
    setRun(undefined);
    setResp(null);
    try {
      const r = await api<{ run_id: string; generated_at?: string }>(`/api/forecast/topics/${enc(topic)}/latest-run`);
      setRun(r);
      await loadRun(r.run_id);
    } catch (e) {
      const msg = errorText(e);
      if (/404|not found|no .*run/i.test(msg)) setRun(null);
      else {
        setRun(null);
        setError(msg);
      }
    }
  }, [topic, loadRun]);

  useEffect(() => {
    if (topic) void load();
  }, [topic, load]);

  return { run, resp, addendums, statuses, error, reload: load, reloadRun: () => (run ? loadRun(run.run_id) : Promise.resolve()) };
}

function VerdictDistribution({ a }: { a: ForecastAssessment }) {
  const dist = a.summary?.verdict_distribution ?? ({} as Record<string, number>);
  const total = VERDICTS.reduce((s, v) => s + (dist[v] ?? 0), 0);
  if (!total) return null;
  return (
    // Five verdicts: a wrapping row (the grid allows at most four columns)
    <Stack as="ul" direction="row" gap="sm" label="Verdict distribution">
      {VERDICTS.map((v) => <Stat key={v} as="li" size="compact" surface="panel" tone={(dist[v] ?? 0) > 0 ? VERDICT_STAT_TONE[v] : 'default'} icon={<Icon name={VERDICT_ICON[v]} size="sm" />} label={v} value={dist[v] ?? 0} />)}
    </Stack>
  );
}

function Evidence({ title, items }: { title: string; items: { article_uri: string; title?: string; rationale?: string }[] }) {
  if (!items.length) return null;
  return (
    <Stack gap="sm">
      <Text variant="label" as="div">{title}</Text>
      <Stack as="ul" gap="sm" label={title}>
        {items.map((s) => (
          <li key={s.article_uri}>
            <Stack gap="sm">
              {/^https?:/.test(s.article_uri) ? <TextLink href={s.article_uri} external>{s.title || s.article_uri}</TextLink> : <Text as="span">{s.title || s.article_uri}</Text>}
              {s.rationale && <Text variant="caption">{s.rationale}</Text>}
            </Stack>
          </li>
        ))}
      </Stack>
    </Stack>
  );
}

function ScenarioCard({ v, baseline, addendum, onDone }: { v: ScenarioVerdict; baseline?: BaselineCorrection['per_scenario'][string]; addendum?: AddendumScenario; onDone?: () => void }) {
  const deck = v.top_articles?.deck_info;
  const label = baseline ? CUSTOMER_LABEL[baseline.label] ?? baseline.label : v.verdict_label;
  const tone = baseline ? LABEL_TONE[baseline.label] ?? 'neutral' : VERDICT_TONE[v.verdict_label] ?? 'muted';
  const icon = baseline ? LABEL_ICON[baseline.label] : VERDICT_ICON[v.verdict_label];
  return (
    <SettingRow
      title={deck?.deck_scenario_name || v.scenario_title}
      description={`${HORIZON_LABEL[v.horizon_type] ?? v.horizon_type}${deck?.consensus_pct != null ? ` · ${deck.consensus_pct}% original consensus` : ''}${addendum ? ' · added from an emerging theme' : ''}`}
      actionsPlacement="title"
      actions={
        <>
          <Chip size="sm" tone={tone} icon={icon && <Icon name={icon} size="sm" />}>{label}</Chip>
          {onDone && <Button variant="ghost" size="sm" onClick={onDone}>Done</Button>}
        </>
      }
    >
      <Stack gap="sm">
        {deck?.primary_signal && <Text variant="description">{deck.primary_signal}</Text>}
        <Text variant="caption">{`${v.supports} confirming · ${v.contradicts} contradicting · ${v.neutral} neutral`}</Text>
        {baseline && (
          <Text variant="caption">{`Confirmation vs. pre-forecast: ${baseline.net_rate >= 0 ? '+' : ''}${(baseline.net_rate * 100).toFixed(2)}% (live ${baseline.live_supports}/${baseline.live_pool}, placebo ${baseline.placebo_supports}/${baseline.placebo_pool})`}</Text>
        )}
        {((v.top_articles?.supports?.length ?? 0) > 0 || (v.top_articles?.contradicts?.length ?? 0) > 0) && (
          <Collapsible>
            <CollapsibleTrigger variant="ghost" size="sm">Evidence</CollapsibleTrigger>
            <CollapsibleContent>
              <Stack gap="md">
                <Evidence title="Top confirming evidence" items={(v.top_articles?.supports ?? []).slice(0, 3)} />
                <Evidence title="Strongest contradicting evidence" items={(v.top_articles?.contradicts ?? []).slice(0, 2)} />
              </Stack>
            </CollapsibleContent>
          </Collapsible>
        )}
      </Stack>
    </SettingRow>
  );
}

function Snapshots({ topic, titles }: { topic: string; titles?: Record<number, string> }) {
  const [rows, setRows] = useState<AssessmentSnapshot[] | null>(null);
  useEffect(() => {
    api<{ snapshots: AssessmentSnapshot[] }>(`/api/forecast/snapshots/by-topic?topic=${enc(topic)}`).then((r) => setRows(r.snapshots ?? []), () => setRows([]));
  }, [topic]);
  if (!rows || rows.length < 2) return null;
  const count = (s: AssessmentSnapshot, l: string) => s.per_scenario.filter((p) => p.label === l).length;
  return (
    <Panel title="Snapshot history" description={`${rows.length} paired assessments over time: each scenario's status at every re-assessment, then the totals.`}>
      <Stack gap="md">
      <SnapshotGrid snapshots={rows} titles={titles} />
      <Table
        caption="Snapshot history"
        hideCaption
        rowKey={(s) => s.assessment_id}
        rows={rows}
        columns={[
          { key: 'assessed', header: 'Assessed', rowHeader: true, render: (s) => fmtDate(s.assessed_at) },
          { key: 'up', header: 'Strengthening', align: 'end', render: (s) => count(s, 'Above baseline') },
          { key: 'flat', header: 'Stable', align: 'end', render: (s) => count(s, 'At baseline') },
          { key: 'down', header: 'Cooling', align: 'end', render: (s) => count(s, 'Below baseline') },
          { key: 'pool', header: 'Articles', align: 'end', render: (s) => s.evidence_count ?? '—' },
          { key: 'window', header: 'Window', render: (s) => (s.window_weeks ? `±${s.window_weeks}w` : 'full') },
          { key: 'surprises', header: 'Emerging themes', align: 'end', render: (s) => s.surprises_count ?? 0 },
        ]}
      />
      </Stack>
    </Panel>
  );
}

function PromoteDialog({ runId, assessmentId, cluster, index, onClose, onSaved }: { runId: string; assessmentId: string; cluster: SurpriseCluster; index: number; onClose: () => void; onSaved: (statusUrl: string) => void }) {
  const [draft, setDraft] = useState<ScenarioDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<ScenarioDraft>(`/api/forecast/${enc(runId)}/scenarios/draft-from-surprise`, { method: 'POST', json: { assessment_id: assessmentId, surprise_index: index } }).then(setDraft, (e) => setError(errorText(e)));
  }, [runId, assessmentId, index]);
  const set = (p: Partial<ScenarioDraft>) => setDraft((d) => (d ? { ...d, ...p } : d));
  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await api<{ status_url: string }>(`/api/forecast/${enc(runId)}/scenarios`, { method: 'POST', json: { ...draft, window_weeks: 8 } });
      onSaved(r.status_url);
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Track as scenario"
      description={`Turn the emerging theme “${cluster.label}” (${cluster.size} articles) into a scenario. Saving starts a fresh paired assessment.`}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!draft?.title?.trim()} onClick={save}>Save & reassess</Button>
        </>
      }
    >
      {error && <Banner tone="error" icon="WarningCircle" title="That didn’t work" description={error} />}
      {!draft && !error ? (
        <Stack gap="sm"><Text variant="hint">Drafting the scenario…</Text><Skeleton variant="block" /></Stack>
      ) : draft && (
        <Stack gap="md">
          <TextField label="Title" value={draft.title} onChange={(title) => set({ title })} />
          <TextArea label="Description" rows={5} value={draft.description} onChange={(description) => set({ description })} />
          <Grid columns={2} stackAt="small" gap="md">
            <Select label="Horizon" fullWidth options={['h1', 'h2', 'h3'].map((h) => ({ value: h, label: HORIZON_LABEL[h] }))} value={draft.horizon_type} onValueChange={(h) => set({ horizon_type: h as ScenarioDraft['horizon_type'] })} />
            <TextField label="Timeframe" placeholder="2026-2030" value={draft.timeframe} onChange={(timeframe) => set({ timeframe })} />
          </Grid>
        </Stack>
      )}
    </Dialog>
  );
}

function TopicCadence({ topic, notify }: { topic: string; notify: (m: string) => void }) {
  const [cfg, setCfg] = useState<{ cadence: string; recipient: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    api<{ configs: { topic: string; cadence: string; recipient_email?: string | null }[] }>('/api/forecast/topics/delivery').then(
      (r) => {
        const c = r.configs?.find((x) => x.topic === topic);
        setCfg({ cadence: c?.cadence ?? 'none', recipient: c?.recipient_email ?? '' });
      },
      () => setCfg({ cadence: 'none', recipient: '' }),
    );
  }, [topic]);
  if (!cfg) return null;
  const save = async () => {
    try {
      await api(`/api/forecast/topics/${enc(topic)}/delivery`, { method: 'PATCH', json: { cadence: cfg.cadence, recipient_email: cfg.recipient.trim() || null } });
      setDirty(false);
      notify('Delivery cadence saved');
    } catch (e) {
      // The old control swallowed this (it needs an admin account)
      notify(`Not saved: ${errorText(e)}`);
    }
  };
  return (
    <Panel title="Delivery cadence for this topic" headingLevel={3}>
      <Stack direction="row" gap="sm">
        <Select label="Cadence" options={[{ value: 'none', label: 'None' }, { value: 'monthly', label: 'Monthly' }, { value: 'quarterly', label: 'Quarterly' }]} value={cfg.cadence} onValueChange={(cadence) => { setCfg({ ...cfg, cadence }); setDirty(true); }} />
        <TextField label="Recipient" placeholder="recipient@example.com" value={cfg.recipient} onChange={(recipient) => { setCfg({ ...cfg, recipient }); setDirty(true); }} />
        {dirty && <Button onClick={save}>Save</Button>}
      </Stack>
    </Panel>
  );
}

function TopicForecast({ topic, notify, askConfirm }: { topic: string; notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const f = useForecast(topic);
  // Paired is the recommended mode, so it's the default (the old page defaulted to live)
  const [mode, setMode] = useState('paired');
  const [weeks, setWeeks] = useState('8');
  const [promoting, setPromoting] = useState<{ cluster: SurpriseCluster; index: number } | null>(null);
  const job = useJob(4000);
  const weeksOk = Number.isInteger(Number(weeks)) && Number(weeks) >= 1 && Number(weeks) <= 52;
  const a = f.resp?.assessment ?? null;
  const hist = !a ? f.resp?.historical_assessment ?? null : null;
  const runId = f.run?.run_id;

  const runAssessment = async () => {
    if (!runId) return;
    try {
      const url = mode === 'paired' ? `/api/forecast/${enc(runId)}/assess-paired?window_weeks=${weeks}` : `/api/forecast/${enc(runId)}/assess?mode=${mode}&window_weeks=${weeks}`;
      const r = await api<{ status_url: string }>(url, { method: 'POST' });
      job.watch(r.status_url, () => { notify('Assessment complete'); void f.reloadRun(); });
    } catch (e) {
      notify(`Assessment didn’t start: ${errorText(e)}`);
    }
  };

  const setStatus = async (body: Record<string, unknown>) => {
    if (!runId) return;
    try {
      await api(`/api/forecast/${enc(runId)}/scenarios/status`, { method: 'PATCH', json: body });
      await f.reloadRun();
    } catch (e) {
      notify(`Not changed: ${errorText(e)}`);
    }
  };

  if (f.run === undefined) return <Skeleton lines={6} />;
  if (f.error) return <Banner tone="error" icon="WarningCircle" title="Couldn’t load the forecast" description={f.error} />;
  if (f.run === null) {
    return (
      <Panel title={`Forecast Tracker — ${topic}`}>
        <EmptyState icon="ChartLineUp" title="No stored Future Horizons run for this topic">
          Generate the analysis on the Future Horizons tab first; the tracker then scores that forecast against what happens next.
        </EmptyState>
      </Panel>
    );
  }

  const shown = a ?? hist;
  const verdicts = shown?.scenario_verdicts ?? [];
  const baseline = shown?.summary?.baseline_correction;
  const byIdx = a ? addendumsByIdx(verdicts, f.addendums) : {};
  const assessedIds = new Set(verdicts.map((v) => v.user_scenario_id).filter(Boolean));
  const running = job.state.kind === 'running';

  return (
    <>
      <Panel
        title={`Forecast Tracker — ${topic}`}
        description={[
          f.run.generated_at && `Forecast generated ${fmtDate(f.run.generated_at)}`,
          a && `Last assessed ${fmtDate(a.assessed_at)} over ${a.evidence_count} post-forecast articles`,
        ].filter(Boolean).join(' · ') || undefined}
        headerAside={
          a && (
            <Stack direction="row" gap="sm">
              <Button variant="secondary" size="sm" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => downloadFile(`/api/forecast/${enc(a.run_id)}/assessment/${enc(a.id)}/export.pptx`, `forecast-${topic}.pptx`).catch((e) => notify(errorText(e)))}>Export .pptx</Button>
              <Button variant="ghost" size="sm" onClick={() => downloadFile(`/api/forecast/${enc(a.run_id)}/assessment/${enc(a.id)}/export.pptx?updates_only=true`, `forecast-${topic}-updates.pptx`).catch((e) => notify(errorText(e)))}>Updates only</Button>
            </Stack>
          )
        }
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <Select label="Mode" options={MODES} value={mode} onValueChange={setMode} />
            <TextField label="Window (weeks)" type="number" min={1} max={52} value={weeks} onChange={setWeeks} error={weeksOk ? undefined : 'Enter 1–52 weeks.'} />
          </Stack>
          <Stack direction="row" gap="sm">
            <Button iconStart={<Icon name="Play" size="sm" />} disabled={!weeksOk || running} busy={running} onClick={runAssessment}>
              {running ? 'Running assessment…' : a ? 'Re-run assessment' : 'Run assessment'}
            </Button>
          </Stack>
          {job.state.kind === 'running' && <Meter label="Assessment progress" progress value={job.state.pct} valueText={`${job.state.pct}% · ${job.state.message}`} />}
          {job.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Assessment failed" description={job.state.message} />}
        </Stack>
      </Panel>

      <Collapsible>
        <Panel title="How the Forecast Tracker works" headerAside={<CollapsibleTrigger variant="secondary">Read</CollapsibleTrigger>}>
          <CollapsibleContent>
            <DocPanel name="how-it-works-forecast-tracker" />
          </CollapsibleContent>
        </Panel>
      </Collapsible>

      {hist && (
        <Banner
          tone="warning"
          icon="Warning"
          title="This forecast run hasn’t been assessed yet"
          description={`Showing the topic’s earlier assessment (run ${f.resp?.historical_assessment_run_id ?? hist.run_id}) read-only. Run an assessment to score this run.`}
        />
      )}

      {shown && <Snapshots topic={topic} titles={Object.fromEntries(verdicts.map((v) => [v.scenario_idx, v.top_articles?.deck_info?.deck_scenario_name || v.scenario_title]))} />}

      {shown ? (
        <>
          <VerdictDistribution a={shown} />
          <Panel
            title="Per-scenario tracking"
            description={baseline ? `Corrected against the pre-forecast trend (live pool ${baseline.live_pool}, placebo pool ${baseline.placebo_pool}).` : undefined}
          >
            <Grid as="ul" columns={2} gap="sm" label="Scenarios">
              {verdicts.filter((v) => (v.verdict_label as string) !== 'Done').map((v) => (
                <li key={v.user_scenario_id || v.scenario_key || `idx-${v.scenario_idx}`}>
                  <ScenarioCard
                    v={v}
                    baseline={baseline?.per_scenario?.[String(v.scenario_idx)]}
                    addendum={byIdx[v.scenario_idx]}
                    onDone={
                      a
                        ? () =>
                            askConfirm({
                              title: 'Mark scenario done?',
                              message: `“${v.top_articles?.deck_info?.deck_scenario_name || v.scenario_title}” will be skipped from future assessments. Its history is kept, and you can undo this.`,
                              action: 'Mark done',
                              // Identify the scenario by its own key; an index points at a different one once scenarios are added
                              onConfirm: () => void setStatus(v.user_scenario_id ? { user_scenario_id: v.user_scenario_id, status: 'done' } : v.scenario_key ? { scenario_key: v.scenario_key, status: 'done' } : { scenario_idx: v.scenario_idx, status: 'done' }),
                            })
                        : undefined
                    }
                  />
                </li>
              ))}
            </Grid>
          </Panel>

          {a && f.addendums.some((x) => f.statuses.addendums[x.id]?.status !== 'done') && (
            <Panel title="Added scenarios" description="Scenarios promoted from emerging themes.">
              <Stack as="ul" gap="sm" label="Added scenarios">
                {f.addendums.filter((x) => f.statuses.addendums[x.id]?.status !== 'done').map((x) => (
                  <li key={x.id}>
                    <SettingRow
                      title={x.title}
                      description={`${HORIZON_LABEL[x.horizon_type] ?? x.horizon_type}${x.timeframe ? ` · ${x.timeframe}` : ''} · added ${fmtDate(x.created_at)}${x.source_surprise_label ? ` · from “${x.source_surprise_label}”` : ''}`}
                      actionsPlacement="title"
                      actions={!assessedIds.has(x.id) && <Chip size="sm" tone="info">Assessment pending</Chip>}
                    >
                      <Text variant="description">{x.description}</Text>
                    </SettingRow>
                  </li>
                ))}
              </Stack>
            </Panel>
          )}

          {a && verdicts.some((v) => (v.verdict_label as string) === 'Done') && (
            <Panel title="Resolved scenarios" description="Marked done: skipped from future assessments; their history is kept.">
              <Stack as="ul" gap="sm" label="Resolved scenarios">
                {verdicts.filter((v) => (v.verdict_label as string) === 'Done').map((v) => {
                  const add = byIdx[v.scenario_idx];
                  const row = add ? f.statuses.addendums[add.id] : (v.scenario_key ? f.statuses.by_key?.[v.scenario_key] : undefined) ?? f.statuses.originals[String(v.scenario_idx)];
                  return (
                    <li key={v.user_scenario_id || v.scenario_key || `idx-${v.scenario_idx}`}>
                      <SettingRow
                        title={v.top_articles?.deck_info?.deck_scenario_name || v.scenario_title}
                        description={`${HORIZON_LABEL[v.horizon_type] ?? v.horizon_type}${row?.marked_done_at ? ` · marked done ${fmtDate(row.marked_done_at)}` : ''}${row?.note ? ` · ${row.note}` : ''}`}
                        actions={<Button variant="ghost" size="sm" onClick={() => void setStatus(add ? { user_scenario_id: add.id, status: 'active' } : v.scenario_key ? { scenario_key: v.scenario_key, status: 'active' } : { scenario_idx: v.scenario_idx, status: 'active' })}>Un-mark</Button>}
                      />
                    </li>
                  );
                })}
              </Stack>
            </Panel>
          )}

          {a && (a.surprises ?? []).length > 0 && (
            <Panel title="Emerging themes" description="Clusters of new articles the forecast didn’t anticipate.">
              <Grid as="ul" columns={2} gap="sm" label="Emerging themes">
                {a.surprises.map((s, i) => (
                  <li key={`${i}-${s.label}`}>
                    <SettingRow
                      title={s.label}
                      description={`${s.size} articles${s.note ? ` · ${s.note}` : ''}`}
                      actionsPlacement="title"
                      actions={<Button variant="secondary" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setPromoting({ cluster: s, index: i })}>Track as scenario</Button>}
                    >
                      <Stack as="ul" gap="sm" label={`${s.label} articles`}>
                        {(s.sample_articles ?? []).slice(0, 5).map((x) => (
                          <li key={x.uri}>{/^https?:/.test(x.uri) ? <TextLink href={x.uri} external>{x.title || x.uri}</TextLink> : <Text as="span">{x.title || x.uri}</Text>}</li>
                        ))}
                      </Stack>
                    </SettingRow>
                  </li>
                ))}
              </Grid>
            </Panel>
          )}

          {a && <TopicCadence topic={topic} notify={notify} />}
          {a && (
            <LineItems
              label="Assessment details"
              items={[
                { id: 'mode', label: 'Mode', amount: a.mode === 'live' && baseline ? 'Paired' : a.mode },
                { id: 'pool', label: 'Evidence pool', amount: String(a.summary?.evidence_pool ?? a.evidence_count) },
                { id: 'model', label: 'Model', amount: a.model_used },
                { id: 'time', label: 'Runtime', amount: `${Math.round(a.runtime_seconds ?? 0)} s` },
              ]}
            />
          )}
        </>
      ) : (
        !running && (
          <Panel title="Assessment">
            <EmptyState icon="ChartLineUp" title="No assessment yet">
              Run an assessment to score each scenario against the articles that arrived since the forecast. It takes 5–15 minutes.
            </EmptyState>
          </Panel>
        )
      )}

      {promoting && runId && a && (
        <PromoteDialog
          runId={runId}
          assessmentId={a.id}
          cluster={promoting.cluster}
          index={promoting.index}
          onClose={() => setPromoting(null)}
          onSaved={(url) => {
            notify('Scenario saved — reassessing');
            job.watch(url, () => { notify('Reassessment complete'); void f.reloadRun(); });
          }}
        />
      )}
    </>
  );
}

export function ForecastTracker({ config, notify, setTopic, askConfirm }: ViewProps) {
  const [scope, setScope] = useState('topic');
  return (
    <>
      <SegmentedControl
        label="Forecast Tracker scope"
        value={scope}
        onValueChange={setScope}
        options={[{ value: 'topic', label: 'This topic' }, { value: 'all', label: 'All topics' }]}
      />
      {scope === 'topic' ? (
        <TopicForecast topic={config.topic} notify={notify} askConfirm={askConfirm} />
      ) : (
        <AllTopicsForecast notify={notify} onOpen={(t) => { setTopic(t); setScope('topic'); }} />
      )}
      <Deliverables notify={notify} askConfirm={askConfirm} />
    </>
  );
}
