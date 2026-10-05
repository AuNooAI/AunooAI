/**
 * Top voices: the outside accounts posting about this market.
 *
 * Its own tab. It sat at the bottom of Analysis, after a dozen panels about
 * the vendors, and a reader asking "who is driving this conversation" had to
 * scroll past hiring charts to find out. The data is the same ``/voices``
 * call; the table is the one that was on Analysis.
 *
 * A handle on its own is a stranger. Each row links to the account on its
 * platform and to its latest relevant post, and carries the account profile
 * Brand Watcher builds (bio, reach, what they post about, their part in this
 * market) once one has been built — here, or from the Accounts tab.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, Loader2, RefreshCw, Star, UserRound } from 'lucide-react';
import {
  getTopVoices, getVoiceProfileJob, profileAllVoices, profileVoice,
  getFollowed, followAccount, unfollowAccount, collectFollowed, type FollowedAccount,
  type TopVoices, type Voice, type VoiceProfileJob,
} from '../../services/marketMonitorApi';
import { DataTable } from './DataTable';
import { CoverageLine, Panel } from './MarketAnalysisView';
import type { DrilldownSpec } from './MarketDrilldownHost';
import { useVendorColours, VendorSwatch } from './vendorColours';

const PLATFORM_LABEL: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', tiktok: 'TikTok',
  instagram: 'Instagram', linkedin: 'LinkedIn',
};
const PROFILABLE = new Set(['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok']);
const ROLE_LABEL: Record<string, string> = {
  vendor: 'vendor', vendor_staff: 'vendor staff', practitioner: 'practitioner',
  analyst_or_press: 'analyst / press', reseller: 'reseller',
  promoter_or_bot: 'promoter / bot', unrelated: 'unrelated',
};

function roleOf(v: Voice): string {
  if (v.vendor_tag) return v.vendor_tag.label;
  const r = v.account?.role;
  if (r) return ROLE_LABEL[r] ?? r;
  // No profile: what the account's own posts say it is, when they agree.
  if (v.audience?.source === 'account_posts') return v.audience.label.toLowerCase();
  return v.account?.profiled ? 'not read' : 'not profiled';
}

function roleTitle(v: Voice): string | undefined {
  if (v.vendor_tag || v.account?.role) return undefined;
  if (v.audience?.source === 'account_posts')
    return `Read from ${v.audience.n ?? 'their'} classified post(s) by this account; profile it for a stronger reading.`;
  return undefined;
}

/** A vendor's own account, or their staff, kept on the list and marked. */
function VendorBadge({ tag }: { tag: NonNullable<Voice['vendor_tag']> }) {
  return (
    <span
      title={tag.org
        ? `${tag.label}: ${tag.org}${tag.tracked ? ' (a vendor we track)' : ''}`
          + (tag.linked ? '; this account is recorded on the vendor profile' : '')
        : tag.label}
      className="inline-flex items-center text-[10px] uppercase tracking-wide px-1 py-0.5 rounded
                 bg-amber-50 text-amber-800 border border-amber-200
                 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800">
      {tag.label}{tag.org ? ` · ${tag.org}` : ''}{tag.linked ? ' · on profile' : ''}
    </span>
  );
}

function platformLabel(p: string): string {
  return PLATFORM_LABEL[p] ?? p;
}

function compact(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function clip(s: string | null | undefined, n: number): string {
  const t = (s ?? '').trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
}

export function MarketVoicesView({ marketId, days, onRecords }: {
  marketId: number;
  days?: number;
  onRecords?: (spec: DrilldownSpec) => void;
}) {
  const colours = useVendorColours(marketId);
  const [voices, setVoices] = useState<TopVoices | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [job, setJob] = useState<VoiceProfileJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const poll = useRef<number | null>(null);

  const load = useCallback(() => {
    return getTopVoices(marketId, days, 50)
      .then(v => { setVoices(v); return v; })
      .catch(e => { setError(String(e.message ?? e)); return null; });
  }, [marketId, days]);

  useEffect(() => {
    let live = true;
    setVoices(null);
    setError(null);
    setSelected(null);
    getTopVoices(marketId, days, 50)
      .then(v => { if (live) setVoices(v); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    // A run started before this mount is still worth showing.
    getVoiceProfileJob(marketId)
      .then(j => { if (live && j.state === 'running') setJob(j); })
      .catch(() => { /* status is a convenience */ });
    return () => { live = false; };
  }, [marketId, days]);

  // Poll a running bulk job; reload the table when it finishes so the new
  // profiles show without a manual refresh.
  useEffect(() => {
    if (!job || job.state !== 'running') {
      if (poll.current) { window.clearInterval(poll.current); poll.current = null; }
      return;
    }
    poll.current = window.setInterval(() => {
      getVoiceProfileJob(marketId)
        .then(j => {
          setJob(j);
          if (j.state !== 'running') load();
        })
        .catch(() => { /* keep polling */ });
    }, 3000);
    return () => { if (poll.current) { window.clearInterval(poll.current); poll.current = null; } };
  }, [job?.state, marketId, load]);

  const keyOf = (v: Voice) => `${v.platform}:${v.author}`;

  // The follow list: accounts whose timelines are read for the market, so a
  // person we know matters shows up whatever the keyword collector caught.
  const [followed, setFollowed] = useState<FollowedAccount[] | null>(null);
  const [followPlatform, setFollowPlatform] = useState<'twitter' | 'bluesky' | 'reddit'>('twitter');
  const [followHandle, setFollowHandle] = useState('');
  const [followNote, setFollowNote] = useState<string | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const loadFollowed = useCallback(() => {
    getFollowed(marketId).then(r => setFollowed(r.accounts)).catch(() => setFollowed([]));
  }, [marketId]);
  useEffect(() => { loadFollowed(); }, [loadFollowed]);

  const follow = async (platform: string, handle: string) => {
    setFollowBusy(true); setFollowNote(null);
    try {
      await followAccount(marketId, platform, handle.replace(/^@/, ''));
      setFollowNote(`Following @${handle.replace(/^@/, '')}. Its posts that touch the market are read on the next collection.`);
      setFollowHandle('');
      loadFollowed(); load();
    } catch (e: any) {
      setFollowNote(`Could not follow @${handle}: ${e.message ?? e}`);
    } finally { setFollowBusy(false); }
  };
  const unfollow = async (platform: string, handle: string) => {
    setFollowBusy(true); setFollowNote(null);
    try {
      await unfollowAccount(marketId, platform, handle);
      loadFollowed(); load();
    } catch (e: any) {
      setFollowNote(`Could not unfollow @${handle}: ${e.message ?? e}`);
    } finally { setFollowBusy(false); }
  };
  const collectNow = async () => {
    setFollowBusy(true); setFollowNote(null);
    try {
      const r = await collectFollowed(marketId);
      setFollowNote(`${r.accounts} account${r.accounts === 1 ? '' : 's'} read: ${r.fetched} posts, `
        + `${r.matched} about the market, ${r.stored} new.`
        + (r.skipped.length ? ` Skipped: ${r.skipped.join('; ')}` : ''));
      load();
    } catch (e: any) {
      setFollowNote(`Could not read the followed accounts: ${e.message ?? e}`);
    } finally { setFollowBusy(false); }
  };
  const isFollowed = (v: Voice) => !!v.account?.watchlisted
    || !!followed?.some(f => f.platform === v.platform && f.handle.toLowerCase() === v.author.toLowerCase());

  const profileOne = async (v: Voice) => {
    const k = keyOf(v);
    setBusy(prev => new Set(prev).add(k));
    setJobError(null);
    try {
      await profileVoice(marketId, v.platform, v.author);
      await load();
      setSelected(k);
    } catch (e: any) {
      setJobError(`@${v.author}: ${e.message ?? e}`);
    } finally {
      setBusy(prev => { const n = new Set(prev); n.delete(k); return n; });
    }
  };

  const profileAll = async (refresh: boolean) => {
    setJobError(null);
    try {
      const j = await profileAllVoices(marketId, { days, limit: 50, refresh });
      setJob(j);
      if (j.state !== 'running') load();
    } catch (e: any) {
      setJobError(String(e.message ?? e));
    }
  };

  if (error) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error}</div>;
  }

  const rows = voices?.voices ?? [];
  const unprofiled = rows.filter(v => PROFILABLE.has(v.platform) && !v.account?.profiled).length;
  const current = selected ? rows.find(v => keyOf(v) === selected) ?? null : null;
  const running = job?.state === 'running';

  return (
    <div className="space-y-4">
        <Panel title="Top voices">
          {voices ? (
            <>
              <CoverageLine
                coverage={voices.coverage}
                note="Accounts posting about the market. Vendors' LinkedIn company posts are counted under Analysis, not here; a vendor's own X, Bluesky or Reddit account stays on this list and is tagged." />
              <p className="text-xs text-slate-500 dark:text-gray-400 mb-2">
                {voices.accounts} accounts posted in the period; {voices.accounts_multi_post} of
                them more than once. Sorted by posts, then reactions, so a single post that
                travelled sits below an account that keeps posting.
                {' '}{voices.profiled} of the {rows.length} shown have a profile.
              </p>

              <div className="flex flex-wrap items-center gap-2 mb-3">
                <button
                  onClick={() => profileAll(false)}
                  disabled={running || unprofiled === 0}
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border
                             bg-white hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed
                             dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
                  <UserRound className="w-3.5 h-3.5" />
                  {unprofiled === 0 ? 'All shown accounts profiled'
                    : `Profile the ${unprofiled} unprofiled`}
                </button>
                <button
                  onClick={() => profileAll(true)}
                  disabled={running || rows.length === 0}
                  title="Rebuild every profile on the list from the platform again"
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border
                             bg-white hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed
                             dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
                  <RefreshCw className="w-3.5 h-3.5" />
                  Rebuild all
                </button>
                {running && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 dark:text-gray-300">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Profiling {job?.done ?? 0} of {job?.total ?? 0}…
                  </span>
                )}
                {job && job.state === 'done' && (
                  <span className="text-xs text-slate-500 dark:text-gray-400">
                    Last run: {job.built ?? 0} built
                    {job.failed ? `, ${job.failed} failed` : ''}
                    {job.skipped ? `, ${job.skipped} skipped` : ''}.
                    {job.errors && job.errors.length > 0 && (
                      <span title={job.errors.join('\n')}> (hover for the failures)</span>
                    )}
                  </span>
                )}
                <span className="text-xs text-slate-400 dark:text-gray-500">
                  Each profile is two xpoz calls and one short model call. Same profiles as
                  Brand Watcher → Accounts.
                </span>
              </div>
              {jobError && (
                <div className="text-xs text-red-600 dark:text-red-400 mb-2">{jobError}</div>
              )}

              {current && (
                <VoiceDetail
                  voice={current}
                  busy={busy.has(keyOf(current))}
                  onClose={() => setSelected(null)}
                  onRebuild={() => profileOne(current)}
                  onPosts={onRecords ? () => onRecords({
                    kind: 'voice',
                    title: `@${current.author}: posts about this market`,
                    author: current.author, days,
                    expectedTotal: current.posts,
                  }) : undefined} />
              )}

              <div className="border rounded-lg bg-white p-3 mb-3 space-y-2 dark:bg-gray-800">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-800 dark:text-gray-100">
                    Accounts we follow
                  </span>
                  <span className="text-xs text-slate-500 dark:text-gray-400">
                    Their timelines are read on each collection and the posts that touch the
                    market kept, whatever the keyword search caught. They lead "Voices worth
                    reading" on the front page.
                  </span>
                  <div className="flex-1" />
                  <button onClick={collectNow} disabled={followBusy || !followed?.length}
                          className="text-xs px-2.5 py-1.5 border rounded-md hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-gray-700">
                    Read them now
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 items-center">
                  {(followed ?? []).map(f => (
                    <span key={`${f.platform}:${f.handle}`}
                          className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border bg-slate-50 dark:bg-gray-700 dark:border-gray-600">
                      <Star className="w-3 h-3 text-amber-500 fill-amber-500" />
                      {f.display_name ? `${f.display_name} · ` : ''}@{f.handle}
                      <span className="text-slate-400">{f.platform === 'twitter' ? 'X' : f.platform}</span>
                      <button onClick={() => unfollow(f.platform, f.handle)} disabled={followBusy}
                              title="Stop following" className="text-slate-400 hover:text-red-600">×</button>
                    </span>
                  ))}
                  {followed && followed.length === 0 && (
                    <span className="text-xs text-slate-400 dark:text-gray-500">None yet.</span>
                  )}
                </div>
                <form className="flex flex-wrap gap-2 items-center"
                      onSubmit={e => { e.preventDefault(); if (followHandle.trim()) follow(followPlatform, followHandle.trim()); }}>
                  <select value={followPlatform} onChange={e => setFollowPlatform(e.target.value as any)}
                          className="text-xs px-2 py-1.5 border rounded-md bg-white text-slate-700 dark:bg-gray-800 dark:text-gray-300">
                    <option value="twitter">X</option>
                    <option value="bluesky">Bluesky</option>
                    <option value="reddit">Reddit</option>
                  </select>
                  <input value={followHandle} onChange={e => setFollowHandle(e.target.value)}
                         placeholder="@handle" maxLength={200}
                         className="text-xs px-2 py-1.5 border rounded-md bg-white text-slate-800 min-w-[200px] dark:bg-gray-800 dark:text-gray-100" />
                  <button type="submit" disabled={followBusy || !followHandle.trim()}
                          className="text-xs px-2.5 py-1.5 border rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50">
                    Follow
                  </button>
                  <span className="text-xs text-slate-500 dark:text-gray-400">
                    Following profiles the account first (two xpoz calls, one short model call).
                    Reddit has no per-user history through the provider.
                  </span>
                </form>
                {followNote && (
                  <div className="text-xs px-2 py-1.5 rounded bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-300">
                    {followNote}
                  </div>
                )}
              </div>

              <DataTable
                rows={rows}
                rowKey={keyOf}
                initialSort="posts" initialDir="desc"
                columns={[
                  { key: 'author', label: 'Account', groupable: false,
                    value: v => v.author,
                    render: v => (
                      <div className="max-w-[16rem]">
                        <div className="flex items-center gap-1">
                          {v.profile_url ? (
                            <a href={v.profile_url} target="_blank" rel="noopener noreferrer"
                               onClick={e => e.stopPropagation()}
                               className="text-sky-700 dark:text-sky-400 hover:underline inline-flex items-center gap-1">
                              @{v.author}<ExternalLink className="w-3 h-3 opacity-60" />
                            </a>
                          ) : <span>@{v.author}</span>}
                          <button disabled={followBusy}
                                  title={isFollowed(v) ? 'Stop following' : 'Follow: read this account\'s timeline for the market'}
                                  onClick={e => { e.stopPropagation(); isFollowed(v) ? unfollow(v.platform, v.author) : follow(v.platform, v.author); }}
                                  className="p-0.5 rounded hover:bg-slate-100 dark:hover:bg-gray-700">
                            <Star className={`w-3.5 h-3.5 ${isFollowed(v) ? 'text-amber-500 fill-amber-500' : 'text-slate-300 dark:text-gray-600'}`} />
                          </button>
                          {v.vendor_tag && <VendorBadge tag={v.vendor_tag} />}
                        </div>
                        {v.account?.profiled && (
                          <div className="text-xs text-slate-500 dark:text-gray-400">
                            {v.account.display_name ?? ''}
                            {v.account.followers != null && (
                              <span>{v.account.display_name ? ' · ' : ''}{compact(v.account.followers)} followers</span>
                            )}
                            {v.account.verified && <span title="Verified on the platform"> · verified</span>}
                          </div>
                        )}
                      </div>
                    ) },
                  { key: 'platform', label: 'Platform', groupable: true,
                    value: v => platformLabel(v.platform),
                    render: v => platformLabel(v.platform) },
                  // Who is speaking, in one word, so the list can be grouped
                  // into vendors and everyone else.
                  { key: 'role', label: 'Role', groupable: true,
                    value: roleOf,
                    render: v => (
                      <span title={roleTitle(v)}
                        className={v.vendor_tag ? 'text-amber-800 dark:text-amber-300'
                          : (!v.account?.role && v.audience?.source === 'account_posts') ? 'text-slate-500 dark:text-gray-400 italic'
                          : 'text-slate-600 dark:text-gray-300'}>
                        {roleOf(v)}
                      </span>
                    ) },
                  { key: 'who', label: 'Who they are', sortable: false,
                    render: v => v.account?.profiled ? (
                      <button
                        onClick={e => { e.stopPropagation(); setSelected(keyOf(v)); }}
                        title="Open the profile"
                        className="text-left max-w-[20rem] hover:underline">
                        <span className="text-sm">{clip(v.account.summary, 100) || '—'}</span>
                        {v.account.relation && (
                          <span className="block text-xs text-slate-500 dark:text-gray-400">
                            {clip(v.account.relation, 80)}
                          </span>
                        )}
                      </button>
                    ) : PROFILABLE.has(v.platform) ? (
                      <button
                        onClick={e => { e.stopPropagation(); profileOne(v); }}
                        disabled={busy.has(keyOf(v)) || running}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border
                                   bg-white hover:bg-slate-50 disabled:opacity-50
                                   dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
                        {busy.has(keyOf(v))
                          ? <Loader2 className="w-3 h-3 animate-spin" />
                          : <UserRound className="w-3 h-3" />}
                        Profile
                      </button>
                    ) : (
                      <span className="text-xs text-slate-400 dark:text-gray-500">not profilable</span>
                    ) },
                  // A ranked list of handles with no subject is a list of
                  // strangers. What they talk about is the useful part.
                  { key: 'about', label: 'Talking about', sortable: false,
                    // Capped, or an account naming a dozen terms and
                    // vendors pushes its row tall enough that the table
                    // becomes an endless scroll instead of a scan.
                    render: v => {
                      const terms = v.terms.slice(0, 4);
                      const vendors = v.vendors.slice(0, 3);
                      const extra = (v.terms.length - terms.length)
                        + (v.vendors.length - vendors.length);
                      return (
                        <span className="flex flex-wrap gap-1">
                          {terms.length === 0 && vendors.length === 0 && (
                            <span className="text-slate-400 dark:text-gray-500">—</span>)}
                          {terms.map(t => (
                            <span key={t.term}
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-slate-50 text-slate-600 dark:bg-gray-700 dark:text-gray-400">
                              {t.term}
                            </span>
                          ))}
                          {vendors.map(x => (
                            <span key={x.vendor}
                                  className="text-xs px-1 py-0.5 rounded border inline-flex items-center gap-1
                                             bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
                              <VendorSwatch color={colours.byName(x.vendor)} />
                              {x.vendor}
                            </span>
                          ))}
                          {extra > 0 && (
                            <span className="text-xs text-slate-400 dark:text-gray-500">+{extra} more</span>
                          )}
                        </span>
                      );
                    } },
                  { key: 'posts', label: 'Posts', align: 'right',
                    // Opens every relevant post by this account. A ranked
                    // handle whose posts cannot be read is an assertion.
                    render: v => onRecords ? (
                      <button
                        onClick={e => { e.stopPropagation();
                                        onRecords({
                                          kind: 'voice',
                                          title: `@${v.author}: posts about this market`,
                                          author: v.author, days,
                                          expectedTotal: v.posts,
                                        }); }}
                        className="text-sky-700 dark:text-sky-400 hover:underline">
                        {v.posts}
                      </button>
                    ) : v.posts },
                  { key: 'engagement', label: 'Reactions', align: 'right' },
                  { key: 'last_seen', label: 'Latest post', align: 'right',
                    value: v => v.last_seen,
                    render: v => {
                      const date = (v.last_seen ?? '').slice(0, 10) || '—';
                      return v.latest_post?.url ? (
                        <a href={v.latest_post.url} target="_blank" rel="noopener noreferrer"
                           onClick={e => e.stopPropagation()}
                           title={v.latest_post.title ?? undefined}
                           className="text-sky-700 dark:text-sky-400 hover:underline inline-flex items-center gap-1">
                          {date}<ExternalLink className="w-3 h-3 opacity-60" />
                        </a>
                      ) : date;
                    } },
                ]} />
            </>
          ) : (
            <div className="py-10 text-center text-slate-400 dark:text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            </div>
          )}
        </Panel>
    </div>
  );
}

/** One account, read in full: who they are, their reach, what they post
 *  about and their part in this market. */
function VoiceDetail({ voice, busy, onClose, onRebuild, onPosts }: {
  voice: Voice;
  busy: boolean;
  onClose: () => void;
  onRebuild: () => void;
  onPosts?: () => void;
}) {
  const a = voice.account;
  return (
    <div className="mb-3 border rounded-lg p-3 bg-slate-50 dark:bg-gray-900/40 dark:border-gray-700">
      <div className="flex items-start gap-3">
        {a?.avatar_url ? (
          // Platforms often refuse the image to a third-party page; a broken
          // image icon is worse than none, so the tag removes itself.
          <img src={a.avatar_url} alt="" referrerPolicy="no-referrer"
               onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
               className="w-10 h-10 rounded-full object-cover shrink-0" />
        ) : (
          <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-gray-700 shrink-0 flex items-center justify-center">
            <UserRound className="w-5 h-5 text-slate-500" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium text-slate-800 dark:text-gray-100">
              {a?.display_name ?? `@${voice.author}`}
            </span>
            {voice.profile_url ? (
              <a href={voice.profile_url} target="_blank" rel="noopener noreferrer"
                 className="text-sm text-sky-700 dark:text-sky-400 hover:underline inline-flex items-center gap-1">
                @{voice.author} on {platformLabel(voice.platform)}<ExternalLink className="w-3 h-3 opacity-60" />
              </a>
            ) : (
              <span className="text-sm text-slate-500">@{voice.author} on {platformLabel(voice.platform)}</span>
            )}
            {a?.verified && <span className="text-xs text-slate-500">verified</span>}
            {voice.vendor_tag && <VendorBadge tag={voice.vendor_tag} />}
          </div>
          {a?.profiled ? (
            <>
              <div className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">
                {compact(a.followers)} followers
                {a.posts_count != null && <> · {compact(a.posts_count)} posts on the platform</>}
                {' '}· {voice.posts} about this market, {voice.engagement} reactions
                {a.last_profiled_at && <> · profiled {a.last_profiled_at.slice(0, 10)}</>}
              </div>
              {a.bio && <p className="text-sm mt-2 text-slate-700 dark:text-gray-300">{a.bio}</p>}
              {a.summary && <p className="text-sm mt-2 text-slate-800 dark:text-gray-200">{a.summary}</p>}
              {a.relation && (
                <p className="text-sm mt-1 text-slate-700 dark:text-gray-300">
                  <span className="text-xs uppercase tracking-wide text-slate-500 dark:text-gray-400 mr-1">In this market</span>
                  {a.relation}
                </p>
              )}
              {a.topics.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {a.topics.map(t => (
                    <span key={t} className="text-xs px-1.5 py-0.5 rounded border bg-white dark:bg-gray-800 dark:border-gray-600 text-slate-600 dark:text-gray-300">{t}</span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm mt-1 text-slate-600 dark:text-gray-400">
              Not profiled yet. {voice.posts} post{voice.posts === 1 ? '' : 's'} about this market, {voice.engagement} reactions.
            </p>
          )}
          <div className="flex flex-wrap gap-2 mt-3">
            {onPosts && (
              <button onClick={onPosts}
                className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-50 dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200">
                Their posts about this market
              </button>
            )}
            {voice.latest_post?.url && (
              <a href={voice.latest_post.url} target="_blank" rel="noopener noreferrer"
                 className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-50 dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200 inline-flex items-center gap-1">
                Latest post<ExternalLink className="w-3 h-3 opacity-60" />
              </a>
            )}
            {PROFILABLE.has(voice.platform) && (
              <button onClick={onRebuild} disabled={busy}
                className="text-xs px-2 py-1 rounded border bg-white hover:bg-slate-50 disabled:opacity-50 dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-600 dark:text-gray-200 inline-flex items-center gap-1">
                {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                {a?.profiled ? 'Rebuild profile' : 'Build profile'}
              </button>
            )}
            <button onClick={onClose}
              className="text-xs px-2 py-1 text-slate-500 hover:underline">Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}
