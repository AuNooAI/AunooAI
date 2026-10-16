import { useEffect, useState } from 'react';
import { ArticleCard, Button, Checkbox, Chip, Eyebrow, Grid, Icon, LineItems, Meter, Panel, Select, SettingRow, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import { api } from '../../shell';
import { GeneratorFrame } from '../components/GeneratorFrame';
import { SourceArticles, type SourceArticle } from '../components/SourceArticles';
import { saveText } from '../lib/download';
import { useGenerator, type Event, type Stage } from '../lib/generator';
import { GeneratorTune } from '../overlays/GeneratorTune';
import type { ViewProps } from './types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Persona = Record<string, any> & { id: string; name: string };
interface Dynamics {
  consensus_areas?: { topic: string; description: string; supporting_personas?: string[] }[];
  tension_points?: { topic: string; description: string; opposing_sides?: { side_a?: string[]; side_b?: string[] } }[];
  power_dynamics?: { most_influential?: string; most_vulnerable?: string; likely_coalition?: string[] };
  diversity_score?: number;
  diversity_analysis?: string;
  blind_spots?: string[];
  key_insight?: string;
}
interface Result {
  scan_id?: string;
  personas: Persona[];
  focus_group_summary?: string;
  interaction_dynamics?: Dynamics;
  metadata?: Event;
  articles?: SourceArticle[];
  article_uris?: string[];
}
interface Settings { max_personas: number; min_evidence_threshold: number; include_demographics: boolean; include_psychographics: boolean; include_voice: boolean; days_back: number }

const STAGES: Stage[] = [
  { id: 'discovery', label: 'Discovery', from: 0, to: 0.2 },
  { id: 'clustering', label: 'Clustering', from: 0.2, to: 0.45 },
  { id: 'profiling', label: 'Profiling', from: 0.45, to: 0.8 },
  { id: 'synthesis', label: 'Synthesis', from: 0.8, to: 1 },
];
// days_back: the server always took 30 because the old page never sent it
const DEFAULTS: Settings = { max_personas: 6, min_evidence_threshold: 2, include_demographics: true, include_psychographics: true, include_voice: true, days_back: 30 };
const DAYS = [7, 30, 90, 180, 365].map((d) => ({ value: String(d), label: `Last ${d} days` }));
const toResult = (e: Event): Result => ({
  scan_id: e.scan_id, personas: e.personas ?? [], focus_group_summary: e.focus_group_summary, interaction_dynamics: e.interaction_dynamics,
  metadata: e.metadata, articles: e.articles ?? [], article_uris: e.article_uris ?? [],
});
const words = (v: unknown) => (typeof v === 'string' ? v.replace(/_/g, ' ') : v == null ? '' : String(v));

function SettingsForm({ s, set }: { s: Settings; set: (p: Partial<Settings>) => void }) {
  return (
    <Stack gap="md">
      <Grid columns={3} stackAt="small" gap="md">
        <TextField label="Max personas" type="number" min={1} max={6} value={String(s.max_personas)} onChange={(v) => set({ max_personas: Math.max(1, Math.min(6, Number(v) || 1)) })} />
        <TextField label="Evidence threshold" type="number" min={1} max={5} value={String(s.min_evidence_threshold)} onChange={(v) => set({ min_evidence_threshold: Math.max(1, Math.min(5, Number(v) || 1)) })} hint="Mentions a persona needs" />
        <Select label="Articles from" fullWidth options={DAYS} value={String(s.days_back ?? 30)} onValueChange={(v) => set({ days_back: Number(v) })} />
      </Grid>
      <div>
        <Checkbox label="Demographics" checked={s.include_demographics} onCheckedChange={(v) => set({ include_demographics: v })} />
        <Checkbox label="Psychographics" checked={s.include_psychographics} onCheckedChange={(v) => set({ include_psychographics: v })} />
        <Checkbox label="Voice and typical questions" checked={s.include_voice} onCheckedChange={(v) => set({ include_voice: v })} />
      </div>
    </Stack>
  );
}

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <Stack gap="sm">
      <Eyebrow as="h4">{title}</Eyebrow>
      <Stack as="ul" gap="sm" label={title}>{items.map((x, i) => <li key={i}><Text variant="description" as="span">{x}</Text></li>)}</Stack>
    </Stack>
  );
}

// Technology stance coloured as the old cards did, and risk tolerance as a bar (green low, red high)
const STANCE_TONE: Record<string, 'error' | 'warning' | 'success' | 'info'> = { skeptic: 'error', pragmatist: 'warning', enthusiast: 'success', evangelist: 'info' };
const pctOf = (v: unknown) => Math.round((Number(v) || 0) * (Number(v) > 1 ? 1 : 100));

function PersonaCard({ p, onNotes }: { p: Persona; onNotes: (notes: string) => void }) {
  return (
    <ArticleCard
      as="li"
      variant="card"
      expandFullWidth
      flag={<Chip size="sm" tone="neutral">{`Confidence ${Math.round((Number(p.confidence_score) || 0) * (p.confidence_score > 1 ? 1 : 100))}%`}</Chip>}
      meta={[p.archetype, p.user_notes && 'has notes'].filter(Boolean).join(' · ')}
      title={p.name}
      summary={
        <Stack gap="sm">
          <Text variant="label" as="span">{[p.role_title, p.sector, words(p.experience_level)].filter(Boolean).join(' · ')}</Text>
          {p.technology_stance && (
            <Stack direction="row" gap="sm">
              <Chip size="sm" tone={STANCE_TONE[String(p.technology_stance).toLowerCase()] ?? 'neutral'}>{`Technology: ${words(p.technology_stance)}`}</Chip>
            </Stack>
          )}
          {p.risk_tolerance != null && (
            <Meter label={`${p.name} risk tolerance`} value={pctOf(p.risk_tolerance)} valueText={`Risk tolerance ${pctOf(p.risk_tolerance)}%`} tone={pctOf(p.risk_tolerance) < 30 ? 'success' : pctOf(p.risk_tolerance) < 70 ? 'warning' : 'error'} />
          )}
          <Stack direction="row" gap="sm">
            {(p.primary_values ?? []).slice(0, 4).map((v: string) => <Chip key={v} size="sm" tone="muted">{v}</Chip>)}
          </Stack>
          {(p.primary_concerns ?? []).length > 0 && <Text variant="caption" as="span">{`Concerns: ${p.primary_concerns.slice(0, 2).join('; ')}`}</Text>}
        </Stack>
      }
      details={
        <Stack gap="md">
          <LineItems
            label={`${p.name} profile`}
            items={[
              ['Change receptivity', p.change_receptivity], ['Technology stance', p.technology_stance], ['Decision style', p.decision_style],
              ['Risk tolerance', p.risk_tolerance != null ? `${Math.round(Number(p.risk_tolerance) * (p.risk_tolerance > 1 ? 1 : 100))}%` : null],
              ['Decision authority', p.decision_authority], ['Time horizon', p.time_horizon_focus], ['Reads by', p.information_consumption],
              ['Trusts authority', p.authority_trust], ['Trusts media', p.media_trust], ['Prefers', p.communication_preference],
            ].filter(([, v]) => v != null && v !== '').map(([l, v]) => ({ id: String(l), label: String(l), amount: words(v) }))}
          />
          <List title="Concerns" items={p.primary_concerns} />
          <List title="Fear triggers" items={p.fear_triggers} />
          <List title="Opportunity interests" items={p.opportunity_interests} />
          {p.voice_description && <Stack gap="sm"><Eyebrow as="h4">Voice</Eyebrow><Text variant="description">{p.voice_description}</Text></Stack>}
          <List title="Typical questions" items={p.typical_questions} />
          <List title="What decides it for them" items={p.decision_factors} />
          <List title="How to influence them" items={p.influence_vectors} />
          <Text variant="caption">{`Derived from ${p.mention_count ?? 0} article mentions`}</Text>
          <TextArea label="Your notes" rows={2} value={p.user_notes ?? ''} onChange={onNotes} hint="Kept with this result in your browser and in saves." />
        </Stack>
      }
    />
  );
}

function toMarkdown(r: Result, topic: string) {
  const d = r.interaction_dynamics ?? {};
  const out = [`# Focus Group: ${topic}`, '', r.focus_group_summary ?? '', ''];
  if (d.key_insight) out.push(`**Key insight:** ${d.key_insight}`, '');
  r.personas.forEach((p) => {
    out.push(`## ${p.name} — ${p.archetype ?? ''}`, `${[p.role_title, p.sector].filter(Boolean).join(', ')}`, '');
    if (p.primary_concerns?.length) out.push('**Concerns**', ...p.primary_concerns.map((x: string) => `- ${x}`), '');
    if (p.typical_questions?.length) out.push('**Typical questions**', ...p.typical_questions.map((x: string) => `- ${x}`), '');
    if (p.influence_vectors?.length) out.push('**How to influence**', ...p.influence_vectors.map((x: string) => `- ${x}`), '');
    if (p.user_notes) out.push(`**Notes:** ${p.user_notes}`, '');
  });
  return out.join('\n');
}

export function FocusGroup({ config, notify, askConfirm }: ViewProps) {
  const gen = useGenerator<Result>({ url: '/api/focus-groups/scan', stages: STAGES, storageKey: 'aunoo.anticipate.fg', toResult });
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [tune, setTune] = useState(false);
  useEffect(() => {
    api<Partial<Settings>>('/api/focus-groups/config').then((c) => setS((x) => ({ ...x, ...c })), () => undefined);
  }, []);
  const set = (p: Partial<Settings>) => setS((x) => ({ ...x, ...p }));
  const r = gen.result;
  const d = r?.interaction_dynamics ?? {};
  const setNotes = (id: string, notes: string) => r && gen.setResult({ ...r, personas: r.personas.map((p) => (p.id === id ? { ...p, user_notes: notes, user_edited: true } : p)) });

  return (
    <>
      <GeneratorFrame<Result>
        title="Focus Group"
        icon="ChatCentered"
        description="Synthetic stakeholder personas drawn from who is speaking in the articles."
        topic={config.topic}
        gen={gen}
        stages={STAGES}
        summary={`Up to ${s.max_personas} personas · evidence ≥ ${s.min_evidence_threshold} · last ${s.days_back ?? 30} days`}
        settings={<SettingsForm s={s} set={set} />}
        generateLabel="Generate focus group"
        onGenerate={() => void gen.run({ topic: config.topic, ...s })}
        onTune={() => setTune(true)}
        liveStats={[gen.stats.mentions_found != null && `${gen.stats.mentions_found} mentions`, gen.stats.clusters_formed != null && `${gen.stats.clusters_formed} clusters`, gen.stats.personas_created != null && `${gen.stats.personas_created} personas`].filter(Boolean).join(' · ') || undefined}
        emptyText="Generate personas for this topic. It needs at least 5 articles in the window and takes a few minutes."
        actions={
          r && (
            <>
              <Button variant="ghost" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => window.print()}>PDF</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(toMarkdown(r, config.topic), `focus-group-${config.topic}.md`, 'text/markdown')}>Markdown</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(JSON.stringify(r, null, 2), `focus-group-${config.topic}.json`, 'application/json')}>JSON</Button>
            </>
          )
        }
        saved={{ base: '/api/focus-groups', listKey: 'saved_focus_groups', loadKey: 'focus_group' }}
        fromSaved={(e) => ({
          scan_id: e.scan_id as string, personas: (e.personas as Persona[]) ?? [], focus_group_summary: e.focus_group_summary as string,
          interaction_dynamics: e.interaction_dynamics as Dynamics, metadata: e.metadata as Event, articles: [], article_uris: (e.article_uris as string[]) ?? [],
        })}
        toSave={(name, description) => ({
          topic: config.topic, name, description, personas: r?.personas ?? [], focus_group_summary: r?.focus_group_summary ?? '',
          interaction_dynamics: r?.interaction_dynamics ?? {}, config: s, metadata: r?.metadata ?? {}, articles_used: r?.articles?.length ?? 0,
          // the old save left these out, so loaded focus groups had no references
          article_uris: r?.article_uris ?? [], model_used: (r?.metadata?.models ?? []).join(', ') || undefined, persona_count: r?.personas.length ?? 0,
        })}
        notify={notify}
        askConfirm={askConfirm}
      >
        {r && (
          <>
            {r.focus_group_summary && <Panel title="Focus group overview"><Text variant="description">{r.focus_group_summary}</Text></Panel>}
            <Panel title="Dynamics">
              <Stack gap="md">
                {d.diversity_score != null && <Meter label="Diversity of views" value={Math.round(d.diversity_score * (d.diversity_score > 1 ? 1 : 100))} valueText={`${Math.round(d.diversity_score * (d.diversity_score > 1 ? 1 : 100))}% diverse`} />}
                {d.key_insight && <Text><strong>Key insight:</strong> {d.key_insight}</Text>}
                <Grid columns={2} stackAt="small" gap="sm">
                  <Stack gap="sm">
                    <Eyebrow as="h3"><Icon name="CheckCircle" size="sm" /> Where they agree</Eyebrow>
                    {(d.consensus_areas ?? []).map((c) => <SettingRow key={c.topic} title={c.topic} description={c.description} />)}
                  </Stack>
                  <Stack gap="sm">
                    <Eyebrow as="h3"><Icon name="Warning" size="sm" /> Where they clash</Eyebrow>
                    {(d.tension_points ?? []).map((c) => <SettingRow key={c.topic} title={c.topic} description={c.description} />)}
                  </Stack>
                </Grid>
                {d.power_dynamics && (
                  <LineItems
                    label="Power dynamics"
                    items={[
                      ...(d.power_dynamics.most_influential ? [{ id: 'inf', label: 'Most influential', amount: d.power_dynamics.most_influential }] : []),
                      ...(d.power_dynamics.most_vulnerable ? [{ id: 'vul', label: 'Most vulnerable', amount: d.power_dynamics.most_vulnerable }] : []),
                      ...(d.power_dynamics.likely_coalition?.length ? [{ id: 'coal', label: 'Likely coalition', amount: d.power_dynamics.likely_coalition.join(', ') }] : []),
                    ]}
                  />
                )}
                {d.diversity_analysis && <Text variant="description">{d.diversity_analysis}</Text>}
                <List title="Blind spots" items={d.blind_spots} />
              </Stack>
            </Panel>
            <Panel title={`Stakeholder personas (${r.personas.length})`}>
              <Grid as="ul" columns={2} gap="sm" label="Personas">
                {r.personas.map((p) => <PersonaCard key={p.id} p={p} onNotes={(n) => setNotes(p.id, n)} />)}
              </Grid>
            </Panel>
            <SourceArticles articles={r.articles} name={`focus-group-${config.topic}`} />
          </>
        )}
      </GeneratorFrame>
      <GeneratorTune
        open={tune}
        onOpenChange={setTune}
        title="Focus Group"
        base="/api/focus-groups"
        notify={notify}
        settings={(c, setC) => <SettingsForm s={{ ...DEFAULTS, ...c } as Settings} set={setC} />}
        onSaved={(c) => setS((x) => ({ ...x, ...c }))}
      />
    </>
  );
}
