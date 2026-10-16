import { useCallback, useEffect, useState } from 'react';
import { ArticleCard, Banner, Button, Chip, EmptyState, Panel, Skeleton, Stack, type MenuItem } from '@aunoo/ui';
import { ShareDialog } from '../shared/ShareDialog';
import { api, errorText } from '../../shell';

/*
 * Tracked emerging topics, as the old SavedEmergingTopicsSection: /api/emerging-topics/tracked, with
 * untrack. Opening one goes to the Emerging Topics tab. Untracking is undone by tracking the theme
 * again there, so it doesn't ask first.
 */

interface Tracked {
  id: number;
  topic_label: string;
  topic_description: string;
  detection_date: string;
  detection_type: string;
  article_count: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  trend_score?: { composite: number };
  key_entities?: string[];
  tracked_at?: string;
}

const VELOCITY: Record<string, { label: string; tone: 'success' | 'error' | 'neutral' }> = {
  accelerating: { label: 'Accelerating', tone: 'success' },
  decelerating: { label: 'Slowing', tone: 'error' },
  stable: { label: 'Stable', tone: 'neutral' },
};
const fmt = (d?: string) => (d ? new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '');

const ACTIONS: MenuItem[] = [
  { id: 'open', label: 'Open in Emerging Topics', icon: 'TrendUp' },
  { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
  { id: 'untrack', label: 'Stop tracking', icon: 'EyeSlash', separatorBefore: true },
];

export function EmergingTopics({ notify, onOpen }: { notify: (m: string) => void; onOpen: () => void }) {
  const [items, setItems] = useState<Tracked[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sharing, setSharing] = useState<Tracked | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api<{ topics?: Tracked[] }>('/api/emerging-topics/tracked');
      setItems(r.topics ?? []);
    } catch (e) {
      setItems([]);
      setError(errorText(e));
    }
  }, []);
  useEffect(() => void load(), [load]);

  const untrack = async (t: Tracked) => {
    try {
      await api(`/api/emerging-topics/topics/${t.id}/track`, { method: 'DELETE' });
      setItems((list) => (list ?? []).filter((x) => x.id !== t.id));
      notify(`Stopped tracking “${t.topic_label}”`);
    } catch (e) {
      // The old section logged this to the console only
      notify(`Still tracked: ${errorText(e)}`);
    }
  };

  return (
    <Panel title="Tracked emerging topics" description={items ? `${items.length} tracked` : undefined}>
      {error && <Banner tone="error" title="Tracked topics didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
      {!items ? <Skeleton variant="text" lines={4} /> : items.length === 0 && !error ? (
        <EmptyState icon="TrendUp" title="No tracked topics">Track a theme from its menu on the Emerging Topics tab and it appears here.</EmptyState>
      ) : (
        <Stack as="ul" gap="sm" label="Tracked emerging topics">
          {items.map((t) => {
            const v = VELOCITY[t.velocity] ?? VELOCITY.stable;
            const ents = t.key_entities ?? [];
            return (
              <ArticleCard
                key={t.id}
                as="li"
                variant="row"
                headingLevel={3}
                title={t.topic_label}
                meta={[`${t.article_count} articles`, t.trend_score ? `score ${Math.round(t.trend_score.composite)}` : null, t.tracked_at ? `tracked ${fmt(t.tracked_at)}` : `found ${fmt(t.detection_date)}`].filter(Boolean).join(' · ')}
                flag={<Chip size="sm" tone={v.tone}>{v.label}</Chip>}
                summary={t.topic_description}
                tags={ents.length ? (
                  <Stack direction="row" gap="sm">
                    {ents.slice(0, 3).map((e) => <Chip key={e} size="sm" tone="muted">{e}</Chip>)}
                    {ents.length > 3 && <Chip size="sm" tone="muted">{`+${ents.length - 3}`}</Chip>}
                  </Stack>
                ) : undefined}
                actions={ACTIONS}
                actionsLabel={`Actions for “${t.topic_label}”`}
                onAction={(id) => {
                  if (id === 'open') onOpen();
                  else if (id === 'share') setSharing(t);
                  else void untrack(t);
                }}
              />
            );
          })}
        </Stack>
      )}
      {sharing && (
        <ShareDialog
          open
          onOpenChange={(o) => !o && setSharing(null)}
          kind="emerging-topic"
          title={sharing.topic_label}
          payload={{
            topic_id: sharing.id, topic_label: sharing.topic_label, topic_description: sharing.topic_description, score: sharing.trend_score?.composite,
            velocity: sharing.velocity, article_count: sharing.article_count, key_entities: sharing.key_entities, trend_score: sharing.trend_score,
          }}
          notify={notify}
        />
      )}
    </Panel>
  );
}
