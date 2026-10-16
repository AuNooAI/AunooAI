import { useEffect, useState } from 'react';
import { Banner, Button, Grid, Select, Sheet, Skeleton, Stack, Text, TextArea, TextField, TextLink } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell';
import { Annotations } from './Annotations';
import { getArticle, optionLists, saveArticle, type EditorArticle, type OptionLists } from './api';

/*
 * Edit one article's stored analysis by hand, as the old "Edit article" panel did: title, source,
 * summary, the four classification fields with their explanations, dates and tags, plus notes.
 * Saving writes exactly what is on the form; it doesn't re-run the AI analysis.
 */

interface Form {
  title: string; news_source: string; summary: string; publication_date: string; submission_date: string; tags: string;
  category: string; sentiment: string; sentiment_explanation: string; future_signal: string; future_signal_explanation: string;
  time_to_impact: string; time_to_impact_explanation: string; driver_type: string; driver_type_explanation: string;
}

const s = (v: unknown) => (v == null ? '' : String(v));
const toForm = (a: EditorArticle): Form => ({
  title: s(a.title), news_source: s(a.news_source), summary: s(a.summary),
  publication_date: s(a.publication_date).slice(0, 10), submission_date: s(a.submission_date).replace(' ', 'T').slice(0, 16),
  tags: Array.isArray(a.tags) ? a.tags.join(', ') : s(a.tags),
  category: s(a.category), sentiment: s(a.sentiment), sentiment_explanation: s(a.sentiment_explanation),
  future_signal: s(a.future_signal), future_signal_explanation: s(a.future_signal_explanation),
  time_to_impact: s(a.time_to_impact), time_to_impact_explanation: s(a.time_to_impact_explanation),
  driver_type: s(a.driver_type), driver_type_explanation: s(a.driver_type_explanation),
});

const NONE = '__none__';
/** A picker over the topic's allowed values; a stored value outside the list is kept and marked */
function Pick({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  const all = value && !options.includes(value) ? [...options, value] : options;
  return (
    <Select
      label={label}
      fullWidth
      value={value || NONE}
      onValueChange={(v) => onChange(v === NONE ? '' : v)}
      options={[{ value: NONE, label: 'Not set' }, ...all.map((o) => ({ value: o, label: options.includes(o) ? o : `${o} (not in this topic’s list)` }))]}
    />
  );
}

const words = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);

export function ArticleEditor({ uri, pageTopic, onClose, onSaved, notify, askConfirm }: {
  uri: string | null;
  /** The topic picked on the page, used when the article itself has none */
  pageTopic: string;
  onClose: () => void;
  onSaved: () => void;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}) {
  const [article, setArticle] = useState<EditorArticle | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [opts, setOpts] = useState<OptionLists | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!uri) return;
    let live = true;
    setArticle(null);
    setForm(null);
    setError(null);
    getArticle(uri).then(
      async (a) => {
        if (!live) return;
        setArticle(a);
        setForm(toForm(a));
        const o = await optionLists(a.topic || pageTopic);
        if (live) setOpts(o);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [uri, pageTopic]);

  const set = (patch: Partial<Form>) => setForm((f) => (f ? { ...f, ...patch } : f));

  const save = async () => {
    if (!form || !article) return;
    setSaving(true);
    try {
      await saveArticle({
        ...form,
        uri: article.uri,
        // The old page sent [""] for an empty tag box; blanks are dropped here
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        submission_date: form.submission_date,
        topic: article.topic || pageTopic,
      });
      notify('Article saved');
      onSaved();
      onClose();
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const o = opts ?? { categories: [], futureSignals: [], sentiments: [], timeToImpact: [], driverTypes: [] };

  return (
    <Sheet
      open={!!uri}
      onOpenChange={(open) => !open && onClose()}
      size="lg"
      title="Edit article"
      description="Changes the stored analysis by hand. Saving doesn’t re-run the AI."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button busy={saving} disabled={!form || saving} onClick={() => void save()}>Save changes</Button>
        </>
      }
    >
      {error && <Banner tone="error" title="The article didn’t load" description={error} />}
      {!form || !article ? (!error && <Skeleton variant="text" lines={10} />) : (
        <Stack gap="lg">
          <TextField label="Title" value={form.title} onChange={(title) => set({ title })} />
          <Grid columns={2} stackAt="small" gap="md">
            <TextField label="Source" value={form.news_source} onChange={(news_source) => set({ news_source })} />
            <Stack gap="sm">
              <Text variant="label">Address</Text>
              <TextLink href={article.uri} external>{article.uri}</TextLink>
            </Stack>
          </Grid>
          <TextArea label={`Summary (${words(form.summary)} words)`} rows={4} value={form.summary} onChange={(summary) => set({ summary })} />
          <Grid columns={2} stackAt="small" gap="md">
            <Stack gap="sm">
              <Pick label="Category" value={form.category} options={o.categories} onChange={(category) => set({ category })} />
            </Stack>
            <Stack gap="sm">
              <Pick label="Sentiment" value={form.sentiment} options={o.sentiments} onChange={(sentiment) => set({ sentiment })} />
              <TextArea label="Why this sentiment" rows={2} value={form.sentiment_explanation} onChange={(sentiment_explanation) => set({ sentiment_explanation })} />
            </Stack>
            <Stack gap="sm">
              <Pick label="Future signal" value={form.future_signal} options={o.futureSignals} onChange={(future_signal) => set({ future_signal })} />
              <TextArea label="Why this signal" rows={2} value={form.future_signal_explanation} onChange={(future_signal_explanation) => set({ future_signal_explanation })} />
            </Stack>
            <Stack gap="sm">
              <Pick label="Time to impact" value={form.time_to_impact} options={o.timeToImpact} onChange={(time_to_impact) => set({ time_to_impact })} />
              <TextArea label="Why this time to impact" rows={2} value={form.time_to_impact_explanation} onChange={(time_to_impact_explanation) => set({ time_to_impact_explanation })} />
            </Stack>
            <Stack gap="sm">
              <Pick label="Driver type" value={form.driver_type} options={o.driverTypes} onChange={(driver_type) => set({ driver_type })} />
              <TextArea label="Why this driver type" rows={2} value={form.driver_type_explanation} onChange={(driver_type_explanation) => set({ driver_type_explanation })} />
            </Stack>
          </Grid>
          <Grid columns={2} stackAt="small" gap="md">
            <TextField label="Publication date" type="date" value={form.publication_date} onChange={(publication_date) => set({ publication_date })} />
            <TextField label="Submission date" type="datetime-local" value={form.submission_date} onChange={(submission_date) => set({ submission_date })} />
          </Grid>
          <TextField label="Tags" hint="Separate tags with commas." value={form.tags} onChange={(tags) => set({ tags })} />
          <Annotations uri={article.uri} notify={notify} askConfirm={askConfirm} />
        </Stack>
      )}
    </Sheet>
  );
}
