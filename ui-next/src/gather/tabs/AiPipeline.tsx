import { useState } from 'react';
import {
  ActivityRow, Banner, Button, Chip, EmptyState, Eyebrow, Grid, Icon, IconButton, LineItems, Meter, Pagination, Panel, PipelineFlow,
  type PipelineStep, SegmentedControl, SettingRow, Skeleton, Stack, Stat, Text,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import * as t from '@monolith/trainingApi';
import type { DataQualityReport, InferenceMode, ModelInfo, PreclassifierInfo, TrainingRun } from '@monolith/trainingApi';
import { errorText } from '../../shell';
import { fmt, type Notify } from '../lib';
import { RelevanceTriageDialog } from '../overlays/RelevanceTriageDialog';
import { collecting, DEBERTA_THRESHOLD, FEEDBACK_GOAL, fullyReady, useTraining } from '../useTraining';
import { LabeledMeter, TopicTrainingCard } from './TopicTrainingCard';

const PAGE_SIZE = 12;
/** The data quality list shows the weakest topics first, this many until expanded. */
const AUDIT_PREVIEW = 5;
/** Below this DeBERTa confidence the hybrid mode falls back to the LLM. */
const CONFIDENCE_OK = 0.6;

const INFERENCE_MODES: { value: InferenceMode; label: string; description: string }[] = [
  { value: 'local', label: 'Local Only', description: 'Local models only (DeBERTa, Phi-3, Qwen): fastest and free' },
  { value: 'hybrid', label: 'Hybrid', description: 'Local models with LLM fallback for low confidence: balanced' },
  { value: 'external', label: 'External', description: 'The LLM for all processing: most accurate, costs apply' },
];

/** Which model runs each step in each mode (the old tab's getPipelineConfig). */
function pipelineSteps(mode: InferenceMode): PipelineStep[] {
  const ext = mode === 'external';
  const pick = (local: string, hybrid: string) => (mode === 'local' ? local : mode === 'hybrid' ? hybrid : 'LLM');
  return [
    { id: 'collection', title: 'Collection', detail: 'RSS, APIs' },
    { id: 'relevance', title: 'Relevance', detail: pick('DeBERTa', 'DeBERTa → LLM'), tags: [{ label: ext ? 'LLM' : mode === 'hybrid' ? 'Hybrid' : 'DeBERTa', tone: 'accent' }] },
    { id: 'category', title: 'Category', detail: pick('Qwen', '→ LLM fallback'), tags: [{ label: ext ? 'LLM' : 'Qwen', tone: 'info' }] },
    { id: 'summary', title: 'Summary', detail: pick('Phi-3', '→ LLM fallback'), tags: [{ label: ext ? 'LLM' : 'Phi-3', tone: 'success' }] },
    { id: 'enrichment', title: 'Enrichment', detail: pick('DeBERTa', '→ LLM fallback'), tags: [{ label: ext ? 'LLM' : 'DeBERTa', tone: 'warning' }] },
    { id: 'tags', title: 'Tags + NER', detail: pick('KeyBERT', 'Phi-3 → LLM'), tags: [{ label: ext ? 'LLM' : 'KeyBERT', tone: 'neutral' }] },
  ];
}

const RUN_TONE: Record<TrainingRun['status'], 'success' | 'info' | 'error' | 'muted'> = {
  deployed: 'success', completed: 'info', failed: 'error', pending: 'muted', running: 'info', exporting: 'info', training: 'info',
};
const PC_LABEL: Record<PreclassifierInfo['training_status'], string> = {
  idle: 'Not trained', training: 'Training…', completed: 'Trained', failed: 'Failed', interrupted: 'Interrupted', error: 'Failed',
};

function ModelRow({ m }: { m: ModelInfo }) {
  return (
    <SettingRow
      title={m.name}
      description={[m.description, m.usage].filter(Boolean).join(' · ')}
      actions={<Chip size="sm" tone={m.status === 'available' ? 'success' : 'muted'}>{m.status === 'available' ? m.latency ?? 'Ready' : 'Unavailable'}</Chip>}
    />
  );
}

function DataQuality({ notify }: { notify: Notify }) {
  const [report, setReport] = useState<DataQualityReport | null>(null);
  const [running, setRunning] = useState(false);
  const [all, setAll] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      setReport(await t.getDataQualityReport(24, 5));
    } catch (e) {
      notify(`Audit failed: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setRunning(false);
    }
  };
  const rows = report ? [...report.topic_reports].sort((a, b) => a.pass_rate - b.pass_rate) : [];
  const pct = report ? Math.round(report.overall_pass_rate * 100) : 0;
  return (
    <Panel
      title="Data Quality Audit"
      headerAside={
        <Button variant="secondary" iconStart={<Icon name="Play" size="sm" />} busy={running} onClick={run}>
          {running ? 'Running audit…' : 'Run Audit'}
        </Button>
      }
    >
      {report ? (
        <Stack gap="md">
          <Meter
            label="Approved articles that match their topic"
            value={pct}
            valueText={`${pct}% pass`}
            tone={report.overall_pass_rate >= 0.8 ? 'success' : report.overall_pass_rate >= 0.6 ? 'warning' : 'error'}
          />
          <Text variant="description">{fmt(report.topics_audited)} topics · {fmt(report.total_sampled)} articles sampled from the last {report.hours_checked}h</Text>
          {report.alerts.map((a) => <Banner key={a} tone="warning" icon="Warning" title="Alert" description={a} />)}
          <Stack as="ul" gap="sm" label="Audit by topic">
            {(all ? rows : rows.slice(0, AUDIT_PREVIEW)).map((r) => (
              <ActivityRow
                key={r.topic}
                as="li"
                primary={r.topic}
                secondary={`${r.passed} of ${r.sampled} passed · ${Math.round(r.pass_rate * 100)}%`}
                dotTone={r.pass_rate >= 0.8 ? 'live' : 'pending'}
                dotLabel={r.pass_rate >= 0.8 ? 'Good' : 'Needs a look'}
              />
            ))}
          </Stack>
          {rows.length > AUDIT_PREVIEW && (
            <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)}>{all ? 'Show less' : `Show all ${rows.length} topics`}</Button>
          )}
        </Stack>
      ) : (
        <EmptyState icon="CheckCircle">
          {running ? 'Checking approved articles from the last 24h…' : 'Spot-checks approved articles against their topics using LLM verification. Click Run Audit to check the last 24h.'}
        </EmptyState>
      )}
    </Panel>
  );
}

interface Props {
  /** Load when the tab is first shown. */
  active: boolean;
  notify: Notify;
  askConfirm: (c: Confirm) => void;
}

export function AiPipeline({ active, notify, askConfirm }: Props) {
  const d = useTraining(active);
  const [page, setPage] = useState(1);
  const [savingMode, setSavingMode] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [triage, setTriage] = useState(false);

  if (d.loading) {
    return (
      <Stack gap="lg">
        <Text>Loading training status…</Text>
        <Skeleton variant="block" />
        <Grid columns={2} gap="md">
          <Skeleton variant="block" />
          <Skeleton variant="block" />
        </Grid>
      </Stack>
    );
  }

  const modeInfo = INFERENCE_MODES.find((m) => m.value === d.mode) ?? INFERENCE_MODES[1];
  const totalSamples = d.topics.reduce((s, x) => s + x.total_samples, 0);
  const ready = d.topics.filter(fullyReady);
  const onLlm = d.topics.filter(collecting);
  const deployed = d.runs.find((r) => r.status === 'deployed');
  const fb = d.feedback?.totals ?? { total_feedback: 0, more_like_this: 0, less_like_this: 0 };
  const pageCount = Math.max(1, Math.ceil(d.topics.length / PAGE_SIZE));

  const setMode = async (mode: InferenceMode) => {
    setSavingMode(true);
    try {
      await t.setInferenceMode(mode);
      d.setData((x) => ({ ...x, mode }));
      notify(`Inference mode set to ${INFERENCE_MODES.find((m) => m.value === mode)?.label}`, 'Cpu');
    } catch (e) {
      const msg = errorText(e);
      notify(mode === 'local' && msg.includes('missing models') ? `${msg}. Train local models first or use Hybrid.` : msg, 'WarningCircle');
    } finally {
      setSavingMode(false);
    }
  };

  const act = async (key: string, fn: () => Promise<string | undefined>) => {
    setBusy(key);
    const msg = await d.run(fn);
    setBusy(null);
    if (msg) notify(msg);
  };

  const finetune = (topic?: string) =>
    act(`finetune:${topic ?? 'all'}`, async () => {
      const r = await t.triggerFinetuning(topic ? [topic] : undefined);
      return `Fine-tuning started (run ${r.run_id}): ${fmt(r.sample_count)} samples, ${r.topics_included.join(', ')}`;
    });
  const trainRelevance = () =>
    act('relevance', async () => {
      const r = await t.triggerRelevanceTraining();
      return `${r.message} (${fmt(r.feedback_count)} feedback samples)`;
    });
  const autoInit = () =>
    act('autoinit', async () => {
      let added = 0;
      const withArticles = d.topics.filter((x) => x.article_count > 0);
      for (const x of withArticles) added += (await t.initializeRelevanceFeedback(x.topic, FEEDBACK_GOAL)).total_added;
      return added > 0
        ? `Added ${fmt(added)} feedback entries from scored articles across ${withArticles.length} topics`
        : 'Nothing to add: every scored article already has feedback';
    });
  const deploy = (runId: string) =>
    act(`deploy:${runId}`, async () => {
      await t.deployModel(runId);
      return `Run ${runId} deployed`;
    });

  return (
    <Stack gap="lg">
      {d.error && (
        <Banner tone="error" icon="WarningCircle" title="Something went wrong" description={d.error} action={<Button variant="secondary" onClick={d.clearError}>Dismiss</Button>} />
      )}

      <Panel
        title={
          <Stack direction="row" gap="sm" wrap={false}>
            <span>Inference Mode</span>
            <IconButton
              icon={<Icon name="Info" size="sm" />}
              label={`Local Only uses DeBERTa, Phi-3 and Qwen and needs ${DEBERTA_THRESHOLD}+ samples per topic. Hybrid uses local models when confident (DeBERTa above ${CONFIDENCE_OK * 100}%) and falls back to the LLM otherwise. External uses the LLM for everything. Samples are collected automatically whenever the LLM processes articles.`}
            />
          </Stack>
        }
        description={modeInfo.description}
        headerAside={
          <SegmentedControl
            label="Inference mode"
            value={d.mode}
            onValueChange={(v) => !savingMode && void setMode(v as InferenceMode)}
            options={INFERENCE_MODES.map((m) => ({ value: m.value, label: m.label }))}
          />
        }
      >
        {d.local && (
          <Stack direction="row" gap="sm">
            {d.local.available ? (
              <Chip size="sm" tone="success" icon={<Icon name="CheckCircle" size="sm" />}>Local models ready</Chip>
            ) : (
              <Chip size="sm" tone="warning" icon={<Icon name="Warning" size="sm" />}>{d.local.missing.length} local model(s) unavailable</Chip>
            )}
            {d.local.external_llm_available ? (
              <Chip size="sm" tone="success" icon={<Icon name="CheckCircle" size="sm" />}>External LLM ready</Chip>
            ) : (
              <Chip size="sm" tone="warning" icon={<Icon name="Warning" size="sm" />}>No API keys configured</Chip>
            )}
          </Stack>
        )}
      </Panel>

      <Grid as="ul" columns={4} gap="sm" label="Training overview">
        <Stat as="li" surface="panel" label="Total samples" value={fmt(totalSamples)} meta="Labelled by the LLM so far" />
        <Stat as="li" surface="panel" label="Topics" value={fmt(d.topics.length)} meta="With training data" />
        <Stat as="li" surface="panel" label="DeBERTa ready" value={fmt(ready.length)} meta={`${fmt(DEBERTA_THRESHOLD)}+ samples on every field`} />
        <Stat as="li" surface="panel" label="Collecting" value={fmt(onLlm.length)} meta="Still on the LLM" />
      </Grid>

      <DataQuality notify={notify} />

      <Panel
        title={<><Icon name="ArrowsClockwise" size="sm" /> Article Processing Pipeline</>}
        headerAside={<IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh training status" onClick={() => void d.reload()} />}
      >
        <Stack gap="md">
          <PipelineFlow label="Article processing pipeline" steps={pipelineSteps(d.mode)} />
          <Stack direction="row" gap="sm">
            <Chip size="sm" tone="accent">{modeInfo.label}</Chip>
            {d.pipeline && (
              <Text as="span">
                Today: <strong>{fmt(d.pipeline.articles_today)}</strong> articles · <strong>{fmt(d.pipeline.relevance_passed)}</strong> passed relevance ·{' '}
                <strong>{fmt(d.pipeline.topics_active)}</strong> topics active
              </Text>
            )}
            <Chip size="sm" tone="neutral">{fmt(onLlm.length)} topics using {d.mode === 'local' ? 'Qwen' : 'the LLM'}</Chip>
          </Stack>
        </Stack>
      </Panel>

      <Grid columns={2} gap="md">
        <Panel title="Training Status">
          <Stack gap="md">
            <Stack direction="row" gap="sm">
              <Chip size="sm" tone={d.system?.hybrid_enrichment?.deberta_available ? 'success' : 'muted'} icon={<Icon name={d.system?.hybrid_enrichment?.deberta_available ? 'Check' : 'Minus'} size="sm" />}>Enrichment</Chip>
              <Chip size="sm" tone={d.system?.finetuning?.current_model_exists ? 'success' : 'muted'} icon={<Icon name={d.system?.finetuning?.current_model_exists ? 'Check' : 'Minus'} size="sm" />}>Relevance</Chip>
              <Chip size="sm" tone="neutral">{fmt(ready.length)} topics on DeBERTa</Chip>
              <Chip size="sm" tone="neutral">{fmt(onLlm.length)} on the LLM</Chip>
            </Stack>
            {deployed && (
              <Text>
                {fmt(deployed.sample_count ?? 0)} samples · {deployed.topics_included?.length ?? 0} topic(s) · deployed{' '}
                {deployed.completed_at ? new Date(deployed.completed_at).toLocaleDateString('en-GB') : ''}
                {deployed.topics_included?.length ? ` — ${deployed.topics_included.join(', ')}` : ''}
              </Text>
            )}
            <SettingRow title="DeBERTa Confidence (24h)">
              {d.confidence && Object.keys(d.confidence.stats).length > 0 ? (
                <Stack gap="sm">
                  {Object.entries(d.confidence.stats).map(([topic, s]) => (
                    <LabeledMeter key={topic} label={topic} value={Math.round(s.overall_avg * 100)} valueText={`${Math.round(s.overall_avg * 100)}%`} tone={s.overall_avg >= CONFIDENCE_OK ? 'success' : 'warning'} />
                  ))}
                </Stack>
              ) : (
                <Text>No data yet — appears when DeBERTa processes articles</Text>
              )}
            </SettingRow>
            <SettingRow title="Relevance Scoring (24h)">
              {d.relevance && Object.keys(d.relevance.stats).length > 0 ? (
                <Stack gap="sm">
                  {Object.entries(d.relevance.stats).map(([topic, s]) => (
                    <LabeledMeter key={topic} label={topic} value={Math.round(s.avg_score * 100)} valueText={`${Math.round(s.avg_score * 100)}%`} />
                  ))}
                </Stack>
              ) : (
                <Text>No relevance scores in the last 24h</Text>
              )}
            </SettingRow>
            <SettingRow
              title="Relevance triage"
              description={fb.total_feedback >= FEEDBACK_GOAL ? 'Ready to train' : `${fmt(FEEDBACK_GOAL - fb.total_feedback)} more to begin training · ${fmt(FEEDBACK_GOAL)} min`}
            >
              <Stack gap="md">
                <Grid columns={3} stackAt="never" gap="sm">
                  <Stat size="compact" surface="panel" label="Total" value={fmt(fb.total_feedback)} />
                  <Stat size="compact" surface="panel" label="Relevant" value={fmt(fb.more_like_this)} tone="success" />
                  <Stat size="compact" surface="panel" label="Not relevant" value={fmt(fb.less_like_this)} tone="error" />
                </Grid>
                <Meter label="Feedback toward training" progress value={Math.min(fb.total_feedback, FEEDBACK_GOAL)} max={FEEDBACK_GOAL} valueText={`${fmt(fb.total_feedback)} of ${fmt(FEEDBACK_GOAL)}`} />
                {d.feedback && d.feedback.by_topic.length > 0 && (
                  <LineItems
                    label="Feedback by topic"
                    items={d.feedback.by_topic.slice(0, 5).map((x) => ({ id: x.topic, label: x.topic, amount: `+${fmt(x.more_like_this)} / −${fmt(x.less_like_this)}` }))}
                  />
                )}
                <Stack direction="row" gap="sm">
                  <Button iconStart={<Icon name="Play" size="sm" />} onClick={() => setTriage(true)}>Start Triage</Button>
                  {fb.total_feedback < FEEDBACK_GOAL && (
                    <Button variant="onSurface" iconStart={<Icon name="Lightning" size="sm" />} busy={busy === 'autoinit'} onClick={() => void autoInit()}>
                      Auto-Initialize
                    </Button>
                  )}
                  <Button
                    variant="onSurface"
                    iconStart={<Icon name="Brain" size="sm" />}
                    disabled={fb.total_feedback < FEEDBACK_GOAL}
                    busy={busy === 'relevance'}
                    onClick={() => void trainRelevance()}
                  >
                    Train Relevance Model
                  </Button>
                </Stack>
              </Stack>
            </SettingRow>
          </Stack>
        </Panel>

        <Panel title="Model Usage">
          <Stack gap="md">
            <Eyebrow as="h3">Local models (free)</Eyebrow>
            {d.models?.local_models.length ? (
              <Stack as="ul" gap="sm" label="Local models">
                {d.models.local_models.map((m) => <li key={m.name}><ModelRow m={m} /></li>)}
              </Stack>
            ) : (
              <Text>Model list unavailable.</Text>
            )}
            <Eyebrow as="h3">External LLMs (fallback)</Eyebrow>
            {d.models?.external_models.length ? (
              <Stack as="ul" gap="sm" label="External LLMs">
                {d.models.external_models.map((m) => <li key={m.name}><ModelRow m={m} /></li>)}
              </Stack>
            ) : (
              <Text>Model list unavailable.</Text>
            )}
            {d.savings && (
              <>
                <Eyebrow as="h3">Cost savings ({d.savings.window_hours}h)</Eyebrow>
                <Meter label="Articles processed free by local models" value={Math.round(d.savings.local_percentage)} valueText={`${Math.round(d.savings.local_percentage)}% free`} tone="success" />
                <LineItems
                  label={`Processing split (${d.savings.window_hours}h)`}
                  items={[
                    { id: 'local', label: 'Local', amount: fmt(d.savings.local_model_count) },
                    { id: 'llm', label: 'LLM', amount: fmt(d.savings.llm_fallback_count) },
                    ...(d.savings.savings_amount > 0 ? [{ id: 'saved', label: 'Saved', amount: `~$${d.savings.savings_amount.toFixed(2)}` }] : []),
                  ]}
                />
              </>
            )}
            <Banner tone="info" icon="Info" title="When the LLM is used" description={`LLM fallback only when DeBERTa confidence is below ${CONFIDENCE_OK} or a local model is unavailable.`} />
          </Stack>
        </Panel>
      </Grid>

      <Panel title={`Topics (${d.topics.length})`}>
        {d.topics.length === 0 ? (
          <EmptyState icon="Brain" title="No training data yet">Samples appear here as the LLM processes articles.</EmptyState>
        ) : (
          <Stack gap="md">
            <Grid as="ul" columns={3} gap="sm" label="Topics">
              {d.topics.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((x) => (
                <li key={x.topic}>
                  <TopicTrainingCard topic={x} busy={busy !== null} onFinetune={(tp) => void finetune(tp)} onDeploy={(id) => void deploy(id)} onChanged={() => void d.reload()} />
                </li>
              ))}
            </Grid>
            {pageCount > 1 && <Pagination page={page} pageCount={pageCount} onPageChange={setPage} label="Topics pages" />}
          </Stack>
        )}
      </Panel>

      {d.preclassifiers.length > 0 && (
        <Panel title={`Preclassifiers (${d.preclassifiers.length})`}>
          <Grid as="ul" columns={2} gap="sm" label="Preclassifiers">
            {d.preclassifiers.map((p) => {
              const counts = Object.entries(p.category_counts).sort((a, b) => a[1] - b[1]);
              return (
                <li key={p.id}>
                  <SettingRow
                    title={p.display_name}
                    description={p.description}
                    actionsPlacement="title"
                    actions={
                      <Chip size="sm" tone={p.training_status === 'training' ? 'info' : p.model_available ? 'success' : p.training_status === 'failed' || p.training_status === 'error' ? 'error' : 'muted'}>
                        {p.model_available && p.training_status !== 'training' ? 'Active' : PC_LABEL[p.training_status] ?? p.training_status}
                      </Chip>
                    }
                  >
                    <Stack gap="sm">
                      <Text variant="hint">
                        {fmt(p.total_samples)} samples · {p.categories_ready}/{p.categories_total} categories ready
                        {p.last_trained ? ` · trained ${new Date(p.last_trained).toLocaleDateString('en-GB')}` : ''}
                      </Text>
                      {counts.slice(0, 4).map(([cat, n]) => (
                        <LabeledMeter key={cat} label={cat} value={Math.min(n, p.min_samples_per_category)} max={p.min_samples_per_category} valueText={`${fmt(n)} / ${fmt(p.min_samples_per_category)}`} tone={n >= p.min_samples_per_category ? 'success' : 'neutral'} />
                      ))}
                      {counts.length > 4 && <Text variant="hint">Showing the 4 categories furthest from ready, of {counts.length}.</Text>}
                      {p.error && <Text tone="error">{p.error}</Text>}
                      <Stack direction="row" gap="sm">
                        <Button
                          size="sm"
                          iconStart={<Icon name="Brain" size="sm" />}
                          disabled={p.training_status === 'training' || busy !== null}
                          busy={busy === `pc:${p.id}`}
                          onClick={() => void act(`pc:${p.id}`, async () => (await t.trainPreclassifier(p.id)).message)}
                        >
                          Trigger Finetuning
                        </Button>
                        {(p.model_available || p.training_status === 'completed') && (
                          <Button
                            size="sm"
                            variant="secondary"
                            iconStart={<Icon name="ArrowClockwise" size="sm" />}
                            busy={busy === `reload:${p.id}`}
                            onClick={() => void act(`reload:${p.id}`, async () => (await t.reloadPreclassifier(p.id), `${p.display_name} reloaded`))}
                          >
                            Reload Model
                          </Button>
                        )}
                      </Stack>
                      <Text variant="hint">Needs {fmt(p.min_samples_per_category)}+ LLM samples per category to train.</Text>
                    </Stack>
                  </SettingRow>
                </li>
              );
            })}
          </Grid>
        </Panel>
      )}

      <Panel title="Training Runs">
        {d.runs.length === 0 ? (
          <EmptyState icon="Brain">No training runs yet.</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Training runs">
            {d.runs.map((r) => (
              <li key={r.run_id}>
                <SettingRow
                  title={r.run_id}
                  description={[
                    `${fmt(r.sample_count ?? 0)} samples · ${r.topics_included?.length ?? 0} topic(s)`,
                    r.metrics?.eval_accuracy != null ? `${Math.round(r.metrics.eval_accuracy * 100)}% accuracy` : null,
                    r.completed_at ? new Date(r.completed_at).toLocaleString('en-GB') : null,
                    r.error_message,
                  ].filter(Boolean).join(' · ')}
                  actions={
                    <>
                      <Chip size="sm" tone={RUN_TONE[r.status]}>{r.status}</Chip>
                      {r.status === 'completed' && (
                        <Button size="sm" variant="secondary" busy={busy === `deploy:${r.run_id}`} onClick={() => void deploy(r.run_id)}>Deploy</Button>
                      )}
                      {['failed', 'deployed', 'completed'].includes(r.status) && (
                        <IconButton
                          icon={<Icon name="Trash" size="sm" />}
                          label={`Delete run ${r.run_id}`}
                          tone="danger"
                          onClick={() =>
                            askConfirm({
                              title: 'Delete training run?',
                              message: `Run ${r.run_id} and its model files will be deleted. This can’t be undone.`,
                              action: 'Delete run',
                              onConfirm: () => void act(`delete:${r.run_id}`, async () => (await t.deleteRun(r.run_id), `Run ${r.run_id} deleted`)),
                            })
                          }
                        />
                      )}
                    </>
                  }
                />
              </li>
            ))}
          </Stack>
        )}
      </Panel>

      <RelevanceTriageDialog
        open={triage}
        onOpenChange={setTriage}
        startTotal={fb.total_feedback}
        onTrain={() => void trainRelevance()}
        onClosed={() => void d.reload()}
      />
    </Stack>
  );
}
