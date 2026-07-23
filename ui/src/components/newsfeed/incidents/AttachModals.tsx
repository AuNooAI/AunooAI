/**
 * Evidence-attach dialogs for the incident case file: article/post search
 * and the account-profile picker. Built on the shared ui/dialog primitives
 * (the Brand Watcher tab historically hand-rolled fixed-inset modals).
 */
import { Loader2, Search, UserCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../ui/dialog';
import { IncidentCase } from './useIncidentCase';

export function AttachSearchDialog({ c }: { c: IncidentCase }) {
  if (!c.detail) return null;
  return (
    <Dialog open={c.search.open} onOpenChange={open => c.setSearch(s => ({ ...s, open }))}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col z-[1100]">
        <DialogHeader>
          <DialogTitle className="text-sm">Attach articles / posts to incident #{c.detail.id}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 overflow-y-auto flex-1">
          <div className="flex items-center gap-2">
            <input type="text" value={c.search.q} autoFocus
              onChange={e => c.setSearch(s => ({ ...s, q: e.target.value }))}
              onKeyDown={e => { if (e.key === 'Enter') c.doAttachSearch(); }}
              placeholder="Search title / summary, or paste a URI…"
              className="flex-1 text-xs px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
            <select value={c.search.kind} onChange={e => c.setSearch(s => ({ ...s, kind: e.target.value as 'all' | 'news' | 'social' }))}
              className="text-xs px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
              <option value="all">all</option><option value="news">news</option><option value="social">social</option>
            </select>
            <button onClick={c.doAttachSearch} disabled={c.search.busy || !c.search.q.trim()}
              className="text-xs px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1">
              {c.search.busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />} Search
            </button>
          </div>
          <div className="space-y-1">
            {c.search.results.map(r => (
              <label key={r.uri} className="flex items-start gap-2 p-2 rounded border border-gray-100 dark:border-gray-700 hover:border-blue-200 cursor-pointer">
                <input type="checkbox" checked={c.search.sel.has(r.uri)}
                  onChange={e => c.setSearch(s => {
                    const sel = new Set(s.sel);
                    if (e.target.checked) sel.add(r.uri); else sel.delete(r.uri);
                    return { ...s, sel };
                  })} className="mt-0.5 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${r.is_social ? 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400' : 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400'}`}>
                      {r.is_social ? (r.platform || 'social') : 'news'}
                    </span>
                    <span className="text-xs text-gray-800 dark:text-gray-100 truncate">{r.title || r.uri}</span>
                  </div>
                  <p className="text-xs text-gray-400 truncate">{r.news_source}{r.author ? ` · @${r.author}` : ''} · {(r.publication_date || '').slice(0, 10)}{r.topic_alignment_score != null ? ` · rel ${r.topic_alignment_score}` : ''}</p>
                </div>
              </label>
            ))}
            {c.search.searched && !c.search.busy && !c.search.results.length && (
              <p className="text-xs text-gray-400 text-center py-4">No matches in the last year of collected content.</p>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 pt-3 border-t border-gray-200 dark:border-gray-700">
          <button onClick={() => c.setSearch(s => ({ ...s, open: false }))}
            className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300">Cancel</button>
          <button onClick={c.attachSearchSelection} disabled={!c.search.sel.size || c.search.busy}
            className="text-xs px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
            Attach {c.search.sel.size || ''} selected
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ProfilePickerDialog({ c }: { c: IncidentCase }) {
  if (!c.detail) return null;
  return (
    <Dialog open={c.profilePick.open} onOpenChange={open => c.setProfilePick(p => ({ ...p, open }))}>
      <DialogContent className="max-w-lg max-h-[75vh] flex flex-col z-[1100]">
        <DialogHeader>
          <DialogTitle className="text-sm">Attach an account profile to incident #{c.detail.id}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 overflow-y-auto flex-1">
          <input type="text" value={c.profilePick.filter} autoFocus
            onChange={e => c.setProfilePick(p => ({ ...p, filter: e.target.value }))}
            placeholder="Filter by handle / name / platform…"
            className="w-full text-xs px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
          {c.profilePick.profiles
            .filter(p => !c.profilePick.filter.trim() || `${p.handle} ${p.display_name || ''} ${p.platform}`.toLowerCase().includes(c.profilePick.filter.toLowerCase()))
            .map(p => (
              <button key={p.id} onClick={() => c.attachProfile(p)}
                className="w-full flex items-center gap-2 p-2 rounded border border-gray-100 dark:border-gray-700 hover:border-emerald-300 text-left">
                {p.avatar_url ? <img src={p.avatar_url} alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0" /> : <UserCircle className="w-7 h-7 text-gray-300 flex-shrink-0" />}
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-gray-800 dark:text-gray-100 truncate">{p.display_name || `@${p.handle}`} <span className="text-gray-400">@{p.handle} · {p.platform}</span></p>
                  <p className="text-xs text-gray-400 truncate">{p.followers_count != null ? `${Number(p.followers_count).toLocaleString()} followers · ` : ''}{p.summary || p.bio || ''}</p>
                </div>
              </button>
            ))}
          {!c.profilePick.profiles.length && <p className="text-xs text-gray-400 text-center py-4">No profiled accounts yet — build profiles from the Social tab first.</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
