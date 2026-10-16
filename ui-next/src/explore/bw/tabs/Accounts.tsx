import { useCallback, useEffect, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, Dialog, DialogClose, EmptyState, Eyebrow, Grid, Icon, IconButton, Panel, PanelDivider, Select, Skeleton, Stack,
  StackedBarChart, StackedBars, Stat, TagInput, Text, TextArea, TextField, TextLink,
} from '@aunoo/ui';
import {
  buildAccountProfile, deepDiveAccount, deleteAccountProfile, emailAccountReport, getAccountProfile, listAccountProfiles, setAccountAnnotation,
  setAccountTags, setAccountWatchlist, type BWAccountDeepDive, type BWAccountProfile,
} from '@monolith/socialProfileApi';
import { buildAccountReportHtml, downloadAccountReport } from '@monolith/socialProfileReportHtml';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';
import { AddToIncidentDialog, type IncidentSource } from '../overlays/AddToIncidentDialog';
import { PROFILE_PLATFORMS, fmtCount, platLabel, sentOf, SENT_TONE, signed, takeQueuedAccount } from './social/helpers';

/*
 * Accounts: one social account's identity, reach, what it posts about and how it talks about the
 * brand, as the old Accounts sub-tab. Stored profiles are read from the database; building or
 * refreshing a profile and the deep dive read the account from Xpoz, which uses paid credits,
 * so they run only from their buttons.
 */

const PLATFORMS = PROFILE_PLATFORMS.map((p) => ({ value: p, label: platLabel(p) }));

function EmailDialog({ profile, deep, onClose, notify }: { profile: BWAccountProfile | null; deep: BWAccountDeepDive | null; onClose: () => void; notify: (m: string) => void }) {
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setTo('');
    setError(null);
  }, [profile]);
  const send = async () => {
    if (!profile) return;
    setBusy(true);
    try {
      await emailAccountReport(profile.id, to.trim(), buildAccountReportHtml(profile, deep, new Date().toISOString()));
      notify(`Report for @${profile.handle} sent to ${to.trim()}`);
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to.trim());
  return (
    <Dialog
      open={!!profile}
      onOpenChange={(o) => !o && onClose()}
      title="Email this report"
      description={profile ? `@${profile.handle} on ${platLabel(profile.platform)}` : undefined}
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy || !valid} onClick={() => void send()}>{busy ? 'Sending…' : 'Send'}</Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Not sent" description={error} />}
        <TextField label="Send to" type="email" value={to} onChange={setTo} onSubmit={() => valid && void send()} hint="The same HTML report as the download, as an attachment." />
      </Stack>
    </Dialog>
  );
}

function DeepDive({ dd, onClose }: { dd: BWAccountDeepDive; onClose: () => void }) {
  return (
    <Stack gap="md">
      <Stack direction="row" justify="between" gap="sm">
        <Eyebrow as="h4">Deep dive, {dd.posts_analyzed} posts</Eyebrow>
        <Button variant="ghost" size="sm" onClick={onClose}>Hide</Button>
      </Stack>
      <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Engagement">
        <li><Stat size="compact" label="Total likes" value={fmtCount(dd.engagement.total_likes) ?? '–'} /></li>
        <li><Stat size="compact" label="Average likes" value={fmtCount(dd.engagement.avg_likes) ?? '–'} /></li>
        <li><Stat size="compact" label="Comments" value={fmtCount(dd.engagement.total_comments) ?? '–'} /></li>
        <li><Stat size="compact" label="Most likes on one post" value={fmtCount(dd.engagement.max_likes) ?? '–'} /></li>
      </Grid>
      {dd.timeline.length > 0 && (
        <StackedBarChart title="Posts per day" categories={dd.timeline.map((t) => t.date)} series={[{ id: 'count', label: 'Posts', color: 1, values: dd.timeline.map((t) => t.count) }]} maxLabels={6} />
      )}
      {dd.connections.length > 0 ? (
        <Stack gap="sm">
          <Text variant="caption">Accounts they follow (a sample of {dd.connections.length})</Text>
          <Stack as="ul" direction="row" gap="sm" label="Accounts they follow">
            {dd.connections.map((c) => <li key={c.handle ?? c.name ?? ''}><Chip size="sm" tone="neutral">@{c.handle}{c.followers != null ? ` · ${fmtCount(c.followers)}` : ''}</Chip></li>)}
          </Stack>
        </Stack>
      ) : dd.platform !== 'twitter' && dd.platform !== 'instagram' ? (
        <Text variant="caption">Who they follow isn’t available for {platLabel(dd.platform)}.</Text>
      ) : null}
    </Stack>
  );
}

function ProfileView({ p, ctx, deep, setDeep, onChanged, onRemoved, onRebuild, building, onAttach, onEmail }: {
  p: BWAccountProfile; ctx: BwContext; deep: BWAccountDeepDive | null; setDeep: (d: BWAccountDeepDive | null) => void;
  onChanged: (p: BWAccountProfile) => void; onRemoved: (id: number) => void; onRebuild: () => void; building: boolean;
  onAttach: () => void; onEmail: () => void;
}) {
  const { notify, askConfirm, focusBrand } = ctx;
  const [note, setNote] = useState(p.annotation?.text ?? '');
  const [deepBusy, setDeepBusy] = useState(false);
  useEffect(() => setNote(p.annotation?.text ?? ''), [p.id, p.annotation?.text]);
  const s = p.post_sentiment;

  const save = async (fn: () => Promise<BWAccountProfile>, done: string) => {
    try {
      onChanged(await fn());
      notify(done);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    }
  };
  const runDeep = async () => {
    setDeepBusy(true);
    try {
      setDeep(await deepDiveAccount(p.platform, p.handle, focusBrand?.display_name ?? null));
    } catch (e) {
      notify(`Deep dive failed: ${errorText(e)}`);
    } finally {
      setDeepBusy(false);
    }
  };

  return (
    <Panel
      title={`${p.display_name || p.handle}${p.verified ? ' (verified)' : ''}`}
      description={<TextLink href={p.profile_url || `#`} external>@{p.handle} on {platLabel(p.platform)}</TextLink>}
      headingLevel={3}
      headerAside={
        <Stack direction="row" gap="sm">
          <Button size="sm" variant={p.watchlisted ? 'primary' : 'secondary'} iconStart={<Icon name="Star" size="sm" />}
            onClick={() => void save(() => setAccountWatchlist(p.id, !p.watchlisted), p.watchlisted ? 'Taken off the watchlist' : 'On the watchlist')}>
            {p.watchlisted ? 'Watching' : 'Watch'}
          </Button>
          <IconButton icon={<Icon name="ShieldCheck" size="sm" />} label="Add to incident" onClick={onAttach} />
          <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download HTML report" onClick={() => downloadAccountReport(p, deep)} />
          <IconButton icon={<Icon name="Export" size="sm" />} label="Email report" onClick={onEmail} />
          <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh from Xpoz (uses paid credits)" disabled={building} onClick={onRebuild} />
          <IconButton
            icon={<Icon name="Trash" size="sm" />}
            label="Delete profile"
            onClick={() => askConfirm({
              title: 'Delete this profile?',
              message: `The stored profile of @${p.handle}, with its tags and note, is removed. Posts stay.`,
              action: 'Delete profile',
              onConfirm: () => void deleteAccountProfile(p.id).then(() => { onRemoved(p.id); notify('Profile deleted'); }, (e: unknown) => notify(`Not deleted: ${errorText(e)}`)),
            })}
          />
        </Stack>
      }
    >
      <Stack gap="lg">
        {p.bio && <Text variant="description">{p.bio}</Text>}
        <Grid as="ul" columns={3} stackAt="never" gap="sm" label="Reach">
          <li><Stat size="compact" surface="panel" label="Followers" value={fmtCount(p.followers_count) ?? '–'} /></li>
          <li><Stat size="compact" surface="panel" label="Following" value={fmtCount(p.following_count) ?? '–'} /></li>
          <li><Stat size="compact" surface="panel" label={p.platform === 'reddit' ? 'Link karma' : 'Posts'} value={fmtCount(p.posts_count) ?? '–'} /></li>
        </Grid>
        {p.summary && <Stack gap="sm"><Eyebrow as="h4">Summary</Eyebrow><Text variant="description">{p.summary}</Text></Stack>}
        {p.brand_context && <Banner tone="info" icon="Target" headingLevel={4} title="Relationship to the brand" description={p.brand_context} />}
        {!!p.topics?.length && (
          <Stack as="ul" direction="row" gap="sm" label="Topics">
            {p.topics.map((t) => <li key={t}><Chip size="sm" tone="neutral">{t}</Chip></li>)}
          </Stack>
        )}
        {s && s.scored ? (
          <StackedBars
            title={`Sentiment${focusBrand ? ` toward ${focusBrand.display_name}` : ''} across ${s.scored} recent posts (net ${signed(s.net ?? null)})`}
            series={[{ id: 'pos', label: 'Positive', color: 'positive' }, { id: 'neu', label: 'Neutral', color: 'neutral' }, { id: 'neg', label: 'Negative', color: 'negative' }]}
            rows={[{ id: 'mix', label: 'Recent posts', values: [s.pos ?? 0, s.neu ?? 0, s.neg ?? 0] }]}
          />
        ) : null}
        <TagInput label="Tags" tags={p.tags ?? []} onChange={(tags) => void save(() => setAccountTags(p.id, tags), 'Tags saved')} />
        <Stack gap="sm">
          <TextArea label="Analyst note" rows={2} value={note} onChange={setNote} />
          <div>
            <Button size="sm" variant="secondary" disabled={note === (p.annotation?.text ?? '')} onClick={() => void save(() => setAccountAnnotation(p.id, note.trim()), 'Note saved')}>Save note</Button>
          </div>
        </Stack>
        {!!p.sample_posts?.length && (
          <Stack gap="sm">
            <Eyebrow as="h4">Top posts</Eyebrow>
            <Stack as="ul" gap="sm" label="Top posts">
              {p.sample_posts.map((sp) => {
                const sent = sentOf((sp as { sentiment?: string }).sentiment);
                const reach = ([['likes', sp.likes], ['comments', sp.comments], ['plays', sp.plays]] as [string, number | null | undefined][])
                  .filter(([, v]) => v != null).map(([k, v]) => `${fmtCount(v)} ${k}`).join(' · ');
                return (
                  <ArticleCard
                    key={sp.id}
                    as="li"
                    variant="row"
                    headingLevel={4}
                    href={sp.url ?? undefined}
                    meta={sp.created_at?.slice(0, 10)}
                    title={(sp.text || '(no text)').slice(0, 140)}
                    summary={(sp.text?.length ?? 0) > 140 ? sp.text ?? undefined : undefined}
                    tags={sent !== 'unrated' ? <Chip size="sm" tone={SENT_TONE[sent]}>{(sp as { sentiment?: string }).sentiment}</Chip> : undefined}
                    footer={reach ? <span>{reach}</span> : undefined}
                  />
                );
              })}
            </Stack>
          </Stack>
        )}
        <PanelDivider />
        {deep ? <DeepDive dd={deep} onClose={() => setDeep(null)} /> : (
          <Stack gap="sm">
            <div><Button variant="secondary" size="sm" iconStart={<Icon name="TrendUp" size="sm" />} disabled={deepBusy} onClick={() => void runDeep()}>{deepBusy ? 'Reading the account…' : 'Deep dive: activity, engagement, who they follow'}</Button></div>
            <Text variant="caption">Reads the account’s recent posts from Xpoz, which uses paid credits. Nothing is stored.</Text>
          </Stack>
        )}
        {p.last_profiled_at && <Text variant="caption">Profiled {p.last_profiled_at.slice(0, 10)}</Text>}
      </Stack>
    </Panel>
  );
}

export function Accounts(ctx: BwContext) {
  const { notify, focusBrand } = ctx;
  const [list, setList] = useState<BWAccountProfile[] | null>(null);
  const [current, setCurrent] = useState<BWAccountProfile | null>(null);
  const [platform, setPlatform] = useState('twitter');
  const [handle, setHandle] = useState('');
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** A handle opened from a post with no stored profile: offer to build it */
  const [notStored, setNotStored] = useState<{ platform: string; handle: string } | null>(null);
  const [deep, setDeep] = useState<BWAccountDeepDive | null>(null);
  const [attach, setAttach] = useState<IncidentSource | null>(null);
  const [emailFor, setEmailFor] = useState<BWAccountProfile | null>(null);

  const loadList = useCallback(() => listAccountProfiles().then(setList, () => setList([])), []);
  const open = (p: BWAccountProfile) => {
    setCurrent(p);
    setDeep(null);
    setNotStored(null);
    setError(null);
  };
  const upsert = (p: BWAccountProfile) => {
    setCurrent(p);
    setList((l) => [p, ...(l ?? []).filter((x) => x.id !== p.id)]);
  };

  // Paid: reads the account from Xpoz and stores the profile
  const build = async (pl: string, h: string) => {
    const clean = h.trim().replace(/^@/, '');
    if (!clean) return;
    setBuilding(true);
    setError(null);
    try {
      const p = await buildAccountProfile(pl, clean, focusBrand?.display_name ?? null);
      upsert(p);
      setDeep(null);
      setNotStored(null);
      setHandle('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBuilding(false);
    }
  };

  useEffect(() => {
    void loadList();
    // Opened from a post author on the Social tab: show the stored profile, or offer to build one
    const q = takeQueuedAccount();
    if (!q) return;
    setPlatform(q.platform);
    getAccountProfile(q.platform, q.handle).then(open, () => setNotStored(q));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Panel
        title="Accounts"
        description={`Profile any X, Bluesky, Reddit, Instagram or TikTok account: who they are, their reach, what they post about${focusBrand ? ` and how they talk about ${focusBrand.display_name}` : ''}. Tip: open a post author from the Social tab.`}
        headingLevel={3}
      >
        <Stack gap="sm">
          <Stack direction="row" gap="sm">
            <Select label="Network" hideLabel options={PLATFORMS} value={platform} onValueChange={setPlatform} />
            <TextField
              label="Handle"
              hideLabel
              placeholder="Handle, without @"
              value={handle}
              onChange={setHandle}
              onSubmit={() => void build(platform, handle)}
              action={<Button size="lg" disabled={building || !handle.trim()} onClick={() => void build(platform, handle)}>{building ? 'Profiling…' : 'Profile'}</Button>}
            />
          </Stack>
          <Text variant="caption">Profiling reads the account from Xpoz, which uses paid credits. Saved profiles open without a new lookup.</Text>
          {error && <Banner tone="error" title="No profile" description={error} />}
        </Stack>
      </Panel>

      <Grid columns="main-aside" gap="md">
        <div>
          {building && !current ? <Skeleton variant="block" size="card" /> : notStored ? (
            <Panel title={`@${notStored.handle}`} headingLevel={3}>
              <EmptyState
                icon="User"
                title="No stored profile yet"
                action={<Button disabled={building} onClick={() => void build(notStored.platform, notStored.handle)}>{building ? 'Profiling…' : `Build profile from ${platLabel(notStored.platform)}`}</Button>}
              >
                Building reads the account from Xpoz, which uses paid credits, and stores the profile for next time.
              </EmptyState>
            </Panel>
          ) : current ? (
            <ProfileView
              key={current.id}
              p={current}
              ctx={ctx}
              deep={deep}
              setDeep={setDeep}
              onChanged={upsert}
              onRemoved={(id) => { setList((l) => (l ?? []).filter((x) => x.id !== id)); setCurrent(null); }}
              onRebuild={() => void build(current.platform, current.handle)}
              building={building}
              onAttach={() => setAttach({ kind: 'account_profile', ref: `${current.platform}:${current.handle_canonical || current.handle}`, label: `@${current.handle} on ${platLabel(current.platform)}`, brandId: focusBrand?.id ?? null })}
              onEmail={() => setEmailFor(current)}
            />
          ) : (
            <Panel title="No account open" headingLevel={3}>
              <Text>Profile a handle or pick a saved profile to see identity, reach, sentiment, topics and top posts.</Text>
            </Panel>
          )}
        </div>
        <Panel title={`Saved profiles${list ? ` (${list.length})` : ''}`} headingLevel={3}>
          {!list ? <Skeleton variant="text" lines={6} /> : list.length === 0 ? <Text>No profiles yet. Profile a handle above.</Text> : (
            <Stack as="ul" gap="sm" label="Saved profiles">
              {list.map((a) => (
                <li key={a.id}>
                  <Stack direction="row" gap="sm" wrap={false}>
                    <Button variant={current?.id === a.id ? 'secondary' : 'ghost'} size="sm" onClick={() => open(a)}>
                      {a.display_name || a.handle}
                    </Button>
                    <Chip size="sm" tone="muted">{platLabel(a.platform)}</Chip>
                    {a.watchlisted && <Chip size="sm" tone="warning" icon={<Icon name="Star" size="sm" />}>Watching</Chip>}
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Panel>
      </Grid>

      <AddToIncidentDialog source={attach} onClose={() => setAttach(null)} notify={notify} />
      <EmailDialog profile={emailFor} deep={deep} onClose={() => setEmailFor(null)} notify={notify} />
    </>
  );
}

