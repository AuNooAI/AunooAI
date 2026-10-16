import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Chip, Icon, IconButton, Panel, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import {
  collectFollowed, followAccount, getFollowed, getTopVoices, getVoiceProfileJob, profileAllVoices, profileVoice, unfollowAccount,
  type FollowedAccount, type TopVoices, type Voice, type VoiceProfileJob,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { LinkButton, Missing, SortTable } from '../shared/SortTable';
import { VendorSwatch } from '../shared/colours';
import { FollowPanel } from './voices/FollowPanel';
import { clip, compact, keyOf, platformLabel, PROFILABLE, roleNote, roleOf, sentence, vendorTagText } from './voices/helpers';
import { VoiceSheet } from './voices/VoiceSheet';
import { AccountPhoto } from '../shared/RemoteImage';


/*
 * Top voices: the outside accounts posting about this market, as the old MarketVoicesView.tsx, on
 * /api/market-monitor/markets/{id}/voices. A handle on its own is a stranger, so each row links to
 * the account and its latest post, and carries the account profile Brand Watcher builds once one has
 * been built. Profiles are paid (two xpoz calls and one short model call each), so building them is
 * always a button, and the bulk runs ask first.
 */
export function Voices(ctx: MmContext) {
  const { marketId, periodDays, colours, askConfirm, openRecords } = ctx;
  const [voices, setVoices] = useState<TopVoices | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [job, setJob] = useState<VoiceProfileJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [followed, setFollowed] = useState<FollowedAccount[] | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const [followNote, setFollowNote] = useState<string | null>(null);

  const load = useCallback(
    () => getTopVoices(marketId, periodDays, 50).then((v) => setVoices(v), (e) => setError(errorText(e))),
    [marketId, periodDays],
  );
  const loadFollowed = useCallback(() => getFollowed(marketId).then((r) => setFollowed(r.accounts), () => setFollowed([])), [marketId]);

  useEffect(() => {
    let live = true;
    setVoices(null);
    setError(null);
    setSelected(null);
    getTopVoices(marketId, periodDays, 50).then((v) => live && setVoices(v), (e) => live && setError(errorText(e)));
    // A profiling run started before this view opened is still worth showing
    getVoiceProfileJob(marketId).then((j) => live && j.state === 'running' && setJob(j), () => undefined);
    return () => {
      live = false;
    };
  }, [marketId, periodDays]);
  useEffect(() => {
    void loadFollowed();
  }, [loadFollowed]);

  // Poll a running bulk job, and reload the table when it ends so the new profiles show
  const running = job?.state === 'running';
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => {
      getVoiceProfileJob(marketId).then((j) => {
        setJob(j);
        if (j.state !== 'running') void load();
      }, () => undefined);
    }, 3000);
    return () => window.clearInterval(t);
  }, [running, marketId, load]);

  const isFollowed = (v: Voice) => !!v.account?.watchlisted || !!followed?.some((f) => f.platform === v.platform && f.handle.toLowerCase() === v.author.toLowerCase());

  const follow = async (platform: string, handle: string) => {
    const h = handle.replace(/^@/, '');
    setFollowBusy(true);
    setFollowNote(null);
    try {
      await followAccount(marketId, platform, h);
      setFollowNote(`Following @${h}. Its posts that touch the market are read on the next collection.`);
      void loadFollowed();
      void load();
      return true;
    } catch (e) {
      setFollowNote(`Couldn’t follow @${h}: ${errorText(e)}`);
      return false;
    } finally {
      setFollowBusy(false);
    }
  };
  const unfollow = async (platform: string, handle: string) => {
    setFollowBusy(true);
    setFollowNote(null);
    try {
      await unfollowAccount(marketId, platform, handle);
      void loadFollowed();
      void load();
    } catch (e) {
      setFollowNote(`Couldn’t stop following @${handle}: ${errorText(e)}`);
    } finally {
      setFollowBusy(false);
    }
  };
  const collectNow = async () => {
    setFollowBusy(true);
    setFollowNote(null);
    try {
      const r = await collectFollowed(marketId);
      setFollowNote(
        `${r.accounts} account${r.accounts === 1 ? '' : 's'} read: ${r.fetched} posts, ${r.matched} about the market, ${r.stored} new.${r.skipped.length ? ` Skipped: ${r.skipped.join('; ')}` : ''}`,
      );
      void load();
    } catch (e) {
      setFollowNote(`Couldn’t read the followed accounts: ${errorText(e)}`);
    } finally {
      setFollowBusy(false);
    }
  };

  const profileOne = async (v: Voice) => {
    const k = keyOf(v);
    setBusy((prev) => new Set(prev).add(k));
    setJobError(null);
    try {
      await profileVoice(marketId, v.platform, v.author);
      await load();
      setSelected(k);
    } catch (e) {
      setJobError(`@${v.author}: ${errorText(e)}`);
    } finally {
      setBusy((prev) => {
        const n = new Set(prev);
        n.delete(k);
        return n;
      });
    }
  };
  const profileAll = (refresh: boolean, count: number) =>
    askConfirm({
      title: refresh ? `Rebuild all ${count} profiles?` : `Profile ${count} accounts?`,
      message: `Each profile costs two xpoz calls and one short model call, so this makes about ${count * 2} xpoz calls and ${count} model calls. It runs in the background; the table updates when it ends.`,
      action: refresh ? 'Rebuild profiles' : 'Build profiles',
      onConfirm: () => {
        setJobError(null);
        profileAllVoices(marketId, { days: periodDays, limit: 50, refresh }).then(
          (j) => {
            setJob(j);
            if (j.state !== 'running') void load();
          },
          (e) => setJobError(errorText(e)),
        );
      },
    });

  const voicePosts = (v: Voice) =>
    openRecords({ kind: 'voice', title: `@${v.author}: posts about this market`, author: v.author, days: periodDays, expectedTotal: v.posts });

  if (error) return <Banner tone="error" title="Top voices didn’t load" description={error} />;

  const rows = voices?.voices ?? [];
  const unprofiled = rows.filter((v) => PROFILABLE.has(v.platform) && !v.account?.profiled).length;
  const current = selected ? rows.find((v) => keyOf(v) === selected) ?? null : null;

  return (
    <>
      <Panel
        title="Top voices"
        description="Accounts posting about the market. Vendors’ LinkedIn company posts are counted under Analysis, not here; a vendor’s own X, Bluesky or Reddit account stays on this list and is marked."
        headerAside={
          <Stack direction="row" gap="sm">
            <Button variant="secondary" size="sm" iconStart={<Icon name="User" size="sm" />} disabled={!voices || running || unprofiled === 0} onClick={() => profileAll(false, unprofiled)}>
              {unprofiled === 0 ? 'All shown accounts profiled' : `Profile the ${unprofiled} unprofiled`}
            </Button>
            <Button variant="ghost" size="sm" iconStart={<Icon name="ArrowsClockwise" size="sm" />} disabled={!voices || running || rows.length === 0} onClick={() => profileAll(true, rows.length)}>
              Rebuild all
            </Button>
          </Stack>
        }
      >
        {!voices ? <Skeleton variant="text" lines={8} /> : (
          <Stack gap="md">
            <Text variant="caption">
              {sentence(voices.coverage.label)}.{!voices.coverage.complete ? ' Not every vendor is covered yet.' : ''} {voices.accounts} accounts posted in the period, {voices.accounts_multi_post} of
              them more than once. Sorted by posts, then reactions, so a single post that travelled sits below an account that keeps posting. {voices.profiled} of the {rows.length} shown have a profile.
            </Text>
            {running && <Banner tone="info" title="Building profiles" description={`Profiling ${job?.done ?? 0} of ${job?.total ?? 0}…`} />}
            {job?.state === 'done' && (
              <Text variant="caption">
                {`Last run: ${job.built ?? 0} built${job.failed ? `, ${job.failed} failed` : ''}${job.skipped ? `, ${job.skipped} skipped` : ''}.`}
                {job.errors?.length ? ` Failures: ${job.errors.join('; ')}` : ''}
              </Text>
            )}
            {jobError && <Banner tone="error" title="Profiling failed" description={jobError} />}

            <SortTable
              caption="Top voices"
              rows={rows}
              rowKey={keyOf}
              initialSort="posts"
              initialDir="desc"
              emptyText="No outside accounts posted about this market in the period."
              columns={[
                {
                  key: 'author', label: 'Account', rowHeader: true, wrap: true, value: (v) => v.author,
                  render: (v) => (
                    <Stack gap="sm">
                      <Stack direction="row" gap="sm">
                        <AccountPhoto src={v.account?.avatar_url} size={28} icon={<Icon name="User" size="sm" />} />
                        {v.profile_url ? <TextLink href={v.profile_url} external>{`@${v.author}`}</TextLink> : <span>{`@${v.author}`}</span>}
                        <IconButton
                          icon={<Icon name={isFollowed(v) ? 'BookmarkSimple' : 'Star'} size="sm" />}
                          label={isFollowed(v) ? `Stop following @${v.author}` : `Follow @${v.author}: read its timeline for the market`}
                          disabled={followBusy || (!isFollowed(v) && !['twitter', 'bluesky', 'reddit'].includes(v.platform))}
                          onClick={() => void (isFollowed(v) ? unfollow(v.platform, v.author) : follow(v.platform, v.author))}
                        />
                        {isFollowed(v) && <Chip tone="accent" size="sm">followed</Chip>}
                      </Stack>
                      {v.vendor_tag && <Chip tone="warning" size="sm">{vendorTagText(v.vendor_tag)}</Chip>}
                      {v.account?.profiled && (
                        <Text variant="caption">
                          {[v.account.display_name, v.account.followers != null ? `${compact(v.account.followers)} followers` : null, v.account.verified ? 'verified' : null].filter(Boolean).join(' · ')}
                        </Text>
                      )}
                    </Stack>
                  ),
                },
                { key: 'platform', label: 'Platform', groupable: true, value: (v) => platformLabel(v.platform), render: (v) => platformLabel(v.platform) },
                {
                  key: 'role', label: 'Role', groupable: true, wrap: true, value: roleOf,
                  render: (v) => (roleNote(v) ? <Text as="span" variant="hint">{`${roleOf(v)} (${roleNote(v)})`}</Text> : roleOf(v)),
                },
                {
                  key: 'who', label: 'Who they are', sortable: false, wrap: true,
                  render: (v) => v.account?.profiled ? (
                    <Stack gap="sm">
                      <LinkButton onClick={() => setSelected(keyOf(v))} label={`Open the profile of @${v.author}`}>{clip(v.account.summary, 100) || 'Open the profile'}</LinkButton>
                      {v.account.relation && <Text as="span" variant="caption">{clip(v.account.relation, 80)}</Text>}
                    </Stack>
                  ) : PROFILABLE.has(v.platform) ? (
                    <Stack direction="row" gap="sm">
                      <Button variant="secondary" size="sm" busy={busy.has(keyOf(v))} disabled={running} iconStart={<Icon name="User" size="sm" />} onClick={() => void profileOne(v)}>Profile</Button>
                      <LinkButton onClick={() => setSelected(keyOf(v))}>Details</LinkButton>
                    </Stack>
                  ) : <Missing>can’t be profiled</Missing>,
                },
                {
                  // What they talk about is the useful part; capped so a row doesn't grow tall
                  key: 'about', label: 'Talking about', sortable: false, wrap: true,
                  render: (v) => {
                    const terms = v.terms.slice(0, 4);
                    const named = v.vendors.slice(0, 3);
                    const extra = v.terms.length - terms.length + (v.vendors.length - named.length);
                    if (!terms.length && !named.length) return <Missing />;
                    return (
                      <Stack direction="row" gap="sm">
                        {terms.map((t) => <Chip key={t.term} tone="muted" size="sm">{t.term}</Chip>)}
                        {named.map((x) => <Chip key={x.vendor} tone="info" size="sm" icon={<VendorSwatch color={colours.byName(x.vendor)} />}>{x.vendor}</Chip>)}
                        {extra > 0 && <Text as="span" variant="hint">{`+${extra} more`}</Text>}
                      </Stack>
                    );
                  },
                },
                // Opens every relevant post by this account: a ranked handle whose posts can't be read is only an assertion
                { key: 'posts', label: 'Posts', align: 'end', render: (v) => <LinkButton onClick={() => voicePosts(v)} label={`${v.posts} posts by @${v.author}`}>{v.posts}</LinkButton> },
                { key: 'engagement', label: 'Reactions', align: 'end' },
                {
                  key: 'last_seen', label: 'Latest post', align: 'end', value: (v) => v.last_seen,
                  render: (v) => {
                    const date = (v.last_seen ?? '').slice(0, 10) || '—';
                    return v.latest_post?.url ? <TextLink href={v.latest_post.url} external>{date}</TextLink> : date;
                  },
                },
              ]}
            />
          </Stack>
        )}
      </Panel>

      <FollowPanel followed={followed} busy={followBusy} note={followNote} onFollow={follow} onUnfollow={(p, h) => void unfollow(p, h)} onCollect={() => void collectNow()} />

      <VoiceSheet
        voice={current}
        busy={current ? busy.has(keyOf(current)) : false}
        onClose={() => setSelected(null)}
        onRebuild={() => current && void profileOne(current)}
        onPosts={() => current && voicePosts(current)}
      />
    </>
  );
}
