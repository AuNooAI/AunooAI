import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Chip, EmptyState, Eyebrow, Grid, Icon, IconButton, Menu, Panel, PanelDivider, Skeleton, Stack, Text, ArticleCard,
  type MenuItem,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import { askAuspex, download, unsaveIncident, type SavedIncident } from '../feed/api';
import { AgentSignalBadge } from '../agents/signalBadge';
import { AddToBriefingDialog } from '../desk/AddToBriefingDialog';
import { ShareDialog } from '../shared/ShareDialog';
import { downloadPdf } from '../shared/exports';
import { IncidentNotes } from './incidents/IncidentNotes';
import {
  articlesOf, consensusPrompt, investigatePrompt, isLowQuality, keyOf, lastDate, leadPrompt, nameOf, PLAUS_TONE, prettyFlag, QUALITY_TONE,
  SIG_TONE, sharePayload, signalTagsOf, timelineDates, toCsv, toMarkdown, toStyledMarkdown, TYPE_LABEL,
} from './incidents/helpers';
import { TimelineRuler } from '../feed/visuals';
import './incidents/incidents.css';

/*
 * Saved incidents, as the old SavedIncidentsSection in its full-tab form: every incident saved from
 * the News Feed (or promoted from an article), for the topic picked in the filter bar or all of them.
 * Reads /api/news-feed/saved/incidents, which only reads the database. Investigate, Consensus and the
 * investigation leads open Auspex with a prepared question; nothing runs on load.
 */

export interface SavedIncidentsProps {
  topic?: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  openArticle: (a: { uri: string; title?: string }) => void;
}

const loadSaved = (topic?: string) =>
  api<{ incidents?: SavedIncident[] }>(`/api/news-feed/saved/incidents${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`).then((r) => r.incidents ?? []);

const fmtDay = (t: number) => new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

export function SavedIncidents({ topic, notify, askConfirm, openArticle }: SavedIncidentsProps) {
  const [list, setList] = useState<SavedIncident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [briefing, setBriefing] = useState<SavedIncident | null>(null);
  const [sharing, setSharing] = useState<SavedIncident | null>(null);

  const load = useCallback(() => {
    setError(null);
    loadSaved(topic).then(setList, (e) => {
      setList([]);
      setError(errorText(e));
    });
  }, [topic]);
  useEffect(() => {
    setList(null);
    load();
  }, [load]);

  // The saved row's own topic decides which row is removed. The old page used the filter bar's topic
  // and silently did nothing when "all topics" was picked.
  const topicOf = (i: SavedIncident) => i.topic || topic || '';

  const unsave = (i: SavedIncident) => {
    const t = topicOf(i);
    if (!t) {
      notify('This incident was saved without a topic, so it can’t be removed from here.');
      return;
    }
    askConfirm({
      title: `Remove “${nameOf(i)}” from Saved?`,
      message: 'It leaves the Saved tab, along with its analyst notes. The incident itself stays in the News Feed while it is current.',
      action: 'Remove',
      onConfirm: async () => {
        try {
          await unsaveIncident(nameOf(i), t);
          setList((l) => (l ?? []).filter((x) => keyOf(x) !== keyOf(i)));
          notify(`Removed “${nameOf(i)}” from Saved`);
        } catch (e) {
          notify(`Not removed: ${errorText(e)}`);
        }
      },
    });
  };

  const act = (i: SavedIncident, id: string) => {
    if (id === 'investigate') askAuspex(investigatePrompt(i), i.topic);
    else if (id === 'consensus') askAuspex(consensusPrompt(i), i.topic);
    else if (id === 'briefing') setBriefing(i);
    else if (id === 'share') setSharing(i);
    else if (id === 'unsave') unsave(i);
  };

  const stamp = new Date().toISOString().slice(0, 10);
  const exportMenu = (
    <Menu
      label="Download saved incidents"
      align="end"
      trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download saved incidents" disabled={!list?.length} />}
      items={[
        { id: 'pdf', label: 'PDF report', icon: 'FileText' },
        { id: 'styled', label: 'Markdown report', icon: 'FileText' },
        { id: 'md', label: 'Markdown (plain)', icon: 'FileText', separatorBefore: true },
        { id: 'csv', label: 'CSV', icon: 'Table' },
      ]}
      onSelect={(id) => {
        if (!list?.length) return;
        if (id === 'md') download(`saved-incidents-${stamp}.md`, toMarkdown(list, topic));
        else if (id === 'styled') download(`incident-report-${stamp}.md`, toStyledMarkdown(list, topic));
        else if (id === 'pdf') {
          downloadPdf({
            filename: `incident-report-${stamp}.pdf`,
            title: `Incident report${topic ? `: ${topic}` : ''}`,
            subtitle: `${list.length} saved incident${list.length === 1 ? '' : 's'}`,
            markdown: toStyledMarkdown(list, topic),
          }).catch((e) => notify(`PDF not made: ${errorText(e)}`));
        } else download(`saved-incidents-${stamp}.csv`, toCsv(list), 'text/csv');
      }}
    />
  );

  return (
    <Panel
      title="Saved incidents"
      description={list ? `${list.length} saved${topic ? ` for ${topic}` : ' across all topics'}` : undefined}
      headerAside={
        <Stack direction="row" gap="sm" wrap={false}>
          {exportMenu}
          <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload saved incidents" onClick={load} />
        </Stack>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Saved incidents didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={load}>Try again</Button>} />}
        {!list ? <Skeleton variant="block" size="card" /> : list.length === 0 && !error ? (
          <EmptyState icon="BookmarkSimple" title="No saved incidents">
            Save an incident from the News Feed with its menu (⋮) and “Save”. Saved incidents stay here, with your notes, after they drop out of the feed.
          </EmptyState>
        ) : (
          <Grid as="ul" columns={2} gap="md" label="Saved incidents">
            {list.map((i) => {
              const n = nameOf(i);
              const arts = articlesOf(i);
              const dates = timelineDates(i);
              const agents = signalTagsOf(i);
              const leads = Array.isArray(i.investigation_leads) ? i.investigation_leads : [];
              const actions: MenuItem[] = [
                { id: 'investigate', label: 'Investigate with Auspex', icon: 'ChatCentered' },
                ...(arts.length ? [{ id: 'consensus', label: 'Consensus across sources (Auspex)', icon: 'Scales' as const }] : []),
                { id: 'briefing', label: 'Add to a briefing', icon: 'Notebook' },
                { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
                { id: 'unsave', label: 'Remove from Saved', icon: 'Trash', separatorBefore: true },
              ];
              return (
                <ArticleCard
                  key={keyOf(i)}
                  as="li"
                  variant="row"
                  headingLevel={3}
                  meta={lastDate(i) || (i._saved_at as string | undefined)?.slice(0, 10)}
                  flag={isLowQuality(i) ? <Chip size="sm" tone="error">Check the sources</Chip> : undefined}
                  title={n}
                  summary={i.description || i.summary}
                  actions={actions}
                  actionsLabel={`Actions for “${n}”`}
                  onAction={(id) => act(i, id)}
                  expandFullWidth
                  tags={
                    <>
                      <Chip size="sm" tone="neutral">{TYPE_LABEL[i.type] ?? i.type ?? 'Event'}</Chip>
                      {i.significance && <Chip size="sm" tone={SIG_TONE[i.significance] ?? 'muted'}>{`Significance: ${i.significance}`}</Chip>}
                      {i.plausibility && <Chip size="sm" tone={PLAUS_TONE[i.plausibility] ?? 'muted'}>{`Plausibility: ${i.plausibility}`}</Chip>}
                      {i.source_quality && <Chip size="sm" tone={QUALITY_TONE[i.source_quality] ?? 'muted'}>{`Sources: ${i.source_quality}`}</Chip>}
                      {i.topic && !topic && <Chip size="sm" tone="muted">{i.topic}</Chip>}
                      {!!i.analyst_notes?.length && <Chip size="sm" tone="info">{`${i.analyst_notes.length} ${i.analyst_notes.length === 1 ? 'note' : 'notes'}`}</Chip>}
                      {agents.length > 0 && <AgentSignalBadge agentNames={agents} compact />}
                    </>
                  }
                  details={
                    <>
                      <PanelDivider />
                      <Stack gap="lg">
                        {i.organizational_relevance && <Banner tone="info" icon="Target" headingLevel={4} title="Why it matters to us" description={i.organizational_relevance} />}
                        {i.credibility_summary && (
                          <Stack gap="sm"><Eyebrow as="h4">Credibility</Eyebrow><Text variant="description">{i.credibility_summary}</Text></Stack>
                        )}
                        {!!i.misinfo_flags?.length && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Misinformation flags</Eyebrow>
                            <Stack direction="row" gap="sm">{i.misinfo_flags.map((f) => <Chip key={f} size="sm" tone="warning">{prettyFlag(f)}</Chip>)}</Stack>
                          </Stack>
                        )}
                        {dates.length > 0 && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">{dates.length === 1 ? 'Date' : 'Timeline'}</Eyebrow>
                            <Text variant="description">
                              {dates.length === 1 ? fmtDay(dates[0]) : `${fmtDay(dates[0])} to ${fmtDay(dates[dates.length - 1])}, ${dates.length} dates`}
                            </Text>
                            <TimelineRuler dates={dates} label={`${nameOf(i)} timeline`} />
                          </Stack>
                        )}
                        {!!i.entities?.length && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Entities</Eyebrow>
                            <Stack direction="row" gap="sm">{i.entities.map((e) => <Chip key={e} size="sm" tone="neutral">{e}</Chip>)}</Stack>
                          </Stack>
                        )}
                        {arts.length > 0 && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">{`Source articles (${arts.length})`}</Eyebrow>
                            <Stack as="ul" gap="sm" label="Source articles">
                              {arts.map((a) => (
                                <li key={a.uri}>
                                  <Stack direction="row" gap="sm">
                                    <Button variant="ghost" size="sm" className="saved-incidents-wrap" onClick={() => openArticle({ uri: a.uri, title: a.title })}>{a.title}</Button>
                                    {a.source && <Text variant="caption" as="span">{a.source}</Text>}
                                    {a.factual && <Chip size="sm" tone="muted">{`Factual: ${a.factual}`}</Chip>}
                                  </Stack>
                                </li>
                              ))}
                            </Stack>
                          </Stack>
                        )}
                        {leads.length > 0 && (
                          <Stack gap="sm">
                            <Eyebrow as="h4">Investigation leads</Eyebrow>
                            <Stack as="ul" gap="sm" label="Investigation leads">
                              {leads.map((l) => (
                                <li key={l}>
                                  <Stack direction="row" gap="sm" wrap={false}>
                                    <Text variant="description" as="span">{l}</Text>
                                    <IconButton icon={<Icon name="ChatCentered" size="sm" />} label={`Research with Auspex: ${l}`} onClick={() => askAuspex(leadPrompt(i, l), i.topic)} />
                                  </Stack>
                                </li>
                              ))}
                            </Stack>
                          </Stack>
                        )}
                        <Stack direction="row" gap="sm">
                          <Button size="sm" variant="secondary" iconStart={<Icon name="ChatCentered" size="sm" />} onClick={() => askAuspex(investigatePrompt(i), i.topic)}>Investigate</Button>
                          {arts.length > 0 && (
                            <Button size="sm" variant="secondary" iconStart={<Icon name="Scales" size="sm" />} onClick={() => askAuspex(consensusPrompt(i), i.topic)}>Consensus</Button>
                          )}
                          <Button size="sm" variant="ghost" iconStart={<Icon name="Trash" size="sm" />} onClick={() => unsave(i)}>Remove from Saved</Button>
                        </Stack>
                        <IncidentNotes incident={i} topic={topicOf(i)} notify={notify} />
                      </Stack>
                    </>
                  }
                />
              );
            })}
          </Grid>
        )}
      </Stack>
      {sharing && (
        <ShareDialog open onOpenChange={(o) => !o && setSharing(null)} kind="incident" title={nameOf(sharing)} payload={sharePayload(sharing)} notify={notify} />
      )}
      {briefing && (
        <AddToBriefingDialog
          open
          onClose={() => setBriefing(null)}
          notify={notify}
          itemType="incident"
          incident={{
            name: nameOf(briefing),
            title: briefing.title,
            type: briefing.type,
            significance: briefing.significance,
            description: briefing.description,
            summary: briefing.summary,
            topic: briefing.topic || topic,
            timeline: Array.isArray(briefing.timeline) ? briefing.timeline[0] : briefing.timeline,
            first_seen: briefing.first_seen,
            last_seen: briefing.last_seen,
            entities: briefing.entities,
            article_uris: articlesOf(briefing).map((a) => a.uri),
            organizational_relevance: briefing.organizational_relevance,
            plausibility: briefing.plausibility,
            source_quality: briefing.source_quality,
            credibility_summary: briefing.credibility_summary,
            investigation_leads: briefing.investigation_leads,
            analyst_notes: briefing.analyst_notes,
          }}
        />
      )}
    </Panel>
  );
}
