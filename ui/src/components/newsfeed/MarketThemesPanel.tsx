/**
 * Themes — what the matched corpus is actually about, not just what matched
 * a phrase.
 *
 * Two scopes over the same clustering: the whole market's coverage, or just
 * what vendors post about themselves. Clustering is embedding k-means and is
 * free to run; narrating what a cluster has in common is a model call and
 * stays behind an explicit button, the same "figures first, prose on
 * request" split as the Briefings tab.
 */

import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Sparkles } from 'lucide-react';
import { getThemes, type MarketThemes } from '../../services/marketMonitorApi';

/** Bold and paragraphs only — the narration prompt asks for exactly that,
 *  the same reasoning MarketBriefingsView gives for its own tiny renderer:
 *  a library for two rules is more code than the two rules. */
function renderNarrative(md: string): string {
  const esc = (s: string) => s
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return md.split(/\n{2,}/).map(block => {
    const inline = esc(block.trim()).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return `<p>${inline}</p>`;
  }).join('');
}

function ThemeCard({ scope, cluster }: {
  scope: 'all' | 'vendor'; cluster: MarketThemes['clusters'][number];
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg bg-white p-3 dark:bg-gray-800">
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center gap-2 text-left">
        {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0 dark:text-gray-500" />
              : <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0 dark:text-gray-500" />}
        <span className="text-sm font-medium text-slate-800 truncate dark:text-gray-100">
          {cluster.sample[0]?.title ?? `Theme ${cluster.id}`}
        </span>
        <span className="text-xs text-slate-400 tabular-nums shrink-0 dark:text-gray-500">
          {cluster.size}
        </span>
        {cluster.top_vendors.length > 0 && (
          <span className="text-xs text-slate-500 truncate shrink-0 max-w-[40%] dark:text-gray-400">
            {cluster.top_vendors.slice(0, 3).map(v => v.vendor).join(', ')}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 pl-5 space-y-1">
          {cluster.sample.map(s => (
            <a key={s.uri} href={s.uri} target="_blank" rel="noreferrer"
               className="block text-xs text-slate-600 hover:underline truncate dark:text-gray-400">
              {s.title}
              <span className="text-slate-400 dark:text-gray-500">
                {' '}· {s.source ?? (scope === 'vendor' ? 'vendor post' : 'unknown')} ·{' '}
                {(s.published ?? '').slice(0, 10)}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export function MarketThemesPanel({ marketId }: { marketId: number }) {
  const [scope, setScope] = useState<'all' | 'vendor'>('all');
  const [days, setDays] = useState(30);
  const [data, setData] = useState<MarketThemes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [narrating, setNarrating] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null); setError(null);
    getThemes(marketId, { scope, days })
      .then(d => { if (live) setData(d); })
      .catch(e => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [marketId, scope, days]);

  async function narrate() {
    setNarrating(true);
    try {
      const d = await getThemes(marketId, { scope, days, narrate: true });
      setData(d);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setNarrating(false);
    }
  }

  return (
    <div className="border rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm font-medium text-slate-800 dark:text-gray-100">Themes</div>
        <div className="flex-1" />
        <div className="flex border rounded-md overflow-hidden">
          {([['all', 'The market'], ['vendor', 'Competitors']] as const).map(([id, label]) => (
            <button key={id} onClick={() => setScope(id)}
                    className={`text-sm px-2.5 py-1 ${
                      scope === id ? 'bg-slate-800 text-white'
                                   : 'bg-white text-slate-600 hover:bg-slate-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'}`}>
              {label}
            </button>
          ))}
        </div>
        <select value={days} onChange={e => setDays(Number(e.target.value))}
                className="text-sm px-2 py-1 border rounded-md bg-white text-slate-700 dark:bg-gray-800 dark:text-gray-300">
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>
      <p className="text-xs text-slate-500 mt-1 mb-3 dark:text-gray-400">
        {scope === 'vendor'
          ? "What vendors themselves are posting about, grouped by embedding "
            + 'similarity — their own claims, not third-party coverage of them.'
          : "What the market's whole matched coverage is about, whether or "
            + 'not any two articles say the same thing.'}
      </p>

      {error && (
        <div className="text-sm text-red-700 p-3 border rounded-md bg-red-50 dark:text-red-400 dark:bg-red-900/20">{error}</div>
      )}

      {!error && data === null && (
        <div className="py-8 text-center text-slate-400 dark:text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mx-auto" />
        </div>
      )}

      {!error && data && data.clusters.length === 0 && (
        <p className="text-sm text-slate-500 py-6 text-center dark:text-gray-400">
          {data.reason ?? 'Nothing matched in this window.'}
        </p>
      )}

      {!error && data && data.clusters.length > 0 && (
        <>
          <div className="flex items-center gap-2 mb-3">
            <button onClick={narrate} disabled={narrating}
                    className="text-xs px-2.5 py-1.5 border rounded-md
                               hover:bg-slate-50 disabled:opacity-50
                               inline-flex items-center gap-1.5 dark:hover:bg-gray-700">
              {narrating ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Sparkles className="w-3.5 h-3.5" />}
              {data.narrative ? 'Re-narrate' : 'Narrate with AI'}
            </button>
            <span className="text-xs text-slate-400 dark:text-gray-500">
              {data.n} articles, {data.k} theme{data.k === 1 ? '' : 's'}
            </span>
          </div>

          {data.narrative && (
            <div className="text-sm text-slate-700 space-y-2 mb-4 [&_p]:leading-relaxed"
                 dangerouslySetInnerHTML={{ __html: renderNarrative(data.narrative) }} />
          )}

          <div className="space-y-2">
            {data.clusters.map(c => (
              <ThemeCard key={c.id} scope={scope} cluster={c} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
