import { useEffect, useMemo, useState } from 'react';
import {
  ActivityRow, ArticleCard, Banner, Button, Chip, Eyebrow, Grid, Icon, IconButton, Menu, Panel, PanelDivider, Skeleton, Stack, Text, TextArea,
  type MenuItem,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText, session } from '../../shell';
import {
  addIncidentNote, askAuspex, download, fetchIncidentPrefs, hideIncident, saveIncident, setIncidentPreference, unsaveIncident,
  type Incident, type SavedIncident,
} from './api';
import type { Feed } from './useFeed';
import { AddToBriefingDialog, incidentForBriefing } from '../desk/AddToBriefingDialog';
import { ShareDialog } from '../shared/ShareDialog';
import { incidentDates, TimelineRuler } from './visuals';
import { downloadCsv, downloadPdf } from '../shared/exports';

type Tone = 'success' | 'warning' | 'error' | 'info' | 'muted' | 'neutral';
const SIG_TONE: Record<string, Tone> = { high: 'error', medium: 'warning', low: 'muted' };
const PLAUS_TONE: Record<string, Tone> = { likely: 'success', questionable: 'warning', implausible: 'error' };
const QUALITY_TONE: Record<string, Tone> = { high: 'success', mixed: 'warning', low: 'error' };
const TYPE_LABEL: Record<string, string> = {
  incident: 'Incident', entity: 'Entity', expertise: 'Expertise', informed_insider: 'Informed insider', trend_signal: 'Trend signal',
  strategic_shift: 'Strategic shift', event: 'Event',
};
const nameOf = (i: Incident) => i.name || i.title || '';
const ANALYST_KEY = 'aunoo_analyst_name';

/** Latest date the incident names: its timeline holds dates or text such as "reported 2026-10-12" */
function lastDate(i: Incident) {
  const text = [...(Array.isArray(i.timeline) ? i.timeline : [i.timeline ?? '']), i.last_seen ?? '', i.first_seen ?? ''].join(' ');
  const dates = text.match(/\d{4}-\d{2}-\d{2}/g) ?? [];
  return dates.sort().pop() ?? '';
}

function toMarkdown(list: Incident[]) {
  const out = ['# Incidents', ''];
  for (const i of list) {
    out.push(`## ${nameOf(i)}`, '', `${TYPE_LABEL[i.type] ?? i.type} · significance ${i.significance}${i.topic ? ` · ${i.topic}` : ''}`, '');
    if (i.description || i.summary) out.push(i.description || i.summary || '', '');
    if (i.organizational_relevance) out.push(`**Why it matters to us:** ${i.organizational_relevance}`, '');
    for (const a of i.article_metadata ?? []) out.push(`- ${a.title} (${a.news_source || a.source || ''})${a.uri ? ` ${a.uri}` : ''}`);
    out.push('');
  }
  return out.join('\n');
}

/** One incident in the shape /api/share/incident (and each entry of /api/share/incidents) takes */
function sharePayload(i: Incident, topic: string) {
  return {
    incident_name: nameOf(i), incident_type: i.type, significance: i.significance, description: i.description || i.summary,
    topic: i.topic || topic, entities: i.entities, strategic_relevance: i.organizational_relevance, plausibility: i.plausibility,
    source_quality: i.source_quality, credibility_summary: i.credibility_summary, timeline: i.timeline, investigation_leads: i.investigation_leads,
    first_seen: i.first_seen, last_seen: i.last_seen,
    articles: (i.article_metadata ?? []).map((a) => ({ title: a.title, source: a.news_source || a.source, url: a.uri, summary: a.summary })),
    analyst_notes: i.analyst_notes,
  };
}

/** The incidents as CSV rows, one per incident */
function csvRows(list: Incident[]) {
  return list.map((i) => ({
    Name: nameOf(i), Type: TYPE_LABEL[i.type] ?? i.type, Significance: i.significance, Topic: i.topic || '', Plausibility: i.plausibility || '',
    'Source quality': i.source_quality || '', 'Last date': lastDate(i), Description: i.description || i.summary || '',
    'Why it matters': i.organizational_relevance || '', Entities: (i.entities ?? []).join('; '), Articles: (i.article_metadata ?? []).length,
    'Analyst notes': (i.analyst_notes ?? []).map((n) => `${n.analyst}: ${n.comment}`).join(' | '),
  }));
}

function Notes({ i, topic, onAdded, notify }: { i: SavedIncident; topic: string; onAdded: () => void; notify: (m: string) => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const add = async () => {
    let analyst = session.user.username;
    try {
      analyst = localStorage.getItem(ANALYST_KEY) || analyst;
    } catch {
      // use the signed-in name
    }
    setBusy(true);
    try {
      await addIncidentNote(nameOf(i), topic, analyst, text.trim(), i._saved_id);
      setText('');
      onAdded();
      notify('Note added');
    } catch (e) {
      notify(`Note not added: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack gap="sm">
      <Eyebrow as="h4">Analyst notes</Eyebrow>
      {(i.analyst_notes ?? []).length > 0 && (
        <Stack as="ul" gap="sm" label="Analyst notes">
          {(i.analyst_notes ?? []).map((n) => (
            <ActivityRow key={n.id} as="li" primary={n.comment} secondary={n.analyst} timestamp={n.timestamp.slice(0, 16).replace('T', ' ')} dateTime={n.timestamp} />
          ))}
        </Stack>
      )}
      <TextArea label="Add a note" rows={2} value={text} onChange={setText} />
      <div><Button size="sm" variant="secondary" disabled={busy || !text.trim()} onClick={() => void add()}>Add note</Button></div>
    </Stack>
  );
}

interface Props {
  feed: Feed;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onOpenArticle: (uri: string) => void;
  onConfigure: () => void;
}

export function Incidents({ feed, notify, askConfirm, onOpenArticle, onConfigure }: Props) {
  const [prefs, setPrefs] = useState<Record<string, 'more' | 'less'>>({});
  const [hidden, setHidden] = useState<string[]>([]);
  const [toBriefing, setToBriefing] = useState<Incident | null>(null);
  const [share, setShare] = useState<null | { kind: 'incident' | 'incidents'; payload: Record<string, unknown>; title: string }>(null);
  useEffect(() => {
    void fetchIncidentPrefs().then((p) =>
      setPrefs(Object.fromEntries([...p.more_like.map((x) => [x.incident_name, 'more']), ...p.less_like.map((x) => [x.incident_name, 'less'])])),
    );
  }, []);

  const r = feed.incidents;
  const savedByName = useMemo(() => new Map(feed.saved.map((s) => [nameOf(s), s])), [feed.saved]);
  // Incidents saved by hand (often promoted from an article) that this run didn't produce, first; then this run's, with saved notes merged in
  const list = useMemo(() => {
    const ai = r?.incidents ?? [];
    const aiNames = new Set(ai.map(nameOf));
    const promoted = feed.saved
      .filter((s) => !aiNames.has(nameOf(s)) && (!s.topic || feed.topics.includes(s.topic)))
      .map((s) => ({ ...s, isPromoted: true }));
    const merged = ai.map((i) => {
      const s = savedByName.get(nameOf(i));
      return s ? { ...i, analyst_notes: s.analyst_notes, _saved_id: s._saved_id } : i;
    });
    return [...promoted, ...merged].filter((i) => !hidden.includes(nameOf(i)));
  }, [r, feed.saved, feed.topics, savedByName, hidden]);

  const topicFor = (i: Incident) => i.topic || feed.topic || feed.topics[0] || '';
  const p = feed.progress;
  const progressText = p
    ? p.phase === 'reading'
      ? `Reading articles: batch ${p.batches_done ?? 0} of ${p.batches_total ?? '?'}${p.articles_total ? `, ${p.articles_total} articles` : ''}`
      : p.phase === 'merging' ? `Merging ${p.candidates ?? ''} findings` : p.phase === 'writing' ? `Writing up ${p.incidents ?? ''} incidents` : 'Starting…'
    : 'Reading the stored results…';
  const cov = r?.coverage;

  const act = async (i: Incident, id: string) => {
    const n = nameOf(i);
    try {
      if (id === 'briefing') {
        setToBriefing(i);
      } else if (id === 'share') {
        setShare({ kind: 'incident', payload: sharePayload(i, topicFor(i)), title: n });
      } else if (id === 'save') {
        await saveIncident(i, topicFor(i));
        feed.reloadSaved();
        notify('Incident saved');
      } else if (id === 'unsave') {
        await unsaveIncident(n, topicFor(i));
        feed.reloadSaved();
        notify('Incident removed from Saved');
      } else if (id === 'more' || id === 'less') {
        const next = prefs[n] === id ? null : id;
        await setIncidentPreference(i, next, feed.topic);
        setPrefs((x) => {
          const c = { ...x };
          if (next) c[n] = next;
          else delete c[n];
          return c;
        });
        notify(next ? `You’ll see ${next === 'more' ? 'more' : 'fewer'} incidents like this` : 'Preference cleared');
      } else if (id === 'investigate') {
        askAuspex(`Investigate this incident: "${n}". ${i.description || i.summary || ''} What do we know, how credible is it, and what should we watch next?`, i.topic);
      } else if (id === 'hide') {
        askConfirm({
          title: 'Hide this incident?',
          message: 'It leaves this list now and later runs leave it out.',
          action: 'Hide incident',
          onConfirm: () =>
            void hideIncident(n).then(
              () => {
                setHidden((h) => [...h, n]);
                notify('Incident hidden');
              },
              (e: unknown) => notify(`Not hidden: ${errorText(e)}`),
            ),
        });
      }
    } catch (e) {
      notify(`Not done: ${errorText(e)}`);
    }
  };

  return (
    <>
    <Panel
      title="Incidents"
      description={
        cov
          ? `Top ${list.length} of ${cov.candidates} findings from all ${cov.articles_read} articles${r?.analysis_period ? `, ${r.analysis_period}` : ''}`
          : r?.message ?? `${list.length} incidents`
      }
      headerAside={
        <Stack direction="row" gap="sm">
          <Menu
            label="Download the incidents"
            align="end"
            trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download the incidents" disabled={!list.length} />}
            items={[
              { id: 'md', label: 'Markdown', icon: 'FileText' },
              { id: 'pdf', label: 'PDF', icon: 'FileText' },
              { id: 'csv', label: 'CSV (one row per incident)', icon: 'Table' },
            ]}
            onSelect={(id) => {
              const name = `incidents-${(feed.topic || 'all-topics').replace(/\W+/g, '-').toLowerCase()}`;
              if (id === 'md') download(`${name}.md`, toMarkdown(list));
              else if (id === 'csv') downloadCsv(`${name}.csv`, csvRows(list));
              else downloadPdf({ filename: `${name}.pdf`, title: 'Incidents', subtitle: feed.topic || 'All topics', markdown: toMarkdown(list).replace(/^# .*\n/, '') }).catch((e: unknown) => notify(`PDF not made: ${errorText(e)}`));
            }}
          />
          <IconButton
            icon={<Icon name="ShareNetwork" size="sm" />}
            label="Share all incidents by email"
            disabled={!list.length}
            onClick={() => setShare({ kind: 'incidents', title: `${list.length} incidents`, payload: { topic: feed.topic, incidents: list.map((i) => sharePayload(i, topicFor(i))) } })}
          />
          <IconButton icon={<Icon name="SlidersHorizontal" size="sm" />} label="Incident settings" onClick={onConfigure} />
          <Button size="sm" variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={feed.incidentsBusy || !feed.topics.length} onClick={() => void feed.runIncidents(false)}>
            Generate
          </Button>
        </Stack>
      }
    >
      <Stack gap="md">
        {feed.incidentsError && <Banner tone="error" title="Incidents didn’t load" description={feed.incidentsError} />}
        {!!cov?.slices_incomplete && (
          <Banner tone="warning" title="Some days weren’t fully read" description={`${cov.slices_incomplete} of ${cov.slices} topic-days are incomplete. Generate again to finish them.`} />
        )}
        {feed.incidentsBusy && <Text variant="caption"><span role="status">{progressText}</span></Text>}
        {feed.incidentsBusy && !list.length ? <Skeleton variant="block" size="card" /> : list.length === 0 ? (
          <Text>{feed.topics.length ? 'No stored incidents for these topics and dates. Generate reads every article in the window, which can take a few minutes the first time.' : 'Pick a topic to see incidents.'}</Text>
        ) : (
          <Grid as="ul" columns={2} gap="md" label="Incidents">
            {list.map((i) => {
              const n = nameOf(i);
              const isSaved = savedByName.has(n);
              const actions: MenuItem[] = [
                isSaved ? { id: 'unsave', label: 'Remove from Saved', icon: 'BookmarkSimple' } : { id: 'save', label: 'Save', icon: 'BookmarkSimple' },
                { id: 'investigate', label: 'Investigate with Auspex', icon: 'ChatCentered' },
                { id: 'briefing', label: 'Add to a briefing', icon: 'Notebook' },
                { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
                { id: 'more', label: prefs[n] === 'more' ? 'Clear “More like this”' : 'More like this', icon: 'ArrowUp' },
                { id: 'less', label: prefs[n] === 'less' ? 'Clear “Less like this”' : 'Less like this', icon: 'ArrowDown' },
                ...(i.isPromoted ? [] : [{ id: 'hide', label: 'Hide', icon: 'EyeSlash' as const, separatorBefore: true }]),
              ];
              const meta = i.article_metadata ?? [];
              return (
                <ArticleCard
                  key={n}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  meta={lastDate(i)}
                  flag={i.isPromoted ? <Chip size="sm" tone="accent">Promoted</Chip> : isSaved ? <Chip size="sm" tone="accent">Saved</Chip> : undefined}
                  title={n}
                  summary={i.description || i.summary}
                  actions={actions}
                  actionsLabel={`Actions for “${n}”`}
                  onAction={(id) => void act(i, id)}
                  expandFullWidth
                  tags={
                    <>
                      <Chip size="sm" tone="neutral">{TYPE_LABEL[i.type] ?? i.type}</Chip>
                      {i.significance && <Chip size="sm" tone={SIG_TONE[i.significance] ?? 'muted'}>Significance: {i.significance}</Chip>}
                      {i.plausibility && <Chip size="sm" tone={PLAUS_TONE[i.plausibility] ?? 'muted'}>Plausibility: {i.plausibility}</Chip>}
                      {i.source_quality && <Chip size="sm" tone={QUALITY_TONE[i.source_quality] ?? 'muted'}>Sources: {i.source_quality}</Chip>}
                      {i.topic && feed.topics.length > 1 && <Chip size="sm" tone="muted">{i.topic}</Chip>}
                      {!!i.analyst_notes?.length && <Chip size="sm" tone="info">{i.analyst_notes.length} {i.analyst_notes.length === 1 ? 'note' : 'notes'}</Chip>}
                    </>
                  }
                  details={
                    <>
                      <PanelDivider />
                      <Stack gap="lg">
                        {i.organizational_relevance && <Banner tone="info" icon="Target" headingLevel={4} title="Why it matters to us" description={i.organizational_relevance} />}
                        {incidentDates(i).length > 1 && (
                          <Stack gap="sm"><Eyebrow as="h4">Timeline</Eyebrow><TimelineRuler dates={incidentDates(i)} label={`${n} timeline`} /></Stack>
                        )}
                        {i.credibility_summary && (
                          <Stack gap="sm"><Eyebrow as="h4">Credibility</Eyebrow><Text variant="description">{i.credibility_summary}</Text></Stack>
                        )}
                        {!!i.misinfo_flags?.length && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Misinformation flags</Eyebrow>
                            <Stack direction="row" gap="sm">{i.misinfo_flags.map((f) => <Chip key={f} size="sm" tone="warning">{f.replace(/_/g, ' ')}</Chip>)}</Stack>
                          </Stack>
                        )}
                        {!!i.entities?.length && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Entities</Eyebrow>
                            <Stack direction="row" gap="sm">{i.entities.map((e) => <Chip key={e} size="sm" tone="neutral">{e}</Chip>)}</Stack>
                          </Stack>
                        )}
                        {meta.length > 0 && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Articles</Eyebrow>
                            <Stack as="ul" gap="sm" label="Articles">
                              {meta.map((a, k) => {
                                const uri = a.uri ?? i.article_uris?.[k];
                                return (
                                  <li key={uri ?? k}>
                                    <Stack direction="row" gap="sm">
                                      {uri ? <Button variant="ghost" size="sm" onClick={() => onOpenArticle(uri)}>{a.title}</Button> : <Text as="span">{a.title}</Text>}
                                      <Text variant="caption" as="span">{a.news_source || a.source}</Text>
                                      {a.factual_reporting && <Chip size="sm" tone="muted">Factual: {a.factual_reporting}</Chip>}
                                    </Stack>
                                  </li>
                                );
                              })}
                            </Stack>
                          </Stack>
                        )}
                        {!!i.investigation_leads?.length && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Investigation leads</Eyebrow>
                            <Stack as="ul" gap="sm" label="Investigation leads">
                              {i.investigation_leads.map((l) => (
                                <li key={l}>
                                  <Stack direction="row" gap="sm" wrap={false}>
                                    <Text variant="description" as="span">{l}</Text>
                                    <IconButton icon={<Icon name="ChatCentered" size="sm" />} label={`Ask Auspex: ${l}`} onClick={() => askAuspex(`${l} (context: the incident "${n}")`, i.topic)} />
                                  </Stack>
                                </li>
                              ))}
                            </Stack>
                          </Stack>
                        )}
                        {isSaved && <Notes i={{ ...i, ...savedByName.get(n) }} topic={topicFor(i)} onAdded={feed.reloadSaved} notify={notify} />}
                      </Stack>
                    </>
                  }
                />
              );
            })}
          </Grid>
        )}
      </Stack>
    </Panel>
    {share && <ShareDialog open onOpenChange={(o) => !o && setShare(null)} kind={share.kind} payload={share.payload} title={share.title} notify={notify} />}
    <AddToBriefingDialog
      open={!!toBriefing}
      onClose={() => setToBriefing(null)}
      itemType="incident"
      incident={toBriefing ? incidentForBriefing(toBriefing, topicFor(toBriefing)) : undefined}
      notify={notify}
    />
    </>
  );
}
