import { useEffect, useState } from 'react';
import { Button, Checkbox, Collapsible, CollapsibleContent, CollapsibleTrigger, Select, Stack, Switch, Text, TextArea, TextField } from '@aunoo/ui';
import { DEFAULT_PODCAST_PROMPT, DEFAULT_REPORT_PROMPT, type AgentForm } from './form';

/*
 * What an agent does when it finds matches. Every one of these runs later, when the agent runs;
 * ticking a box here only saves the setting.
 */

interface Voice { voice_id: string; name: string; category?: string }

export function ActionsPanel({ f, set, disabled }: { f: AgentForm; set: (p: Partial<AgentForm>) => void; disabled: boolean }) {
  const [voices, setVoices] = useState<Voice[] | null>(null);

  // The voice list comes from ElevenLabs through the server (a listing, not an audio job), and only
  // once podcasts are switched on, as on the old dialog
  useEffect(() => {
    if (!f.podcast || voices) return;
    fetch('/api/available_voices', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : []))
      .then(
        (list: Voice[]) => {
          setVoices(Array.isArray(list) ? list : []);
          if (!f.podcastVoice && Array.isArray(list) && list.length) set({ podcastVoice: (list.find((v) => v.category === 'premade') ?? list[0]).voice_id });
        },
        () => setVoices([]),
      );
  }, [f.podcast]); // eslint-disable-line react-hooks/exhaustive-deps

  const voiceOptions = (voices ?? []).map((v) => ({ value: v.voice_id, label: v.category ? `${v.name} (${v.category})` : v.name }));
  if (f.podcastVoice && !voiceOptions.some((o) => o.value === f.podcastVoice)) voiceOptions.unshift({ value: f.podcastVoice, label: f.podcastVoice });

  return (
    <Stack gap="md">
      <Text variant="caption">
        Matches always go to the notification bell for review. The rest is up to you. Email and Bluesky messages go out only when a run finds at
        least as many matches as the alert threshold on the Search tab.
      </Text>

      <Switch
        label="Tag matching articles"
        description="Adds a “SIGNAL_<agent name>” tag to each match so you can filter on it. Scheduled runs follow this setting; a manual run asks again."
        checked={f.tagArticles}
        onCheckedChange={(tagArticles) => set({ tagArticles })}
        disabled={disabled}
      />
      <Switch label="Star matching articles" description="Adds the matches to your starred articles." checked={f.starArticles} onCheckedChange={(starArticles) => set({ starArticles })} disabled={disabled} />

      <Switch
        label="Write a report"
        description="The AI writes a summary report of each run’s matches."
        checked={f.report}
        onCheckedChange={(report) => set({ report })}
        disabled={disabled}
      />
      {f.report && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm">Report instructions</CollapsibleTrigger>
          <CollapsibleContent>
            <Stack gap="sm">
              <TextArea label="How the AI should analyse and summarise the matches" rows={6} value={f.reportPrompt} onChange={(reportPrompt) => set({ reportPrompt })} />
              <Checkbox
                label="Include recommendations and guidance (off by default: reports state findings, themes and significance only; this adds a section scoped to your organisation’s remit)"
                checked={f.includeRecommendations}
                onCheckedChange={(includeRecommendations) => set({ includeRecommendations })}
                disabled={disabled}
              />
              <div><Button variant="ghost" size="sm" disabled={disabled} onClick={() => set({ reportPrompt: DEFAULT_REPORT_PROMPT })}>Reset to the default instructions</Button></div>
            </Stack>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Switch
        label="Write a podcast script"
        description="The AI writes a short spoken-style summary of the matches, for turning into audio."
        checked={f.podcast}
        onCheckedChange={(podcast) => set({ podcast })}
        disabled={disabled}
      />
      {f.podcast && (
        <Stack gap="sm">
          <Select
            label="Voice"
            hint="The voice used when the script is turned into audio."
            placeholder={voices === null ? 'Loading voices…' : voiceOptions.length ? 'Pick a voice' : 'No voices available'}
            options={voiceOptions}
            value={f.podcastVoice || undefined}
            onValueChange={(podcastVoice) => set({ podcastVoice })}
            disabled={disabled || !voiceOptions.length}
            fullWidth
          />
          <Collapsible>
            <CollapsibleTrigger variant="ghost" size="sm">Podcast instructions</CollapsibleTrigger>
            <CollapsibleContent>
              <Stack gap="sm">
                <TextArea label="How the AI should write the spoken summary" rows={6} value={f.podcastPrompt} onChange={(podcastPrompt) => set({ podcastPrompt })} />
                <div><Button variant="ghost" size="sm" disabled={disabled} onClick={() => set({ podcastPrompt: DEFAULT_PODCAST_PROMPT })}>Reset to the default instructions</Button></div>
              </Stack>
            </CollapsibleContent>
          </Collapsible>
        </Stack>
      )}

      <Switch
        label="Deep research"
        description="Runs a further search of the collected articles for more material related to the matches."
        checked={f.deepResearch}
        onCheckedChange={(deepResearch) => set({ deepResearch })}
        disabled={disabled}
      />

      <Switch label="Send an email" description="Emails the matches, with a download link that needs no login." checked={f.sendEmail} onCheckedChange={(sendEmail) => set({ sendEmail })} disabled={disabled} />
      {f.sendEmail && (
        <Stack gap="sm">
          <TextField label="Recipient" type="email" placeholder="recipient@example.com" hint="Leave blank to use the site’s default notification address." value={f.emailRecipient} onChange={(emailRecipient) => set({ emailRecipient })} disabled={disabled} />
          <Checkbox
            label="Attach the report as a PDF, so it can be read offline and forwarded"
            checked={f.attachPdf}
            onCheckedChange={(attachPdf) => set({ attachPdf })}
            disabled={disabled}
          />
        </Stack>
      )}

      <Switch label="Send a Bluesky message" description="Sends a direct message on Bluesky when matches are found." checked={f.blueskyDm} onCheckedChange={(blueskyDm) => set({ blueskyDm })} disabled={disabled} />
      {f.blueskyDm && (
        <TextField label="Bluesky handle" placeholder="@username or username.bsky.social" value={f.blueskyRecipient} onChange={(blueskyRecipient) => set({ blueskyRecipient })} disabled={disabled} />
      )}
    </Stack>
  );
}
