import { useEffect, useRef, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Select, Skeleton, Stack, Text } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import './agents.css';

/*
 * Voices a script with ElevenLabs and plays it, after the old pages' podcast flow
 * (POST /api/generate_tts_podcast, then polling /api/podcast/status/{id}). Voicing is paid, so
 * nothing runs until the reader picks a voice and presses the button, and the dialog says so.
 * When audio already exists (an agent run with a voice set voices its summary itself), it just
 * plays it.
 */

interface Voice { voice_id: string; name: string; category?: string }
interface StartResponse { podcast_id?: string; audio_url?: string }
interface StatusResponse { status: string; audio_url?: string | null; error?: string | null }

// The TTS service reads roughly 150 words a minute
const minutesOf = (text: string) => Math.max(1, Math.round(text.split(/\s+/).filter(Boolean).length / 150));

/** Markdown down to speakable text: no headings marks, links, tables or emphasis */
export function speakable(md: string) {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s*\|.*\|\s*$/gm, ' ')
    .replace(/^#+\s*/gm, '')
    .replace(/[*_`>]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function VoiceDialog({ open, onOpenChange, title, script, audioUrl, defaultVoice, notify }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  /** What gets read out */
  script: string;
  /** Existing audio; when set, the dialog only plays it */
  audioUrl?: string | null;
  defaultVoice?: string | null;
  notify: (m: string) => void;
}) {
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [voice, setVoice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audio, setAudio] = useState<string | null>(audioUrl ?? null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setAudio(audioUrl ?? null);
    setError(null);
    // The voice list is a free listing from ElevenLabs; it only loads once the dialog opens
    if (!audioUrl && voices === null) {
      api<Voice[]>('/api/available_voices').then(
        (list) => {
          setVoices(list);
          setVoice((v) => v || defaultVoice || (list.find((x) => x.category === 'premade') ?? list[0])?.voice_id || '');
        },
        (e) => { setVoices([]); setError(`Voices didn’t load: ${errorText(e)}`); },
      );
    }
  }, [open, audioUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<StartResponse>('/api/generate_tts_podcast', {
        method: 'POST',
        json: { podcast_name: 'Observer agents', episode_title: title, script, mode: 'bulletin', duration: 'short', host_voice_id: voice },
      });
      if (r.audio_url) { setAudio(r.audio_url); setBusy(false); return; }
      if (!r.podcast_id) throw new Error('The server didn’t start the audio.');
      const started = Date.now();
      timer.current = window.setInterval(async () => {
        try {
          const s = await api<StatusResponse>(`/api/podcast/status/${r.podcast_id}`);
          if (s.status === 'completed' && s.audio_url) {
            window.clearInterval(timer.current!);
            setAudio(s.audio_url);
            setBusy(false);
            notify('The audio is ready. It is also listed under Saved podcasts.');
          } else if (s.status === 'failed') {
            window.clearInterval(timer.current!);
            setError(s.error || 'The audio failed.');
            setBusy(false);
          } else if (Date.now() - started > 5 * 60_000) {
            window.clearInterval(timer.current!);
            setError('No audio after five minutes. It may still finish; check Saved podcasts later.');
            setBusy(false);
          }
        } catch {
          // a missed poll; the next one tries again
        }
      }, 2500);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };

  const minutes = minutesOf(script);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={audio ? `Listen: ${title}` : `Voice “${title}”`}
      description={audio ? undefined : `Reads the text aloud with an AI voice (ElevenLabs). About ${minutes} minute${minutes === 1 ? '' : 's'} of audio; voicing is paid per character.`}
      footer={audio ? <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose> : (
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" busy={busy} disabled={busy || !voice || !script.trim()} onClick={() => void generate()}>{busy ? 'Making the audio…' : 'Make the audio'}</Button>
        </>
      )}
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="No audio" description={error} />}
        {audio ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls src={audio} className="agents-audio">Your browser can’t play this audio.</audio>
        ) : voices === null ? <Skeleton variant="text" lines={2} /> : (
          <>
            <Select label="Voice" fullWidth options={voices.map((v) => ({ value: v.voice_id, label: v.category ? `${v.name} (${v.category})` : v.name }))} value={voice || undefined} onValueChange={setVoice} disabled={busy} />
            {busy && <Text variant="caption">This usually takes under a minute. You can close this; the audio still appears under Saved podcasts.</Text>}
          </>
        )}
      </Stack>
    </Dialog>
  );
}
