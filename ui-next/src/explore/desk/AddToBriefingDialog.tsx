import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Icon, SettingRow, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import {
  addArticleToBriefing, addEmergingTopicToBriefing, addIncidentToBriefing, createBriefing, fetchBriefings,
  type BriefingSummary,
} from '@monolith/briefingDeskApi';
import { errorText } from '../../shell';

/*
 * Adds an article, an incident or an emerging topic to a Briefing Desk briefing, as the old
 * AddToBriefingModal: pick a draft briefing, or create one and add to it. Adding only stores the
 * item (/api/desk-briefings/{id}/articles, /incidents, /emerging-topics); nothing is written by the
 * AI until someone generates the briefing on the Briefing Desk. Finalised briefings are read-only.
 */

type ArticleItem = Parameters<typeof addArticleToBriefing>[1];
type IncidentItem = Parameters<typeof addIncidentToBriefing>[1];
type EmergingItem = Parameters<typeof addEmergingTopicToBriefing>[1];

export interface AddToBriefingDialogProps {
  open: boolean;
  onClose: () => void;
  itemType: 'article' | 'incident' | 'emerging_topic';
  article?: ArticleItem;
  incident?: IncidentItem;
  emergingTopic?: EmergingItem;
  onSuccess?: () => void;
  notify?: (m: string) => void;
}

const KIND_LABEL = { article: 'Article', incident: 'Incident', emerging_topic: 'Emerging topic' } as const;

export function AddToBriefingDialog({ open, onClose, itemType, article, incident, emergingTopic, onSuccess, notify }: AddToBriefingDialogProps) {
  const [briefings, setBriefings] = useState<BriefingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | 'new' | null>(null);
  const [newName, setNewName] = useState('');

  useEffect(() => {
    if (!open) return;
    setBriefings(null);
    setError(null);
    setNewName('');
    fetchBriefings().then(setBriefings, (e) => {
      setBriefings([]);
      setError(`Briefings didn’t load: ${errorText(e)}`);
    });
  }, [open]);

  // The old modal's "Create & add" skipped emerging topics, so the briefing was created empty
  const addTo = async (id: number) => {
    if (itemType === 'article' && article) await addArticleToBriefing(id, article);
    else if (itemType === 'incident' && incident) await addIncidentToBriefing(id, incident);
    else if (itemType === 'emerging_topic' && emergingTopic) await addEmergingTopicToBriefing(id, emergingTopic);
    else throw new Error('Nothing to add');
  };

  const done = (message: string) => {
    notify?.(message);
    onSuccess?.();
    onClose();
  };

  const add = async (b: BriefingSummary) => {
    setBusy(b.id);
    setError(null);
    try {
      await addTo(b.id);
      done(`Added to “${b.name}”`);
    } catch (e) {
      setError(`Not added: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const createAndAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy('new');
    setError(null);
    let created: number | null = null;
    try {
      created = (await createBriefing(name)).briefing_id;
      await addTo(created);
      done(`Created “${name}” and added the ${KIND_LABEL[itemType].toLowerCase()}`);
    } catch (e) {
      setError(created ? `“${name}” was created, but the item wasn’t added: ${errorText(e)}` : `Not created: ${errorText(e)}`);
      if (created) fetchBriefings().then(setBriefings, () => undefined);
    } finally {
      setBusy(null);
    }
  };

  const title = itemType === 'article' ? article?.title || 'Article' : itemType === 'incident' ? incident?.name || incident?.title || 'Incident' : emergingTopic?.name || 'Emerging topic';
  const from = article?.topic || incident?.topic || emergingTopic?.topic;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Add to a briefing"
      description={`${KIND_LABEL[itemType]}: ${title}${from ? `, from ${from}` : ''}`}
      footer={<DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>}
    >
      <Stack gap="lg">
        <Text variant="caption">Adding only stores the item in the briefing. The briefing’s text is written when you generate it on the Briefing Desk.</Text>
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        {!briefings ? <Skeleton variant="text" lines={4} /> : briefings.length > 0 && (
          <Stack gap="sm">
            <Text variant="label">Add to an existing briefing</Text>
            <Stack as="ul" gap="sm" label="Briefings">
              {briefings.map((b) => {
                const finalized = b.status === 'finalized';
                const counts = `${b.articles_count} articles, ${b.incidents_count} incidents${b.emerging_topics_count ? `, ${b.emerging_topics_count} emerging topics` : ''}`;
                return (
                  <li key={b.id}>
                    <SettingRow
                      title={b.name}
                      description={finalized ? `${counts}. Finalised, so it can’t be changed.` : counts}
                      actions={
                        <Button
                          variant="secondary"
                          size="sm"
                          iconStart={<Icon name={finalized ? 'Lock' : 'Plus'} size="sm" />}
                          disabled={finalized || busy !== null}
                          onClick={() => void add(b)}
                        >
                          {busy === b.id ? 'Adding…' : finalized ? 'Locked' : 'Add'}
                        </Button>
                      }
                    />
                  </li>
                );
              })}
            </Stack>
          </Stack>
        )}
        <Stack gap="sm">
          <Text variant="label">Or start a new briefing</Text>
          <TextField label="Briefing name" value={newName} onChange={setNewName} onSubmit={() => void createAndAdd()} placeholder="e.g. Weekly board update" />
          <div>
            <Button iconStart={<Icon name="Plus" size="sm" />} disabled={!newName.trim() || busy !== null} onClick={() => void createAndAdd()}>
              {busy === 'new' ? 'Creating…' : 'Create and add'}
            </Button>
          </div>
        </Stack>
      </Stack>
    </Dialog>
  );
}

/** An incident as the briefing stores it, as the old News Feed built it (timeline and leads normalised) */
export function incidentForBriefing(i: {
  name?: string; title?: string; type?: string; significance?: string; description?: string; summary?: string; topic?: string;
  timeline?: string | string[]; first_seen?: string; last_seen?: string; entities?: string[]; article_uris?: string[];
  organizational_relevance?: string; plausibility?: string; source_quality?: string; credibility_summary?: string;
  investigation_leads?: string[] | string; analyst_notes?: IncidentItem['analyst_notes'];
}, fallbackTopic?: string): IncidentItem {
  const leads = i.investigation_leads;
  return {
    name: i.name || i.title || 'Unnamed incident',
    title: i.title, type: i.type, significance: i.significance, description: i.description, summary: i.summary,
    topic: i.topic || fallbackTopic,
    timeline: Array.isArray(i.timeline) ? i.timeline[0] : i.timeline,
    first_seen: i.first_seen, last_seen: i.last_seen, entities: i.entities, article_uris: i.article_uris,
    organizational_relevance: i.organizational_relevance, plausibility: i.plausibility, source_quality: i.source_quality,
    credibility_summary: i.credibility_summary,
    investigation_leads: Array.isArray(leads) ? leads : typeof leads === 'string' ? leads.split(/[;\n]/).map((s) => s.trim()).filter(Boolean) : undefined,
    analyst_notes: i.analyst_notes,
  };
}
