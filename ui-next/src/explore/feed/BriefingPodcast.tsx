import { useEffect, useRef, useState } from 'react';
import './feed.css';
import { Banner, Button, Dialog, DialogClose, Select, Stack, Text, TextArea, TextField } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { api, errorText } from '../../shell';
import type { TopStory } from './api';

/*
 * The podcast from the briefing, as the old BriefingSection: the AI writes a bulletin script from
 * the briefing's stories (/api/generate_podcast_script), the reader can edit it, then text to
 * speech reads it out (/api/generate_tts_podcast, a paid voice service) and the page polls
 * /api/podcast/status until the audio is ready. Both steps are buttons that ask first.
 */

type Story = TopStory & Record<string, unknown>;

const DURATIONS = [
  { value: 'short', label: 'Short (about 2 minutes)' },
  { value: 'medium', label: 'Medium (about 5 minutes)' },
  { value: 'long', label: 'Long (about 10 minutes)' },
];

function articlesFor(stories: Story[]) {
  return stories.map((s) => ({
    title: s.title || s.headline || 'Untitled',
    summary: s.executive_takeaway || s.summary || '',
    source: (s.source as string) || '',
    category: s.category || 'General',
    future_signal: s.signal_strength || 'N/A',
    sentiment: s.risk_opportunity || 'N/A',
    time_to_impact: s.time_horizon || 'N/A',
    executive_takeaway: s.executive_takeaway || '',
    strategic_relevance: s.strategic_relevance || '',
    time_horizon: s.time_horizon || 'N/A',
    risk_opportunity: s.risk_opportunity || 'N/A',
    signal_strength: s.signal_strength || 'N/A',
    detailed_report: (s.detailed_report as unknown) ?? null,
  }));
}

interface Voice { voice_id: string; name: string; category?: string }

export function BriefingPodcast({ open, onOpenChange, stories, persona, model, askConfirm, notify }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  stories: TopStory[];
  persona: string;
  model: string;
  askConfirm: (c: Confirm) => void;
  notify: (m: string) => void;
}) {
  const [script, setScript] = useState('');
  const [title, setTitle] = useState('');
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [voice, setVoice] = useState('');
  const [duration, setDuration] = useState('medium');
  const [busy, setBusy] = useState<null | 'script' | 'audio'>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poll = useRef<number | null>(null);

  const stopPoll = () => {
    if (poll.current) window.clearInterval(poll.current);
    poll.current = null;
  };
  useEffect(() => stopPoll, []);

  // The voice list is a free listing from the voice service; it loads when the dialog opens
  useEffect(() => {
    if (!open) return;
    setError(null);
    setTitle((t) => t || `Executive briefing for ${persona}, ${new Date().toLocaleDateString('en-GB')}`);
    if (voices) return;
    api<Voice[]>('/api/available_voices').then(
      (v) => {
        setVoices(v);
        if (v.length && !voice) setVoice(v[0].voice_id);
      },
      () => setVoices([]),
    );
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const writeScript = () =>
    askConfirm({
      title: 'Write the podcast script with the AI?',
      message: `The AI (${model}) writes a spoken bulletin from the ${stories.length} stories in your briefing. It is one AI call. You can edit the script before any audio is made.`,
      action: 'Write the script',
      onConfirm: () => void (async () => {
        setBusy('script');
        setError(null);
        try {
          const r = await api<{ script?: string }>('/api/generate_podcast_script', {
            method: 'POST',
            json: { podcast_name: 'Your Briefing', episode_title: title, model, mode: 'bulletin', duration, articles: articlesFor(stories as Story[]) },
          });
          if (!r.script) throw new Error('The AI returned no script');
          setScript(r.script);
        } catch (e) {
          setError(`The script wasn’t written: ${errorText(e)}`);
        } finally {
          setBusy(null);
        }
      })(),
    });

  const makeAudio = () =>
    askConfirm({
      title: 'Make the audio?',
      message: 'The script is read out by a paid text-to-speech service, charged by length. It usually takes one to three minutes.',
      action: 'Make the audio',
      onConfirm: () => void (async () => {
        setBusy('audio');
        setError(null);
        setAudioUrl(null);
        try {
          const r = await api<{ podcast_id?: string; audio_url?: string }>('/api/generate_tts_podcast', {
            method: 'POST',
            json: { podcast_name: 'Your Briefing', episode_title: title, script, mode: 'bulletin', duration, host_voice_id: voice },
          });
          if (r.audio_url) {
            setAudioUrl(r.audio_url);
            setBusy(null);
            return;
          }
          if (!r.podcast_id) throw new Error('The voice service didn’t start a job');
          const started = Date.now();
          stopPoll();
          poll.current = window.setInterval(() => {
            api<{ status: string; audio_url?: string; error?: unknown }>(`/api/podcast/status/${r.podcast_id}`).then(
              (s) => {
                if (s.status === 'completed' && s.audio_url) {
                  stopPoll();
                  setAudioUrl(s.audio_url);
                  setBusy(null);
                  notify('Your briefing podcast is ready. It is also kept under Saved.');
                } else if (s.status === 'failed') {
                  stopPoll();
                  setError(`The audio failed: ${typeof s.error === 'string' ? s.error : 'the voice service reported an error'}`);
                  setBusy(null);
                } else if (Date.now() - started > 5 * 60_000) {
                  stopPoll();
                  setError('The audio took more than five minutes. It may still finish; look under Saved later.');
                  setBusy(null);
                }
              },
              () => undefined,
            );
          }, 2500);
        } catch (e) {
          setError(`The audio wasn’t made: ${errorText(e)}`);
          setBusy(null);
        }
      })(),
    });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Briefing podcast"
      description="Turn your briefing into a short spoken bulletin: the AI writes the script, then a voice reads it."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
          <Button variant="secondary" size="lg" busy={busy === 'script'} disabled={busy !== null || !stories.length} onClick={writeScript}>{script ? 'Write the script again' : 'Write the script'}</Button>
          <Button size="lg" busy={busy === 'audio'} disabled={busy !== null || !script.trim() || !voice} onClick={makeAudio}>Make the audio</Button>
        </>
      }
    >
      <Stack gap="md">
        <TextField label="Episode title" value={title} onChange={setTitle} maxLength={200} />
        <Stack direction="row" gap="md">
          <Select label="Length" options={DURATIONS} value={duration} onValueChange={setDuration} />
          <Select
            label="Voice"
            options={(voices ?? []).map((v) => ({ value: v.voice_id, label: v.category ? `${v.name} (${v.category})` : v.name }))}
            value={voice}
            onValueChange={setVoice}
            placeholder={voices === null ? 'Loading voices…' : voices.length ? 'Pick a voice' : 'No voices available'}
            disabled={!voices?.length}
          />
        </Stack>
        <TextArea
          label="Script"
          rows={12}
          value={script}
          onChange={setScript}
          hint={script ? 'Edit freely; the audio reads exactly this text.' : 'Write the script first, or paste your own.'}
        />
        {busy === 'audio' && <Text variant="caption">Making the audio. You can close this dialog; the finished episode is kept under Saved.</Text>}
        {audioUrl && (
          <Stack gap="sm">
            <Text variant="label">Your podcast</Text>
            <audio controls src={audioUrl} className="feed-audio" />
          </Stack>
        )}
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
      </Stack>
    </Dialog>
  );
}
