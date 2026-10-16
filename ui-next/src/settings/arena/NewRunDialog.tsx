import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, MultiSelect, Select, SettingRow, Skeleton, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell/api';
import { getTopicFields, sampleArticles, startRun, type ArenaModel, type SampleArticle, type TopicFields } from './api';

/*
 * Create a bias evaluation, as the old page's form: a benchmark model, one to five models to compare
 * with it, how many rounds and articles, and the topic whose fields the models fill in. Starting it
 * runs in the background on the server and costs money, so it asks first and says how many model
 * calls it makes.
 */

const ROUNDS = [
  { value: '1', label: '1 round: a single evaluation' },
  { value: '2', label: '2 rounds: checks consistency' },
  { value: '3', label: '3 rounds: some drift tracking' },
  { value: '4', label: '4 rounds: more drift tracking' },
  { value: '5', label: '5 rounds: full drift analysis' },
];
const MAX_COMPARE = 5;

export function NewRunDialog({ open, onOpenChange, models, topics, notify, askConfirm, onStarted }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  models: ArenaModel[];
  topics: string[];
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onStarted: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [benchmark, setBenchmark] = useState('');
  const [compare, setCompare] = useState<string[]>([]);
  const [rounds, setRounds] = useState('1');
  const [count, setCount] = useState('25');
  const [topic, setTopic] = useState('');
  const [fields, setFields] = useState<TopicFields | null | 'loading' | 'failed'>(null);
  const [preview, setPreview] = useState<SampleArticle[] | null | 'loading'>(null);
  const [error, setError] = useState<string | null>(null);

  // Starts blank each time it opens, rather than showing the last evaluation's choices
  useEffect(() => {
    if (!open) return;
    setName('');
    setDescription('');
    setBenchmark('');
    setCompare([]);
    setRounds('1');
    setCount('25');
    setTopic('');
    setFields(null);
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!topic) {
      setFields(null);
      return;
    }
    let live = true;
    setFields('loading');
    getTopicFields(topic).then((f) => live && setFields(f), () => live && setFields('failed'));
    return () => {
      live = false;
    };
  }, [topic]);

  const n = Math.max(1, Math.min(100, Number(count) || 0));
  const roundsN = Number(rounds);
  // The benchmark plus each compared model reads every article once per round
  const calls = (compare.length + 1) * n * roundsN;
  const label = (id: string) => models.find((m) => m.name === id)?.display_name ?? id;
  const ready = name.trim() && benchmark && compare.length >= 1 && compare.length <= MAX_COMPARE && topic;

  const start = () => {
    if (!ready) return;
    askConfirm({
      title: 'Start this bias evaluation?',
      message: `${label(benchmark)} (benchmark) and ${compare.map(label).join(', ')} each read ${n} articles from ${topic}, ${roundsN} time${roundsN === 1 ? '' : 's'}: about ${calls.toLocaleString()} model calls, charged by each provider. It runs in the background; you’ll be notified when it finishes.`,
      action: 'Start evaluation',
      onConfirm: async () => {
        try {
          await startRun({ name: name.trim(), description: description.trim(), benchmark_model: benchmark, selected_models: compare, article_count: n, rounds: roundsN, topic });
          notify('Bias evaluation started. You’ll be notified when it finishes.');
          onOpenChange(false);
          onStarted();
        } catch (e) {
          setError(`Not started: ${errorText(e)}`);
        }
      },
    });
  };

  const showPreview = async () => {
    setPreview('loading');
    try {
      setPreview(await sampleArticles(n, topic || null));
    } catch (e) {
      setPreview(null);
      setError(`The preview didn’t load: ${errorText(e)}`);
    }
  };

  const modelOptions = models.map((m) => ({ value: m.name, label: m.display_name }));
  const fieldList = fields && typeof fields === 'object'
    ? ([['Categories', fields.categories], ['Sentiments', fields.sentiments], ['Future signals', fields.future_signals], ['Driver types', fields.driver_types]] as const).filter(([, v]) => v.length)
    : [];

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        size="lg"
        title="New bias evaluation"
        description="Compare how different AI models label the same articles. The benchmark is the reference the others are measured against."
        footer={
          <>
            <Button variant="ghost" size="lg" disabled={!topic || preview === 'loading'} onClick={() => void showPreview()}>Preview the articles</Button>
            <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
            <Button size="lg" disabled={!ready} onClick={start}>Start evaluation…</Button>
          </>
        }
      >
        <Stack gap="md">
          <TextField label="Evaluation name" placeholder="e.g. AI news bias test, October" value={name} onChange={setName} maxLength={100} />
          <TextArea label="Description (optional)" rows={2} value={description} onChange={setDescription} />
          <Select
            label="Benchmark model"
            hint="The reference point the other models are compared with."
            placeholder="Pick the benchmark"
            fullWidth
            options={modelOptions}
            value={benchmark || undefined}
            onValueChange={(v) => {
              setBenchmark(v);
              setCompare((c) => c.filter((x) => x !== v));
            }}
          />
          <MultiSelect
            label={`Models to compare (1 to ${MAX_COMPARE})`}
            placeholder="Pick the models to compare"
            options={modelOptions.filter((m) => m.value !== benchmark)}
            value={compare}
            onValueChange={(v) => setCompare(v.slice(0, MAX_COMPARE))}
          />
          {compare.length >= MAX_COMPARE && <Text variant="caption">{`That’s the most: ${MAX_COMPARE} models besides the benchmark.`}</Text>}
          <Select label="Rounds" hint="More rounds show how consistent each model is, and whether its answers drift." fullWidth options={ROUNDS} value={rounds} onValueChange={setRounds} />
          <TextField label="Number of articles" type="number" min={1} max={100} value={count} onChange={setCount} hint="Random articles from the topic, 1 to 100." />
          <Select label="Topic" hint="The models fill in this topic’s fields for each article." placeholder="Pick a topic" fullWidth options={topics.map((t) => ({ value: t, label: t }))} value={topic || undefined} onValueChange={setTopic} />
          {fields === 'loading' && <Skeleton variant="text" lines={2} />}
          {fields === 'failed' && <Text variant="caption" tone="error">This topic’s fields didn’t load.</Text>}
          {fields && typeof fields === 'object' && (
            fieldList.length ? (
              <Stack gap="sm">
                {fieldList.map(([k, v]) => (
                  <SettingRow key={k} title={k} description={v.length > 5 ? `${v.slice(0, 5).join(', ')} and ${v.length - 5} more` : v.join(', ')} />
                ))}
              </Stack>
            ) : <Text variant="caption">This topic has no specific field lists; the models use the general ones.</Text>
          )}
          {ready && <Text variant="caption">{`About ${calls.toLocaleString()} model calls in all.`}</Text>}
          {error && <Banner tone="error" title="Something went wrong" description={error} />}
        </Stack>
      </Dialog>

      <Dialog
        open={preview !== null}
        onOpenChange={(o) => !o && setPreview(null)}
        size="lg"
        title="Article preview"
        description={Array.isArray(preview) ? `A random sample like the one the evaluation will draw: ${preview.length} articles. The evaluation draws its own sample when it starts.` : undefined}
      >
        {preview === 'loading' ? <Skeleton variant="text" lines={8} /> : Array.isArray(preview) && (
          preview.length === 0 ? <Text>No articles found for this topic.</Text> : (
            <Stack as="ul" gap="sm" label="Sample articles">
              {preview.map((a, i) => (
                <li key={a.uri ?? i}>
                  <SettingRow
                    title={a.title}
                    description={`${[a.news_source, a.topic, a.category || 'no category'].filter(Boolean).join(' · ')}${a.summary ? ` — ${a.summary.slice(0, 200)}${a.summary.length > 200 ? '…' : ''}` : ''}`}
                  />
                </li>
              ))}
            </Stack>
          )
        )}
      </Dialog>
    </>
  );
}
