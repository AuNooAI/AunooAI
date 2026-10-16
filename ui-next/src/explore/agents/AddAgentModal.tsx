import { useEffect, useState } from 'react';
import { Banner, Button, Chip, DialogClose, Dialog, Select, Stack, TabPanel, Tabs, Text, TextArea, TextField } from '@aunoo/ui';
import { getAvailableModels } from '@monolith/api';
import type { CreateAgentRequest, ResearchAgent } from '@monolith/researchAgentsApi';
import { session } from '../../shell';
import { useModules } from '../lib/useModules';
import { ActionsPanel } from './add/ActionsPanel';
import { emptyForm, fromAgent, TEMPLATES, toRequest, type AgentForm, type SearchStrategy } from './add/form';
import { SchedulePanel } from './add/SchedulePanel';

/*
 * Create or edit an Observer Agent, as the old AddAgentModal.tsx, with the same props. Saving only
 * stores the agent; nothing runs from here. The form is split into four tabs: what to look for,
 * how to search, what to do with matches, and when to run.
 */

interface AddAgentModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (agent: CreateAgentRequest) => Promise<boolean>;
  topics?: string[];
  loading?: boolean;
  /** If provided, the dialog edits this agent */
  editAgent?: ResearchAgent | null;
}

type Section = 'basics' | 'search' | 'actions' | 'schedule';
const STRATEGY_HINT: Record<SearchStrategy, string> = {
  recent: 'Reads only the most recent articles. Fastest.',
  chunked: 'Reads every article in the period, in batches. Most thorough, and the most AI calls.',
  semantic: 'Finds the articles closest in meaning to the instruction first, then reads those.',
};
type Model = { id: string; name: string; provider?: string };

export function AddAgentModal({ open, onClose, onSave, topics = [], loading = false, editAgent = null }: AddAgentModalProps) {
  // A dedicated Brand Watcher site: agents must watch a "Brand Monitoring …" topic
  const mods = useModules();
  const dedicated = (mods.dedicated ?? session.dedicatedBw) === true;
  const [f, setF] = useState<AgentForm>(emptyForm);
  const [section, setSection] = useState<Section>('basics');
  const [models, setModels] = useState<Model[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (p: Partial<AgentForm>) => setF((cur) => ({ ...cur, ...p }));
  const busy = saving || loading;

  // Start from the agent being edited, or from a blank form. The old dialog kept the last edited
  // agent's values when "Add" was opened next, because it only reset itself on close in create mode.
  useEffect(() => {
    if (!open) return;
    setF(editAgent ? fromAgent(editAgent) : emptyForm());
    setSection('basics');
    setError(null);
  }, [open, editAgent]);

  useEffect(() => {
    if (open && models === null) getAvailableModels().then((m) => setModels(m as Model[]), () => setModels([]));
  }, [open, models]);

  const save = async () => {
    if (!f.name.trim()) return setError('Give the agent a name.');
    if (!f.instruction.trim()) return setError('Write the instruction: what the agent should look for.');
    if (dedicated && !f.topic.startsWith('Brand Monitoring')) {
      setSection('basics');
      return setError('Agents on this site report on brand data only. Pick the brand topic this agent watches.');
    }
    setSaving(true);
    setError(null);
    try {
      if (await onSave(toRequest(f))) setF(emptyForm());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The agent wasn’t saved.');
    } finally {
      setSaving(false);
    }
  };

  const topicOptions = [...(dedicated ? [] : [{ value: '__all__', label: 'All topics' }]), ...topics.map((t) => ({ value: t, label: t }))];
  // An agent can hold a model that's no longer offered; keep it listed so editing doesn't change it
  const modelOptions = [
    { value: '__default__', label: 'Site default (Kimi K2.5)' },
    ...(f.model && models && !models.some((m) => m.id === f.model) ? [{ value: f.model, label: f.model }] : []),
    ...(models ?? []).map((m) => ({ value: m.id, label: m.provider ? `${m.name} (${m.provider})` : m.name })),
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      size="lg"
      title={editAgent ? 'Edit Observer Agent' : 'Create an Observer Agent'}
      description={
        editAgent
          ? 'Change the agent and save. Nothing runs until the agent is run or its schedule comes round.'
          : 'An agent reads collected articles with the AI, following your instruction, and acts on the ones that match. Saving here doesn’t run it.'
      }
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg" disabled={saving}>Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy || !f.name.trim() || !f.instruction.trim()} onClick={() => void save()}>
            {saving ? (editAgent ? 'Saving…' : 'Creating…') : editAgent ? 'Save changes' : 'Create agent'}
          </Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Not saved yet" description={error} />}
        <Tabs
          label="Agent settings"
          scrollable
          value={section}
          onValueChange={(v) => setSection(v as Section)}
          items={[
            { value: 'basics', label: 'What to look for' },
            { value: 'search', label: 'Search' },
            { value: 'actions', label: 'When it finds matches' },
            { value: 'schedule', label: 'Schedule' },
          ]}
        >
          <TabPanel value="basics">
            <Stack gap="md">
              {!editAgent && (
                <Stack gap="sm">
                  <Text variant="label">Start from a template</Text>
                  <Stack direction="row" gap="sm">
                    {TEMPLATES.map((t) => (
                      <Chip
                        key={t.name}
                        tone="neutral"
                        label={`Use the ${t.name} template`}
                        onClick={() => {
                          set({ name: t.name, instruction: t.instruction, ...(t.entities ? { entitiesHint: t.entities, entities: '' } : {}) });
                          setError(null);
                        }}
                      >
                        {t.name}
                      </Chip>
                    ))}
                  </Stack>
                </Stack>
              )}
              <TextField label="Name" placeholder="e.g. Executive announcements" value={f.name} onChange={(name) => set({ name })} disabled={busy} maxLength={200} />
              <TextField label="Description (optional)" placeholder="What this agent watches, in a line" value={f.description} onChange={(description) => set({ description })} disabled={busy} />
              <Select
                label="Topic"
                hint={dedicated ? 'Agents on this site report on brand data only: pick the brand this agent watches.' : 'Limit the agent to one topic’s articles, or let it read all of them.'}
                placeholder={dedicated ? 'Pick a brand topic' : undefined}
                options={topicOptions}
                value={f.topic || (dedicated ? undefined : '__all__')}
                onValueChange={(v) => set({ topic: v === '__all__' ? '' : v })}
                disabled={busy}
                fullWidth
              />
              <Select
                label="AI model"
                hint="The model that reads each article."
                placeholder={models === null ? 'Loading models…' : undefined}
                options={modelOptions}
                value={f.model || '__default__'}
                onValueChange={(v) => set({ model: v === '__default__' ? '' : v })}
                disabled={busy || models === null}
                fullWidth
              />
              <TextArea
                label="Instruction"
                rows={5}
                placeholder="What should the agent flag? Be specific about the kinds of content, names or events, and ask it to explain why each match is relevant."
                hint="The AI follows this when it reads each article, and says why each match is relevant."
                value={f.instruction}
                onChange={(instruction) => set({ instruction })}
              />
              <TextArea
                label="Names to watch for (optional)"
                rows={3}
                placeholder={f.entitiesHint}
                hint="Articles that mention these are looked at first."
                value={f.entities}
                onChange={(entities) => set({ entities })}
              />
            </Stack>
          </TabPanel>

          <TabPanel value="search">
            <Stack gap="md">
              <Select
                label="How to search"
                hint={STRATEGY_HINT[f.searchStrategy]}
                options={[
                  { value: 'recent', label: 'Recent articles (fast)' },
                  { value: 'chunked', label: 'Every article, in batches (thorough)' },
                  { value: 'semantic', label: 'Closest in meaning first (precise)' },
                ]}
                value={f.searchStrategy}
                onValueChange={(v) => set({ searchStrategy: v as SearchStrategy })}
                disabled={busy}
                fullWidth
              />
              <TextField
                label="Most articles to read"
                type="number"
                min={10}
                max={1000}
                hint="Between 10 and 1,000. Each article read is one AI call."
                value={String(f.maxArticles)}
                onChange={(v) => set({ maxArticles: Math.min(1000, Math.max(10, parseInt(v) || 100)) })}
                disabled={busy}
              />
              <TextField
                label="Alert threshold"
                type="number"
                min={1}
                max={100}
                hint="How many matches a run needs before email or Bluesky messages go out."
                value={String(f.alertThreshold)}
                onChange={(v) => set({ alertThreshold: Math.min(100, Math.max(1, parseInt(v) || 1)) })}
                disabled={busy}
              />
            </Stack>
          </TabPanel>

          <TabPanel value="actions">
            <ActionsPanel f={f} set={set} disabled={busy} />
          </TabPanel>

          <TabPanel value="schedule">
            <SchedulePanel f={f} set={set} disabled={busy} agent={editAgent} />
          </TabPanel>
        </Tabs>
      </Stack>
    </Dialog>
  );
}
