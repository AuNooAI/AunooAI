/**
 * Brand Watcher — Voices view.
 *
 * Who is talking about the brand, and what each audience thinks. Every
 * on-brand social post carries the author's role from the social evaluation
 * step (patient, clinician, customer, employee, journalist ...). This view
 * groups the window's posts by that role, opens on the pair the backend
 * suggests (clinicians vs patients on a health tenant), and asks a model for
 * a short digest of each side with verbatim quotes as evidence.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, Info, RefreshCw, Eye, Quote, FileDown, UserSearch } from 'lucide-react';
import { downloadVoicesReport } from '../../services/voicesReportHtml';
import {
  Brand, BWVoicesResponse, BWVoiceRole, BWVoicesDigest, BWVoicePost, BWVoicesProfileStatus,
  getVoices, getVoicesDigest, startVoicesProfiling, getVoicesProfilingStatus,
} from '../../services/brandWatcherApi';

const PLATFORM_COLORS: Record<string, string> = {
  twitter: '#0f172a', bluesky: '#0ea5e9', reddit: '#f97316',
  instagram: '#d6249f', tiktok: '#ff0050', glassdoor: '#0caa41', social: '#6b7280',
};
const PLATFORM_LABELS: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit',
  instagram: 'Instagram', tiktok: 'TikTok', glassdoor: 'Glassdoor', social: 'Other',
};
const SENT_COLORS: Record<string, string> = {
  positive: '#10b981', neutral: '#94a3b8', negative: '#ef4444', unrated: '#d1d5db',
};

function netChipClass(net: number | null): string {
  if (net === null) return 'bg-gray-100 dark:bg-gray-700 text-gray-400';
  if (net >= 20) return 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300';
  if (net <= -20) return 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300';
  return 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300';
}

function themeSentClass(s: string): string {
  if (s === 'positive') return 'text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/30';
  if (s === 'negative') return 'text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30';
  if (s === 'mixed') return 'text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/30';
  return 'text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700';
}

function SplitBar({ r }: { r: BWVoiceRole }) {
  if (!r.n) return null;
  const pct = (x: number) => `${(x / r.n) * 100}%`;
  return (
    <div className="h-1.5 w-full rounded-full overflow-hidden flex bg-gray-200 dark:bg-gray-700"
      title={`${r.positive} positive · ${r.neutral} neutral · ${r.negative} negative`}>
      <div style={{ width: pct(r.positive), backgroundColor: SENT_COLORS.positive }} />
      <div style={{ width: pct(r.neutral), backgroundColor: SENT_COLORS.neutral }} />
      <div style={{ width: pct(r.negative), backgroundColor: SENT_COLORS.negative }} />
    </div>
  );
}

function PostRow({ p }: { p: BWVoicePost }) {
  const plat = p.platform || 'social';
  return (
    <div className="flex gap-2 py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <div className="w-1 rounded-full flex-shrink-0" style={{ backgroundColor: SENT_COLORS[p.sentiment || 'unrated'] }} title={p.sentiment || 'unrated'} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white flex-shrink-0"
            style={{ backgroundColor: PLATFORM_COLORS[plat] || PLATFORM_COLORS.social }}>{PLATFORM_LABELS[plat] || plat}</span>
          {p.author && <span className="truncate font-medium text-gray-700 dark:text-gray-200">{p.author}</span>}
          {p.publication_date && <span className="flex-shrink-0">{p.publication_date.slice(0, 10)}</span>}
          <a href={p.uri} target="_blank" rel="noopener noreferrer" className="ml-auto text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1 flex-shrink-0">
            <Eye className="w-3 h-3" /> View
          </a>
        </div>
        <p className="text-sm text-gray-800 dark:text-gray-100 mt-0.5 line-clamp-4 whitespace-pre-wrap break-words" title={p.text}>{p.text}</p>
        {p.author_role_source === 'account_profile' ? (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 italic">
            Role from the account profile{p.account_market_role ? ` (${p.account_market_role.replace(/_/g, ' ')}` + (p.account_org ? `, ${p.account_org}` : '') + ')' : ''}
            {p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : ''}
          </p>
        ) : p.author_role_source === 'account_posts' ? (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 italic">
            Role from this account's other posts{p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : ''}
          </p>
        ) : p.author_role_reason ? (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 italic">Why this role: {p.author_role_reason}</p>
        ) : null}
      </div>
    </div>
  );
}

function RoleColumn({ role, brandId, daysBack, minRelevance }: { role: BWVoiceRole; brandId: number; daysBack: number; minRelevance: number }) {
  const [digest, setDigest] = useState<BWVoicesDigest | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setLoading(true); setErr(null);
    getVoicesDigest(role.role, brandId, daysBack, minRelevance)
      .then(d => setDigest(d))
      .catch(e => setErr(e?.message || 'Digest failed'))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    setDigest(null);
    if (role.n >= 2) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role.role, brandId, daysBack, minRelevance, role.n]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 flex flex-col min-w-0">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{role.label}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{role.hint}</p>
          </div>
          <span className={`text-xs font-semibold px-2 py-1 rounded ${netChipClass(role.net)}`}
            title="Net sentiment: (positive − negative) ÷ posts × 100">
            {role.net === null ? 'n/a' : `${role.net > 0 ? '+' : ''}${role.net}`}
          </span>
        </div>
        <div className="mt-3 flex items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
          <span><b>{role.n}</b> post{role.n === 1 ? '' : 's'}</span>
          <span className="text-green-600 dark:text-green-400">{role.positive} positive</span>
          <span className="text-gray-500">{role.neutral} neutral</span>
          <span className="text-red-600 dark:text-red-400">{role.negative} negative</span>
        </div>
        <div className="mt-2"><SplitBar r={role} /></div>
        <div className="mt-2 flex flex-wrap gap-1">
          {Object.entries(role.by_platform).sort((a, b) => b[1] - a[1]).map(([plat, n]) => (
            <span key={plat} className="text-[10px] px-1.5 py-0.5 rounded-full text-white"
              style={{ backgroundColor: PLATFORM_COLORS[plat] || PLATFORM_COLORS.social }}>{PLATFORM_LABELS[plat] || plat} {n}</span>
          ))}
        </div>
      </div>

      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200 inline-flex items-center gap-1.5"><Quote className="w-3.5 h-3.5" /> What {role.label.toLowerCase()} are saying</h4>
          <button onClick={load} disabled={loading || role.n < 2} title="Rebuild the digest"
            className="text-xs text-gray-400 hover:text-blue-600 disabled:opacity-40 inline-flex items-center gap-1">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {role.n < 2 && <p className="text-xs text-gray-500 dark:text-gray-400">Fewer than two posts from this audience in the window; nothing to summarise yet.</p>}
        {loading && <p className="text-xs text-gray-500 inline-flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /> Reading {role.n} posts…</p>}
        {err && <p className="text-xs text-red-600">{err}</p>}
        {!loading && digest && (
          <div className="space-y-3">
            {digest.context && <p className="text-xs text-gray-500 dark:text-gray-400">{digest.context}</p>}
            {digest.summary && <p className="text-sm text-gray-800 dark:text-gray-100">{digest.summary}</p>}
            {digest.note && <p className="text-xs text-gray-500 dark:text-gray-400">{digest.note}</p>}
            {digest.themes.map((t, i) => (
              <div key={i} className="rounded border border-gray-100 dark:border-gray-700 p-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-800 dark:text-gray-100">{t.theme}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${themeSentClass(t.sentiment)}`}>{t.sentiment}</span>
                  {t.post_count > 0 && <span className="text-[10px] text-gray-400">{t.post_count} post{t.post_count === 1 ? '' : 's'}</span>}
                </div>
                {t.quotes.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {t.quotes.map((q, j) => (
                      <li key={j} className="text-xs text-gray-600 dark:text-gray-300 border-l-2 border-gray-200 dark:border-gray-600 pl-2 italic">“{q}”</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {(digest.asks?.length ?? 0) > 0 && (
              <div>
                <h5 className="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-1">What these posts ask for</h5>
                <ul className="space-y-0.5">
                  {digest.asks!.map((a, i) => <li key={i} className="text-xs text-gray-700 dark:text-gray-300 pl-3 relative before:content-['•'] before:absolute before:left-0">{a}</li>)}
                </ul>
              </div>
            )}
            {(digest.summary || digest.themes.length > 0) && <p className="text-[10px] text-gray-400">AI digest of {digest.post_count} post{digest.post_count === 1 ? '' : 's'}. Quotes are copied from the posts; check the post before citing one.</p>}
          </div>
        )}
      </div>

      <div className="p-4 max-h-[32rem] overflow-y-auto">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Posts</h4>
        {role.posts.length === 0 && <p className="text-xs text-gray-400">No posts.</p>}
        {role.posts.map(p => <PostRow key={p.uri} p={p} />)}
        {role.n > role.posts.length && <p className="text-[11px] text-gray-400 mt-2">Showing the {role.posts.length} most recent of {role.n}.</p>}
      </div>
    </div>
  );
}

export function BrandWatcherVoices({ brands, daysBack }: { brands: Brand[]; daysBack: number }) {
  const enabled = useMemo(() => brands.filter(b => b.enabled !== false), [brands]);
  const [brandId, setBrandId] = useState<number | null>(null);
  const [data, setData] = useState<BWVoicesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The two audiences shown side by side. Null = the backend's suggested pair.
  const [picked, setPicked] = useState<string[] | null>(null);
  const [exporting, setExporting] = useState(false);
  // Profiling the accounts behind the posts. A profiled account carries its
  // audience onto every post, which is what moves posts out of Bystanders.
  const [profiling, setProfiling] = useState<BWVoicesProfileStatus | null>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const minRelevance = 0.4;

  const effectiveBrand = brandId ?? (enabled.find(b => b.is_primary)?.id ?? enabled[0]?.id ?? null);

  useEffect(() => {
    if (effectiveBrand == null) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true); setError(null);
    if (reloadKey === 0) setPicked(null);
    getVoices(effectiveBrand, daysBack, minRelevance)
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [effectiveBrand, daysBack, reloadKey]);

  // Pick up a run already going for this brand, then poll while it runs and
  // reload the table once it finishes.
  useEffect(() => {
    if (effectiveBrand == null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const st = await getVoicesProfilingStatus(effectiveBrand);
        if (cancelled) return;
        setProfiling(prev => {
          if (prev?.state === 'running' && st.state === 'done') setReloadKey(k => k + 1);
          return st;
        });
        if (st.state === 'running') timer = setTimeout(tick, 3000);
      } catch { /* status is a convenience; the table stands without it */ }
    };
    tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [effectiveBrand, profiling?.state === 'running' ? 'run' : 'idle']);

  const profilePosters = async () => {
    if (effectiveBrand == null) return;
    setProfileErr(null);
    try {
      const st = await startVoicesProfiling(effectiveBrand, daysBack, minRelevance);
      setProfiling(st);
      if (st.state === 'done') setReloadKey(k => k + 1);
    } catch (e: any) {
      setProfileErr(e?.message || 'Could not start profiling');
    }
  };

  const roles = data?.roles || [];
  const shown = picked ?? data?.focus ?? [];
  const toggle = (role: string) => {
    setPicked(prev => {
      const cur = [...(prev ?? shown)];
      const i = cur.indexOf(role);
      if (i >= 0) { cur.splice(i, 1); return cur; }
      if (cur.length >= 2) cur.shift();
      cur.push(role);
      return cur;
    });
  };
  const columns = shown.map(r => roles.find(x => x.role === r)).filter((x): x is BWVoiceRole => !!x);

  // One self-contained .html for the brand's team: the audience table, the
  // two compared columns with their digests, every post with its source.
  // Digests are cached server-side per post set, so re-fetching them here is
  // one cheap call each rather than a second model run.
  const exportHtml = async () => {
    if (!data) return;
    setExporting(true);
    try {
      const digests: Record<string, BWVoicesDigest | null> = {};
      for (const r of columns) {
        digests[r.role] = r.n >= 2
          ? await getVoicesDigest(r.role, data.brand_id, daysBack, minRelevance).catch(() => null)
          : null;
      }
      downloadVoicesReport({ voices: data, compared: columns.map(r => r.role), digests, daysBack, generatedAt: new Date().toISOString() });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Voices</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">Who is talking about the brand, and what each audience thinks. Last {daysBack} days, on-brand posts only.</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={profilePosters} disabled={!data || loading || profiling?.state === 'running'}
              title="Build an account profile for every poster in this window that has none yet. A profiled account carries its audience onto all its posts, so posts the text alone could not place leave Bystanders."
              className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40">
              {profiling?.state === 'running'
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Profiling {profiling.done ?? 0}/{profiling.total ?? 0}</>
                : <><UserSearch className="w-3 h-3" /> Profile posters</>}
            </button>
            <button onClick={exportHtml} disabled={!data || loading || exporting}
              title="Download this view as a self-contained HTML report: audience table, the two compared audiences with their digests, and every post"
              className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40">
              {exporting ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileDown className="w-3 h-3" />} Export HTML
            </button>
            <label className="text-xs text-gray-500 dark:text-gray-400">Brand</label>
            <select value={effectiveBrand ?? ''} onChange={e => setBrandId(Number(e.target.value))}
              className="text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
              {enabled.map(b => <option key={b.id} value={b.id}>{b.display_name}{b.is_primary ? ' (primary)' : ''}</option>)}
            </select>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500 inline-flex items-start gap-1">
          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
          <span>The role is read from the post itself by the social evaluation model: first-person use of the service reads as a patient or customer, prescribing or referring as a clinician, a reporter or outlet as press, the company's own promotion as brand voice. Glassdoor reviews count as employees. Where the text gives no clue the poster counts as a bystander rather than being guessed. An account profiled under Market Monitor Top voices, the Accounts tab or Profile posters here carries its profile role onto all its posts, and an account whose other posts keep reading the same way is taken as that. The brand's own LinkedIn and website posts are not included.</span>
        </p>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-gray-500 p-4"><Loader2 className="w-4 h-4 animate-spin" /> Loading voices…</div>}
      {error && <div className="text-sm text-red-600 p-4">{error}</div>}
      {profileErr && <div className="text-xs text-red-600 px-4">{profileErr}</div>}
      {profiling?.state === 'done' && (profiling.total ?? 0) > 0 && (
        <div className="text-xs text-gray-500 dark:text-gray-400 px-4">
          Profiled {profiling.built ?? 0} of {profiling.total} account{profiling.total === 1 ? '' : 's'}
          {(profiling.failed ?? 0) > 0 ? `, ${profiling.failed} could not be read` : ''}.
        </div>
      )}

      {!loading && data && (
        <>
          {data.coverage_notes.length > 0 && (
            <div className="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded p-2 space-y-0.5">
              {data.coverage_notes.map((n, i) => <div key={i}>{n}</div>)}
            </div>
          )}

          {roles.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
              {roles.map(r => {
                const on = shown.includes(r.role);
                return (
                  <button key={r.role} onClick={() => toggle(r.role)} title={`${r.hint}. Click to compare.`}
                    className={`text-left rounded-lg border p-3 transition ${on
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{r.label}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${netChipClass(r.net)}`}>{r.net === null ? '—' : `${r.net > 0 ? '+' : ''}${r.net}`}</span>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{r.n} post{r.n === 1 ? '' : 's'}</div>
                    <div className="mt-2"><SplitBar r={r} /></div>
                  </button>
                );
              })}
            </div>
          )}

          {columns.length > 0 ? (
            <div className={`grid gap-4 ${columns.length > 1 ? 'md:grid-cols-2' : ''}`}>
              {columns.map(r => (
                <RoleColumn key={r.role} role={r} brandId={data.brand_id} daysBack={daysBack} minRelevance={minRelevance} />
              ))}
            </div>
          ) : roles.length > 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 p-4">Pick up to two audiences above to compare them.</p>
          ) : null}
        </>
      )}
    </div>
  );
}
