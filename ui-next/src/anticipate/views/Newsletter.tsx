import { useEffect, useState } from 'react';
import { Button, Chip, Grid, Icon, Panel, Select, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import { api } from '../../shell';
import { Markdown } from '../../shell/Markdown';
import { Disclosure } from '../components/Disclosure';
import { GeneratorFrame } from '../components/GeneratorFrame';
import { MarkdownEditor } from '../components/MarkdownEditor';
import { saveText } from '../lib/download';
import { useGenerator, type Event, type Stage } from '../lib/generator';
import { GeneratorTune } from '../overlays/GeneratorTune';
import type { ViewProps } from './types';

interface Result {
  content: string;
  article_count?: number;
  articles_used?: number;
  deep_dive_topic?: string;
  model?: string;
  /** When it was generated (the old page always showed today's date) */
  generated_at: string;
}
interface Settings { title: string; intro: string; days_back: number; deep_dive_topic: string }

// The server's progress counts are placeholders, so only the stage is shown
const STAGES: Stage[] = [
  { id: 'fetching', label: 'Fetching articles', from: 0, to: 0.3 },
  { id: 'categorizing', label: 'Sorting into sections', from: 0.3, to: 0.5 },
  { id: 'generating', label: 'Writing', from: 0.5, to: 1 },
];
// One fallback title, the server's (the old page used two different ones)
const DEFAULTS: Settings = { title: 'Weekly Intelligence Digest', intro: '', days_back: 7, deep_dive_topic: '' };
const DAYS = [1, 3, 7, 14, 30].map((d) => ({ value: String(d), label: `Last ${d} day${d === 1 ? '' : 's'}` }));

export function Newsletter({ config, notify, askConfirm }: ViewProps) {
  const toResult = (e: Event): Result => ({
    content: e.newsletter ?? '', article_count: e.article_count, articles_used: e.articles_used, deep_dive_topic: e.deep_dive_topic,
    model: config.model, generated_at: new Date().toISOString(),
  });
  const gen = useGenerator<Result>({ url: '/api/newsletter/generate', stages: STAGES, storageKey: 'aunoo.anticipate.newsletter', toResult });
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [tune, setTune] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  useEffect(() => {
    api<Partial<Settings>>('/api/newsletter/config').then((c) => setS((x) => ({ ...x, ...c, deep_dive_topic: c.deep_dive_topic ?? '' })), () => undefined);
  }, []);
  const set = (p: Partial<Settings>) => setS((x) => ({ ...x, ...p }));
  const r = gen.result;
  // What's shown and saved: the edit in progress counts (the old Save posted the unedited text)
  const content = editing ?? r?.content ?? '';

  const settingsForm = (
    <Stack gap="md">
      <Grid columns={2} stackAt="small" gap="md">
        <Select label="Articles from" fullWidth options={DAYS} value={String(s.days_back)} onValueChange={(v) => set({ days_back: Number(v) })} />
        <TextField label="Deep-dive topic (optional)" value={s.deep_dive_topic} onChange={(v) => set({ deep_dive_topic: v })} />
      </Grid>
      <TextField label="Title" value={s.title} onChange={(v) => set({ title: v })} />
      <TextArea label="Introduction" rows={2} value={s.intro} onChange={(v) => set({ intro: v })} hint="Shown above the newsletter." />
    </Stack>
  );

  return (
    <>
      <GeneratorFrame<Result>
        title="Newsletter"
        icon="Newspaper"
        description="A newsletter digest of the topic."
        topic={config.topic}
        gen={gen}
        stages={STAGES}
        summary={`${DAYS.find((d) => d.value === String(s.days_back))?.label ?? `${s.days_back} days`}${s.deep_dive_topic ? ` · deep dive: ${s.deep_dive_topic}` : ''} · ${config.model}`}
        settings={settingsForm}
        generateLabel="Generate newsletter"
        onGenerate={() => { setEditing(null); void gen.run({ topic: config.topic, days_back: s.days_back, deep_dive_topic: s.deep_dive_topic || undefined, model: config.model }); }}
        onTune={() => setTune(true)}
        emptyText="Generate a newsletter of this topic’s recent articles."
        actions={
          r && (
            <>
              {editing === null ? (
                <Button variant="ghost" size="sm" iconStart={<Icon name="PencilSimple" size="sm" />} onClick={() => setEditing(r.content)}>Edit</Button>
              ) : (
                <>
                  <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>Discard edits</Button>
                  <Button size="sm" onClick={() => { gen.setResult({ ...r, content: editing }); setEditing(null); notify('Edits kept'); }}>Keep edits</Button>
                </>
              )}
              <Button variant="ghost" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => window.print()}>PDF</Button>
              <Button variant="ghost" size="sm" onClick={() => saveText(`# ${s.title}\n\n${s.intro ? `${s.intro}\n\n` : ''}${content}`, `newsletter-${config.topic}.md`, 'text/markdown')}>Markdown</Button>
            </>
          )
        }
        saved={{ base: '/api/newsletter', listKey: 'newsletters', loadKey: 'newsletter' }}
        fromSaved={(e) => ({
          content: String(e.newsletter_content ?? ''), articles_used: e.articles_used as number, deep_dive_topic: e.deep_dive_topic as string,
          model: e.model_used as string, generated_at: String(e.created_at ?? new Date().toISOString()),
        })}
        toSave={(name, description) => ({
          topic: config.topic, name, description, newsletter_content: content, config: s, days_back: s.days_back,
          deep_dive_topic: r?.deep_dive_topic || s.deep_dive_topic || undefined, articles_used: r?.articles_used ?? 0, article_uris: [], model_used: r?.model ?? config.model,
        })}
        notify={notify}
        askConfirm={askConfirm}
      >
        {r && (
          <>
            <Stack direction="row" gap="sm">
              {r.article_count != null && <Chip size="sm" tone="neutral">{`${r.article_count} articles found`}</Chip>}
              {r.articles_used != null && <Chip size="sm" tone="neutral">{`${r.articles_used} used`}</Chip>}
              {r.deep_dive_topic && <Chip size="sm" tone="accent">{`Deep dive: ${r.deep_dive_topic}`}</Chip>}
            </Stack>
            <Panel title={s.title} description={`Generated ${new Date(r.generated_at).toLocaleString('en-GB', { dateStyle: 'long', timeStyle: 'short' })}`}>
              <Stack gap="md">
                {s.intro && <Text variant="description">{s.intro}</Text>}
                {editing !== null ? <MarkdownEditor label="Newsletter (Markdown)" value={editing} onChange={setEditing} topic={config.topic} /> : <Markdown text={content} />}
              </Stack>
            </Panel>
            {/* The old footer always named GPT-4.1 */}
            <Disclosure dashboard="Newsletter" purpose="To summarise recent articles as a newsletter" model={r.model} generatedAt={r.generated_at} />
          </>
        )}
      </GeneratorFrame>
      <GeneratorTune
        open={tune}
        onOpenChange={setTune}
        title="Newsletter"
        base="/api/newsletter"
        notify={notify}
        settings={(c, setC) => (
          <Stack gap="md">
            <TextField label="Default title" value={String(c.title ?? '')} onChange={(v) => setC({ title: v })} />
            <TextArea label="Default introduction" rows={2} value={String(c.intro ?? '')} onChange={(v) => setC({ intro: v })} />
            <Grid columns={2} stackAt="small" gap="md">
              <Select label="Default window" fullWidth options={DAYS} value={String(c.days_back ?? 7)} onValueChange={(v) => setC({ days_back: Number(v) })} />
              <TextField label="Default deep-dive topic" value={String(c.deep_dive_topic ?? '')} onChange={(v) => setC({ deep_dive_topic: v })} />
            </Grid>
          </Stack>
        )}
        onSaved={(c) => setS((x) => ({ ...x, ...c, deep_dive_topic: c.deep_dive_topic ?? '' }))}
      />
    </>
  );
}
