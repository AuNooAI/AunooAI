import { useCallback, useEffect, useState } from 'react';
import { ArticleCard, Banner, Button, Chip, EmptyState, Panel, Skeleton, Stack, Text, type MenuItem } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import { download, unsaveNarrative } from '../feed/api';
import { ShareDialog } from '../shared/ShareDialog';
import { AddToBriefingDialog } from '../desk/AddToBriefingDialog';

/*
 * Saved narratives, as the old SavedNarrativesSection: /api/news-feed/saved/narratives, with
 * unsave, Markdown and CSV downloads, and Add to briefing.
 */

interface Narrative {
  name: string;
  description?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  topic?: string;
  saved_at?: string;
}

interface ApiNarrative {
  name?: string;
  theme_name?: string;
  description?: string;
  theme_summary?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  topic?: string;
  _saved_at?: string;
}

const toneOf = (s?: string) => {
  const v = (s || '').toLowerCase();
  return v.includes('neg') ? 'error' : v.includes('pos') ? 'success' : 'muted';
};
const pct = (c?: number) => (c == null ? null : `${Math.round(c <= 1 ? c * 100 : c)}% confidence`);
const slug = (s: string) => s.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '').slice(0, 60) || 'narrative';

function asMarkdown(n: Narrative) {
  const lines = [`# ${n.name}`, ''];
  if (n.topic) lines.push(`**Topic:** ${n.topic}`);
  if (n.sentiment) lines.push(`**Sentiment:** ${n.sentiment}`);
  if (pct(n.confidence)) lines.push(`**Confidence:** ${pct(n.confidence)}`);
  if (n.article_count != null) lines.push(`**Articles:** ${n.article_count}`);
  if (n.source_count != null) lines.push(`**Sources:** ${n.source_count}`);
  lines.push('');
  if (n.description) lines.push(n.description, '');
  if (n.key_entities?.length) lines.push('## Key entities', '', ...n.key_entities.map((e) => `- ${e}`), '');
  lines.push('---', '', '*Written by AI from collected articles. It may contain errors; check the sources before acting on it.*');
  return lines.join('\n');
}

const csvCell = (v: unknown) => {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
function asCsv(n: Narrative) {
  const head = ['name', 'description', 'topic', 'sentiment', 'confidence', 'article_count', 'source_count', 'key_entities'];
  const row = [n.name, n.description, n.topic, n.sentiment, n.confidence, n.article_count, n.source_count, (n.key_entities ?? []).join('; ')];
  return `${head.join(',')}\n${row.map(csvCell).join(',')}\n`;
}

const ACTIONS: MenuItem[] = [
  { id: 'briefing', label: 'Add to briefing', icon: 'FolderPlus' },
  { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
  { id: 'md', label: 'Download as Markdown', icon: 'FileText', separatorBefore: true },
  { id: 'csv', label: 'Download as CSV', icon: 'Table' },
  { id: 'unsave', label: 'Remove from saved', icon: 'BookmarkSimple', separatorBefore: true },
];

export function Narratives({ notify, askConfirm }: { notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [items, setItems] = useState<Narrative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [briefing, setBriefing] = useState<Narrative | null>(null);
  const [sharing, setSharing] = useState<Narrative | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api<{ narratives?: ApiNarrative[] }>('/api/news-feed/saved/narratives');
      setItems((r.narratives ?? []).map((n) => ({
        name: n.name || n.theme_name || '', description: n.description || n.theme_summary, sentiment: n.sentiment, confidence: n.confidence,
        article_count: n.article_count, source_count: n.source_count, key_entities: n.key_entities, topic: n.topic, saved_at: n._saved_at,
      })));
    } catch (e) {
      // The old section showed an empty list when this failed
      setItems([]);
      setError(errorText(e));
    }
  }, []);
  useEffect(() => void load(), [load]);

  const unsave = (n: Narrative) =>
    askConfirm({
      title: `Remove “${n.name}” from saved?`,
      message: 'The saved copy is deleted. The narrative may come back in a later analysis run, but this snapshot of it won’t.',
      action: 'Remove',
      onConfirm: async () => {
        try {
          await unsaveNarrative(n.name, n.topic);
          setItems((list) => (list ?? []).filter((x) => !(x.name === n.name && x.topic === n.topic)));
          notify(`Removed “${n.name}”`);
        } catch (e) {
          notify(`Not removed: ${errorText(e)}`);
        }
      },
    });

  return (
    <Panel title="Saved narratives" description={items ? `${items.length} saved` : undefined}>
      {error && <Banner tone="error" title="Saved narratives didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
      {!items ? <Skeleton variant="text" lines={4} /> : items.length === 0 && !error ? (
        <EmptyState icon="Brain" title="No saved narratives">Save a narrative from the News Feed’s narratives section and it appears here.</EmptyState>
      ) : (
        <Stack as="ul" gap="sm" label="Saved narratives">
          {items.map((n) => (
            <ArticleCard
              key={`${n.name}|${n.topic ?? ''}`}
              as="li"
              variant="row"
              headingLevel={3}
              title={n.name}
              meta={[n.topic, n.saved_at ? `saved ${new Date(n.saved_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}` : null].filter(Boolean).join(' · ')}
              summary={n.description}
              tags={
                <Stack direction="row" gap="sm">
                  {n.sentiment && <Chip size="sm" tone={toneOf(n.sentiment)}>{n.sentiment}</Chip>}
                  {pct(n.confidence) && <Chip size="sm" tone="muted">{pct(n.confidence)!}</Chip>}
                  {n.article_count != null && <Chip size="sm" tone="muted">{`${n.article_count} articles`}</Chip>}
                  {n.source_count != null && <Chip size="sm" tone="muted">{`${n.source_count} sources`}</Chip>}
                </Stack>
              }
              details={n.key_entities?.length ? (
                <Stack gap="sm">
                  <Text variant="label">Key entities</Text>
                  <Stack direction="row" gap="sm">{n.key_entities.map((e) => <Chip key={e} size="sm" tone="neutral">{e}</Chip>)}</Stack>
                </Stack>
              ) : undefined}
              actions={ACTIONS}
              actionsLabel={`Actions for “${n.name}”`}
              onAction={(id) => {
                if (id === 'briefing') setBriefing(n);
                else if (id === 'share') setSharing(n);
                else if (id === 'md') download(`narrative_${slug(n.name)}.md`, asMarkdown(n));
                else if (id === 'csv') download(`narrative_${slug(n.name)}.csv`, asCsv(n), 'text/csv');
                else if (id === 'unsave') unsave(n);
              }}
            />
          ))}
        </Stack>
      )}
      {sharing && (
        <ShareDialog
          open
          onOpenChange={(o) => !o && setSharing(null)}
          kind="narrative"
          title={sharing.name}
          payload={{
            narrative_name: sharing.name, description: sharing.description, topic: sharing.topic, sentiment: sharing.sentiment,
            confidence: sharing.confidence, article_count: sharing.article_count, source_count: sharing.source_count, key_entities: sharing.key_entities,
          }}
          notify={notify}
        />
      )}
      {briefing && (
        <AddToBriefingDialog
          open
          onClose={() => setBriefing(null)}
          itemType="emerging_topic"
          emergingTopic={{
            name: briefing.name, summary: briefing.description, description: briefing.description,
            article_count: briefing.article_count, key_entities: briefing.key_entities, topic: briefing.topic,
          }}
          notify={notify}
        />
      )}
    </Panel>
  );
}
