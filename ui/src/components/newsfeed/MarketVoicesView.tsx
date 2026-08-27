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
import { ExternalLink, Loader2, RefreshCw, UserRound } from 'lucide-react';
import {
  getTopVoices, getVoiceProfileJob, profileAllVoices, profileVoice,
  type TopVoices, type Voice, type VoiceProfileJob,
} from '../../services/marketMonitorApi';
import { DataTable } from './DataTable';
import { CoverageLine, Panel } from './MarketAnalysisView';
import type { DrilldownSpec } from './MarketDrilldownHost';

const PLATFORM_LABEL: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', tiktok: 'TikTok',
  instagram: 'Instagram', linkedin: 'LinkedIn',
};
const PROFILABLE = new Set(['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok']);

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
                note="Accounts posting about the market. Vendors' own company posts are excluded — they are counted under Analysis." />
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
                                  className="text-xs px-1 py-0.5 rounded border
                                             bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800">
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
