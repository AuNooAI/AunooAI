import { useState } from 'react';
import { Banner, Button, Chip, Icon, Panel, Select, Stack, Text, TextField } from '@aunoo/ui';
import type { FollowedAccount } from '@monolith/marketMonitorApi';

/**
 * The accounts we follow for this market. Their timelines are read on each collection and the posts
 * that touch the market are kept, whatever the keyword search caught. They lead "Voices worth
 * reading" on the market's front page.
 */
export function FollowPanel({ followed, busy, note, onFollow, onUnfollow, onCollect }: {
  followed: FollowedAccount[] | null;
  busy: boolean;
  note: string | null;
  onFollow: (platform: string, handle: string) => Promise<boolean>;
  onUnfollow: (platform: string, handle: string) => void;
  onCollect: () => void;
}) {
  const [platform, setPlatform] = useState('twitter');
  const [handle, setHandle] = useState('');
  const submit = async () => {
    if (!handle.trim()) return;
    if (await onFollow(platform, handle.trim())) setHandle('');
  };

  return (
    <Panel
      title="Accounts we follow"
      headingLevel={3}
      description="Their timelines are read on each collection, and the posts that touch the market are kept whatever the keyword search caught. They lead “Voices worth reading” on the market’s front page."
      headerAside={
        <Button variant="secondary" size="sm" iconStart={<Icon name="ArrowsClockwise" size="sm" />} disabled={busy || !followed?.length} onClick={onCollect}>
          Read them now
        </Button>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          {followed === null ? <Text variant="caption">Loading…</Text> : followed.length === 0 ? <Text variant="caption">None yet.</Text> : followed.map((f) => (
            <Chip
              key={`${f.platform}:${f.handle}`}
              tone="neutral"
              icon={<Icon name="X" size="sm" />}
              label={`Stop following @${f.handle}`}
              onClick={busy ? undefined : () => onUnfollow(f.platform, f.handle)}
            >
              {`${f.display_name ? `${f.display_name} · ` : ''}@${f.handle} (${f.platform === 'twitter' ? 'X' : f.platform})`}
            </Chip>
          ))}
        </Stack>
        <Stack direction="row" gap="sm">
          <Select
            label="Platform"
            hideLabel
            options={[{ value: 'twitter', label: 'X' }, { value: 'bluesky', label: 'Bluesky' }, { value: 'reddit', label: 'Reddit' }]}
            value={platform}
            onValueChange={setPlatform}
          />
          <TextField label="Handle" hideLabel placeholder="@handle" maxLength={200} value={handle} onChange={setHandle} onSubmit={() => void submit()} />
          <Button iconStart={<Icon name="Plus" size="sm" />} disabled={busy || !handle.trim()} onClick={() => void submit()}>Follow</Button>
        </Stack>
        <Text variant="hint">Following an account profiles it first if it has no profile yet (two xpoz calls and one short model call). The provider has no per-user history for Reddit.</Text>
        {note && <Banner tone="info" title="Follow list" description={note} />}
      </Stack>
    </Panel>
  );
}
