import { useEffect, useState } from 'react';
import {
  ArticleCard, Button, Checkbox, Chip, Eyebrow, Grid, Icon, LineItems, Meter, Panel, Select, Stack, Text, TextField,
} from '@aunoo/ui';
import { api } from '../../shell';
import { GeneratorFrame } from '../components/GeneratorFrame';
import { SourceArticles, type SourceArticle } from '../components/SourceArticles';
import { saveText } from '../lib/download';
import { useGenerator, type Event, type Stage } from '../lib/generator';
import { GeneratorTune } from '../overlays/GeneratorTune';
import type { ViewProps } from './types';

interface Scenario {
  id: string;
  category: 'black_swan' | 'contrarian' | 'wild_card';
  title: string;
  subtitle?: string;
  description: string;
  probability?: string;
  impact_rating?: number;
  time_horizon?: string;
  weak_signals?: string[];
  amplification_path?: string;
  trigger_events?: string[];
  early_warning_signs?: string[];
  strategic_implications?: string;
  preparation_actions?: string[];
  source_trends?: string[];
  source_consensus?: string[];
}
interface Result {
  scan_id?: string;
  scenarios: Scenario[];
  metadata?: { signals_detected?: number; pathways_explored?: number; scenarios_generated?: number; generated_at?: string; models?: string[]; warnings?: string[]; config?: Event };
  articles?: SourceArticle[];
  article_uris?: string[];
}
interface Settings { scenario_count: number; time_horizon: 'near' | 'mid' | 'long'; include_black_swans: boolean; include_contrarian: boolean; include_wild_cards: boolean }

const STAGES: Stage[] = [
  { id: 'weak_signals', label: 'Weak signals', from: 0, to: 0.2 },
  { id: 'amplification', label: 'Amplification', from: 0.2, to: 0.45 },
  { id: 'scenario_building', label: 'Scenario building', from: 0.45, to: 0.8 },
  { id: 'implications', label: 'Implications', from: 0.8, to: 1 },
];
const HORIZONS = [
  { value: 'near', label: 'Near (0–2 years)' },
  { value: 'mid', label: 'Mid (2–5 years)' },
  { value: 'long', label: 'Long (5–10+ years)' },
];
const CATEGORIES = [
  { id: 'black_swan', label: 'Black Swan Events', key: 'include_black_swans', icon: 'Warning' },
  { id: 'contrarian', label: 'Contrarian Analysis', key: 'include_contrarian', icon: 'ArrowsClockwise' },
  { id: 'wild_card', label: 'Wild Card Futures', key: 'include_wild_cards', icon: 'Lightning' },
] as const;
// Probability coloured by level, and impact as a bar, as the old scenario cards showed them
const PROBABILITY_TONE: Record<string, 'muted' | 'info' | 'warning'> = { very_low: 'muted', low: 'info', moderate: 'warning' };
const impactTone = (n: number) => (n >= 8 ? 'error' : n >= 5 ? 'warning' : 'neutral') as 'error' | 'warning' | 'neutral';
const DEFAULTS: Settings = { scenario_count: 5, time_horizon: 'mid', include_black_swans: true, include_contrarian: true, include_wild_cards: true };
const toResult = (e: Event): Result => ({ scan_id: e.scan_id, scenarios: e.scenarios ?? [], metadata: e.metadata, articles: e.articles ?? [] });

function SettingsForm({ s, set }: { s: Settings; set: (p: Partial<Settings>) => void }) {
  return (
    <Stack gap="md">
      <Grid columns={2} stackAt="small" gap="md">
        <TextField label="Number of scenarios" type="number" min={1} max={10} value={String(s.scenario_count)} onChange={(v) => set({ scenario_count: Math.max(1, Math.min(10, Number(v) || 1)) })} />
        <Select label="Time horizon" fullWidth options={HORIZONS} value={s.time_horizon} onValueChange={(v) => set({ time_horizon: v as Settings['time_horizon'] })} />
      </Grid>
      <div>
        {CATEGORIES.map((c) => <Checkbox key={c.id} label={c.label} checked={s[c.key]} onCheckedChange={(v) => set({ [c.key]: v } as Partial<Settings>)} />)}
      </div>
    </Stack>
  );
}

function ScenarioCard({ s }: { s: Scenario }) {
  const list = (title: string, items?: string[], numbered = false) =>
    items?.length ? (
      <Stack gap="sm">
        <Eyebrow as="h4">{title}</Eyebrow>
        <Stack as="ul" gap="sm" label={title}>
          {items.map((x, i) => <li key={i}><Text variant="description" as="span">{numbered ? `${i + 1}. ${x}` : x}</Text></li>)}
        </Stack>
      </Stack>
    ) : null;
  return (
    <ArticleCard
      as="li"
      variant="card"
      expandFullWidth
      flag={<Chip size="sm" tone={(s.probability && PROBABILITY_TONE[s.probability]) || 'neutral'}>{s.probability ? `${s.probability.replace('_', ' ')} probability` : 'Scenario'}</Chip>}
      meta={[s.time_horizon && `Time horizon: ${s.time_horizon}`].filter(Boolean).join(' · ')}
      title={s.title}
      summary={
        <Stack gap="sm">
          {s.impact_rating != null && (
            <Meter label={`${s.title} impact`} value={Number(s.impact_rating)} max={10} valueText={`Impact ${s.impact_rating}/10`} tone={impactTone(Number(s.impact_rating))} />
          )}
          {s.subtitle && <Text variant="label" as="span">{s.subtitle}</Text>}
          <Text variant="description" as="span">{s.description}</Text>
          {(s.trigger_events?.length ?? 0) > 0 && <Text variant="caption" as="span">{`Triggers: ${s.trigger_events!.slice(0, 2).join('; ')}`}</Text>}
        </Stack>
      }
      details={
        <Stack gap="md">
          {list('Trigger events', s.trigger_events)}
          {list('Weak signals detected', s.weak_signals)}
          {s.amplification_path && <Stack gap="sm"><Eyebrow as="h4">Amplification path</Eyebrow><Text variant="description">{s.amplification_path}</Text></Stack>}
          {list('Early warning signs', s.early_warning_signs)}
          {s.strategic_implications && <Stack gap="sm"><Eyebrow as="h4">Strategic implications</Eyebrow><Text variant="description">{s.strategic_implications}</Text></Stack>}
          {list('Preparation actions', s.preparation_actions, true)}
          {((s.source_trends?.length ?? 0) > 0 || (s.source_consensus?.length ?? 0) > 0) && (
            <Text variant="caption">{`Derived from — trends: ${(s.source_trends ?? []).join(', ') || '—'}; consensus: ${(s.source_consensus ?? []).join(', ') || '—'}`}</Text>
          )}
        </Stack>
      }
    />
  );
}

function toMarkdown(r: Result, topic: string) {
  const out = [`# Extreme Outlier Scenarios: ${topic}`, '', `Generated ${r.metadata?.generated_at ?? ''}`, ''];
  CATEGORIES.forEach((c) => {
    const items = r.scenarios.filter((s) => s.category === c.id);
    if (!items.length) return;
    out.push(`## ${c.label}`, '');
    items.forEach((s) => {
      out.push(`### ${s.title}`, s.subtitle ? `*${s.subtitle}*` : '', '', s.description, '');
      if (s.probability || s.impact_rating) out.push(`Probability: ${s.probability ?? '—'} · Impact: ${s.impact_rating ?? '—'}/10 · ${s.time_horizon ?? ''}`, '');
      if (s.trigger_events?.length) out.push('**Trigger events**', ...s.trigger_events.map((x) => `- ${x}`), '');
      if (s.early_warning_signs?.length) out.push('**Early warning signs**', ...s.early_warning_signs.map((x) => `- ${x}`), '');
      if (s.strategic_implications) out.push('**Strategic implications**', s.strategic_implications, '');
      if (s.preparation_actions?.length) out.push('**Preparation actions**', ...s.preparation_actions.map((x, i) => `${i + 1}. ${x}`), '');
    });
  });
  return out.join('\n');
}

export function ExtremeOutliers({ config, notify, askConfirm }: ViewProps) {
  const gen = useGenerator<Result>({ url: '/api/eos/scan', stages: STAGES, storageKey: 'aunoo.anticipate.eos', toResult });
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [tune, setTune] = useState(false);
  useEffect(() => {
    api<Partial<Settings>>('/api/eos/config').then((c) => setS((x) => ({ ...x, ...c })), () => undefined);
  }, []);
  const set = (p: Partial<Settings>) => setS((x) => ({ ...x, ...p }));
  const r = gen.result;
  const m = r?.metadata;

  return (
    <>
      <GeneratorFrame<Result>
        title="Extreme Outliers"
        icon="Lightning"
        description="Low-probability, high-impact scenarios that break the consensus."
        topic={config.topic}
        gen={gen}
        stages={STAGES}
        summary={`${s.scenario_count} scenarios · ${HORIZONS.find((h) => h.value === s.time_horizon)?.label} · ${CATEGORIES.filter((c) => s[c.key]).map((c) => c.label.split(' ')[0]).join(', ') || 'no categories'}`}
        settings={<SettingsForm s={s} set={set} />}
        generateLabel="Generate scenarios"
        onGenerate={() => void gen.run({ topic: config.topic, ...s })}
        onTune={() => setTune(true)}
        liveStats={[gen.stats.signals_detected != null && `${gen.stats.signals_detected} signals`, gen.stats.pathways_identified != null && `${gen.stats.pathways_identified} pathways`, gen.stats.scenarios_built != null && `${gen.stats.scenarios_built} scenarios`].filter(Boolean).join(' · ') || undefined}
        emptyText="Generate outlier scenarios for this topic from the last 30 days of articles. It takes a few minutes."
        actions={
          r && (
            <>
              <Button variant="ghost" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => window.print()}>PDF</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(toMarkdown(r, config.topic), `extreme-outliers-${config.topic}.md`, 'text/markdown')}>Markdown</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(JSON.stringify(r, null, 2), `extreme-outliers-${config.topic}.json`, 'application/json')}>JSON</Button>
            </>
          )
        }
        saved={{ base: '/api/eos', listKey: 'saved_eos', loadKey: 'eos' }}
        fromSaved={(e) => ({ scan_id: e.scan_id as string, scenarios: (e.scenarios as Scenario[]) ?? [], metadata: e.metadata as Result['metadata'], articles: [], article_uris: e.article_uris as string[] })}
        toSave={(name, description) => ({
          topic: config.topic, name, description, scenarios: r?.scenarios ?? [], metadata: m ?? {},
          // snake_case, matching metadata.config (the old save sent camelCase keys)
          config: m?.config ?? s,
          articles_used: r?.articles?.length ?? 0, article_uris: (r?.articles ?? []).map((a) => a.uri).filter(Boolean),
          model_used: (m?.models ?? []).join(', ') || undefined, time_horizon: s.time_horizon, scenario_count: r?.scenarios.length ?? 0,
        })}
        notify={notify}
        askConfirm={askConfirm}
      >
        {r && (
          <>
            <LineItems
              label="Run"
              items={[
                { id: 'signals', label: 'Signals detected', amount: String(m?.signals_detected ?? '—') },
                { id: 'paths', label: 'Pathways explored', amount: String(m?.pathways_explored ?? '—') },
                { id: 'count', label: 'Scenarios', amount: String(m?.scenarios_generated ?? r.scenarios.length) },
                ...(m?.generated_at ? [{ id: 'at', label: 'Generated', amount: new Date(m.generated_at).toLocaleString('en-GB') }] : []),
                ...(m?.models?.length ? [{ id: 'models', label: 'Models', amount: m.models.join(', ') }] : []),
              ]}
            />
            {(m?.warnings ?? []).map((w) => <Text key={w} variant="hint">{`Note: ${w}`}</Text>)}
            {CATEGORIES.map((c) => {
              const items = r.scenarios.filter((x) => x.category === c.id);
              if (!items.length) return null;
              return (
                <Panel key={c.id} title={<><Icon name={c.icon} size="sm" /> {`${c.label} (${items.length})`}</>}>
                  <Grid as="ul" columns={2} gap="sm" label={c.label}>
                    {items.map((x) => <ScenarioCard key={x.id ?? x.title} s={x} />)}
                  </Grid>
                </Panel>
              );
            })}
            {!r.scenarios.length && <Text>No outlier scenarios were produced.</Text>}
            <SourceArticles articles={r.articles} name={`extreme-outliers-${config.topic}`} />
          </>
        )}
      </GeneratorFrame>
      <GeneratorTune
        open={tune}
        onOpenChange={setTune}
        title="Extreme Outliers"
        base="/api/eos"
        notify={notify}
        settings={(c, setC) => <SettingsForm s={{ ...DEFAULTS, ...c } as Settings} set={setC} />}
        onSaved={(c) => setS((x) => ({ ...x, ...c }))}
      />
    </>
  );
}
