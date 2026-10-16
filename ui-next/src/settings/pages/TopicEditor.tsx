import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Button, Icon, Panel, Select, Skeleton, Stack, TagInput, Text, TextArea, TextField } from '@aunoo/ui';
import { errorText } from '../../shell';
import { emptyLists, getTopic, LABEL_LISTS, listTopicNames, saveTopic, suggestionsFrom, type LabelList, type TopicConfig } from '../topics/api';
import { DeleteTopicDialog } from '../topics/DeleteTopicDialog';
import type { SettingsPageProps } from '../types';

/*
 * The manual topic editor, as the old /create_topic page (templates/create_topic.html): pick a topic
 * to edit or start a new one, set its name, description and the five label lists the AI analysis
 * step picks from. ?topic=<name> opens that topic, as before. The guided set-up lives in the shell's
 * "Set up topic" wizard.
 */

const NEW = '__new__';
const MAX_SUGGESTIONS = 24;

const HELP: Record<LabelList, { label: string; help: string }> = {
  future_signals: {
    label: 'Future signals',
    help: 'Scenarios that suggest where the topic could go. For an AI hype model they might run from “AI is hype” and “AI is evolving gradually” to “AI is accelerating”.',
  },
  categories: {
    label: 'Categories',
    help: 'The parts the topic breaks down into, so articles can be organised and compared. A topic on AI might have categories such as AI in Finance or Cloud Quarterly Earnings.',
  },
  sentiment: {
    label: 'Sentiments',
    help: 'The tones the AI can detect, beyond positive, neutral and negative: mocking, critical, hyperbolic or optimistic, for example.',
  },
  time_to_impact: {
    label: 'Time to impact',
    help: 'When a trend’s impact is expected, following the Three Horizon Model: immediate, short-term (3–18 months), mid-term (18–60 months) or long-term (5+ years).',
  },
  driver_types: {
    label: 'Driver types',
    help: 'How an article bears on the topic. Accelerator: speeds a trend up. Delayer: slows it down. Blocker: stops it advancing. Catalyst: changes its course significantly.',
  },
};

type Draft = Pick<TopicConfig, 'name' | 'description' | LabelList>;
const blank = (): Draft => ({ name: '', description: '', categories: [], future_signals: [], sentiment: [], time_to_impact: [], driver_types: [] });
const asList = (v: unknown) => (Array.isArray(v) ? v.map((x) => String(x)) : []);
const toDraft = (t: TopicConfig): Draft => ({
  name: t.name, description: t.description ?? '', categories: asList(t.categories), future_signals: asList(t.future_signals),
  sentiment: asList(t.sentiment), time_to_impact: asList(t.time_to_impact), driver_types: asList(t.driver_types),
});

/** Keeps ?topic= in step with the topic open, so the address can be shared */
function setTopicParam(name: string | null) {
  const url = new URL(window.location.href);
  if (name) url.searchParams.set('topic', name);
  else url.searchParams.delete('topic');
  window.history.replaceState({}, '', url.toString());
}

export function TopicEditor({ notify, askConfirm }: SettingsPageProps) {
  const [names, setNames] = useState<string[] | null>(null);
  const [all, setAll] = useState<TopicConfig[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>(NEW);
  // The topic as saved, so a save keeps every key this page doesn't show (queries, flags…)
  const [original, setOriginal] = useState<TopicConfig | null>(null);
  const [draft, setDraft] = useState<Draft>(blank);
  const [opening, setOpening] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const list = await listTopicNames();
      setNames(list);
      // Every topic's lists, for the suggestions under each field
      const configs = await Promise.all(list.map((n) => getTopic(n).catch(() => null)));
      setAll(configs.filter((c): c is TopicConfig => !!c));
      return list;
    } catch (e) {
      setLoadError(errorText(e));
      setNames([]);
      return [];
    }
  }, []);

  const open = useCallback(async (name: string) => {
    setSaveError(null);
    if (name === NEW) {
      setSelected(NEW);
      setOriginal(null);
      setDraft(blank());
      setTopicParam(null);
      return;
    }
    setSelected(name);
    setOpening(true);
    try {
      const t = await getTopic(name);
      setOriginal(t);
      setDraft(toDraft(t));
      setTopicParam(name);
    } catch (e) {
      notify(`Couldn’t open “${name}”: ${errorText(e)}`);
      setSelected(NEW);
      setOriginal(null);
      setDraft(blank());
    } finally {
      setOpening(false);
    }
  }, [notify]);

  useEffect(() => {
    void load().then((list) => {
      const wanted = new URLSearchParams(window.location.search).get('topic');
      if (wanted && list.includes(wanted)) void open(wanted);
    });
  }, [load, open]);

  const suggestions = useMemo(() => suggestionsFrom(all), [all]);
  const editing = selected !== NEW;
  const empty = emptyLists(draft);
  const nameTaken = !editing && !!draft.name.trim() && (names ?? []).some((n) => n.toLowerCase() === draft.name.trim().toLowerCase());
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));

  const doSave = async () => {
    const name = draft.name.trim();
    setSaving(true);
    setSaveError(null);
    try {
      // Merged over the saved topic: the old page sent only these fields, so a save quietly dropped
      // every other setting the topic had
      const base = editing ? original ?? {} : nameTaken ? all.find((t) => t.name.toLowerCase() === name.toLowerCase()) ?? {} : {};
      const clean = (l: string[]) => l.map((v) => v.trim()).filter(Boolean);
      await saveTopic({
        ...base,
        name,
        description: draft.description?.trim() ?? '',
        categories: clean(draft.categories), future_signals: clean(draft.future_signals), sentiment: clean(draft.sentiment),
        time_to_impact: clean(draft.time_to_impact), driver_types: clean(draft.driver_types),
      } as TopicConfig);
      notify(editing ? `“${name}” saved` : `“${name}” created`);
      await load();
      await open(name);
    } catch (e) {
      setSaveError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const save = () => {
    if (nameTaken) {
      askConfirm({
        title: `Replace “${draft.name.trim()}”?`,
        message: 'A topic with this name already exists. Saving replaces its description and label lists with the ones on this page. Its other settings stay.',
        action: 'Replace it',
        onConfirm: () => void doSave(),
      });
    } else void doSave();
  };

  if (!names) return <Skeleton variant="block" size="card" />;

  return (
    <Stack gap="lg">
      <Panel
        title={editing ? `Edit “${selected}”` : 'Create a topic'}
        description="A topic is what the site collects and analyses articles for. Pick one to edit, or start a new one. For a guided set-up with AI suggestions, use “Set up topic” at the top of the page."
      >
        <Stack gap="md">
          {loadError && <Banner tone="error" title="Topics didn’t load" description={loadError} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
          <Stack direction="row" gap="sm" justify="between">
            <Select
              label="Topic"
              options={[{ value: NEW, label: 'New topic' }, ...names.map((n) => ({ value: n, label: n }))]}
              value={selected}
              onValueChange={(v) => void open(v)}
              disabled={opening || saving}
            />
            {editing && (
              <Button variant="secondary" iconStart={<Icon name="Trash" size="sm" />} disabled={saving} onClick={() => setDeleting(selected)}>Delete topic</Button>
            )}
          </Stack>
        </Stack>
      </Panel>

      {opening ? <Skeleton variant="block" size="card" /> : (
        <Panel title="Name and description">
          <Stack gap="md">
            <TextField
              label="Topic name"
              value={draft.name}
              onChange={(v) => set('name', v)}
              disabled={editing}
              maxLength={200}
              hint={editing
                ? 'The name can’t be changed here: saving under a new name would create a second topic and leave this one behind.'
                : 'A clear description that could be a question, market, field or group.'}
              error={nameTaken ? 'A topic with this name already exists; saving will replace its lists.' : undefined}
            />
            <TextArea
              label="Topic description"
              rows={3}
              value={draft.description ?? ''}
              onChange={(v) => set('description', v)}
              hint="What the topic covers. It helps relevance scoring, especially when the topic has few keywords."
            />
          </Stack>
        </Panel>
      )}

      {!opening && (
        <Panel title="Label lists" description="The AI analysis step labels each article from these lists. A topic needs all five: articles for a topic with an empty list are stored but never analysed.">
          <Stack gap="lg">
            {LABEL_LISTS.map((k) => (
              <Stack key={k} gap="sm">
                <TagInput
                  label={HELP[k].label}
                  tags={draft[k]}
                  onChange={(tags) => set(k, tags)}
                  suggestions={suggestions[k].filter((s) => !draft[k].includes(s)).slice(0, MAX_SUGGESTIONS)}
                  hint={HELP[k].help}
                />
              </Stack>
            ))}
          </Stack>
        </Panel>
      )}

      {!opening && (
        <Panel title="Save">
          <Stack gap="md">
            {empty.length > 0 && (
              <Banner
                tone="warning"
                title="Some lists are empty"
                description={`Fill ${empty.map((k) => HELP[k].label.toLowerCase()).join(', ')} before saving. The server refuses a topic with an empty list, because its articles would never be analysed.`}
              />
            )}
            {saveError && <Banner tone="error" title="Not saved" description={saveError} />}
            <Stack direction="row" gap="sm">
              <Button iconStart={<Icon name="Check" size="sm" />} busy={saving} disabled={saving || !draft.name.trim() || empty.length > 0} onClick={save}>
                {editing ? 'Save changes' : 'Create topic'}
              </Button>
              {editing && <Button variant="ghost" disabled={saving} onClick={() => void open(selected)}>Discard changes</Button>}
            </Stack>
            <Text variant="caption">Saving writes the topic to the site’s settings. Collection picks up a new topic on its next run.</Text>
          </Stack>
        </Panel>
      )}

      <DeleteTopicDialog
        name={deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        onDeleted={(n) => {
          notify(`“${n}” deleted`);
          void load();
          void open(NEW);
        }}
      />
    </Stack>
  );
}
