import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, EmptyState, Icon, IconButton, Meter, Panel, Select,
  Stack, Text, TextField, type IconName,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import { savePng, slug } from '../lib/download';
import type { Generator, Stage } from '../lib/generator';

/** Saved results for a generator: list per topic, load, delete (the old tabs only offered Load once a result existed). */
export interface SavedApi {
  /** e.g. /api/eos — serves /saved/{topic}, /saved/load/{id}, /saved/{id}, /save */
  base: string;
  /** Key of the list in GET /saved/{topic} */
  listKey: string;
  /** Key of the record in GET /saved/load/{id} */
  loadKey: string;
}

interface SavedItem { id: number; name: string; created_at?: string }

export function useSaved(api_: SavedApi | undefined, topic: string) {
  const [items, setItems] = useState<SavedItem[]>([]);
  const load = useCallback(() => {
    if (!api_ || !topic) return;
    api<Record<string, SavedItem[]>>(`${api_.base}/saved/${encodeURIComponent(topic)}`).then((r) => setItems(r[api_.listKey] ?? []), () => setItems([]));
  }, [api_?.base, api_?.listKey, topic]);
  useEffect(load, [load]);
  return { items, reload: load };
}

interface Props<R> {
  title: string;
  icon: IconName;
  description: string;
  topic: string;
  gen: Generator<R>;
  stages: Stage[];
  /** One-line summary of the settings, shown when they're folded. */
  summary: string;
  /** The settings form. */
  settings?: React.ReactNode;
  generateLabel: string;
  onGenerate: () => void;
  /** Opens this generator's Tune dialog. */
  onTune: () => void;
  /** Live numbers while running, e.g. "12 signals · 3 paths". */
  liveStats?: string;
  /** Text streamed while writing (Situation Assessment, Newsletter). */
  livePreview?: React.ReactNode;
  emptyText: string;
  actions: React.ReactNode;
  saved?: SavedApi;
  /** Turns a loaded record into a result. */
  fromSaved?: (record: Record<string, unknown>) => R;
  /** Body for POST {saved.base}/save, given the name and description. */
  toSave?: (name: string, description: string) => Record<string, unknown>;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  children: React.ReactNode;
}

/** The frame every generator tab shares: settings, generate, progress, saved results, and the result. */
export function GeneratorFrame<R>(p: Props<R>) {
  const { gen } = p;
  const saved = useSaved(p.saved, p.topic);
  const [saveOpen, setSaveOpen] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pick, setPick] = useState('');
  const resultRef = useRef<HTMLDivElement>(null);

  const loadSaved = async (id: string) => {
    if (!p.saved || !p.fromSaved) return;
    setPick(id);
    try {
      const r = await api<Record<string, Record<string, unknown>>>(`${p.saved.base}/saved/load/${id}`);
      gen.setResult(p.fromSaved(r[p.saved.loadKey] ?? {}));
      p.notify('Saved result loaded');
    } catch (e) {
      p.notify(`Couldn’t load it: ${errorText(e)}`);
    }
  };
  const doSave = async () => {
    if (!p.saved || !p.toSave) return;
    setBusy(true);
    setSaveError(null);
    try {
      await api(`${p.saved.base}/save`, { method: 'POST', json: p.toSave(name.trim(), desc.trim()) });
      p.notify(`Saved as “${name.trim()}”`);
      setSaveOpen(false);
      saved.reload();
    } catch (e) {
      const msg = errorText(e);
      setSaveError(/409|exist/i.test(msg) ? 'A saved result with this name already exists for this topic.' : msg);
    } finally {
      setBusy(false);
    }
  };
  const removeSaved = () => {
    const item = saved.items.find((x) => String(x.id) === pick);
    if (!item || !p.saved) return;
    p.askConfirm({
      title: 'Delete saved result?',
      message: `“${item.name}” will be deleted. This can’t be undone.`,
      action: 'Delete',
      onConfirm: async () => {
        try {
          await api(`${p.saved!.base}/saved/${item.id}`, { method: 'DELETE' });
          p.notify(`“${item.name}” deleted`);
          setPick('');
          saved.reload();
        } catch (e) {
          p.notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });
  };

  const running = gen.status === 'running';
  return (
    <>
      <Panel
        title={<><Icon name={p.icon} size="sm" /> {p.title}</>}
        description={p.description}
        headingLevel={2}
        headerAside={
          <Stack direction="row" gap="sm">
            <Button variant="ghost" size="sm" iconStart={<Icon name="SlidersHorizontal" size="sm" />} onClick={p.onTune}>Tune</Button>
            <Button iconStart={<Icon name="Sparkle" size="sm" />} busy={running} disabled={!p.topic} onClick={p.onGenerate}>
              {running ? 'Generating…' : p.generateLabel}
            </Button>
          </Stack>
        }
      >
        <Stack gap="md">
          {p.settings ? (
            <Collapsible>
              <Stack gap="md">
                <Stack direction="row" gap="sm">
                  <CollapsibleTrigger variant="secondary">Settings</CollapsibleTrigger>
                  <Text variant="label" as="span">{p.summary}</Text>
                </Stack>
                <CollapsibleContent>{p.settings}</CollapsibleContent>
              </Stack>
            </Collapsible>
          ) : (
            <Text variant="label" as="span">{p.summary}</Text>
          )}
          {p.saved && saved.items.length > 0 && (
            <Stack direction="row" gap="sm">
              <Select
                label="Saved results"
                hideLabel
                icon="BookmarkSimple"
                placeholder={`Saved results (${saved.items.length})`}
                options={saved.items.map((s) => ({ value: String(s.id), label: `${s.name}${s.created_at ? ` · ${new Date(s.created_at).toLocaleDateString('en-GB')}` : ''}` }))}
                value={pick}
                onValueChange={(v) => void loadSaved(v)}
              />
              {pick && <IconButton icon={<Icon name="Trash" size="sm" />} label="Delete this saved result" tone="danger" onClick={removeSaved} />}
            </Stack>
          )}
        </Stack>
      </Panel>

      {running && (
        <Panel title={gen.stageLabel || 'Starting…'} description={p.liveStats}>
          <Stack gap="md">
            <Meter label="Generation progress" progress value={gen.progress} valueText={`${gen.progress}%`} />
            <Stack direction="row" gap="sm">
              {p.stages.map((s) => (
                <Text key={s.id} variant={s.id === gen.stage ? 'label' : 'hint'} as="span">{s.label}</Text>
              ))}
            </Stack>
            {p.livePreview}
            <Stack direction="row" gap="sm"><Button variant="ghost" size="sm" onClick={gen.cancel}>Cancel</Button></Stack>
          </Stack>
        </Panel>
      )}

      {gen.status === 'error' && (
        <Banner
          tone="error"
          icon="WarningCircle"
          headingLevel={2}
          title="Generation didn’t finish"
          description={gen.error}
          action={<Button variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={p.onGenerate}>Try again</Button>}
        />
      )}

      {gen.result && !running ? (
        <>
          <Stack direction="row" justify="end" gap="sm">
            {p.actions}
            <Button variant="ghost" size="sm" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => { if (resultRef.current) savePng(resultRef.current, `${slug(p.title)}-${slug(p.topic)}.png`).catch((e) => p.notify(`Couldn’t save the image: ${errorText(e)}`)); }}>PNG</Button>
            {p.saved && p.toSave && <Button variant="ghost" size="sm" iconStart={<Icon name="BookmarkSimple" size="sm" />} onClick={() => { setName(''); setDesc(''); setSaveError(null); setSaveOpen(true); }}>Save</Button>}
            <Button variant="ghost" size="sm" iconStart={<Icon name="X" size="sm" />} onClick={gen.clear}>Clear</Button>
          </Stack>
          {/* Unstyled wrapper: the PNG export captures what's inside it */}
          <div ref={resultRef}>
            <Stack gap="lg">{p.children}</Stack>
          </div>
        </>
      ) : (
        !running &&
        gen.status !== 'error' && (
          <Panel title="Nothing generated yet">
            <EmptyState icon={p.icon} action={<Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={!p.topic} onClick={p.onGenerate}>{p.generateLabel}</Button>}>
              {p.emptyText}
            </EmptyState>
          </Panel>
        )
      )}

      <Dialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        title="Save result"
        footer={
          <>
            <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
            <Button size="lg" busy={busy} disabled={!name.trim()} onClick={doSave}>Save</Button>
          </>
        }
      >
        <Stack gap="md">
          {saveError && <Banner tone="error" icon="WarningCircle" title="Not saved" description={saveError} />}
          <TextField label="Name" value={name} onChange={setName} />
          <TextField label="Description (optional)" value={desc} onChange={setDesc} />
        </Stack>
      </Dialog>
    </>
  );
}
