import { useEffect, useState } from 'react';
import {
  Banner, Button, Checkbox, Chip, Dialog, Grid, Meter, Panel, Select, Stack, Stepper, TagInput, Text, TextArea, TextField,
} from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { useJob } from '../lib/jobs';

const STEPS = [
  { id: 'framing', label: 'Framing' },
  { id: 'build', label: 'Build' },
  { id: 'overlay', label: 'Overlay' },
  { id: 'delivery', label: 'Delivery' },
];
const HORIZONS = ['h1', 'h2', 'h3', 'h1_h2', 'h2_h3', 'h1_h3'].map((h) => ({ value: h, label: h.toUpperCase().replace('_', '–') }));
const CADENCES = [
  { value: 'none', label: 'None' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
];
const JOB_URL = (id: string) => `/api/forecast/assessment/job/${id}`;

interface DeckScenario {
  deck_scenario_name: string;
  horizon: string;
  consensus_pct: number;
  primary_signal: string;
  minority_view?: string;
  decision_fork?: { favorable?: string; adverse?: string };
  action_windows?: { '0_6_months'?: string; '6_18_months'?: string; '18_plus_months'?: string };
}
interface Overlay {
  topic: string;
  deck_scenarios: Record<string, DeckScenario>;
  [k: string]: unknown;
}
interface Lifecycle {
  topic: string;
  display_name?: string | null;
  description?: string | null;
  owner?: string | null;
  tags?: string[] | null;
  source_topics?: string[] | null;
  status?: string;
  assessment_id?: string | null;
  assessed_at?: string | null;
  cadence?: string | null;
  recipient_email?: string | null;
}

/** Saved per topic so closing the dialog mid-build resumes where it was (the old wizard lost the job). */
interface Saved {
  step: number;
  buildTask?: string;
  overlayTask?: string;
}
const storeKey = (t: string) => `addTopicWizard:${t}`;
const loadSaved = (t: string): Saved | null => {
  try {
    return JSON.parse(localStorage.getItem(storeKey(t)) ?? 'null');
  } catch {
    return null;
  }
};
const save = (t: string, s: Saved) => {
  try {
    localStorage.setItem(storeKey(t), JSON.stringify(s));
  } catch {
    // per visit only
  }
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Resume or start on an existing topic (e.g. a promoted candidate at the overlay step). */
  initialTopic?: string;
  initialStep?: number;
  notify: (m: string) => void;
  /** The topic is active: go to its Forecast Tracker. */
  onCompleted: (topic: string) => void;
}

/** Add a tracked topic: framing → build the forecast → review the deck overlay → delivery. */
export function AddTopicWizard({ open, onOpenChange, initialTopic, initialStep, notify, onCompleted }: Props) {
  const [step, setStep] = useState(0);
  const [topic, setTopic] = useState('');
  const [display, setDisplay] = useState('');
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [available, setAvailable] = useState<{ topic: string; count: number }[]>([]);
  const [suggested, setSuggested] = useState<{ topic: string; total: number }[]>([]);
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [cadence, setCadence] = useState('none');
  const [recipient, setRecipient] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const build = useJob(2000);
  const gen = useJob(1500);

  const loadOverlay = (t: string) =>
    api<{ overlay: Overlay }>(`/api/forecast/topics/${encodeURIComponent(t)}/overlay/proposed`).then(
      (r) => setOverlay(r.overlay),
      () => setOverlay(null),
    );

  const loadLifecycle = async (t: string) => {
    const r = await api<{ topics: Lifecycle[] }>('/api/forecast/topics').catch(() => ({ topics: [] as Lifecycle[] }));
    const row = r.topics.find((x) => x.topic === t) ?? null;
    setLifecycle(row);
    return row;
  };

  // Open: a fresh wizard, or an existing topic at its saved (or requested) step
  useEffect(() => {
    if (!open) return;
    setError(null);
    build.reset();
    gen.reset();
    api<{ topics: { topic: string; count: number }[] }>('/api/forecast/topics/available').then((r) => setAvailable(r.topics ?? []), () => setAvailable([]));
    if (!initialTopic) {
      setStep(0); setTopic(''); setDisplay(''); setDescription(''); setOwner(''); setTags([]); setSources([]);
      setLifecycle(null); setOverlay(null); setCadence('none'); setRecipient('');
      return;
    }
    setTopic(initialTopic);
    const saved = loadSaved(initialTopic);
    // An explicit step (promotion → overlay) wins over a saved one; the old wizard did the reverse
    setStep(initialStep ?? saved?.step ?? 0);
    void loadLifecycle(initialTopic).then((row) => {
      if (!row) return;
      setDisplay(row.display_name ?? ''); setDescription(row.description ?? ''); setOwner(row.owner ?? '');
      setTags(row.tags ?? []); setSources(row.source_topics ?? []);
      setCadence(row.cadence ?? 'none'); setRecipient(row.recipient_email ?? '');
    });
    void loadOverlay(initialTopic);
    if (saved?.buildTask) build.watch(JOB_URL(saved.buildTask), () => void loadLifecycle(initialTopic));
    if (saved?.overlayTask) gen.watch(JOB_URL(saved.overlayTask), () => void loadOverlay(initialTopic));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialTopic, initialStep]);

  useEffect(() => {
    if (topic && open) save(topic, { ...loadSaved(topic), step });
  }, [step, topic, open]);

  // Suggestions for source topics, from the name
  useEffect(() => {
    if (topic.trim().length < 2 || step !== 0) return setSuggested([]);
    const t = window.setTimeout(() => {
      api<{ suggestions: { topic: string; total: number }[] }>(`/api/forecast/topics/suggest?q=${encodeURIComponent(topic.trim())}`).then(
        (r) => setSuggested(r.suggestions ?? []),
        () => setSuggested([]),
      );
    }, 450);
    return () => window.clearTimeout(t);
  }, [topic, step]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      const msg = errorText(e);
      setError(/403|admin/i.test(msg) ? `${msg} — this step needs an admin account.` : msg);
    } finally {
      setBusy(false);
    }
  };

  const saveFraming = () =>
    run(async () => {
      const name = topic.trim();
      await api('/api/forecast/topics', {
        method: 'POST',
        json: { topic: name, display_name: display.trim() || null, description: description.trim() || null, owner: owner.trim() || null, tags, source_topics: sources },
      });
      setTopic(name);
      await loadLifecycle(name);
      setStep(1);
    });

  const startBuild = () =>
    run(async () => {
      const r = await api<{ task_id: string }>(`/api/forecast/topics/${encodeURIComponent(topic)}/wizard/build`, { method: 'POST', json: { source_topics: sources } });
      save(topic, { ...loadSaved(topic), step: 1, buildTask: r.task_id });
      build.watch(JOB_URL(r.task_id), () => {
        save(topic, { step: 2 });
        void loadLifecycle(topic);
      });
    });

  const startOverlay = () =>
    run(async () => {
      const r = await api<{ task_id: string }>(`/api/forecast/topics/${encodeURIComponent(topic)}/overlay/generate`, { method: 'POST' });
      save(topic, { ...loadSaved(topic), step: 2, overlayTask: r.task_id });
      gen.watch(JOB_URL(r.task_id), () => void loadOverlay(topic));
    });

  const approveOverlay = () =>
    run(async () => {
      await api(`/api/forecast/topics/${encodeURIComponent(topic)}/overlay/approve`, { method: 'POST', json: { overlay } });
      setStep(3);
    });

  const finish = () =>
    run(async () => {
      // 'none' is sent too, so a cadence can be cleared (the old wizard skipped it)
      await api(`/api/forecast/topics/${encodeURIComponent(topic)}/delivery`, { method: 'PATCH', json: { cadence, recipient_email: recipient.trim() || null } });
      if (lifecycle?.status !== 'active') {
        await api(`/api/forecast/topics/${encodeURIComponent(topic)}/metadata`, { method: 'PATCH', json: { status: 'active' } });
      }
      try {
        localStorage.removeItem(storeKey(topic));
      } catch {
        // nothing saved
      }
      notify(`“${topic}” is now tracked`);
      onOpenChange(false);
      onCompleted(topic);
    });

  const setDeck = (key: string, patch: Partial<DeckScenario>) =>
    setOverlay((o) => (o ? { ...o, deck_scenarios: { ...o.deck_scenarios, [key]: { ...o.deck_scenarios[key], ...patch } } } : o));

  const building = build.state.kind === 'running';
  const generating = gen.state.kind === 'running';
  const canNext = [
    topic.trim().length > 0 && sources.length > 0,
    Boolean(lifecycle?.assessment_id) && !building,
    Boolean(overlay) && !generating,
    true,
  ][step];
  const nextLabel = ['Save & continue', 'Continue to overlay', 'Approve overlay & continue', 'Finish — activate topic'][step];
  const onNext = [saveFraming, () => setStep(2), approveOverlay, finish][step];

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={initialTopic ? `Set up “${initialTopic}”` : 'Add a tracked topic'}
      description="Four steps. The build runs on the server (about 10 minutes); you can close this and come back."
      footer={
        <>
          <Button variant="secondary" size="lg" disabled={step === 0 || busy} onClick={() => setStep((s) => s - 1)}>Back</Button>
          <Button size="lg" busy={busy} disabled={!canNext} onClick={() => void onNext()}>{nextLabel}</Button>
        </>
      }
    >
      <Stack gap="lg">
        <Stepper steps={STEPS} current={step} label="Add topic progress" />
        {error && <Banner tone="error" icon="WarningCircle" title="That didn’t work" description={error} />}

        {step === 0 && (
          <>
            <Grid columns={2} stackAt="small" gap="md">
              <TextField label="Topic name (required)" placeholder="Patent Cliffs" value={topic} onChange={setTopic} disabled={Boolean(initialTopic)} />
              <TextField label="Display name" value={display} onChange={setDisplay} hint="Shown in reports. Defaults to the topic name." />
            </Grid>
            <TextArea label="Description" value={description} onChange={setDescription} rows={2} />
            <Grid columns={2} stackAt="small" gap="md">
              <TextField label="Owner (username)" placeholder="e.g. admin" value={owner} onChange={setOwner} />
              <TagInput label="Tags" tags={tags} onChange={setTags} hint="Press Enter or type a comma to add." />
            </Grid>
            <Stack gap="sm">
              <Text variant="label" as="div">Source topics (required) — where the seed articles come from</Text>
              {suggested.length > 0 && (
                <Stack direction="row" gap="sm" label="Suggested source topics">
                  {suggested.filter((s) => !sources.includes(s.topic)).map((s) => (
                    <Button key={s.topic} size="sm" variant="secondary" onClick={() => setSources((x) => [...x, s.topic])}>{`+ ${s.topic} (${s.total})`}</Button>
                  ))}
                </Stack>
              )}
              <div>
                {available.map((a) => (
                  <Checkbox
                    key={a.topic}
                    label={`${a.topic} (${a.count})`}
                    checked={sources.includes(a.topic)}
                    onCheckedChange={(c) => setSources((x) => (c ? [...x, a.topic] : x.filter((y) => y !== a.topic)))}
                  />
                ))}
              </div>
            </Stack>
          </>
        )}

        {step === 1 && (
          <Panel title="Build the forecast" headingLevel={3} description={`Seeds: ${sources.join(', ') || 'found automatically'}. Builds the Future Horizons scenarios and a first paired assessment.`}>
            <Stack gap="md">
              {lifecycle?.assessment_id && !building && (
                <Banner tone="success" icon="CheckCircle" title="This topic already has a stored assessment" description={lifecycle.assessed_at ? new Date(lifecycle.assessed_at).toLocaleString('en-GB') : undefined} />
              )}
              {building && build.state.kind === 'running' && (
                <Meter label="Build progress" progress value={build.state.pct} valueText={`${build.state.pct}% · ${build.state.message}`} />
              )}
              {build.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Build failed" description={build.state.message} />}
              {!building && (
                <Stack direction="row" gap="sm">
                  <Button variant={lifecycle?.assessment_id ? 'secondary' : 'primary'} busy={busy} onClick={() => void startBuild()}>
                    {lifecycle?.assessment_id ? 'Re-run build' : 'Run build pipeline'}
                  </Button>
                </Stack>
              )}
              {building && <Text variant="hint">You can close this dialog; the build keeps running and this step picks it up when you reopen it.</Text>}
            </Stack>
          </Panel>
        )}

        {step === 2 && (
          <Stack gap="md">
            {!overlay ? (
              <Panel title="Deck overlay" headingLevel={3} description="The overlay maps scenarios to the report deck’s strategic domains. Generate a proposal, then review it.">
                <Stack gap="md">
                  {generating && gen.state.kind === 'running' && <Meter label="Overlay progress" progress value={gen.state.pct} valueText={`${gen.state.pct}% · ${gen.state.message}`} />}
                  {gen.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Generation failed" description={gen.state.message} />}
                  {!generating && <Button busy={busy} onClick={() => void startOverlay()}>Generate overlay proposal</Button>}
                </Stack>
              </Panel>
            ) : (
              <>
                <Text variant="description">{`Review the ${Object.keys(overlay.deck_scenarios).length} deck scenarios before approving.`}</Text>
                {Object.entries(overlay.deck_scenarios).map(([key, d]) => (
                  <Panel key={key} title={d.deck_scenario_name || key} headingLevel={3} headerAside={<Chip size="sm" tone="neutral">{`${d.consensus_pct}% · ${String(d.horizon).toUpperCase()}`}</Chip>}>
                    <Stack gap="md">
                      <Grid columns={3} stackAt="small" gap="md">
                        <TextField label="Deck name" value={d.deck_scenario_name} onChange={(v) => setDeck(key, { deck_scenario_name: v })} />
                        <Select label="Horizon" fullWidth options={HORIZONS} value={d.horizon} onValueChange={(v) => setDeck(key, { horizon: v })} />
                        <TextField label="Consensus %" type="number" min={0} max={100} value={String(d.consensus_pct)} onChange={(v) => setDeck(key, { consensus_pct: Math.max(0, Math.min(100, Number(v) || 0)) })} />
                      </Grid>
                      <TextArea label="Primary signal" rows={3} value={d.primary_signal ?? ''} onChange={(v) => setDeck(key, { primary_signal: v })} />
                      <TextArea label="Minority view" rows={2} value={d.minority_view ?? ''} onChange={(v) => setDeck(key, { minority_view: v })} />
                      <Grid columns={2} stackAt="small" gap="md">
                        <TextArea label="Decision fork — favorable" rows={2} value={d.decision_fork?.favorable ?? ''} onChange={(v) => setDeck(key, { decision_fork: { ...d.decision_fork, favorable: v } })} />
                        <TextArea label="Decision fork — adverse" rows={2} value={d.decision_fork?.adverse ?? ''} onChange={(v) => setDeck(key, { decision_fork: { ...d.decision_fork, adverse: v } })} />
                      </Grid>
                      <Grid columns={3} stackAt="small" gap="md">
                        {(['0_6_months', '6_18_months', '18_plus_months'] as const).map((w) => (
                          <TextArea
                            key={w}
                            label={`Action window — ${w === '0_6_months' ? '0–6' : w === '6_18_months' ? '6–18' : '18+'} months`}
                            rows={2}
                            value={d.action_windows?.[w] ?? ''}
                            onChange={(v) => setDeck(key, { action_windows: { ...d.action_windows, [w]: v } })}
                          />
                        ))}
                      </Grid>
                    </Stack>
                  </Panel>
                ))}
              </>
            )}
          </Stack>
        )}

        {step === 3 && (
          <Grid columns={2} stackAt="small" gap="md">
            <Select label="Delivery cadence" fullWidth options={CADENCES} value={cadence} onValueChange={setCadence} />
            <TextField label="Recipient email" placeholder="director@example.com" value={recipient} onChange={setRecipient} hint="Comma-separate several addresses." />
          </Grid>
        )}
      </Stack>
    </Dialog>
  );
}
