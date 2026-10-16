import { Banner, Button, Chip, Icon, Sheet, Stack, Text, TextLink } from '@aunoo/ui';
import type { Voice } from '@monolith/marketMonitorApi';
import { compact, platformLabel, PROFILABLE, vendorTagText } from './helpers';
import { AccountPhoto } from '../../shared/RemoteImage';

/**
 * One account read in full: who they are, their reach, what they post about and their part in this
 * market. Building or rebuilding the profile is a paid call (two xpoz calls and one short model
 * call), so it only runs from the button.
 */
export function VoiceSheet({ voice, busy, onClose, onRebuild, onPosts }: {
  voice: Voice | null;
  busy: boolean;
  onClose: () => void;
  onRebuild: () => void;
  onPosts: () => void;
}) {
  if (!voice) return null;
  const a = voice.account;
  const facts = a?.profiled
    ? [
      `${compact(a.followers)} followers`,
      a.posts_count != null ? `${compact(a.posts_count)} posts on the platform` : null,
      `${voice.posts} about this market, ${voice.engagement} reactions`,
      a.last_profiled_at ? `profiled ${a.last_profiled_at.slice(0, 10)}` : null,
    ].filter(Boolean).join(' · ')
    : `Not profiled yet. ${voice.posts} post${voice.posts === 1 ? '' : 's'} about this market, ${voice.engagement} reactions.`;

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      title={a?.display_name ?? `@${voice.author}`}
      description={`@${voice.author} on ${platformLabel(voice.platform)}${a?.verified ? ', verified' : ''}`}
      footer={
        <Stack direction="row" gap="sm">
          <Button variant="secondary" onClick={onPosts}>Their posts about this market</Button>
          {PROFILABLE.has(voice.platform) && (
            <Button variant="secondary" busy={busy} iconStart={<Icon name="ArrowsClockwise" size="sm" />} onClick={onRebuild}>
              {a?.profiled ? 'Rebuild profile' : 'Build profile'}
            </Button>
          )}
        </Stack>
      }
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <AccountPhoto src={a?.avatar_url} size={56} icon={<Icon name="User" />} />
          {voice.profile_url && <TextLink href={voice.profile_url} external>{`Open @${voice.author} on ${platformLabel(voice.platform)}`}</TextLink>}
          {voice.latest_post?.url && <TextLink href={voice.latest_post.url} external>Latest post</TextLink>}
        </Stack>
        {voice.vendor_tag && <Banner tone="info" title="A vendor’s own voice" description={vendorTagText(voice.vendor_tag)} />}
        <Text variant="caption">{facts}</Text>
        {a?.profiled && (
          <>
            {a.bio && <Text>{a.bio}</Text>}
            {a.summary && <Text>{a.summary}</Text>}
            {a.relation && (
              <Stack gap="sm">
                <Text variant="label">In this market</Text>
                <Text>{a.relation}</Text>
              </Stack>
            )}
            {a.topics.length > 0 && (
              <Stack direction="row" gap="sm">
                {a.topics.map((t) => <Chip key={t} tone="muted" size="sm">{t}</Chip>)}
              </Stack>
            )}
          </>
        )}
        {PROFILABLE.has(voice.platform) && (
          <Text variant="hint">A profile costs two xpoz calls and one short model call. It’s the same profile Brand Watcher’s Accounts tab shows.</Text>
        )}
      </Stack>
    </Sheet>
  );
}
