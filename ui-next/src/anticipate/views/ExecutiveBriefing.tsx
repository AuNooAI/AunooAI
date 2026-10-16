import { useEffect, useRef, useState } from 'react';
import {
  ArticleCard, Banner, Button, Checkbox, Chip, Dialog, DialogClose, Eyebrow, Grid, Icon, Meter, Panel, Select, SettingRow, Skeleton, Stack, Text,
  TextArea, TextField, TextLink,
} from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { GeneratorFrame } from '../components/GeneratorFrame';
import { saveText } from '../lib/download';
import { useGenerator, type Event, type Stage } from '../lib/generator';
import { GeneratorTune } from '../overlays/GeneratorTune';
import type { ViewProps } from './types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Article = Record<string, any> & { title: string };
interface Result {
  scan_id?: string;
  articles: Article[];
  briefing_summary?: string;
  themes?: { theme_name: string; description: string; strategic_implication?: string }[];
  priority_actions?: { action: string; urgency?: string; rationale?: string }[];
  risk_summary?: { overall_risk_level?: string; key_risks?: string[]; mitigation_opportunities?: string[] };
  opportunity_summary?: { overall_opportunity_level?: string; key_opportunities?: string[]; action_windows?: string[] };
  focus_areas?: { area: string; reason?: string; time_sensitivity?: string }[];
  podcast_script?: string;
  metadata?: Event;
}
interface Persona { priorities?: string | string[]; risk_appetite?: string; focus?: string | string[] }
interface Settings { persona: string; article_count: number; days_back: number; include_podcast_script: boolean; podcast_duration: 'short' | 'medium' | 'long' }

const STAGES: Stage[] = [
  { id: 'selection', label: 'Selecting articles', from: 0, to: 0.25 },
  { id: 'analysis', label: 'Analysing', from: 0.25, to: 0.7 },
  { id: 'synthesis', label: 'Synthesis', from: 0.7, to: 0.9 },
  // The old progress weights left this stage out, so it showed 0%
  { id: 'podcast', label: 'Podcast script', from: 0.9, to: 1 },
];
/** The server's own persona keys; they're uppercase (the old page sent 'ceo', which fell back to CEO for every persona). */
const BUILT_IN = ['CEO', 'CMO', 'CTO', 'CISO'];
const DAYS = [1, 7, 30, 60, 90].map((d) => ({ value: String(d), label: d === 1 ? 'Last 24 hours' : `Last ${d} days` }));
const DURATIONS = [
  { value: 'short', label: 'Short (2–3 min)' },
  { value: 'medium', label: 'Medium (4–5 min)' },
  { value: 'long', label: 'Long (7–10 min)' },
];
const toResult = (e: Event): Result => ({
  scan_id: e.scan_id, articles: e.articles ?? [], briefing_summary: e.briefing_summary, themes: e.themes, priority_actions: e.priority_actions,
  risk_summary: e.risk_summary, opportunity_summary: e.opportunity_summary, focus_areas: e.focus_areas, podcast_script: e.podcast_script, metadata: e.metadata,
});
const asText = (v: string | string[] | undefined) => (Array.isArray(v) ? v.join(', ') : v ?? '');
// Levels and signal strength coloured as the old briefing did
const levelTone = (v?: string, kind: 'risk' | 'opportunity' = 'risk') => {
  const l = (v ?? '').toLowerCase();
  if (/high|critical|significant/.test(l)) return kind === 'risk' ? 'error' : 'success';
  if (/medium|moderate/.test(l)) return 'warning';
  return 'neutral';
};
const SIGNAL_TONE: Record<string, 'info' | 'neutral' | 'muted'> = { strong: 'info', moderate: 'neutral', weak: 'muted' };

const TONE: Record<string, 'error' | 'warning' | 'success' | 'neutral'> = { risk: 'warning', opportunity: 'success', mixed: 'neutral' };

function PodcastDialog({ open, onOpenChange, result, topic, model, onScript }: { open: boolean; onOpenChange: (o: boolean) => void; result: Result; topic: string; model: string; onScript: (s: string) => void }) {
  const [script, setScript] = useState(result.podcast_script ?? '');
  const [title, setTitle] = useState(`${topic} — executive briefing`);
  const [voices, setVoices] = useState<{ voice_id: string; name: string; category?: string }[]>([]);
  const [voice, setVoice] = useState('');
  const [busy, setBusy] = useState<'script' | 'audio' | null>(null);
  const [audio, setAudio] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poll = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(poll.current), []);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setScript(result.podcast_script ?? '');
    api<{ voice_id: string; name: string; category?: string }[]>('/api/available_voices').then(
      (v) => {
        setVoices(v);
        setVoice((v.find((x) => x.category === 'premade') ?? v[0])?.voice_id ?? '');
      },
      (e) => setError(`Voices unavailable: ${errorText(e)}`),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const writeScript = async () => {
    setBusy('script');
    setError(null);
    try {
      const r = await api<{ script: string }>('/api/executive-briefing/generate-podcast-script', {
        method: 'POST',
        json: {
          topic: topic || 'Intelligence Report', briefing_summary: result.briefing_summary ?? '', themes: (result.themes ?? []).slice(0, 5),
          priority_actions: (result.priority_actions ?? []).slice(0, 5),
          articles: result.articles.slice(0, 6).map((a) => ({ title: a.title, executive_takeaway: a.executive_takeaway, summary: a.summary, strategic_relevance: a.strategic_relevance })),
          duration: result.metadata?.config?.podcast_duration ?? 'short', model,
        },
      });
      setScript(r.script);
      onScript(r.script);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const makeAudio = async () => {
    setBusy('audio');
    setError(null);
    setAudio(null);
    try {
      const r = await api<{ podcast_id: string }>('/api/generate_tts_podcast', {
        method: 'POST',
        json: { podcast_name: 'Executive Briefing', episode_title: title.trim() || 'Executive briefing', script, mode: 'bulletin', duration: result.metadata?.config?.podcast_duration ?? 'short', host_voice_id: voice },
      });
      const started = Date.now();
      const tick = async () => {
        try {
          const s = await api<{ status: string; audio_url?: string; error?: string }>(`/api/podcast/status/${r.podcast_id}`);
          if (s.status === 'completed' && s.audio_url) {
            setAudio(s.audio_url);
            setBusy(null);
            return;
          }
          if (s.status === 'failed') throw new Error(s.error || 'Audio generation failed');
          // Five minutes, then give up (the old timeout read a stale flag and never fired)
          if (Date.now() - started > 300000) throw new Error('Audio is taking longer than five minutes; check back later.');
          poll.current = window.setTimeout(tick, 2000);
        } catch (e) {
          setError(errorText(e));
          setBusy(null);
        }
      };
      void tick();
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  };

  const words = script.trim() ? script.trim().split(/\s+/).length : 0;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Podcast"
      description="Write a spoken script from this briefing, edit it, then turn it into audio."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
          <Button variant="secondary" size="lg" busy={busy === 'script'} disabled={busy !== null} onClick={writeScript}>{script ? 'Rewrite script' : 'Write script'}</Button>
          <Button size="lg" busy={busy === 'audio'} disabled={!script.trim() || !voice || busy !== null} onClick={makeAudio}>Generate audio</Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" icon="WarningCircle" title="That didn’t work" description={error} />}
        <Grid columns={2} stackAt="small" gap="md">
          <TextField label="Episode title" value={title} onChange={setTitle} />
          <Select label="Voice" fullWidth placeholder={voices.length ? 'Choose a voice' : 'Loading voices…'} options={voices.map((v) => ({ value: v.voice_id, label: `${v.name}${v.category ? ` (${v.category})` : ''}` }))} value={voice} onValueChange={setVoice} />
        </Grid>
        {busy === 'script' && !script ? <Skeleton lines={6} /> : <TextArea label="Script" rows={14} value={script} onChange={(v) => { setScript(v); onScript(v); }} hint={`${words} words`} />}
        {busy === 'audio' && <Text variant="hint">Generating audio — usually a minute or two.</Text>}
        {audio && (
          <Stack gap="sm">
            <audio controls src={audio} />
            <TextLink href={audio} external>Download audio</TextLink>
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}

function toMarkdown(r: Result, topic: string, persona: string) {
  const out = [`# Executive Briefing: ${topic}`, '', `For: ${persona} · ${r.articles.length} articles · ${r.metadata?.generated_at ?? ''}`, ''];
  if (r.briefing_summary) out.push('## Summary', r.briefing_summary, '');
  if (r.themes?.length) out.push('## Key themes', ...r.themes.flatMap((t) => [`### ${t.theme_name}`, t.description, t.strategic_implication ? `*Implication:* ${t.strategic_implication}` : '', '']));
  if (r.priority_actions?.length) out.push('## Priority actions', ...r.priority_actions.map((a) => `- **${a.urgency ?? ''}** ${a.action}${a.rationale ? ` — ${a.rationale}` : ''}`), '');
  out.push('## Articles', '');
  r.articles.forEach((a) => out.push(`### ${a.title}`, `${a.source ?? ''} · ${a.date ?? ''} · ${a.url ?? ''}`, '', a.executive_takeaway ?? '', '', a.user_notes ? `*Notes:* ${a.user_notes}` : '', ''));
  return out.join('\n');
}

export function ExecutiveBriefing({ config, notify, askConfirm }: ViewProps) {
  const gen = useGenerator<Result>({ url: '/api/executive-briefing/scan', stages: STAGES, storageKey: 'aunoo.anticipate.eb', toResult });
  const [personas, setPersonas] = useState<Record<string, Persona>>({});
  const [s, setS] = useState<Settings>({ persona: 'CEO', article_count: 6, days_back: 7, include_podcast_script: false, podcast_duration: 'short' });
  const [tune, setTune] = useState(false);
  const [podcast, setPodcast] = useState(false);
  useEffect(() => {
    api<{ personas?: Record<string, Persona>; default_persona?: string; default_article_count?: number; default_days_back?: number }>('/api/executive-briefing/config').then(
      (c) => {
        setPersonas(c.personas ?? {});
        setS((x) => ({
          ...x,
          persona: c.default_persona ? (BUILT_IN.includes(c.default_persona.toUpperCase()) ? c.default_persona.toUpperCase() : c.default_persona) : x.persona,
          article_count: c.default_article_count ?? x.article_count,
          // default_days_back was never applied by the old page
          days_back: c.default_days_back ?? x.days_back,
        }));
      },
      () => undefined,
    );
  }, []);
  const set = (p: Partial<Settings>) => setS((x) => ({ ...x, ...p }));
  const personaKeys = Array.from(new Set([...BUILT_IN, ...Object.keys(personas).filter((k) => !BUILT_IN.includes(k.toUpperCase()))]));
  const isCustom = !BUILT_IN.includes(s.persona);
  const custom = isCustom ? personas[s.persona] : undefined;
  const r = gen.result;

  const settingsForm = (
    <Stack gap="md">
      <Grid columns={3} stackAt="small" gap="md">
        <Select label="Persona" fullWidth options={personaKeys.map((k) => ({ value: k, label: k }))} value={s.persona} onValueChange={(v) => set({ persona: v })} />
        <TextField label="Articles" type="number" min={1} max={8} value={String(s.article_count)} onChange={(v) => set({ article_count: Math.max(1, Math.min(8, Number(v) || 1)) })} />
        <Select label="Articles from" fullWidth options={DAYS} value={String(s.days_back)} onValueChange={(v) => set({ days_back: Number(v) })} />
      </Grid>
      <Stack direction="row" gap="md">
        <Checkbox label="Write a podcast script with the briefing" checked={s.include_podcast_script} onCheckedChange={(v) => set({ include_podcast_script: v })} />
        {s.include_podcast_script && <Select label="Podcast length" options={DURATIONS} value={s.podcast_duration} onValueChange={(v) => set({ podcast_duration: v as Settings['podcast_duration'] })} />}
      </Stack>
      {custom && <Text variant="hint">{`${s.persona}: ${asText(custom.focus) || asText(custom.priorities)}`}</Text>}
    </Stack>
  );

  return (
    <>
      <GeneratorFrame<Result>
        title="Executive Briefing"
        icon="Notebook"
        description="A short briefing on the most important articles, written for one executive role."
        topic={config.topic}
        gen={gen}
        stages={STAGES}
        summary={`${s.persona} · ${s.article_count} articles · ${DAYS.find((d) => d.value === String(s.days_back))?.label ?? `${s.days_back} days`}${s.include_podcast_script ? ' · with podcast script' : ''}`}
        settings={settingsForm}
        generateLabel="Generate briefing"
        onGenerate={() =>
          void gen.run({
            topic: config.topic, persona: s.persona, article_count: s.article_count, days_back: s.days_back, include_synthesis: true,
            include_podcast_script: s.include_podcast_script, podcast_duration: s.podcast_duration,
            // Custom personas from Tune are sent as text, so they're actually used (the old page never sent them)
            custom_persona: custom ? { priorities: asText(custom.priorities), risk_appetite: custom.risk_appetite ?? 'moderate', focus: asText(custom.focus) } : undefined,
          })
        }
        onTune={() => setTune(true)}
        liveStats={[gen.stats.articles_selected != null && `${gen.stats.articles_selected} selected`, gen.stats.articles_analyzed != null && `${gen.stats.articles_analyzed} analysed`, gen.stats.article_title && `Now: ${gen.stats.article_title}`].filter(Boolean).join(' · ') || undefined}
        emptyText="Generate a briefing for this topic. It needs at least 3 articles in the window."
        actions={
          r && (
            <>
              <Button variant="ghost" size="sm" iconStart={<Icon name="SpeakerHigh" size="sm" />} onClick={() => setPodcast(true)}>Podcast</Button>
              <Button variant="ghost" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => window.print()}>PDF</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(toMarkdown(r, config.topic, s.persona), `executive-briefing-${config.topic}.md`, 'text/markdown')}>Markdown</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(JSON.stringify(r, null, 2), `executive-briefing-${config.topic}.json`, 'application/json')}>JSON</Button>
            </>
          )
        }
        // The briefing's own save/load (unreachable on the old page, whose Save stored trend data instead)
        saved={{ base: '/api/executive-briefing', listKey: 'saved_briefings', loadKey: 'briefing' }}
        fromSaved={(e) => ({
          scan_id: e.scan_id as string, articles: (e.articles as Article[]) ?? [], briefing_summary: e.briefing_summary as string, themes: e.themes as Result['themes'],
          priority_actions: e.priority_actions as Result['priority_actions'], metadata: e.metadata as Event,
          // Saved briefings don't keep these; the old loader filled in made-up "moderate" levels
          risk_summary: (e.metadata as Event)?.risk_summary, opportunity_summary: (e.metadata as Event)?.opportunity_summary, focus_areas: (e.metadata as Event)?.focus_areas,
        })}
        toSave={(name, description) => ({
          topic: config.topic, name, description, persona: s.persona, article_count: r?.articles.length ?? 0, articles: r?.articles ?? [],
          briefing_summary: r?.briefing_summary ?? '', themes: r?.themes ?? [], priority_actions: r?.priority_actions ?? [], config: s,
          // The save endpoint has no fields for these, so they ride in metadata and come back on load
          metadata: { ...(r?.metadata ?? {}), risk_summary: r?.risk_summary, opportunity_summary: r?.opportunity_summary, focus_areas: r?.focus_areas, podcast_script: r?.podcast_script },
          articles_used: r?.articles.length ?? 0, article_uris: (r?.articles ?? []).map((a) => a.uri).filter(Boolean),
        })}
        notify={notify}
        askConfirm={askConfirm}
      >
        {r && (
          <>
            <Panel title="Briefing" description={`For ${r.metadata?.persona ?? s.persona}`}>
              <Stack gap="md">
                {r.briefing_summary && <Text variant="description">{r.briefing_summary}</Text>}
                {(r.themes ?? []).length > 0 && (
                  <Stack gap="sm">
                    <Eyebrow as="h3">Key themes</Eyebrow>
                    <Grid as="ul" columns={2} gap="sm" label="Key themes">
                      {r.themes!.map((t) => <li key={t.theme_name}><SettingRow title={t.theme_name} description={t.description}>{t.strategic_implication && <Text variant="caption">{`Implication: ${t.strategic_implication}`}</Text>}</SettingRow></li>)}
                    </Grid>
                  </Stack>
                )}
                {(r.priority_actions ?? []).length > 0 && (
                  <Stack gap="sm">
                    <Eyebrow as="h3">Priority actions</Eyebrow>
                    <Stack as="ul" gap="sm" label="Priority actions">
                      {r.priority_actions!.map((a, i) => (
                        <li key={i}><SettingRow title={a.action} description={a.rationale} actions={a.urgency && <Chip size="sm" tone={a.urgency === 'immediate' ? 'warning' : 'neutral'}>{a.urgency.replace('_', ' ')}</Chip>} actionsPlacement="title" /></li>
                      ))}
                    </Stack>
                  </Stack>
                )}
                <Grid columns={2} stackAt="small" gap="sm">
                  {r.risk_summary && (
                    <SettingRow
                      title={<><Icon name="Warning" size="sm" /> Risks</>}
                      actionsPlacement="title"
                      actions={r.risk_summary.overall_risk_level && <Chip size="sm" tone={levelTone(r.risk_summary.overall_risk_level, 'risk')}>{`${r.risk_summary.overall_risk_level} risk`}</Chip>}
                    >
                      <Stack as="ul" gap="sm" label="Key risks">{(r.risk_summary.key_risks ?? []).map((x) => <li key={x}><Text variant="caption" as="span">{x}</Text></li>)}</Stack>
                    </SettingRow>
                  )}
                  {r.opportunity_summary && (
                    <SettingRow
                      title={<><Icon name="Sparkle" size="sm" /> Opportunities</>}
                      actionsPlacement="title"
                      actions={r.opportunity_summary.overall_opportunity_level && <Chip size="sm" tone={levelTone(r.opportunity_summary.overall_opportunity_level, 'opportunity')}>{`${r.opportunity_summary.overall_opportunity_level} opportunity`}</Chip>}
                    >
                      <Stack as="ul" gap="sm" label="Key opportunities">{(r.opportunity_summary.key_opportunities ?? []).map((x) => <li key={x}><Text variant="caption" as="span">{x}</Text></li>)}</Stack>
                    </SettingRow>
                  )}
                </Grid>
                {(r.focus_areas ?? []).length > 0 && (
                  <Stack gap="sm">
                    <Eyebrow as="h4">Focus areas</Eyebrow>
                    {/* The reasons run to a paragraph, too long for LineItems' right-hand amount column */}
                    <Stack as="ul" gap="sm" label="Focus areas">
                      {r.focus_areas!.map((f) => (
                        <li key={f.area}><SettingRow title={f.area} description={[f.reason, f.time_sensitivity].filter(Boolean).join(' · ') || undefined} /></li>
                      ))}
                    </Stack>
                  </Stack>
                )}
              </Stack>
            </Panel>
            <Panel title={`Analysed articles (${r.articles.length})`}>
              <Grid as="ul" columns={2} gap="sm" label="Articles">
                {r.articles.map((a, i) => (
                  <ArticleCard
                    key={`${i}-${a.uri ?? a.title}`}
                    as="li"
                    variant="card"
                    expandFullWidth
                    href={a.url || undefined}
                    flag={a.risk_opportunity && <Chip size="sm" tone={TONE[a.risk_opportunity] ?? 'neutral'}>{a.risk_opportunity}</Chip>}
                    meta={[a.source, a.date, a.time_horizon, a.category].filter(Boolean).join(' · ')}
                    tags={a.signal_strength && <Chip size="sm" tone={SIGNAL_TONE[String(a.signal_strength).toLowerCase()] ?? 'neutral'}>{`${a.signal_strength} signal`}</Chip>}
                    title={a.title}
                    summary={a.executive_takeaway || a.summary}
                    details={
                      <Stack gap="md">
                        {a.summary && a.executive_takeaway && <Text variant="description">{a.summary}</Text>}
                        {a.strategic_relevance && <Stack gap="sm"><Eyebrow as="h4">Why it matters</Eyebrow><Text variant="description">{a.strategic_relevance}</Text></Stack>}
                        {(a.executive_action ?? []).length > 0 && (
                          <Stack gap="sm"><Eyebrow as="h4">Recommended actions</Eyebrow><Stack as="ul" gap="sm" label="Recommended actions">{a.executive_action.map((x: string) => <li key={x}><Text variant="description" as="span">{x}</Text></li>)}</Stack></Stack>
                        )}
                        {a.scores && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Scores</Eyebrow>
                            {Object.entries(a.scores as Record<string, number>).map(([k, v]) => (
                              <Meter key={k} label={`${k.replace(/_/g, ' ')} score`} value={Number(v) || 0} max={5} valueText={`${k.replace(/_/g, ' ')} ${v}/5`} />
                            ))}
                          </Stack>
                        )}
                        <TextArea label="Your notes" rows={2} value={a.user_notes ?? ''} onChange={(v) => gen.setResult({ ...r, articles: r.articles.map((x, j) => (j === i ? { ...x, user_notes: v, user_edited: true } : x)) })} />
                      </Stack>
                    }
                  />
                ))}
              </Grid>
            </Panel>
            {r.articles.some((a) => a.url) && <Text variant="caption">{`Sources: ${r.articles.length} articles; open each card for its link.`}</Text>}
          </>
        )}
      </GeneratorFrame>
      {r && <PodcastDialog open={podcast} onOpenChange={setPodcast} result={r} topic={config.topic} model={config.model} onScript={(sc) => gen.setResult({ ...r, podcast_script: sc })} />}
      <GeneratorTune
        open={tune}
        onOpenChange={setTune}
        title="Executive Briefing"
        base="/api/executive-briefing"
        notify={notify}
        settings={(c, setC) => (
          <Grid columns={2} stackAt="small" gap="md">
            <Select label="Default persona" fullWidth options={personaKeys.map((k) => ({ value: k, label: k }))} value={String(c.default_persona ?? 'CEO').toUpperCase() === 'CEO' ? 'CEO' : String(c.default_persona ?? 'CEO')} onValueChange={(v) => setC({ default_persona: v })} />
            <TextField label="Default article count" type="number" min={1} max={8} value={String(c.default_article_count ?? 6)} onChange={(v) => setC({ default_article_count: Math.max(1, Math.min(8, Number(v) || 1)) })} />
          </Grid>
        )}
        onSaved={(c) => set({ persona: c.default_persona ?? s.persona, article_count: c.default_article_count ?? s.article_count })}
      />
    </>
  );
}
