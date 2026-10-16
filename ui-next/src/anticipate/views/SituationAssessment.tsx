import { useEffect, useState } from 'react';
import { Button, Grid, Icon, LineItems, Panel, Slider, Stack, Text, TextField } from '@aunoo/ui';
import { api } from '../../shell';
import { Markdown } from '../../shell/Markdown';
import { BriefView } from '../components/BriefView';
import { Disclosure } from '../components/Disclosure';
import { GeneratorFrame } from '../components/GeneratorFrame';
import { SourceArticles, type SourceArticle } from '../components/SourceArticles';
import { saveText } from '../lib/download';
import { useGenerator, type Event, type Stage } from '../lib/generator';
import { GeneratorTune } from '../overlays/GeneratorTune';
import type { ViewProps } from './types';

interface Result {
  scan_id?: string;
  brief: string;
  metadata?: { articles_collected?: number; articles_screened?: number; events_identified?: number; events_analyzed?: number; duration_seconds?: number; generated_at?: string };
  articles?: SourceArticle[];
}
interface Settings { hours_back: number; max_events: number; credibility_threshold: number }

const STAGES: Stage[] = [
  { id: 'discovery', label: 'Discovery', from: 0, to: 0.2 },
  { id: 'triage', label: 'Triage', from: 0.2, to: 0.35 },
  { id: 'deep_analysis', label: 'Deep analysis', from: 0.35, to: 0.8 },
  { id: 'synthesis', label: 'Writing the brief', from: 0.8, to: 1 },
];
const DEFAULTS: Settings = { hours_back: 24, max_events: 30, credibility_threshold: 60 };
const toResult = (e: Event): Result => ({ scan_id: e.scan_id, brief: e.brief ?? '', metadata: e.metadata, articles: e.articles ?? [] });

function SettingsForm({ s, set }: { s: Settings; set: (p: Partial<Settings>) => void }) {
  return (
    <Grid columns={3} stackAt="small" gap="md">
      <TextField label="Look back (hours)" type="number" min={1} max={168} value={String(s.hours_back)} onChange={(v) => set({ hours_back: Math.max(1, Math.min(168, Number(v) || 1)) })} />
      <TextField label="Events to analyse" type="number" min={5} max={100} value={String(s.max_events)} onChange={(v) => set({ max_events: Math.max(5, Math.min(100, Number(v) || 5)) })} />
      <Slider label="Minimum credibility" min={0} max={100} step={10} value={s.credibility_threshold} onValueChange={(v) => set({ credibility_threshold: v })} valueText={`${s.credibility_threshold}%`} />
    </Grid>
  );
}

export function SituationAssessment({ config, notify, askConfirm }: ViewProps) {
  const gen = useGenerator<Result>({ url: '/api/sio/scan', stages: STAGES, storageKey: 'aunoo.anticipate.sio', toResult });
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [tune, setTune] = useState(false);
  useEffect(() => {
    api<Partial<Settings>>('/api/sio/config').then((c) => setS((x) => ({ ...x, ...c })), () => undefined);
  }, []);
  const set = (p: Partial<Settings>) => setS((x) => ({ ...x, ...p }));
  const r = gen.result;
  const m = r?.metadata;

  return (
    <>
      <GeneratorFrame<Result>
        title="Situation Assessment"
        icon="Globe"
        description="An intelligence brief on what happened recently: events, threats, opportunities and actions."
        topic={config.topic}
        gen={gen}
        stages={STAGES}
        summary={`Last ${s.hours_back}h · ${s.max_events} events · credibility ≥ ${s.credibility_threshold}%`}
        settings={<SettingsForm s={s} set={set} />}
        generateLabel="Generate assessment"
        // profile_id isn't sent: the scan endpoint has no such field (the old page sent it and it was ignored)
        onGenerate={() => void gen.run({ topic: config.topic, ...s })}
        onTune={() => setTune(true)}
        liveStats={[gen.stats.articles_found != null && `${gen.stats.articles_found} articles`, gen.stats.passed_screening != null && `${gen.stats.passed_screening} passed screening`, gen.stats.events_identified != null && `${gen.stats.events_identified} events`, gen.stats.current_event && `Now: ${gen.stats.current_event}`].filter(Boolean).join(' · ') || undefined}
        livePreview={gen.text ? <Markdown text={gen.text} /> : undefined}
        emptyText="Generate a situation assessment of this topic’s recent events. It takes a few minutes; the brief appears as it’s written."
        actions={
          r && (
            <>
              <Button variant="ghost" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => window.print()}>PDF</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(r.brief, `situation-assessment-${config.topic}.md`, 'text/markdown')}>Markdown</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(JSON.stringify(r, null, 2), `situation-assessment-${config.topic}.json`, 'application/json')}>JSON</Button>
            </>
          )
        }
        notify={notify}
        askConfirm={askConfirm}
      >
        {r && (
          <>
            <LineItems
              label="Run"
              items={[
                { id: 'collected', label: 'Articles collected', amount: String(m?.articles_collected ?? '—') },
                { id: 'screened', label: 'Passed screening', amount: String(m?.articles_screened ?? '—') },
                { id: 'events', label: 'Events analysed', amount: `${m?.events_analyzed ?? '—'} of ${m?.events_identified ?? '—'}` },
                ...(m?.generated_at ? [{ id: 'at', label: 'Generated', amount: new Date(m.generated_at).toLocaleString('en-GB') }] : []),
                ...(m?.duration_seconds ? [{ id: 'took', label: 'Took', amount: `${Math.round(m.duration_seconds)} s` }] : []),
              ]}
            />
            <Panel title="Brief">{r.brief ? <BriefView brief={r.brief} /> : <Text>The brief came back empty.</Text>}</Panel>
            <SourceArticles articles={r.articles} name={`situation-assessment-${config.topic}`} />
            <Stack><Disclosure dashboard="Situation Assessment" purpose="To assess recent events, threats and opportunities from collected sources" generatedAt={m?.generated_at} /></Stack>
          </>
        )}
      </GeneratorFrame>
      <GeneratorTune
        open={tune}
        onOpenChange={setTune}
        title="Situation Assessment"
        base="/api/sio"
        notify={notify}
        settings={(c, setC) => <SettingsForm s={{ ...DEFAULTS, ...c } as Settings} set={setC} />}
        onSaved={(c) => setS((x) => ({ ...x, ...c }))}
      />
    </>
  );
}
