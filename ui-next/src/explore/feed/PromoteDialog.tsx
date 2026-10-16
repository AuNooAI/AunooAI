import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Grid, Select, Skeleton, Stack, TabPanel, Tabs, Text, TextArea, TextField, type SelectOption } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { fetchSavedIncidents, type SavedIncident } from './api';

/*
 * Promote an article to an incident, as the old PromoteToIncidentModal did: opening it asks the AI
 * to draft the incident (/api/analyze-article-for-incident), which you edit before saving; or add
 * the article to an incident you saved before.
 */

export interface PromoteArticle {
  uri: string;
  title: string;
  summary?: string;
  source?: string;
  publication_date?: string;
  topic?: string;
}

type Draft = { name: string; type?: string; significance?: string; description?: string; timeline?: string; plausibility?: string; source_quality?: string; organizational_relevance?: string; topic?: string } & Record<string, unknown>;

const TYPES: SelectOption[] = ['incident', 'event', 'entity', 'expertise', 'informed_insider', 'trend_signal', 'strategic_shift'].map((v) => ({ value: v, label: v.replace(/_/g, ' ') }));
const LEVELS: SelectOption[] = ['high', 'medium', 'low'].map((v) => ({ value: v, label: v }));
const PLAUS: SelectOption[] = ['likely', 'questionable', 'implausible'].map((v) => ({ value: v, label: v }));
const QUALITY: SelectOption[] = ['high', 'mixed', 'low'].map((v) => ({ value: v, label: v }));

interface Props {
  article: PromoteArticle | null;
  topic?: string;
  profileId?: number | null;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
  notify: (m: string) => void;
}

export function PromoteDialog({ article, topic, profileId, onOpenChange, onDone, notify }: Props) {
  const [tab, setTab] = useState('new');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedIncident[]>([]);
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const meta = article && { uri: article.uri, title: article.title, summary: article.summary, source: article.source, publication_date: article.publication_date };

  useEffect(() => {
    if (!article) return;
    setTab('new');
    setDraft(null);
    setError(null);
    setTarget('');
    let stale = false;
    api<{ success?: boolean; suggested_incident?: Draft }>('/api/analyze-article-for-incident', {
      method: 'POST',
      json: { article_uri: article.uri, topic: topic || article.topic || undefined, profile_id: profileId ?? undefined },
    }).then(
      (r) => !stale && (r.suggested_incident ? setDraft(r.suggested_incident) : setError('The AI returned no draft. Fill it in by hand.')),
      (e: unknown) => {
        if (stale) return;
        setError(`The AI draft failed: ${errorText(e)}. Fill it in by hand.`);
        setDraft({ name: article.title, type: 'incident', significance: 'medium', description: article.summary ?? '' });
      },
    );
    void fetchSavedIncidents().then((s) => !stale && setSaved(s));
    return () => {
      stale = true;
    };
  }, [article, topic, profileId]);

  const set = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const incidentTopic = (draft?.topic as string) || topic || article?.topic || '';

  const create = async () => {
    if (!draft || !article) return;
    setBusy(true);
    try {
      await api('/api/news-feed/saved/incidents', { method: 'POST', json: { ...draft, topic: incidentTopic, article_uris: [article.uri], article_metadata: [meta] } });
      notify(`Incident “${draft.name}” created`);
      onDone();
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const addTo = async () => {
    const inc = saved.find((s) => String(s._saved_id ?? s.name) === target);
    if (!inc || !article) return;
    setBusy(true);
    try {
      await api(`/api/news-feed/saved/incidents/${encodeURIComponent(inc.name)}/articles`, {
        method: 'POST',
        json: { topic: inc.topic || incidentTopic, article_uri: article.uri, article_metadata: meta },
      });
      notify(`Added to “${inc.name}”`);
      onDone();
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={!!article}
      onOpenChange={onOpenChange}
      title="Promote to incident"
      description={article?.title}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          {tab === 'new' ? (
            <Button size="lg" disabled={busy || !draft?.name?.trim()} onClick={() => void create()}>Create incident</Button>
          ) : (
            <Button size="lg" disabled={busy || !target} onClick={() => void addTo()}>Add to incident</Button>
          )}
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="warning" title="Check this" description={error} />}
        <Tabs label="Promote options" stretch value={tab} onValueChange={setTab} items={[{ value: 'new', label: 'New incident' }, { value: 'existing', label: `Add to existing (${saved.length})` }]}>
          <TabPanel value="new">
            {!draft ? (
              <Stack gap="sm"><Text variant="caption"><span role="status">The AI is drafting the incident…</span></Text><Skeleton variant="text" lines={6} /></Stack>
            ) : (
              <Stack gap="md">
                <TextField label="Name" value={draft.name} onChange={(name) => set({ name })} />
                <Grid columns={2} stackAt="small" gap="md">
                  <Select label="Type" fullWidth options={TYPES} value={draft.type || undefined} onValueChange={(type) => set({ type })} />
                  <Select label="Significance" fullWidth options={LEVELS} value={draft.significance || undefined} onValueChange={(significance) => set({ significance })} />
                  <Select label="Plausibility" fullWidth options={PLAUS} value={draft.plausibility || undefined} onValueChange={(plausibility) => set({ plausibility })} />
                  <Select label="Source quality" fullWidth options={QUALITY} value={draft.source_quality || undefined} onValueChange={(source_quality) => set({ source_quality })} />
                </Grid>
                <TextArea label="Description" rows={4} value={draft.description ?? ''} onChange={(description) => set({ description })} />
                <TextArea label="Why it matters to us" rows={3} value={draft.organizational_relevance ?? ''} onChange={(organizational_relevance) => set({ organizational_relevance })} />
                <TextField label="Timeline" value={draft.timeline ?? ''} onChange={(timeline) => set({ timeline })} />
                <Text variant="caption">Filed under {incidentTopic || 'no topic'}.</Text>
              </Stack>
            )}
          </TabPanel>
          <TabPanel value="existing">
            {saved.length === 0 ? <Text>You haven’t saved any incidents yet.</Text> : (
              <Select
                label="Incident"
                fullWidth
                placeholder="Pick an incident"
                options={saved.map((s) => ({ value: String(s._saved_id ?? s.name), label: s.name, description: s.topic }))}
                value={target || undefined}
                onValueChange={setTarget}
              />
            )}
          </TabPanel>
        </Tabs>
      </Stack>
    </Dialog>
  );
}
