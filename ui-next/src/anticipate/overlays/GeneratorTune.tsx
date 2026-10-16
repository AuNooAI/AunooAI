import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Eyebrow, Grid, SegmentedControl, Select, Skeleton, Stack, Text, TextArea } from '@aunoo/ui';
import { getAvailableModels, type AIModel } from '@monolith/api';
import { api, errorText } from '../../shell';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Cfg = Record<string, any>;

interface Prompt {
  id: string;
  name: string;
  description?: string;
  content: string;
  metadata?: { model_config?: { model?: string; temperature?: number } };
}

const STYLES = [
  { value: '0.1', label: 'Precise (0.1)' },
  { value: '0.3', label: 'Balanced (0.3)' },
  { value: '0.5', label: 'Exploratory (0.5)' },
  { value: '0.7', label: 'Creative (0.7)' },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** e.g. /api/eos — serves /config and /prompts */
  base: string;
  /** Default settings editor, given the server config draft. */
  settings?: (cfg: Cfg, set: (patch: Cfg) => void) => React.ReactNode;
  notify: (m: string) => void;
  /** After saving: the saved config, so the tab can use the new defaults. */
  onSaved?: (cfg: Cfg) => void;
}

/**
 * Tune for a generator: its saved defaults (PUT {base}/config) and each agent's prompt, model and
 * style (PUT {base}/prompts/{id}). Opening it no longer overwrites the tab's unsaved settings.
 */
export function GeneratorTune({ open, onOpenChange, title, base, settings, notify, onSaved }: Props) {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [prompts, setPrompts] = useState<Prompt[] | null>(null);
  const [edited, setEdited] = useState<Record<string, { content: string; model: string; temperature: number }>>({});
  const [agent, setAgent] = useState('');
  const [models, setModels] = useState<AIModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cfgDirty, setCfgDirty] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setEdited({});
    setCfgDirty(false);
    Promise.all([api<Cfg>(`${base}/config`).catch(() => ({})), api<{ prompts: Prompt[] }>(`${base}/prompts`), getAvailableModels()]).then(
      ([c, p, m]) => {
        setCfg(c);
        setPrompts(p.prompts ?? []);
        setAgent(p.prompts?.[0]?.id ?? '');
        setModels(m);
      },
      (e) => setError(errorText(e)),
    );
  }, [open, base]);

  const current = prompts?.find((p) => p.id === agent);
  const value = current && (edited[current.id] ?? {
    content: current.content,
    model: current.metadata?.model_config?.model ?? models[0]?.id ?? '',
    temperature: current.metadata?.model_config?.temperature ?? 0.3,
  });
  const edit = (patch: Partial<{ content: string; model: string; temperature: number }>) => {
    if (!current || !value) return;
    setEdited((e) => ({ ...e, [current.id]: { ...value, ...patch } }));
  };
  const modelOptions = (() => {
    const opts = models.map((m) => ({ value: m.id, label: m.name }));
    // A saved model that's no longer offered stays listed rather than silently changing
    if (value?.model && !opts.some((o) => o.value === value.model)) opts.unshift({ value: value.model, label: `${value.model} (no longer offered)` });
    return opts;
  })();

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (cfg && cfgDirty) await api(`${base}/config`, { method: 'PUT', json: cfg });
      for (const [id, v] of Object.entries(edited)) await api(`${base}/prompts/${id}`, { method: 'PUT', json: v });
      notify(`${title}: saved`);
      if (cfg) onSaved?.(cfg);
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={`Tune: ${title}`}
      description="Saved defaults for this generator, and each agent’s prompt, model and style."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={!cfgDirty && Object.keys(edited).length === 0} onClick={save}>Save</Button>
        </>
      }
    >
      {error && <Banner tone="error" icon="WarningCircle" title="Something went wrong" description={error} />}
      {!prompts ? (
        !error && <Skeleton variant="block" />
      ) : (
        <Stack gap="lg">
          {settings && cfg && (
            <Stack gap="sm">
              <Eyebrow as="h3">Default settings</Eyebrow>
              {settings(cfg, (p) => { setCfg((c) => ({ ...c, ...p })); setCfgDirty(true); })}
            </Stack>
          )}
          {prompts.length === 0 ? (
            <Text variant="hint">No agent prompts found for this generator.</Text>
          ) : (
            <Stack gap="md">
              <Eyebrow as="h3">Agents</Eyebrow>
              <SegmentedControl label="Agent" value={agent} onValueChange={setAgent} options={prompts.map((p) => ({ value: p.id, label: p.name.replace(/_agent$/, '').replace(/^[a-z]+_/, '').replace(/_/g, ' ') }))} />
              {current && value && (
                <>
                  {current.description && <Text variant="hint">{current.description}</Text>}
                  <Grid columns={2} stackAt="small" gap="md">
                    <Select label="AI model" fullWidth options={modelOptions} value={value.model} onValueChange={(model) => edit({ model })} />
                    <Select label="Response style" fullWidth options={STYLES.some((s) => Number(s.value) === value.temperature) ? STYLES : [...STYLES, { value: String(value.temperature), label: `Custom (${value.temperature})` }]} value={String(value.temperature)} onValueChange={(t) => edit({ temperature: Number(t) })} />
                  </Grid>
                  <TextArea label="Prompt" rows={14} mono value={value.content} onChange={(content) => edit({ content })} />
                  {edited[current.id] && <Text variant="caption">Edited — not saved yet.</Text>}
                </>
              )}
            </Stack>
          )}
        </Stack>
      )}
    </Dialog>
  );
}
