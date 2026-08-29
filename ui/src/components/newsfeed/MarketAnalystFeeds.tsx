/**
 * The analyst firms' public feeds read for a market (Forrester's security
 * blog, KuppingerCole's research listing, …). Items are read hourly by the
 * RSS monitor and kept when they mention the market; they appear under
 * "Latest research" on the front page. Same shape as the follow-list strip
 * in the voices view: pills, an add form, a note line.
 */
import { useCallback, useEffect, useState } from 'react';
import { type AnalystFeed, getAnalystFeeds, putAnalystFeeds } from '../../services/marketMonitorApi';

export function MarketAnalystFeeds({ marketId }: { marketId: number }) {
  const [feeds, setFeeds] = useState<AnalystFeed[] | null>(null);
  const [defaults, setDefaults] = useState(false);
  const [firm, setFirm] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    getAnalystFeeds(marketId)
      .then(r => { setFeeds(r.feeds); setDefaults(r.defaults); })
      .catch(() => setFeeds([]));
  }, [marketId]);
  useEffect(() => { load(); }, [load]);

  const save = async (next: { firm: string; url: string }[], done: string) => {
    setBusy(true); setNote(null);
    try {
      const r = await putAnalystFeeds(marketId, next);
      setFeeds(r.feeds); setDefaults(false);
      setNote(`${done} ${r.sync.added ? `${r.sync.added} registered with the feed reader.` : ''}`.trim());
    } catch (e: any) {
      setNote(`Could not save: ${e.message ?? e}`);
    } finally { setBusy(false); }
  };

  const host = (u: string) => { try { return new URL(u).host.replace(/^www\./, ''); } catch { return u; } };

  return (
    <div className="border rounded-lg bg-white p-3 space-y-2 dark:bg-gray-800 dark:border-gray-700">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-800 dark:text-gray-100">Analyst feeds</span>
        <span className="text-xs text-slate-500 dark:text-gray-400">
          The firms' public blogs and research listings. Read hourly; items that mention the market
          appear under Latest research on the front page.
          {defaults && ' These are the defaults; saving a change makes the list this market’s own.'}
        </span>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        {(feeds ?? []).map(f => (
          <span key={f.url} title={f.url}
                className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border bg-slate-50 text-slate-700 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600">
            {f.firm} <span className="text-slate-400">{host(f.url)}</span>
            <button onClick={() => save((feeds ?? []).filter(x => x.url !== f.url).map(x => ({ firm: x.firm, url: x.url })),
                                       `Removed ${f.firm}.`)}
                    disabled={busy} title="Stop reading this feed" className="text-slate-400 hover:text-red-600">×</button>
          </span>
        ))}
        {feeds && feeds.length === 0 && (
          <span className="text-xs text-slate-400 dark:text-gray-500">None. Add a feed URL below.</span>
        )}
      </div>
      <form className="flex flex-wrap gap-2 items-center"
            onSubmit={e => {
              e.preventDefault();
              if (!firm.trim() || !url.trim()) return;
              save([...(feeds ?? []).map(x => ({ firm: x.firm, url: x.url })), { firm: firm.trim(), url: url.trim() }],
                   `Added ${firm.trim()}.`).then(() => { setFirm(''); setUrl(''); });
            }}>
        <input value={firm} onChange={e => setFirm(e.target.value)} placeholder="Firm (e.g. Forrester)" maxLength={60}
               className="text-xs px-2 py-1.5 border rounded-md w-40 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
        <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…/feed" maxLength={500}
               className="text-xs px-2 py-1.5 border rounded-md w-80 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100" />
        <button type="submit" disabled={busy || !firm.trim() || !url.trim()}
                className="text-xs px-2.5 py-1.5 rounded-md bg-slate-800 text-white disabled:opacity-50">Add</button>
      </form>
      {note && (
        <div className="text-xs px-2 py-1.5 rounded bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-200">{note}</div>
      )}
    </div>
  );
}
