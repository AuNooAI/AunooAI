import { useState } from 'react';
import { Banner, Button, Chip, EmptyState, Icon, IconButton, Menu, Meter, Panel, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import type { BriefingAction, BriefingReview, BriefingTheme, DeskBriefing, FinalizeProgressEvent } from '@monolith/briefingDeskApi';
import { ShareDialog } from '../../shared/ShareDialog';
import { Synthesis } from './Synthesis';
import { ReviewHeld } from './Review';
import './desk.css';

/*
 * One briefing: what's in it (articles, incidents, emerging themes, each removable while a draft)
 * and the written summary. "Write with AI" finalizes it: the AI analyses each item, writes the
 * summary, themes and actions, and a reviewer checks them against the sources.
 */

function ItemRow({ title, meta, note, onRemove, removeLabel }: { title: string; meta: string; note?: string; onRemove?: () => void; removeLabel: string }) {
  return (
    <li>
      <Stack direction="row" justify="between" gap="sm" wrap={false}>
        <Stack gap="sm">
          <Text variant="label">{title}</Text>
          {meta && <Text variant="caption">{meta}</Text>}
          {note && <Text variant="caption">{note}</Text>}
        </Stack>
        {onRemove && <IconButton icon={<Icon name="X" size="sm" />} label={removeLabel} onClick={onRemove} />}
      </Stack>
    </li>
  );
}

const join = (...parts: (string | number | undefined | null | false)[]) => parts.filter((p) => p !== undefined && p !== null && p !== false && p !== '').join(' · ');

function progressText(p: FinalizeProgressEvent | null) {
  if (p?.stage === 'analysis') return `Analysing item ${p.current_item || 0} of ${p.total_items || 0}${p.item_title ? `: ${p.item_title}` : ''}`;
  if (p?.stage === 'review') return 'Checking the draft against its sources';
  return 'Writing the summary';
}

export function BriefingDetail({
  briefing, modelNames, generating, progress, onBack, onGenerate, onOverride, onReopen, onExport, onDelete,
  onRemoveArticle, onRemoveIncident, onRemoveTopic, onSaveSummary, onSaveThemes, onSaveActions, notify,
}: {
  briefing: DeskBriefing;
  modelNames: string | null;
  generating: boolean;
  progress: FinalizeProgressEvent | null;
  onBack: () => void;
  onGenerate: () => void;
  onOverride: (note: string) => void;
  onReopen: () => void;
  onExport: (format: 'pdf' | 'markdown' | 'html' | 'json') => void;
  onDelete: () => void;
  onRemoveArticle: (uri: string, title: string) => void;
  onRemoveIncident: (name: string) => void;
  onRemoveTopic: (name: string) => void;
  onSaveSummary: (v: string) => Promise<void>;
  onSaveThemes: (v: BriefingTheme[]) => Promise<void>;
  onSaveActions: (v: BriefingAction[]) => Promise<void>;
  notify: (m: string) => void;
}) {
  const [tab, setTab] = useState<'content' | 'synthesis'>('content');
  const [sharing, setSharing] = useState(false);
  const isDraft = briefing.status === 'draft';
  const review = (briefing.metadata as { review?: BriefingReview } | undefined)?.review;
  const topics = briefing.emerging_topics ?? [];
  const itemCount = briefing.articles.length + briefing.incidents.length + topics.length;
  // The server needs at least one article or incident to write from
  const canGenerate = isDraft && (briefing.articles.length > 0 || briefing.incidents.length > 0);

  return (
    <Stack gap="lg">
      <div><Button variant="ghost" iconStart={<Icon name="CaretLeft" size="sm" />} onClick={onBack}>All briefings</Button></div>
      <Panel
        title={briefing.name}
        description={briefing.description}
        headerAside={
          <Stack direction="row" gap="sm">
            <Chip tone={isDraft ? 'muted' : 'success'} size="sm">{isDraft ? 'Draft' : 'Finalized'}</Chip>
            {isDraft ? (
              canGenerate && <Button size="sm" busy={generating} iconStart={<Icon name="Sparkle" size="sm" />} onClick={onGenerate}>{generating ? 'Writing…' : 'Write with AI'}</Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={onReopen}>Reopen to edit</Button>
            )}
            <Menu
              label="Download"
              align="end"
              trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download" />}
              items={[
                { id: 'pdf', label: 'PDF', icon: 'FileText' },
                { id: 'markdown', label: 'Markdown', icon: 'FileText', separatorBefore: true },
                { id: 'html', label: 'HTML', icon: 'FileText' },
                { id: 'json', label: 'JSON', icon: 'Database' },
              ]}
              onSelect={(id) => onExport(id as 'pdf' | 'markdown' | 'html' | 'json')}
            />
            <IconButton icon={<Icon name="ShareNetwork" size="sm" />} label="Share this briefing by email" onClick={() => setSharing(true)} />
            <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label="Delete this briefing" onClick={onDelete} />
          </Stack>
        }
      >
        {isDraft && !canGenerate && itemCount > 0 && (
          <Text variant="hint">The AI writes from articles and incidents; add at least one before “Write with AI” appears.</Text>
        )}
      </Panel>

      {generating && (
        <Panel title="Writing with AI" headingLevel={3}>
          <Stack gap="sm">
            <Text>{progressText(progress)}</Text>
            <Meter label="Progress" progress value={Math.round(Math.min(1, progress?.progress ?? 0) * 100)} />
          </Stack>
        </Panel>
      )}
      {isDraft && !generating && review?.status === 'revision_requested' && (
        <Panel title="Held by the reviewer" headingLevel={3}>
          <ReviewHeld briefing={briefing} review={review} onRegenerate={onGenerate} onOverride={onOverride} busy={generating} />
        </Panel>
      )}

      <Tabs
        label="Briefing sections"
        value={tab}
        onValueChange={(v) => setTab(v as 'content' | 'synthesis')}
        items={[{ value: 'content', label: 'Content', count: itemCount }, { value: 'synthesis', label: isDraft ? 'Summary' : 'Summary (finalized)' }]}
      >
        <TabPanel value="content">
          {itemCount === 0 ? (
            <EmptyState icon="Newspaper" title="Nothing in this briefing yet">Use “Add to briefing” on an article, an incident or an emerging theme.</EmptyState>
          ) : (
            <Stack gap="lg">
              {briefing.articles.length > 0 && (
                <Panel title={`Articles (${briefing.articles.length})`} headingLevel={3}>
                  <Stack as="ul" gap="md" label="Articles">
                    {briefing.articles.map((a, i) => (
                      <ItemRow key={a.uri || i} title={a.title} meta={join(a.source, a.topic)} removeLabel={`Remove “${a.title}”`} onRemove={isDraft ? () => onRemoveArticle(a.uri, a.title) : undefined} />
                    ))}
                  </Stack>
                </Panel>
              )}
              {briefing.incidents.length > 0 && (
                <Panel title={`Incidents (${briefing.incidents.length})`} headingLevel={3}>
                  <Stack as="ul" gap="md" label="Incidents">
                    {briefing.incidents.map((n, i) => (
                      <ItemRow key={n.name || i} title={n.name} meta={join(n.type, n.significance, n.topic)} removeLabel={`Remove “${n.name}”`} onRemove={isDraft ? () => onRemoveIncident(n.name) : undefined} />
                    ))}
                  </Stack>
                </Panel>
              )}
              {topics.length > 0 && (
                <Panel title={`Emerging themes (${topics.length})`} headingLevel={3}>
                  <Stack as="ul" gap="md" label="Emerging themes">
                    {topics.map((t, i) => (
                      <ItemRow
                        key={t.name || i}
                        title={t.name}
                        meta={join(t.article_count ? `${t.article_count} articles` : '', t.velocity, t.topic)}
                        note={t.key_takeaway}
                        removeLabel={`Remove “${t.name}”`}
                        onRemove={isDraft ? () => onRemoveTopic(t.name) : undefined}
                      />
                    ))}
                  </Stack>
                </Panel>
              )}
            </Stack>
          )}
        </TabPanel>
        <TabPanel value="synthesis">
          {review?.status === 'revision_requested' && isDraft && (
            <Banner tone="warning" title="This summary was held by the reviewer" description="It hasn’t been finalized. See the findings above the tabs." />
          )}
          <Synthesis briefing={briefing} modelNames={modelNames} onSaveSummary={onSaveSummary} onSaveThemes={onSaveThemes} onSaveActions={onSaveActions} notify={notify} />
        </TabPanel>
      </Tabs>
      {/* The server builds the email from the stored briefing; only the id and recipient are sent */}
      <ShareDialog
        open={sharing}
        onOpenChange={setSharing}
        kind="desk-briefing"
        title={briefing.name}
        payload={{ briefing_id: briefing.id, name: briefing.name, description: briefing.description, status: briefing.status }}
        notify={notify}
      />
    </Stack>
  );
}
