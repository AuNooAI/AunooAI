import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Select, Skeleton, Stack, Switch, TabPanel, Tabs, Text, TextArea, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';

/*
 * The News Feed's three settings dialogs, on the old modals' storage:
 *  - Briefing: /api/news-feed/six-articles/config (SixArticlesTuneModal)
 *  - Incidents: this browser, localStorage "incidentTrackingConfig", checked by POST /api/incident-config.
 *    The old modal sent snake_case to a camelCase check, so its saves always failed.
 *  - Narratives: this browser only, localStorage "narrativesConfig" (NarrativesConfigModal)
 */

type Notify = (m: string) => void;
interface Base {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  notify: Notify;
}

function Footer({ busy, onSave, extra }: { busy: boolean; onSave: () => void; extra?: React.ReactNode }) {
  return (
    <>
      {extra}
      <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
      <Button size="lg" disabled={busy} onClick={onSave}>Save</Button>
    </>
  );
}

// ── Briefing ────────────────────────────────────────────────────────────

interface PersonaCfg { name?: string; priorities: string; riskAppetite: string; focus: string }
interface BriefingCfg { systemPrompt?: string | null; personas?: Record<string, PersonaCfg>; formatSpec?: string; articleCount?: number }
const PERSONA_IDS = ['CEO', 'CMO', 'CTO', 'CISO'];

export function BriefingTuneDialog({ open, onOpenChange, notify, articleCount, onSaved }: Base & { articleCount: number; onSaved: (count: number) => void }) {
  const [cfg, setCfg] = useState<BriefingCfg | null>(null);
  const [count, setCount] = useState(String(articleCount));
  const [persona, setPersona] = useState('CEO');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setCfg(null);
    setCount(String(articleCount));
    api<BriefingCfg>('/api/news-feed/six-articles/config').then(setCfg, () => setCfg({}));
  }, [open, articleCount]);
  const p = cfg?.personas?.[persona] ?? { priorities: '', riskAppetite: '', focus: '' };
  const setP = (patch: Partial<PersonaCfg>) => setCfg((c) => ({ ...c, personas: { ...(c?.personas ?? {}), [persona]: { ...p, ...patch } } }));

  const save = async () => {
    setBusy(true);
    try {
      const n = Math.min(8, Math.max(1, Number(count) || 6));
      await api('/api/news-feed/six-articles/config', { method: 'POST', json: { ...cfg, systemPrompt: cfg?.systemPrompt || null, articleCount: n } });
      onSaved(n);
      notify('Briefing settings saved. Write a new briefing to use them.');
      onOpenChange(false);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Tune the briefing" footer={<Footer busy={busy || !cfg} onSave={() => void save()} />}>
      {!cfg ? <Skeleton variant="text" lines={8} /> : (
        <Stack gap="md">
          <TextField label="Stories in the briefing" type="number" min={1} max={8} value={count} onChange={setCount} hint="Between 1 and 8." />
          <Select label="Persona" fullWidth options={PERSONA_IDS.map((v) => ({ value: v, label: v }))} value={persona} onValueChange={setPersona} />
          <TextArea label="Priorities" rows={3} value={p.priorities} onChange={(priorities) => setP({ priorities })} />
          <TextField label="Risk appetite" value={p.riskAppetite} onChange={(riskAppetite) => setP({ riskAppetite })} />
          <TextArea label="Focus" rows={2} value={p.focus} onChange={(focus) => setP({ focus })} />
          <TextArea label="Instructions to the AI" hint="Leave empty to use the built-in instructions." rows={6} value={cfg.systemPrompt ?? ''} onChange={(systemPrompt) => setCfg({ ...cfg, systemPrompt })} />
          <TextArea label="Output format" rows={4} value={cfg.formatSpec ?? ''} onChange={(formatSpec) => setCfg({ ...cfg, formatSpec })} />
        </Stack>
      )}
    </Dialog>
  );
}

// ── Incidents ───────────────────────────────────────────────────────────

interface IncidentCfg {
  system_prompt?: string; user_prompt?: string; profile_context_template?: string; enable_profile_integration?: boolean;
  base_ontology?: string; domain_key?: string; domain_overlay?: string; ontology_examples?: string;
  analysis_instructions?: string; quality_guidelines?: string; output_format?: string;
}

/** The routes answer {config: {...}} and {defaults: {...}}, in snake_case or camelCase. */
function toIncidentCfg(r: unknown): IncidentCfg {
  const o = (r ?? {}) as Record<string, Record<string, unknown> | undefined>;
  const c = (o.config ?? o.defaults ?? o) as Record<string, unknown>;
  const pick = (snake: string) => {
    const camel = snake.replace(/_([a-z])/g, (_, x: string) => x.toUpperCase());
    return (c[snake] ?? c[camel]) as never;
  };
  return {
    system_prompt: pick('system_prompt'), user_prompt: pick('user_prompt'), profile_context_template: pick('profile_context_template'),
    enable_profile_integration: pick('enable_profile_integration') ?? true, base_ontology: pick('base_ontology'), domain_key: pick('domain_key'),
    domain_overlay: pick('domain_overlay'), ontology_examples: pick('ontology_examples'), analysis_instructions: pick('analysis_instructions'),
    quality_guidelines: pick('quality_guidelines'), output_format: pick('output_format'),
  };
}
/** Read by every incident run (useFeed → getIncidentConfigFromStorage), as on the old page */
const INCIDENT_KEY = 'incidentTrackingConfig';
const fetchDefaults = () => api('/api/incident-config/defaults').then(toIncidentCfg);

export function IncidentSettingsDialog({ open, onOpenChange, notify }: Base) {
  const [cfg, setCfg] = useState<IncidentCfg | null>(null);
  const [tab, setTab] = useState('prompts');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setCfg(null);
    // This browser's settings over the built-in ones
    let mine: IncidentCfg = {};
    try {
      mine = JSON.parse(localStorage.getItem(INCIDENT_KEY) ?? '{}');
    } catch {
      // none saved
    }
    fetchDefaults().then((d) => setCfg({ ...d, ...mine }), () => setCfg(mine));
  }, [open]);
  const set = (patch: Partial<IncidentCfg>) => setCfg((c) => ({ ...c, ...patch }));
  const field = (k: keyof IncidentCfg, label: string, rows = 6) => (
    <TextArea label={label} rows={rows} value={(cfg?.[k] as string) ?? ''} onChange={(v) => set({ [k]: v })} />
  );

  const save = async () => {
    setBusy(true);
    try {
      // The server checks the prompts (placeholders present) but stores nothing; each run sends them from here
      const c = cfg ?? {};
      await api('/api/incident-config', {
        method: 'POST',
        json: {
          systemPrompt: c.system_prompt ?? '', userPrompt: c.user_prompt ?? '', baseOntology: c.base_ontology ?? '', domainKey: c.domain_key ?? '',
          domainOverlay: c.domain_overlay ?? '', ontologyExamples: c.ontology_examples ?? '', analysisInstructions: c.analysis_instructions ?? '',
          qualityGuidelines: c.quality_guidelines ?? '', outputFormat: c.output_format ?? '', profileContextTemplate: c.profile_context_template ?? '',
          enableProfileIntegration: c.enable_profile_integration ?? true,
        },
      });
      localStorage.setItem(INCIDENT_KEY, JSON.stringify(c));
      notify('Incident settings saved in this browser. Generate again to use them.');
      onOpenChange(false);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    try {
      setCfg(await fetchDefaults());
      try {
        localStorage.removeItem(INCIDENT_KEY);
      } catch {
        // nothing stored
      }
      notify('Built-in settings restored');
    } catch (e) {
      notify(`Defaults didn’t load: ${errorText(e)}`);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Incident settings"
      description="How the AI finds and writes up incidents. Kept in this browser and sent with each run; the server checks the prompts but doesn’t store them."
      footer={<Footer busy={busy || !cfg} onSave={() => void save()} extra={<Button variant="ghost" size="lg" onClick={() => void reset()}>Restore built-in</Button>} />}
    >
      {!cfg ? <Skeleton variant="text" lines={8} /> : (
        <Tabs label="Incident settings" stretch value={tab} onValueChange={setTab} items={[{ value: 'prompts', label: 'Prompts' }, { value: 'ontology', label: 'Ontology' }, { value: 'guidance', label: 'Guidance' }]}>
          <TabPanel value="prompts">
            <Stack gap="md">
              {field('system_prompt', 'System prompt', 8)}
              {field('user_prompt', 'User prompt', 8)}
              <Switch label="Use the audience profile" description="Adds the selected profile to the prompt." checked={!!cfg.enable_profile_integration} onCheckedChange={(enable_profile_integration) => set({ enable_profile_integration })} />
              {field('profile_context_template', 'Profile context template', 4)}
            </Stack>
          </TabPanel>
          <TabPanel value="ontology">
            <Stack gap="md">
              {field('base_ontology', 'Base ontology', 8)}
              <TextField label="Domain" value={cfg.domain_key ?? ''} onChange={(domain_key) => set({ domain_key })} />
              {field('domain_overlay', 'Domain overlay', 4)}
              {field('ontology_examples', 'Examples', 4)}
            </Stack>
          </TabPanel>
          <TabPanel value="guidance">
            <Stack gap="md">
              {field('analysis_instructions', 'Analysis instructions')}
              {field('quality_guidelines', 'Quality guidelines')}
              {field('output_format', 'Output format')}
            </Stack>
          </TabPanel>
        </Tabs>
      )}
    </Dialog>
  );
}

// ── Narratives ──────────────────────────────────────────────────────────

const NARR_KEY = 'narrativesConfig';
interface NarrCfg { system_prompt: string; user_prompt: string; additional_instructions: string }
const EMPTY_NARR: NarrCfg = { system_prompt: '', user_prompt: '', additional_instructions: '' };

export function NarrativeSettingsDialog({ open, onOpenChange, notify }: Base) {
  const [cfg, setCfg] = useState<NarrCfg>(EMPTY_NARR);
  useEffect(() => {
    if (!open) return;
    try {
      setCfg({ ...EMPTY_NARR, ...JSON.parse(localStorage.getItem(NARR_KEY) ?? '{}') });
    } catch {
      setCfg(EMPTY_NARR);
    }
  }, [open]);
  const save = () => {
    try {
      if (!cfg.system_prompt && !cfg.user_prompt && !cfg.additional_instructions) localStorage.removeItem(NARR_KEY);
      else localStorage.setItem(NARR_KEY, JSON.stringify(cfg));
      notify('Narrative settings saved in this browser. Generate again to use them.');
      onOpenChange(false);
    } catch {
      notify('This browser didn’t let the settings be saved.');
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Narrative settings"
      description="Kept in this browser only. Leave a box empty to use the built-in prompt."
      footer={<Footer busy={false} onSave={save} extra={<Button variant="ghost" size="lg" onClick={() => setCfg(EMPTY_NARR)}>Clear all</Button>} />}
    >
      <Stack gap="md">
        <TextArea label="System prompt" rows={8} value={cfg.system_prompt} onChange={(system_prompt) => setCfg({ ...cfg, system_prompt })} />
        <TextArea label="User prompt" rows={8} value={cfg.user_prompt} onChange={(user_prompt) => setCfg({ ...cfg, user_prompt })} />
        <Banner tone="info" title="Not sent yet" description="The old page stored “additional instructions” but never sent them to the server, so that box is left out here." />
        <Text variant="caption">Prompts go to the server with each Generate.</Text>
      </Stack>
    </Dialog>
  );
}
