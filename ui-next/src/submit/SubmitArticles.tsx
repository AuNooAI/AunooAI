import { useEffect, useRef, useState } from 'react';
import { ConfirmDialog, type Confirm, storage, useToasts } from '@aunoo/shell';
import {
  ArticleCard, Banner, Button, Checkbox, Chip, EmptyState, Grid, Icon, Panel, Select, SettingRow, Skeleton, Stack, TabPanel, Tabs, Text, TextArea, TextField,
} from '@aunoo/ui';
import { api, AppShell, errorText } from '../shell';
import {
  analyseLinks, analysePasted, deleteArticle, loadArticle, loadLabels, loadRecent, promoteToIncident, saveMany, saveOne,
  type Analysis, type Labels, type Pasted, type Settings,
} from './api';
import { ResultEditor } from './ResultEditor';

const VOICES = [
  ['business_analyst', 'Business analyst'], ['industry_analyst', 'Industry analyst'], ['market_researcher', 'Market researcher'],
  ['brand_and_communications_lead', 'Brand and communications lead'], ['science_journalist', 'Science journalist'], ['tech_journalist', 'Tech journalist'],
  ['investment_advisor', 'Investment advisor'], ['principal_security_engineer', 'Principal security engineer'], ['ciso', 'CISO'], ['custom', 'Custom'],
].map(([value, label]) => ({ value, label }));
const LENGTHS = ['40', '50', '75', '100'].map((v) => ({ value: v, label: `${v} words` })).concat({ value: 'custom', label: 'Custom' });
const MAX_LINKS = 50;
const KEY = 'aunoo.submit.settings';
const NO_LABELS: Labels = { categories: [], sentiments: [], futureSignals: [], timeToImpacts: [], driverTypes: [] };
const EMPTY_PASTE: Pasted = { url: '', title: '', source: '', date: '', content: '' };

interface Saved { topic: string; model: string; length: string; customLength: string; voice: string; customVoice: string }
const loadSaved = (): Saved => {
  try {
    return { topic: '', model: '', length: '50', customLength: '', voice: 'business_analyst', customVoice: '', ...JSON.parse(storage.get(KEY) ?? '{}') };
  } catch {
    return { topic: '', model: '', length: '50', customLength: '', voice: 'business_analyst', customVoice: '' };
  }
};

const fmt = (d?: string) => {
  const t = d ? new Date(d) : null;
  return t && !Number.isNaN(t.getTime()) ? t.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '';
};

/**
 * Submit Articles: analyse links or pasted text for a topic, correct the result, save it into the
 * topic. The Chrome extension opens this page with ?url, ?topic, ?title, ?source, ?publication_date.
 */
export function SubmitArticles() {
  const { toasts, notify } = useToasts();
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [cfg, setCfg] = useState<Saved>(loadSaved);
  const [topics, setTopics] = useState<string[]>([]);
  const [models, setModels] = useState<{ value: string; label: string }[]>([]);
  const [labels, setLabels] = useState<Labels>(NO_LABELS);
  const [tab, setTab] = useState('links');
  const [links, setLinks] = useState('');
  const [paste, setPaste] = useState<Pasted>(EMPTY_PASTE);
  const [results, setResults] = useState<Analysis[]>([]);
  const [failed, setFailed] = useState<Analysis[]>([]);
  const [promote, setPromote] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Analysis[] | null>(null);
  const abort = useRef<AbortController | null>(null);

  const set = (patch: Partial<Saved>) =>
    setCfg((c) => {
      const next = { ...c, ...patch };
      storage.set(KEY, JSON.stringify(next));
      return next;
    });

  const reloadRecent = () => loadRecent().then(setRecent, () => setRecent([]));

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    api<{ name: string }[]>('/api/topics').then((t) => {
      const names = (Array.isArray(t) ? t : []).map((x) => x.name);
      setTopics(names);
      const wanted = p.get('topic');
      if (wanted && names.includes(wanted)) set({ topic: wanted });
      else setCfg((c) => (c.topic && !names.includes(c.topic) ? { ...c, topic: '' } : c));
    }, (e) => setError(`Couldn’t load topics: ${errorText(e)}`));
    api<{ id: string; name: string }[]>('/api/trend-convergence/models').then((m) => {
      const opts = (Array.isArray(m) ? m : []).map((x) => ({ value: x.id, label: x.name }));
      setModels(opts);
      setCfg((c) => (c.model && opts.some((o) => o.value === c.model) ? c : { ...c, model: opts[0]?.value ?? '' }));
    }, () => setModels([]));
    void reloadRecent();
    // Prefill from the Chrome extension or a link
    const url = p.get('url');
    if (url) setLinks(url);
    const date = p.get('publication_date')?.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? '';
    if (p.get('title') || p.get('source') || date) setPaste((x) => ({ ...x, url: url ?? '', title: p.get('title') ?? '', source: p.get('source') ?? '', date }));
    return () => abort.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadLabels(cfg.topic).then(setLabels, () => setLabels(NO_LABELS));
  }, [cfg.topic]);

  const settings = (): Settings => ({
    topic: cfg.topic,
    model: cfg.model,
    length: cfg.length === 'custom' ? cfg.customLength.trim() || '50' : cfg.length,
    voice: cfg.voice === 'custom' ? cfg.customVoice.trim() || 'business_analyst' : cfg.voice,
  });

  const urls = links.split('\n').map((u) => u.trim()).filter(Boolean);
  const pasteMissing = !paste.url.trim() || !paste.content.trim();

  const runLinks = async () => {
    setError(null);
    if (!cfg.topic) return setError('Choose a topic first.');
    if (urls.length === 0) return setError('Add at least one link.');
    if (urls.length > MAX_LINKS) return setError(`At most ${MAX_LINKS} links at a time. You have ${urls.length}.`);
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setAnalysing(true);
    setResults([]);
    setFailed([]);
    try {
      for await (const a of analyseLinks(urls, settings(), ctrl.signal)) {
        if (a.error) setFailed((f) => [...f, a]);
        else setResults((r) => [...r, a]);
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setError(`Analysis stopped: ${errorText(e)}`);
    } finally {
      setAnalysing(false);
    }
  };

  const runPaste = async () => {
    setError(null);
    if (!cfg.topic) return setError('Choose a topic first.');
    if (pasteMissing) return setError('Add the source link and the article text.');
    setAnalysing(true);
    setResults([]);
    setFailed([]);
    try {
      setResults([await analysePasted(paste, settings())]);
    } catch (e) {
      setError(`Analysis failed: ${errorText(e)}`);
    } finally {
      setAnalysing(false);
    }
  };

  const patch = (i: number, p: Partial<Analysis>) => setResults((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x)));

  const save = async () => {
    if (!cfg.topic) return setError('Choose a topic first.');
    setSaving(true);
    setError(null);
    try {
      let saved: Analysis[];
      if (results.length === 1) {
        await saveOne(results[0], cfg.topic);
        saved = results;
      } else {
        const r = await saveMany(results, cfg.topic);
        saved = r.success ?? [];
        if (r.errors?.length) setError(`${r.errors.length} not saved: ${r.errors.map((e) => e.error).filter(Boolean).slice(0, 3).join('; ')}`);
      }
      let incidents = 0;
      if (promote) {
        for (const a of saved) {
          try {
            if (await promoteToIncident(results.find((x) => x.uri === a.uri) ?? a, cfg.topic)) incidents += 1;
          } catch {
            // one failed incident shouldn't stop the rest
          }
        }
      }
      // Unticked after each save, so a later save can't create incidents by surprise
      setPromote(false);
      const done = new Set(saved.map((a) => a.uri));
      setResults((r) => r.filter((x) => !done.has(x.uri)));
      if (tab === 'paste' && done.size) setPaste(EMPTY_PASTE);
      notify(`${saved.length} article${saved.length === 1 ? '' : 's'} saved to ${cfg.topic}${promote ? `, ${incidents} incident${incidents === 1 ? '' : 's'} created` : ''}`);
      void reloadRecent();
    } catch (e) {
      setError(`Not saved: ${errorText(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const edit = async (a: Analysis) => {
    try {
      const full = await loadArticle(a.uri);
      if (full.topic && topics.includes(full.topic)) set({ topic: full.topic });
      setFailed([]);
      setResults([full]);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      notify(`Couldn’t open it: ${errorText(e)}`);
    }
  };
  const remove = (a: Analysis) =>
    setConfirm({
      title: 'Delete this article?',
      message: `“${a.title || a.uri}” will be deleted from the database, with its analysis.`,
      action: 'Delete',
      onConfirm: () =>
        void deleteArticle(a.uri).then(
          () => {
            setRecent((r) => (r ?? []).filter((x) => x.uri !== a.uri));
            notify('Article deleted');
          },
          (e) => notify(`Not deleted: ${errorText(e)}`),
        ),
    });

  const analyseButton = (onClick: () => void, label: string, disabled: boolean) => (
    <Stack direction="row" gap="sm">
      <Button size="lg" iconStart={<Icon name="Sparkle" size="sm" />} busy={analysing} disabled={disabled || analysing || !cfg.topic} onClick={onClick}>
        {analysing ? 'Analysing…' : label}
      </Button>
      {analysing && tab === 'links' && <Button size="lg" variant="ghost" onClick={() => abort.current?.abort()}>Stop</Button>}
    </Stack>
  );

  return (
    <AppShell current="gather" page="Submit articles" toasts={toasts}>
      <Stack gap="lg">
        {error && <Banner tone="error" icon="WarningCircle" title="Something went wrong" description={error} />}

        <Panel title="Analysis settings" description="The AI reads each article for this topic and fills in its summary and labels. You can correct them before saving.">
          <Grid columns={2} stackAt="small" gap="md">
            <Select label="Topic" fullWidth placeholder="Choose a topic" options={topics.map((t) => ({ value: t, label: t }))} value={cfg.topic || undefined} onValueChange={(topic) => set({ topic })} />
            <Select label="AI model" fullWidth placeholder="No models available" options={models} value={cfg.model || undefined} onValueChange={(model) => set({ model })} />
            <Stack gap="sm">
              <Select label="Summary length" fullWidth options={LENGTHS} value={cfg.length} onValueChange={(length) => set({ length })} />
              {cfg.length === 'custom' && <TextField label="Words" type="number" min={10} max={500} value={cfg.customLength} onChange={(customLength) => set({ customLength })} />}
            </Stack>
            <Stack gap="sm">
              <Select label="Written as" fullWidth hint="Whose voice the summary is written in." options={VOICES} value={cfg.voice} onValueChange={(voice) => set({ voice })} />
              {cfg.voice === 'custom' && <TextField label="Custom voice" placeholder="e.g. procurement lead" value={cfg.customVoice} onChange={(customVoice) => set({ customVoice })} />}
            </Stack>
          </Grid>
        </Panel>

        <Panel title="Add articles">
          <Tabs label="How to add articles" value={tab} onValueChange={setTab} items={[{ value: 'links', label: 'From links', icon: 'Link' }, { value: 'paste', label: 'Paste text', icon: 'FileText' }]}>
            <TabPanel value="links">
              <Stack gap="md">
                <TextArea
                  label="Links"
                  rows={6}
                  placeholder={'https://example.com/article-1\nhttps://example.com/article-2'}
                  hint={`One per line, up to ${MAX_LINKS}.${urls.length ? ` ${urls.length} added.` : ''}`}
                  value={links}
                  onChange={setLinks}
                />
                {analyseButton(() => void runLinks(), urls.length > 1 ? `Analyse ${urls.length} articles` : 'Analyse article', urls.length === 0)}
              </Stack>
            </TabPanel>
            <TabPanel value="paste">
              <Stack gap="md">
                <Text variant="hint">For paywalled or unreachable pages. The title, source and date you enter are kept as they are.</Text>
                <Grid columns={2} stackAt="small" gap="md">
                  <TextField label="Source link" type="url" placeholder="https://example.com/article" value={paste.url} onChange={(url) => setPaste((p) => ({ ...p, url }))} />
                  <TextField label="Title" value={paste.title} onChange={(title) => setPaste((p) => ({ ...p, title }))} />
                  <TextField label="Source" placeholder="e.g. The New York Times" value={paste.source} onChange={(source) => setPaste((p) => ({ ...p, source }))} />
                  <TextField label="Publication date" type="date" value={paste.date} onChange={(date) => setPaste((p) => ({ ...p, date }))} />
                </Grid>
                <TextArea label="Article text" rows={10} placeholder="Paste the full article here" value={paste.content} onChange={(content) => setPaste((p) => ({ ...p, content }))} />
                {analyseButton(() => void runPaste(), 'Analyse article', pasteMissing)}
              </Stack>
            </TabPanel>
          </Tabs>
        </Panel>

        {(results.length > 0 || failed.length > 0 || analysing) && (
          <Panel
            title="Check and save"
            description={results.length ? 'Correct anything the analysis got wrong, then save.' : undefined}
            headerAside={results.length > 0 && <Chip size="sm" tone="neutral">{`${results.length} ready`}</Chip>}
          >
            <Stack gap="md">
              {failed.length > 0 && (
                <Banner
                  tone="warning"
                  icon="Warning"
                  title={`${failed.length} link${failed.length === 1 ? '' : 's'} couldn’t be analysed`}
                  description={
                    <Stack as="ul" gap="sm" label="Links that failed">
                      {failed.map((f) => <li key={f.uri}><Text variant="caption">{`${f.uri}: ${f.error}`}</Text></li>)}
                    </Stack>
                  }
                />
              )}
              {analysing && results.length === 0 && <Skeleton lines={4} />}
              <Stack as="ul" gap="md" label="Analysed articles">
                {results.map((a, i) => (
                  <li key={a.uri}>
                    <SettingRow
                      title={a.title || 'Untitled'}
                      description={a.news_source}
                      actionsPlacement="title"
                      actions={results.length > 1 && <Button size="sm" variant="ghost" iconStart={<Icon name="X" size="sm" />} onClick={() => setResults((r) => r.filter((_, j) => j !== i))}>Leave out</Button>}
                    >
                      <ResultEditor a={a} labels={labels} onChange={(p) => patch(i, p)} />
                    </SettingRow>
                  </li>
                ))}
              </Stack>
              {results.length > 0 && (
                <Stack gap="md">
                  <Checkbox
                    label={`Also create ${results.length === 1 ? 'an incident' : 'incidents'} from ${results.length === 1 ? 'this article' : 'these articles'} (the AI drafts each one)`}
                    checked={promote}
                    onCheckedChange={setPromote}
                  />
                  <Stack direction="row" gap="sm">
                    <Button size="lg" iconStart={<Icon name="Check" size="sm" />} busy={saving} disabled={analysing} onClick={() => void save()}>
                      {results.length === 1 ? 'Save article' : `Save ${results.length} articles`}
                    </Button>
                    <Button size="lg" variant="secondary" disabled={saving} onClick={() => { setResults([]); setFailed([]); }}>Discard</Button>
                  </Stack>
                </Stack>
              )}
            </Stack>
          </Panel>
        )}

        <Panel title="Recently analysed" description="The latest articles with a full analysis, from any source.">
          {recent === null ? (
            <Skeleton lines={4} />
          ) : recent.length === 0 ? (
            <EmptyState icon="Newspaper">No analysed articles yet.</EmptyState>
          ) : (
            <Stack as="ul" gap="sm" label="Recently analysed articles">
              {recent.map((a) => (
                <ArticleCard
                  key={a.uri}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  title={a.title || 'Untitled'}
                  href={a.uri}
                  meta={[a.news_source, a.topic].filter(Boolean).join(' · ')}
                  summary={a.summary}
                  tags={
                    <>
                      {a.category && <Chip size="sm" tone="info">{a.category}</Chip>}
                      {a.sentiment && <Chip size="sm" tone={/pos/i.test(a.sentiment) ? 'success' : /neg|crit/i.test(a.sentiment) ? 'error' : 'muted'}>{a.sentiment}</Chip>}
                      {a.future_signal && <Chip size="sm" tone="muted">{a.future_signal}</Chip>}
                    </>
                  }
                  footer={fmt(a.submission_date) && `Added ${fmt(a.submission_date)}`}
                  actions={[{ id: 'edit', label: 'Edit', icon: 'PencilSimple' }, { id: 'delete', label: 'Delete', icon: 'Trash' }]}
                  actionsLabel={`Actions for ${a.title || a.uri}`}
                  onAction={(id) => (id === 'edit' ? void edit(a) : remove(a))}
                />
              ))}
            </Stack>
          )}
        </Panel>
      </Stack>
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </AppShell>
  );
}
