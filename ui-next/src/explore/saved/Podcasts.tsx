import { useCallback, useEffect, useState } from 'react';
import { ActivityRow, Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Icon, IconButton, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import './saved.css';

/*
 * Saved podcasts, as the old SavedPodcastsSection: /api/podcast/list, finished episodes with their
 * stored audio (play, download, delete) and the ones still being made. Nothing here makes audio.
 */

interface Podcast {
  podcast_id: string;
  title: string;
  status: string;
  audio_url: string | null;
  created_at: string;
  error: string | null;
  transcript: string;
  metadata: { duration?: number; podcast_name?: string; episode_title?: string; mode?: string; topic?: string };
}

const fmt = (d: string) => {
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};
/** metadata.duration is in minutes */
const dur = (m?: number) => {
  if (!m) return null;
  const mins = Math.floor(m);
  return `${mins}:${String(Math.round((m - mins) * 60)).padStart(2, '0')}`;
};

export function Podcasts({ notify, askConfirm }: { notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [items, setItems] = useState<Podcast[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const list = await api<Podcast[]>('/api/podcast/list');
      setItems([...list].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()));
    } catch (e) {
      setItems([]);
      setError(errorText(e));
    }
  }, []);
  useEffect(() => void load(), [load]);

  const remove = (p: Podcast) =>
    askConfirm({
      title: `Delete “${p.title}”?`,
      message: 'The episode and its audio are deleted for everyone on this site. This can’t be undone.',
      action: 'Delete',
      onConfirm: async () => {
        try {
          await api(`/api/podcast/${encodeURIComponent(p.podcast_id)}`, { method: 'DELETE' });
          setItems((l) => (l ?? []).filter((x) => x.podcast_id !== p.podcast_id));
          notify(`Deleted “${p.title}”`);
        } catch (e) {
          // The old section failed silently here
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });

  const done = (items ?? []).filter((p) => p.status === 'completed' && p.audio_url);
  const making = (items ?? []).filter((p) => p.status === 'processing');

  return (
    <Panel title="Saved podcasts" description={items ? `${done.length} episode${done.length === 1 ? '' : 's'}` : undefined}>
      {error && <Banner tone="error" title="Podcasts didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
      {!items ? <Skeleton variant="text" lines={3} /> : (
        <Stack gap="md">
          {making.length > 0 && (
            <Stack as="ul" gap="sm" label="Podcasts being made">
              {making.map((p) => <ActivityRow key={p.podcast_id} as="li" primary={p.title} secondary={`Being made · started ${fmt(p.created_at)}`} dotTone="live" />)}
            </Stack>
          )}
          {done.length === 0 && making.length === 0 && !error ? (
            <EmptyState icon="SpeakerHigh" title="No podcasts yet">Podcasts made from a briefing or an observer agent appear here.</EmptyState>
          ) : (
            <Stack as="ul" gap="md" label="Saved podcasts">
              {done.map((p) => (
                <li key={p.podcast_id}>
                  <Stack gap="sm">
                    <Stack direction="row" justify="between" gap="sm" wrap={false}>
                      <Stack gap="sm">
                        <Text variant="label">{p.title}</Text>
                        <Text variant="caption">{[fmt(p.created_at), dur(p.metadata?.duration), p.metadata?.topic].filter(Boolean).join(' · ')}</Text>
                      </Stack>
                      <Stack direction="row" gap="sm" wrap={false}>
                        <a className="text-link" href={p.audio_url!} download={`${p.title.replace(/[^a-z0-9]/gi, '_')}.mp3`} aria-label={`Download “${p.title}”`}>
                          <Icon name="DownloadSimple" size="sm" />
                        </a>
                        <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${p.title}”`} onClick={() => remove(p)} />
                      </Stack>
                    </Stack>
                    <audio className="saved-audio" controls preload="none" src={p.audio_url!}>
                      <a href={p.audio_url!}>Download the audio</a>
                    </audio>
                    {p.transcript && (
                      <Collapsible>
                        <CollapsibleTrigger variant="ghost" size="sm" className="saved-wrap-trigger">Transcript</CollapsibleTrigger>
                        <CollapsibleContent><Text>{p.transcript}</Text></CollapsibleContent>
                      </Collapsible>
                    )}
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Stack>
      )}
    </Panel>
  );
}
