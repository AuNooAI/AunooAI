import { useState } from 'react';
import {
  Button, Chip, Dialog, DialogClose, Icon, Meter, Select, SettingRow, Skeleton, Stack, Table, Text,
} from '@aunoo/ui';
import { getFieldDistribution, initializeTopicSamples, type FieldDistribution, type TopicTrainingStatus } from '@monolith/trainingApi';
import { errorText } from '../../shell';
import { fmt } from '../lib';
import { DEBERTA_THRESHOLD, topicProgress } from '../useTraining';

/** A Meter's label is for screen readers only; show it as a line above the bar too. */
export function LabeledMeter(props: React.ComponentProps<typeof Meter>) {
  return (
    <div>
      <Text variant="hint">{props.label}</Text>
      <Meter {...props} />
    </div>
  );
}

const FIELD_LABELS: Record<string, string> = {
  sentiment: 'Sentiment',
  time_to_impact: 'Time to Impact',
  driver_type: 'Driver Type',
  future_signal: 'Future Signal',
};
const fieldLabel = (f: string) => FIELD_LABELS[f] ?? f.replace(/_/g, ' ');
/** Initialise Samples asks the backend to label this many existing articles. */
const INIT_LIMIT = 100;

type Tone = 'success' | 'info' | 'warning' | 'error' | 'muted';

function statusOf(t: TopicTrainingStatus): { label: string; tone: Tone; caption: string } {
  const fields = Object.keys(t.field_counts);
  const ready = fields.filter((f) => t.field_counts[f] >= DEBERTA_THRESHOLD).length;
  const allReady = fields.length > 0 && ready === fields.length;
  switch (t.latest_run?.status) {
    case 'deployed':
      return { label: 'Deployed', tone: 'success', caption: 'DeBERTa active' };
    case 'pending':
    case 'running':
    case 'exporting':
    case 'training':
      return { label: 'Training…', tone: 'info', caption: 'Fine-tuning in progress' };
    case 'completed':
      return { label: 'Trained', tone: 'info', caption: 'Trained, not deployed' };
    case 'failed':
      return { label: 'Failed', tone: 'error', caption: 'Last training run failed' };
  }
  if (allReady) return { label: 'Ready to Train', tone: 'warning', caption: 'Ready for fine-tuning' };
  return { label: `${ready}/${fields.length} ready`, tone: 'muted', caption: 'Collecting samples' };
}

interface Props {
  topic: TopicTrainingStatus;
  onFinetune: (topic: string) => void;
  onDeploy: (runId: string) => void;
  busy: boolean;
  /** Reload after samples were initialised. */
  onChanged: () => void;
}

/** One topic's progress toward local (DeBERTa) models, with its field breakdown and training actions. */
export function TopicTrainingCard({ topic: t, onFinetune, onDeploy, busy, onChanged }: Props) {
  const [field, setField] = useState('');
  const [dist, setDist] = useState<FieldDistribution | null | 'loading' | { error: string }>(null);
  const [initMsg, setInitMsg] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [open, setOpen] = useState(false);
  const s = statusOf(t);
  const progress = topicProgress(t);
  const fields = Object.keys(t.field_counts);
  const allReady = fields.length > 0 && fields.every((f) => t.field_counts[f] >= DEBERTA_THRESHOLD);

  const showField = async (f: string) => {
    setField(f);
    setDist('loading');
    try {
      setDist(await getFieldDistribution(t.topic, f));
    } catch (e) {
      setDist({ error: errorText(e) });
    }
  };

  const initialize = async () => {
    setInitializing(true);
    try {
      const r = await initializeTopicSamples(t.topic, INIT_LIMIT);
      setInitMsg(`${fmt(r.bootstrapped)} samples initialised`);
      onChanged();
    } catch (e) {
      setInitMsg(`Couldn’t initialise: ${errorText(e)}`);
    } finally {
      setInitializing(false);
    }
  };

  return (
    <SettingRow
      title={t.topic}
      description={`${fmt(t.total_samples)} samples · ${fmt(t.article_count)} articles`}
      actions={<Chip size="sm" tone={s.tone}>{s.label}</Chip>}
      actionsPlacement="title"
    >
      <Stack gap="sm">
        <Meter
          label={`${t.topic}: ${s.caption}`}
          value={progress}
          valueText={`${progress}%`}
          tone={progress >= 100 ? 'success' : progress >= 50 ? 'warning' : 'neutral'}
        />
        <Stack direction="row" justify="between" gap="sm">
          <Text>{s.caption}</Text>
          <Button variant="ghost" size="sm" iconEnd={<Icon name="CaretRight" size="sm" />} aria-label={`Fields and training for ${t.topic}`} onClick={() => setOpen(true)}>
            Fields
          </Button>
        </Stack>
        <Dialog
          open={open}
          onOpenChange={setOpen}
          title={t.topic}
          description={`${fmt(t.total_samples)} samples · ${fmt(t.article_count)} articles · ${s.label}`}
          footer={
            <DialogClose>
              <Button variant="secondary" size="lg">Close</Button>
            </DialogClose>
          }
        >
            <Stack gap="md">
              <Table
                caption={`${t.topic} training fields`}
                hideCaption
                rowKey={(f) => f}
                rows={fields}
                columns={[
                  { key: 'field', header: 'Field', rowHeader: true, render: (f) => fieldLabel(f) },
                  {
                    key: 'samples',
                    header: 'Samples',
                    align: 'end',
                    render: (f) => {
                      const n = t.field_counts[f];
                      return n >= DEBERTA_THRESHOLD ? fmt(n) : `${fmt(n)} (+${fmt(DEBERTA_THRESHOLD - n)})`;
                    },
                  },
                  { key: 'model', header: 'Model', render: (f) => (t.field_counts[f] >= DEBERTA_THRESHOLD ? 'DeBERTa' : 'LLM') },
                ]}
              />
              <Select
                label="Value spread for a field"
                fullWidth
                placeholder="Choose a field…"
                options={fields.map((f) => ({ value: f, label: fieldLabel(f) }))}
                value={field}
                onValueChange={(f) => void showField(f)}
              />
              {dist === 'loading' && <Skeleton variant="block" />}
              {dist && typeof dist === 'object' && 'error' in dist && <Text tone="error">{dist.error}</Text>}
              {dist && typeof dist === 'object' && 'distribution' in dist && (
                <Stack gap="sm">
                  <Text variant="hint">
                    {fmt(dist.unique_values)} unique values{dist.min_per_class_met ? '' : ' · some values have fewer than 50 samples'}
                  </Text>
                  {dist.distribution.slice(0, 5).map((d) => (
                    <LabeledMeter key={d.value} label={d.value} value={d.percentage} valueText={`${fmt(d.count)} · ${Math.round(d.percentage)}%`} />
                  ))}
                </Stack>
              )}
              <Stack direction="row" gap="sm">
                {allReady && (
                  <Button size="sm" iconStart={<Icon name="Brain" size="sm" />} disabled={busy} onClick={() => onFinetune(t.topic)}>
                    Trigger Finetuning
                  </Button>
                )}
                {t.latest_run?.status === 'completed' && (
                  <Button size="sm" variant="secondary" iconStart={<Icon name="UploadSimple" size="sm" />} disabled={busy} onClick={() => onDeploy(t.latest_run!.run_id)}>
                    Deploy
                  </Button>
                )}
                {!allReady && t.article_count > 0 && t.total_samples === 0 && (
                  <Button size="sm" variant="secondary" iconStart={<Icon name="Lightning" size="sm" />} busy={initializing} onClick={initialize}>
                    Initialize Samples
                  </Button>
                )}
              </Stack>
              {initMsg && <Text variant="hint">{initMsg}</Text>}
              {!allReady && !(t.article_count > 0 && t.total_samples === 0) && (
                <Text variant="hint">Collecting samples using the LLM. DeBERTa takes over at {fmt(DEBERTA_THRESHOLD)} samples per field.</Text>
              )}
            </Stack>
        </Dialog>
      </Stack>
    </SettingRow>
  );
}
